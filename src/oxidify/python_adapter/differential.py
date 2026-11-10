"""Compare original and Rust-backed call paths on inputs Hypothesis generates."""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from oxidify import port_folder as paths
from oxidify.state import read_state

DIFFERENTIAL_SCRIPT = Path(__file__).parent / "differential_script.py"


class DifferentialRunFailed(Exception):
    """The child process that compares the two packages exited non-zero."""


def run_differential(port_folder: Path, examples_per_call_path: int) -> list[dict[str, Any]]:
    """One oracle report `differential` entry per public call path.

    Both packages load in one child process on the port's `.venv`, run with the checkout as
    working folder; it writes `report/differential.json`, whose call paths are returned.
    """
    port = read_state(paths.port_json_path(port_folder), "port")
    report_path = paths.differential_report_path(port_folder)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    module_arguments = []
    for import_name in port["import_names"]:
        module_arguments += ["--modules", import_name, f"{import_name}_rs"]

    # -I keeps the script's own folder and the working folder off sys.path, so the installed
    # original is imported, never the checkout's copy.
    command = [
        str(paths.venv_python(port_folder)),
        "-I",
        str(DIFFERENTIAL_SCRIPT),
        "--output",
        str(report_path),
        "--examples-per-call-path",
        str(examples_per_call_path),
        *module_arguments,
    ]
    # Hypothesis caches Unicode tables in `.hypothesis/` under the working folder unless told
    # otherwise; the checkout must stay untouched.
    with tempfile.TemporaryDirectory(prefix="oxidify_hypothesis_") as hypothesis_folder:
        environment = {**os.environ, "HYPOTHESIS_STORAGE_DIRECTORY": hypothesis_folder}
        result = subprocess.run(
            command,
            cwd=paths.checkout_folder(port_folder),
            env=environment,
            capture_output=True,
            text=True,
        )
    if result.returncode != 0:
        raise DifferentialRunFailed(
            f"differential run exited {result.returncode}: {result.stderr.strip()}"
        )
    report = json.loads(report_path.read_text())
    return report["call_paths"]
