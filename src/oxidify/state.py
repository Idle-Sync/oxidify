"""Read and write the versioned port state files, each checked against its schema in `schemas/`."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

from oxidify import port_folder

FORMAT_VERSION = 1
KINDS = ("port", "coverage_map", "checkpoints", "task_log", "oracle_report")
SCHEMAS_FOLDER = Path(__file__).resolve().parents[2] / "schemas"


class UnknownFormatVersion(Exception):
    """The file was written in a format version this code cannot read."""


class InvalidState(Exception):
    """The file does not match the schema of its kind."""


def schema_for(kind: str) -> dict[str, Any]:
    if kind not in KINDS:
        raise ValueError(f"unknown state kind {kind!r}; known kinds: {', '.join(KINDS)}")
    return json.loads((SCHEMAS_FOLDER / f"{kind}.schema.json").read_text())


def check_against_schema(path: Path, kind: str, data: Any) -> None:
    error = best_match(Draft202012Validator(schema_for(kind)).iter_errors(data))
    if error is None:
        return
    raise InvalidState(f"{path}: {error.message} (at {error.json_path})")


def read_state(path: Path, kind: str) -> dict[str, Any]:
    """Load a state file, refusing an unknown format version or a shape its schema rejects."""
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise InvalidState(f"{path}: not valid JSON: {error}") from error
    # Checked before the schema so a newer file gets a version error, not a list of shape errors.
    if isinstance(data, dict) and "format_version" in data:
        version = data["format_version"]
        if version != FORMAT_VERSION:
            raise UnknownFormatVersion(
                f"{path}: format_version {version} is not supported; "
                f"this code reads format_version {FORMAT_VERSION}"
            )
    check_against_schema(path, kind, data)
    return data


def write_state(path: Path, kind: str, data: dict[str, Any]) -> None:
    """Write a state file after checking it against its schema; nothing is written if it fails."""
    check_against_schema(path, kind, data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def new_coverage_map(modules: dict[str, list[str]]) -> dict[str, Any]:
    """Coverage map with every public name in Python, an empty reason and coverage not measured.

    `modules` maps each dotted module name to its public names.
    """
    coverage_map: dict[str, Any] = {"format_version": FORMAT_VERSION, "modules": {}}
    for module, names in modules.items():
        public_names = {}
        for name in sorted(names):
            public_names[name] = {"implementation": "python", "reason": ""}
        coverage_map["modules"][module] = {
            "status": "python",
            "coverage_percent": None,
            "public_names": public_names,
        }
    return coverage_map


def mark_names_swapped(port: Path, module: str, names: list[str]) -> None:
    """Mark names of one module as implemented in Rust; refuses names the map does not hold."""
    path = port_folder.coverage_map_path(port)
    coverage_map = read_state(path, "coverage_map")
    if module not in coverage_map["modules"]:
        raise ValueError(f"{path}: module {module!r} is not in the coverage map")
    public_names = coverage_map["modules"][module]["public_names"]
    unknown_names = [name for name in names if name not in public_names]
    if unknown_names:
        listed = ", ".join(repr(name) for name in unknown_names)
        raise ValueError(f"{path}: module {module!r} has no public name {listed}")
    for name in names:
        public_names[name] = {"implementation": "rust", "reason": None}
    write_state(path, "coverage_map", coverage_map)


def append_task_log_entry(port: Path, entry: dict[str, Any]) -> None:
    """Add one entry to the task log, creating the log on the first entry."""
    path = port_folder.task_log_path(port)
    task_log: dict[str, Any] = {"format_version": FORMAT_VERSION, "entries": []}
    if path.exists():
        task_log = read_state(path, "task_log")
    task_log["entries"].append(entry)
    write_state(path, "task_log", task_log)


def record_checkpoint(port: Path, step: str) -> None:
    """Record that a step completed now, creating the checkpoints file on the first step."""
    path = port_folder.checkpoints_path(port)
    checkpoints: dict[str, Any] = {"format_version": FORMAT_VERSION, "checkpoints": []}
    if path.exists():
        checkpoints = read_state(path, "checkpoints")
    completed_at = datetime.now(UTC).isoformat(timespec="seconds")
    checkpoints["checkpoints"].append({"step": step, "completed_at": completed_at})
    write_state(path, "checkpoints", checkpoints)
