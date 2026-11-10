"""Compare each public call path of an original module with its Rust-backed counterpart.

Runs inside the port's `.venv` as a child process (`python -I differential_script.py ...`), so
it imports nothing from oxidify: only the standard library, Hypothesis and the two modules.
"""

import argparse
import copy
import importlib
import inspect
import json
import math
import os
import sys
import types
from pathlib import Path
from types import ModuleType
from typing import Any

from hypothesis import Verbosity, given, settings
from hypothesis import strategies as st
from hypothesis.errors import FailedHealthCheck, Flaky, ResolutionFailed

# Text strategies leave out surrogates, and a lone one is where a Rust `&str` and a Python
# `str` part ways, so every `str` parameter also gets this input.
LONE_SURROGATE = "\ud800"


class CallPathsDiffer(Exception):
    """Raised inside the Hypothesis test so it shrinks the input that made the two sides differ."""


def call_and_describe(callable_object: Any, arguments: tuple[Any, ...]) -> tuple[Any, str]:
    """Call on a copy of the arguments; return what to compare and its repr().

    A raised exception is compared by its type and message.
    """
    try:
        value = callable_object(*copy.deepcopy(arguments))
    except Exception as error:
        return ("raised", type(error), str(error)), repr(error)
    return ("returned", type(value), value), repr(value)


def values_agree(original_value: Any, rust_backed_value: Any) -> bool:
    """`==`, except that two NaNs agree and objects without `__eq__` compare their attributes."""
    if type(original_value) is not type(rust_backed_value):
        return False
    if isinstance(original_value, float) and math.isnan(original_value):
        return math.isnan(rust_backed_value)
    if isinstance(original_value, (tuple, list)):
        if len(original_value) != len(rust_backed_value):
            return False
        for original_item, rust_backed_item in zip(original_value, rust_backed_value, strict=True):
            if not values_agree(original_item, rust_backed_item):
                return False
        return True
    if isinstance(original_value, dict):
        if original_value.keys() != rust_backed_value.keys():
            return False
        for key in original_value:
            if not values_agree(original_value[key], rust_backed_value[key]):
                return False
        return True
    # The default `__eq__` is identity, which two separately built results never share.
    value_type = type(original_value)
    if (
        value_type.__module__ != "builtins"
        and value_type.__eq__ is object.__eq__
        and hasattr(original_value, "__dict__")
    ):
        return values_agree(vars(original_value), vars(rust_backed_value))
    return original_value == rust_backed_value


def mismatch_for(original: Any, rust_backed: Any, arguments: tuple[Any, ...]) -> dict | None:
    """The mismatch entry for one input, or None when both sides agree on it."""
    original_outcome, original_repr = call_and_describe(original, arguments)
    rust_backed_outcome, rust_backed_repr = call_and_describe(rust_backed, arguments)
    original_kind, original_type, original_value = original_outcome
    rust_backed_kind, rust_backed_type, rust_backed_value = rust_backed_outcome
    if (
        original_kind == rust_backed_kind
        and original_type is rust_backed_type
        and values_agree(original_value, rust_backed_value)
    ):
        return None
    return {
        "shrunk_input": ", ".join(repr(argument) for argument in arguments),
        "original": original_repr,
        "rust_backed": rust_backed_repr,
    }


def find_mismatch(
    original: Any, rust_backed: Any, arguments_strategy: Any, max_examples: int
) -> tuple[int, dict | None, str | None]:
    """Run Hypothesis on the arguments.

    Returns the inputs tried, the shrunk mismatch if any, and why Hypothesis could not finish
    the run if it could not.
    """
    inputs_tried = 0
    last_mismatch = None

    @settings(
        max_examples=max_examples,
        database=None,
        derandomize=True,
        deadline=None,
        verbosity=Verbosity.quiet,
    )
    @given(arguments_strategy)
    def compare(arguments: tuple[Any, ...]) -> None:
        nonlocal inputs_tried, last_mismatch
        inputs_tried += 1
        mismatch = mismatch_for(original, rust_backed, arguments)
        if mismatch is None:
            return
        last_mismatch = mismatch
        raise CallPathsDiffer(mismatch["shrunk_input"])

    try:
        compare()
    except CallPathsDiffer:
        # Hypothesis replays the minimal failing input last, so last_mismatch holds it.
        return inputs_tried, last_mismatch, None
    except (ResolutionFailed, FailedHealthCheck, Flaky) as error:
        first_line = str(error).splitlines()[0]
        return (
            inputs_tried,
            None,
            f"Hypothesis could not run it: {type(error).__name__}: {first_line}",
        )
    return inputs_tried, None, None


