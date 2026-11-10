import importlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

from oxidify import port_folder
from oxidify.python_adapter.differential import DifferentialRunFailed, run_differential
from oxidify.python_adapter.differential_script import compare_modules, public_names_of

DIFFERENTIAL_MODULES_FOLDER = Path(__file__).parent / "fixtures" / "differential_modules"
TINY_PACKAGE_RS_FOLDER = Path(__file__).parent / "fixtures" / "tiny_package_rs"
EXAMPLES_PER_CALL_PATH = 50
LONE_SURROGATE = "\ud800"


@pytest.fixture
def load_fixture_module(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(DIFFERENTIAL_MODULES_FOLDER))

    def load(name: str) -> ModuleType:
        return importlib.import_module(name)

    return load


@pytest.fixture
def tiny_port_with_stand_in(tmp_path: Path, tiny_port_with_environment: Path) -> Path:
    """The tiny port with the pure-Python `tiny_package_rs` installed into its `.venv`."""
    stand_in_copy = tmp_path / "tiny_package_rs"
    shutil.copytree(TINY_PACKAGE_RS_FOLDER, stand_in_copy)
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--quiet",
            "--python",
            str(port_folder.venv_python(tiny_port_with_environment)),
            str(stand_in_copy),
        ],
        check=True,
    )
    return tiny_port_with_environment


def results_by_call_path(results: list[dict]) -> dict[str, dict]:
    return {result["call_path"]: result for result in results}


def test_matching_modules_report_inputs_tried(load_fixture_module) -> None:
    original = load_fixture_module("matching_original")
    rust_backed = load_fixture_module("matching_rust_backed")
    # append_zero changes its argument, so each side must be called on its own copy.
    public_names = ["shout", "add", "size", "append_zero"]

    results = compare_modules(original, rust_backed, public_names, EXAMPLES_PER_CALL_PATH)

    assert [result["call_path"] for result in results] == [
        "matching_original.shout",
        "matching_original.add",
        "matching_original.size",
        "matching_original.append_zero",
    ]
    for result in results:
        assert result["inputs_tried"] >= EXAMPLES_PER_CALL_PATH
        assert result["skipped_reason"] is None
        assert result["mismatches"] == []
    # Derandomised: a second run tries the same number of inputs.
    assert compare_modules(original, rust_backed, public_names, EXAMPLES_PER_CALL_PATH) == results


def test_mismatch_is_shrunk(load_fixture_module) -> None:
    original = load_fixture_module("underscore_original")
    rust_backed = load_fixture_module("underscore_rust_backed")

    [result] = compare_modules(original, rust_backed, ["shout"], EXAMPLES_PER_CALL_PATH)

    assert result["mismatches"] == [
        {"shrunk_input": repr("_"), "original": repr("_"), "rust_backed": repr("_!")}
    ]


def test_return_type_compared(load_fixture_module) -> None:
    original = load_fixture_module("types_original")
    rust_backed = load_fixture_module("types_rust_backed")

    [result] = compare_modules(original, rust_backed, ["add"], EXAMPLES_PER_CALL_PATH)

    assert result["mismatches"] == [{"shrunk_input": "0, 0", "original": "0", "rust_backed": "0.0"}]


@pytest.mark.parametrize(
    ("rust_backed_name", "mismatch_count"),
    [("exceptions_other_type", 1), ("exceptions_other_message", 1), ("exceptions_same", 0)],
)
def test_exception_type_and_message_compared(
    load_fixture_module, rust_backed_name: str, mismatch_count: int
) -> None:
    original = load_fixture_module("exceptions_original")
    rust_backed = load_fixture_module(rust_backed_name)

    [result] = compare_modules(original, rust_backed, ["check_positive"], EXAMPLES_PER_CALL_PATH)

    assert len(result["mismatches"]) == mismatch_count
    if mismatch_count == 0:
        assert result["inputs_tried"] >= EXAMPLES_PER_CALL_PATH
        return
    [mismatch] = result["mismatches"]
    assert mismatch["shrunk_input"] == "-1"
    assert mismatch["original"] == repr(ValueError("negative: -1"))
    assert mismatch["rust_backed"] != mismatch["original"]


def test_unannotated_call_path_is_listed(load_fixture_module) -> None:
    original = load_fixture_module("matching_original")
    rust_backed = load_fixture_module("matching_rust_backed")

    [result] = compare_modules(original, rust_backed, ["describe"], EXAMPLES_PER_CALL_PATH)

    assert result["call_path"] == "matching_original.describe"
    assert result["inputs_tried"] == 0
    assert result["skipped_reason"] == "parameter 'text' has no type annotation"
    assert result["mismatches"] == []


