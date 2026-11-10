"""Find the public names of the Rust-backed package that still resolve to Python code."""

import json
import subprocess
import tempfile
from pathlib import Path

from oxidify import port_folder as paths
from oxidify.state import read_state

FALLBACK_SCRIPT = Path(__file__).parent / "fallback_script.py"


class FallbackCheckFailed(Exception):
    """The Rust-backed package could not be inspected."""


def names_resolving_to_source_language(port_folder: Path) -> list[str]:
    """Dotted public names of the coverage map whose Rust-backed object is not from the extension.

    Every such name is returned, whatever the map marks it, so the caller can compare the two.
    """
    coverage_map_path = paths.coverage_map_path(port_folder)
    # Checked here because the script in the port environment has no schema check.
    read_state(coverage_map_path, "coverage_map")
    with tempfile.TemporaryDirectory() as output_folder:
        output = Path(output_folder) / "names.json"
        # -I keeps this script's folder and PYTHONPATH off sys.path in the port environment.
        arguments = [
            str(paths.venv_python(port_folder)),
            "-I",
            str(FALLBACK_SCRIPT),
            str(coverage_map_path),
            str(output),
        ]
        result = subprocess.run(arguments, cwd=port_folder, capture_output=True, text=True)
        if result.returncode != 0:
            raise FallbackCheckFailed(
                f"{' '.join(arguments)} exited {result.returncode}: {result.stderr.strip()}"
            )
        return json.loads(output.read_text())
