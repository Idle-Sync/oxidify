"""List the public names of the Rust-backed package whose object is not from its Rust extension.

Run on the port interpreter as `python -I fallback_script.py <coverage_map.json> <output.json>`.
It imports nothing from oxidify, which the port environment does not have. Each module
`<name>.<rest>` of the coverage map is looked up as `<name>_rs.<rest>`; the extension is
`<name>_rs._rust`. The output is a JSON list of dotted names written with the original import name.
"""

import importlib
import json
import sys
from pathlib import Path


def rust_backed_module_name(module: str) -> str:
    package, dot, rest = module.partition(".")
    return f"{package}_rs{dot}{rest}"


def is_from_extension(value: object, extension: object) -> bool:
    """True for a function of the Rust extension: its `__self__` is the extension module."""
    return getattr(value, "__self__", None) is extension


def names_not_from_extension(coverage_map: dict) -> list[str]:
    names = []
    for module, module_entry in coverage_map["modules"].items():
        rust_backed_module = importlib.import_module(rust_backed_module_name(module))
        extension = importlib.import_module(f"{module.partition('.')[0]}_rs._rust")
        for name in module_entry["public_names"]:
            # A public name missing from the Rust-backed module raises AttributeError here.
            value = getattr(rust_backed_module, name)
            if not is_from_extension(value, extension):
                names.append(f"{module}.{name}")
    return names


def main() -> None:
    coverage_map_path, output_path = sys.argv[1:]
    coverage_map = json.loads(Path(coverage_map_path).read_text())
    Path(output_path).write_text(json.dumps(names_not_from_extension(coverage_map)))


if __name__ == "__main__":
    main()
