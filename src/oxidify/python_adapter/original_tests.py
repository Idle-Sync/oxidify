"""Run the original's unchanged tests against the original or the Rust-backed package."""

from pathlib import Path
from typing import Any, Literal


def run_original_tests(
    port_folder: Path, against: Literal["original", "rust_backed"]
) -> dict[str, Any]:
    """Counts `{passed, failed, errors, skipped, collected_test_ids}` from the JUnit XML report."""
    raise NotImplementedError("run_original_tests: running the original tests is not built yet")
