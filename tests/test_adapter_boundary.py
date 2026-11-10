import ast
import inspect
from pathlib import Path

import pytest

from oxidify import adapter
from oxidify.adapter import ADAPTER_INTERFACE_VERSION, SourceLanguageAdapter, load_adapter

REPOSITORY_ROOT = Path(__file__).parent.parent
PACKAGE_FOLDER = REPOSITORY_ROOT / "src" / "oxidify"
ADAPTER_REFERENCE = REPOSITORY_ROOT / "reference" / "adapter-interface.md"
SOURCE_LANGUAGE_ONLY_MODULES = {"grimp", "coverage", "hypothesis", "pytest", "ast"}
ADAPTER_METHODS = [
    "prepare_environment",
    "analyse_source",
    "build_bridge",
    "run_original_tests",
    "run_differential",
    "names_resolving_to_source_language",
]


def modules_outside_python_adapter() -> list[Path]:
    python_adapter_folder = PACKAGE_FOLDER / "python_adapter"
    paths = []
    for path in sorted(PACKAGE_FOLDER.rglob("*.py")):
        if python_adapter_folder not in path.parents:
            paths.append(path)
    return paths


def imported_module_names(path: Path) -> set[str]:
    """Full dotted names a module imports; relative imports resolve against `oxidify`."""
    names = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        if isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level > 0:
                base = f"oxidify.{base}" if base else "oxidify"
            names.add(base)
            for alias in node.names:
                names.add(f"{base}.{alias.name}")
    return names


def protocol_method_names() -> list[str]:
    names = []
    for name, member in vars(SourceLanguageAdapter).items():
        if not name.startswith("_") and inspect.isfunction(member):
            names.append(name)
    return names


def test_modules_outside_python_adapter_import_no_source_language_tools() -> None:
    offenders = []
    for path in modules_outside_python_adapter():
        for name in imported_module_names(path):
            if name.split(".")[0] in SOURCE_LANGUAGE_ONLY_MODULES:
                offenders.append(f"{path.relative_to(PACKAGE_FOLDER)} imports {name}")

    assert offenders == []


def test_only_adapter_module_imports_python_adapter() -> None:
    importers = []
    for path in modules_outside_python_adapter():
        for name in imported_module_names(path):
            if name == "oxidify.python_adapter" or name.startswith("oxidify.python_adapter."):
                importers.append(path.name)

    assert sorted(set(importers)) == ["adapter.py"]


def test_protocol_has_the_six_methods() -> None:
    assert protocol_method_names() == ADAPTER_METHODS


def test_reference_names_every_method_and_the_version() -> None:
    reference = ADAPTER_REFERENCE.read_text()

    assert f"Interface version: {ADAPTER_INTERFACE_VERSION}" in reference
    for name in protocol_method_names():
        assert f"`{name}(" in reference, name


def test_load_adapter_returns_all_six_methods() -> None:
    loaded = load_adapter("python", 1)

    assert loaded.name == "python"
    assert loaded.interface_version == ADAPTER_INTERFACE_VERSION
    for name in ADAPTER_METHODS:
        assert callable(getattr(loaded, name)), name
    assert isinstance(loaded, SourceLanguageAdapter)


def test_load_adapter_refuses_unknown() -> None:
    with pytest.raises(ValueError, match="'ruby'"):
        load_adapter("ruby", 1)
    with pytest.raises(ValueError, match="interface version 2"):
        load_adapter("python", 2)


def test_registry_is_a_plain_dict_with_one_entry() -> None:
    assert list(adapter.ADAPTERS) == ["python"]