def test_variadic_and_keyword_only_call_paths_are_listed(load_fixture_module) -> None:
    original = load_fixture_module("matching_original")
    rust_backed = load_fixture_module("matching_rust_backed")

    results = compare_modules(original, rust_backed, ["join_all", "label"], 5)

    reasons = {result["call_path"]: result["skipped_reason"] for result in results}
    assert reasons == {
        "matching_original.join_all": "parameter 'words' is variadic",
        "matching_original.label": "parameter 'loud' is keyword-only",
    }
    assert [result["inputs_tried"] for result in results] == [0, 0]


def test_public_names_follow_all() -> None:
    with_all = ModuleType("with_all")
    with_all.__dict__.update({"__all__": ["listed"], "listed": len, "unlisted": len})
    without_all = ModuleType("without_all")
    without_all.__dict__.update({"public": len, "_private": len})

    assert public_names_of(with_all) == ["listed"]
    assert public_names_of(without_all) == ["public"]


def test_data_names_are_not_call_paths(load_fixture_module) -> None:
    original = load_fixture_module("matching_original")
    rust_backed = load_fixture_module("matching_rust_backed")

    results = compare_modules(original, rust_backed, ["SEPARATOR", "shout"], 5)

    assert [result["call_path"] for result in results] == ["matching_original.shout"]


def test_lone_surrogate_example_runs(load_fixture_module) -> None:
    original = load_fixture_module("surrogate_original")
    rust_backed = load_fixture_module("surrogate_rust_backed")

    results = compare_modules(
        original, rust_backed, ["encode", "encode_with_label"], EXAMPLES_PER_CALL_PATH
    )

    [encode, encode_with_label] = results
    [mismatch] = encode["mismatches"]
    assert mismatch["shrunk_input"] == repr(LONE_SURROGATE)
    assert mismatch["original"] == repr(LONE_SURROGATE.encode("utf-8", "surrogatepass"))
    assert mismatch["rust_backed"].startswith("UnicodeEncodeError(")
    [mismatch] = encode_with_label["mismatches"]
    assert mismatch["shrunk_input"] == f"0, {LONE_SURROGATE!r}"


def test_builtin_flag_recorded(load_fixture_module) -> None:
    original = load_fixture_module("matching_original")
    rust_backed = load_fixture_module("matching_rust_backed")

    results = compare_modules(original, rust_backed, ["shout", "size"], 5)

    flags = {result["call_path"]: result["rust_backed_is_builtin"] for result in results}
    assert flags == {"matching_original.shout": False, "matching_original.size": True}


def test_both_modules_loaded_in_one_child_process(tiny_port_with_stand_in: Path) -> None:
    port = tiny_port_with_stand_in

    results = run_differential(port, 10)

    report = json.loads(port_folder.differential_report_path(port).read_text())
    assert isinstance(report["process_id"], int)
    assert report["process_id"] != os.getpid()
    assert set(report["modules_loaded"]) == {"tiny_package", "tiny_package_rs"}
    for module_file in report["modules_loaded"].values():
        assert Path(module_file).is_relative_to(port_folder.venv_folder(port))
    assert results == report["call_paths"]
    by_call_path = results_by_call_path(results)
    assert set(by_call_path) == {
        "tiny_package.count_words",
        "tiny_package.evaluate_sum",
        "tiny_package.shout",
        "tiny_package.split_after_vowels",
    }
    for result in results:
        assert result["inputs_tried"] >= 10
        assert result["mismatches"] == []
        assert result["rust_backed_is_builtin"] is False


def test_checkout_clean_after_differential(tiny_port_with_stand_in: Path) -> None:
    port = tiny_port_with_stand_in

    run_differential(port, 10)

    status = subprocess.run(
        ["git", "-C", str(port_folder.checkout_folder(port)), "status", "--porcelain", "--ignored"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert status.stdout == ""
    assert list(port.rglob(".hypothesis")) == []


def test_failed_child_process_raises(tiny_port_with_environment: Path) -> None:
    # Without the stand-in installed, the child cannot import tiny_package_rs.
    with pytest.raises(DifferentialRunFailed, match="No module named 'tiny_package_rs'"):
        run_differential(tiny_port_with_environment, 5)
