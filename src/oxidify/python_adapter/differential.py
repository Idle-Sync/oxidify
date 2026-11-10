"""Compare original and Rust-backed call paths on inputs Hypothesis generates."""

from pathlib import Path
from typing import Any


def run_differential(port_folder: Path, examples_per_call_path: int) -> list[dict[str, Any]]:
    """One oracle report `differential` entry per public call path."""
    raise NotImplementedError("run_differential: differential runs are not built yet")
