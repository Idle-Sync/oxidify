"""Build the Rust-backed package under `<port>/rust_backed/` and install it."""

import shutil
import subprocess
from pathlib import Path
from typing import Any

from oxidify import port_folder as paths
from oxidify.state import read_state


class BridgeBuildFailed(Exception):
    """Writing, building or installing the Rust-backed package failed."""


def run_build_command(arguments: list[str], working_folder: Path) -> None:
    """Run one build command; a non-zero exit raises with its stderr."""
    result = subprocess.run(arguments, cwd=working_folder, capture_output=True)
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        raise BridgeBuildFailed(f"{' '.join(arguments)} exited {result.returncode}: {stderr}")


def module_file(package_folder: Path, module: str) -> Path:
    """Source file of dotted `module` inside the package copied to `package_folder`."""
    parts_below_package = module.split(".")[1:]
    if not parts_below_package:
        return package_folder / "__init__.py"
    module_path = package_folder.joinpath(*parts_below_package)
    if module_path.is_dir():
        return module_path / "__init__.py"
    return module_path.with_suffix(".py")


def rust_names(module_entry: dict[str, Any]) -> list[str]:
    """Public names of one coverage map module that are implemented in Rust."""
    names = []
    for name, entry in module_entry["public_names"].items():
        if entry["implementation"] == "rust":
            names.append(name)
    return names


def write_python_package(port_folder: Path, import_name: str) -> None:
    """Copy the original package to `python/<import name>_rs/` and rebind each Rust name.

    The rebinding lines import from the extension without a `try`, so a missing Rust function
    fails the import instead of leaving the Python one in place.
    """
    original_package = paths.original_source_folder(port_folder) / import_name
    if not original_package.is_dir():
        raise BridgeBuildFailed(
            f"{original_package} is not a folder: the Rust-backed build copies a package folder "
            f"named after the import name {import_name!r}"
        )
    package_folder = paths.rust_backed_python_package_folder(port_folder, import_name)
    if package_folder.exists():
        shutil.rmtree(package_folder)
    shutil.copytree(original_package, package_folder, ignore=shutil.ignore_patterns("__pycache__"))
    coverage_map = read_state(paths.coverage_map_path(port_folder), "coverage_map")
    for module, module_entry in coverage_map["modules"].items():
        names = rust_names(module_entry)
        if not names:
            continue
        source_file = module_file(package_folder, module)
        source = source_file.read_text()
        if not source.endswith("\n"):
            source += "\n"
        for name in names:
            source += f"from {import_name}_rs._rust import {name}\n"
        source_file.write_text(source)


def build_wheel(port_folder: Path) -> Path:
    """Build the maturin project in `rust_backed/` for the port interpreter; return the wheel."""
    rust_backed = paths.rust_backed_folder(port_folder)
    if not (rust_backed / "pyproject.toml").is_file():
        raise BridgeBuildFailed(
            f"{rust_backed} holds no pyproject.toml: copy the maturin project of the Rust code "
            f"there before building"
        )
    wheels = paths.wheels_folder(port_folder)
    # Emptied first so the one wheel left afterwards is the one just built.
    if wheels.exists():
        shutil.rmtree(wheels)
    run_build_command(
        [
            "maturin",
            "build",
            "--release",
            "--quiet",
            "--interpreter",
            str(paths.venv_python(port_folder)),
            "--out",
            str(wheels),
        ],
        rust_backed,
    )
    built_wheels = sorted(wheels.glob("*.whl"))
    if len(built_wheels) != 1:
        raise BridgeBuildFailed(f"expected one wheel in {wheels}, found {len(built_wheels)}")
    return built_wheels[0]


def build_bridge(port_folder: Path) -> None:
    """Build the Rust-backed package with maturin and install its wheel into `<port>/.venv`."""
    port = read_state(paths.port_json_path(port_folder), "port")
    import_names = port["import_names"]
    if len(import_names) != 1:
        raise BridgeBuildFailed(
            f"the Rust-backed build makes one package; port.json lists {len(import_names)} "
            f"import names: {', '.join(import_names)}"
        )
    write_python_package(port_folder, import_names[0])
    wheel = build_wheel(port_folder)
    run_build_command(
        [
            "uv",
            "pip",
            "install",
            "--quiet",
            "--python",
            str(paths.venv_python(port_folder)),
            "--force-reinstall",
            str(wheel),
        ],
        port_folder,
    )
