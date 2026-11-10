"""Print the modules, their source files and their import edges as JSON.

Runs on the port environment's interpreter, where grimp and the original are installed.
Usage: import_graph.py <import name> [<import name> ...]
"""

import importlib.util
import json
import sys
from pathlib import Path

import grimp


def importable_root(import_name: str) -> Path:
    """Folder that holds the top-level package or module, so file paths can be relative to it."""
    spec = importlib.util.find_spec(import_name)
    if spec is None or spec.origin is None:
        raise SystemExit(f"{import_name} is not importable in the port environment")
    origin = Path(spec.origin)
    if origin.name == "__init__.py":
        return origin.parent.parent
    return origin.parent


def module_path(module: str) -> Path:
    spec = importlib.util.find_spec(module)
    if spec is None or spec.origin is None:
        raise SystemExit(f"{module} has no source file")
    return Path(spec.origin)


def main(import_names: list[str]) -> None:
    # No cache folder: grimp would otherwise write `.grimp_cache` into the working folder.
    graph = grimp.build_graph(*import_names, cache_dir=None)
    roots = {name: importable_root(name) for name in import_names}
    modules = []
    edges = []
    for module in sorted(graph.modules):
        root = roots[module.split(".")[0]]
        path = module_path(module)
        modules.append({"name": module, "file": str(path.relative_to(root)), "path": str(path)})
        for imported in sorted(graph.find_modules_directly_imported_by(module)):
            edges.append({"importer": module, "imported": imported})
    print(json.dumps({"modules": modules, "edges": edges}))


main(sys.argv[1:])
