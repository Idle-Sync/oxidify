"""Create the port's own environment, installing the original from an export of its commit."""

import io
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

from oxidify import port_folder as paths
from oxidify.state import read_state

PORT_REQUIREMENTS = Path(__file__).parent / "port_requirements.txt"


class EnvironmentSetupFailed(Exception):
    """A command that builds the port environment failed."""


def run_command(arguments: list[str], working_folder: Path) -> bytes:
    """Run a command and return its standard output; a non-zero exit raises with its stderr."""
    result = subprocess.run(arguments, cwd=working_folder, capture_output=True)
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        raise EnvironmentSetupFailed(f"{' '.join(arguments)} exited {result.returncode}: {stderr}")
    return result.stdout


def export_pinned_commit(port_folder: Path, commit: str) -> None:
    """Replace `original_source/` with `git archive` of the commit.

    The original is built and installed from this export, so its build files never land in
    the checkout.
    """
    original_source = paths.original_source_folder(port_folder)
    if original_source.exists():
        shutil.rmtree(original_source)
    checkout = paths.checkout_folder(port_folder)
    archive = run_command(
        ["git", "-C", str(checkout), "archive", "--format=tar", commit], port_folder
    )
    original_source.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(original_source, filter="data")


def prepare_environment(port_folder: Path) -> None:
    """Create `<port>/.venv` holding the original, its test requirements and the port tools."""
    port = read_state(paths.port_json_path(port_folder), "port")
    export_pinned_commit(port_folder, port["commit"])
    venv_python = str(paths.venv_python(port_folder))
    run_command(
        [
            "uv",
            "venv",
            "--quiet",
            "--clear",
            "--python",
            sys.executable,
            str(paths.venv_folder(port_folder)),
        ],
        port_folder,
    )
    run_command(
        [
            "uv",
            "pip",
            "install",
            "--quiet",
            "--python",
            venv_python,
            "--requirement",
            str(PORT_REQUIREMENTS),
            *port["test_requirements"],
            str(paths.original_source_folder(port_folder)),
        ],
        port_folder,
    )
    import_statement = "import " + ", ".join(port["import_names"])
    run_command([venv_python, "-c", import_statement], port_folder)
