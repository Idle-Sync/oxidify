"""Build the Rust-backed package under `<port>/rust_backed/` and install it."""

from pathlib import Path


def build_bridge(port_folder: Path) -> None:
    """Build the Rust-backed package with maturin and install its wheel into `<port>/.venv`."""
    raise NotImplementedError("build_bridge: the Rust-backed build is not built yet")
