"""Source-language adapter for Python packages; each method is one function in a sibling module."""

from pathlib import Path
from typing import Any, Literal

from oxidify.python_adapter import (
    analysis,
    bridge,
    differential,
    environment,
    fallback_check,
    original_tests,
)


class PythonAdapter:
    name = "python"
    interface_version = 1

    def prepare_environment(self, port_folder: Path) -> None:
        environment.prepare_environment(port_folder)

    def analyse_source(self, port_folder: Path) -> None:
        analysis.analyse_source(port_folder)

    def build_bridge(self, port_folder: Path) -> None:
        bridge.build_bridge(port_folder)

    def run_original_tests(
        self, port_folder: Path, against: Literal["original", "rust_backed"]
    ) -> dict[str, Any]:
        return original_tests.run_original_tests(port_folder, against)

    def run_differential(
        self, port_folder: Path, examples_per_call_path: int
    ) -> list[dict[str, Any]]:
        return differential.run_differential(port_folder, examples_per_call_path)

    def names_resolving_to_source_language(self, port_folder: Path) -> list[str]:
        return fallback_check.names_resolving_to_source_language(port_folder)
