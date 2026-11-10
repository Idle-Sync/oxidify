"""The boundary between language-neutral steps and everything specific to the source language.

Only this module imports a concrete adapter; every other module goes through `load_adapter`.
The interface is described for readers in reference/adapter-interface.md.
"""

from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from oxidify.python_adapter import PythonAdapter

ADAPTER_INTERFACE_VERSION = 1


@runtime_checkable
class SourceLanguageAdapter(Protocol):
    name: str
    interface_version: int

    def prepare_environment(self, port_folder: Path) -> None: ...

    def analyse_source(self, port_folder: Path) -> None: ...

    def build_bridge(self, port_folder: Path) -> None: ...

    def run_original_tests(
        self, port_folder: Path, against: Literal["original", "rust_backed"]
    ) -> dict[str, Any]: ...

    def run_differential(
        self, port_folder: Path, examples_per_call_path: int
    ) -> list[dict[str, Any]]: ...

    def names_resolving_to_source_language(self, port_folder: Path) -> list[str]: ...


ADAPTERS: dict[str, type[SourceLanguageAdapter]] = {"python": PythonAdapter}


def load_adapter(name: str, interface_version: int) -> SourceLanguageAdapter:
    """Adapter registered under `name`, refused unless it implements `interface_version`."""
    if name not in ADAPTERS:
        known = ", ".join(sorted(ADAPTERS))
        raise ValueError(f"no source-language adapter named {name!r}; known adapters: {known}")
    adapter = ADAPTERS[name]()
    if adapter.interface_version != interface_version:
        raise ValueError(
            f"adapter {name!r} implements interface version {adapter.interface_version}, "
            f"not interface version {interface_version}"
        )
    return adapter
