"""Find public names the coverage map marks Rust that still resolve to Python code."""

from pathlib import Path


def names_resolving_to_source_language(port_folder: Path) -> list[str]:
    """Dotted names marked `rust` in the coverage map whose Rust-backed object is Python code."""
    raise NotImplementedError(
        "names_resolving_to_source_language: the no-fallback check is not built yet"
    )
