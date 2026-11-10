"""Print the public names of each module as JSON, saying whether each name is callable.

Runs on the port environment's interpreter, where the original is installed.
Public names are `__all__` when the module has it, otherwise its top-level names without a
leading underscore that are not modules.
Usage: public_names.py <module> [<module> ...]
"""

import importlib
import inspect
import json
import sys
from types import ModuleType


def public_names(module: ModuleType) -> list[str]:
    if hasattr(module, "__all__"):
        return list(module.__all__)
    names = []
    for name, value in vars(module).items():
        if name.startswith("_") or inspect.ismodule(value):
            continue
        names.append(name)
    return names


def main(module_names: list[str]) -> None:
    result = {}
    for module_name in module_names:
        module = importlib.import_module(module_name)
        result[module_name] = {
            name: callable(getattr(module, name)) for name in sorted(public_names(module))
        }
    print(json.dumps(result))


main(sys.argv[1:])