def reason_not_compared(signature: inspect.Signature) -> str | None:
    """Why no inputs can be generated for this signature; None when they can."""
    for parameter in signature.parameters.values():
        if parameter.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            return f"parameter {parameter.name!r} is variadic"
        if parameter.kind == inspect.Parameter.KEYWORD_ONLY:
            return f"parameter {parameter.name!r} is keyword-only"
        if parameter.annotation is inspect.Parameter.empty:
            return f"parameter {parameter.name!r} has no type annotation"
    return None


def arguments_strategy(signature: inspect.Signature, lone_surrogate_for_str: bool) -> Any:
    """Tuple of positional arguments built from the type annotations."""
    strategies = []
    for parameter in signature.parameters.values():
        if lone_surrogate_for_str and parameter.annotation is str:
            strategies.append(st.just(LONE_SURROGATE))
        else:
            strategies.append(st.from_type(parameter.annotation))
    return st.tuples(*strategies)


def compare_call_path(
    call_path: str, original: Any, rust_backed: Any, examples_per_call_path: int
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "call_path": call_path,
        "inputs_tried": 0,
        "skipped_reason": None,
        "rust_backed_is_builtin": isinstance(rust_backed, types.BuiltinFunctionType),
        "mismatches": [],
    }
    try:
        signature = inspect.signature(original, eval_str=True)
    except (NameError, ValueError) as error:
        # NameError: an annotation only imported under TYPE_CHECKING. ValueError: a built-in
        # without a signature.
        result["skipped_reason"] = f"signature cannot be read: {error}"
        return result
    skipped_reason = reason_not_compared(signature)
    if skipped_reason is not None:
        result["skipped_reason"] = skipped_reason
        return result

    has_str_parameter = any(
        parameter.annotation is str for parameter in signature.parameters.values()
    )
    runs = [(arguments_strategy(signature, False), examples_per_call_path)]
    if has_str_parameter:
        runs.append((arguments_strategy(signature, True), 1))
    for strategy, max_examples in runs:
        inputs_tried, mismatch, skipped_reason = find_mismatch(
            original, rust_backed, strategy, max_examples
        )
        result["inputs_tried"] += inputs_tried
        if mismatch is not None:
            result["mismatches"].append(mismatch)
        if skipped_reason is not None:
            result["skipped_reason"] = skipped_reason
            return result
    return result


def missing_from_rust_backed(
    call_path: str, rust_backed_module: ModuleType, name: str
) -> dict[str, Any]:
    """A name the Rust-backed module lacks is a mismatch on every input, so none are tried."""
    error = AttributeError(f"module {rust_backed_module.__name__!r} has no attribute {name!r}")
    return {
        "call_path": call_path,
        "inputs_tried": 0,
        "skipped_reason": None,
        "rust_backed_is_builtin": False,
        "mismatches": [{"shrunk_input": "", "original": call_path, "rust_backed": repr(error)}],
    }


def compare_modules(
    original_module: ModuleType,
    rust_backed_module: ModuleType,
    public_names: list[str],
    examples_per_call_path: int,
) -> list[dict[str, Any]]:
    """One oracle report `differential` entry per callable public name, in the given order."""
    results = []
    for name in public_names:
        original = getattr(original_module, name)
        if not callable(original):
            continue
        call_path = f"{original_module.__name__}.{name}"
        if not hasattr(rust_backed_module, name):
            results.append(missing_from_rust_backed(call_path, rust_backed_module, name))
            continue
        rust_backed = getattr(rust_backed_module, name)
        results.append(compare_call_path(call_path, original, rust_backed, examples_per_call_path))
    return results


def public_names_of(module: ModuleType) -> list[str]:
    """`__all__` when the module defines it, otherwise every name not starting with `_`."""
    if hasattr(module, "__all__"):
        return list(module.__all__)
    return [name for name in dir(module) if not name.startswith("_")]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--examples-per-call-path", type=int, required=True)
    parser.add_argument(
        "--modules",
        nargs=2,
        action="append",
        required=True,
        metavar=("ORIGINAL", "RUST_BACKED"),
    )
    arguments = parser.parse_args()

    call_paths = []
    for original_name, rust_backed_name in arguments.modules:
        original_module = importlib.import_module(original_name)
        rust_backed_module = importlib.import_module(rust_backed_name)
        call_paths += compare_modules(
            original_module,
            rust_backed_module,
            public_names_of(original_module),
            arguments.examples_per_call_path,
        )

    modules_loaded = {}
    for pair in arguments.modules:
        for name in pair:
            modules_loaded[name] = sys.modules[name].__file__
    report = {"process_id": os.getpid(), "modules_loaded": modules_loaded, "call_paths": call_paths}
    arguments.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
