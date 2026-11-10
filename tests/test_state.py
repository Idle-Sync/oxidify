import json
from pathlib import Path

import pytest

from oxidify import port_folder, state
from oxidify.state import InvalidState, UnknownFormatVersion

PINNED_COMMIT = "b00d4d348b32ef5823221b20ee4cbd1d2d924462"


def example_port() -> dict:
    return {
        "format_version": 1,
        "source_url": "https://github.com/jpvanhal/inflection.git",
        "commit": PINNED_COMMIT,
        "adapter": {"name": "python", "interface_version": 1},
        "test_command": ["python", "-m", "pytest"],
        "test_paths": ["test_inflection.py"],
        "test_requirements": ["pytest"],
        "import_names": ["inflection"],
    }


def example_coverage_map() -> dict:
    coverage_map = state.new_coverage_map({"inflection": ["camelize", "dasherize"]})
    coverage_map["modules"]["inflection"]["coverage_percent"] = 98.5
    return coverage_map


def example_checkpoints() -> dict:
    return {
        "format_version": 1,
        "checkpoints": [{"step": "start", "completed_at": "2026-11-10T14:00:00+00:00"}],
    }


def example_task_log() -> dict:
    return {
        "format_version": 1,
        "entries": [
            {
                "step": "build_bridge",
                "module": "inflection",
                "started_at": "2026-11-10T14:00:00+00:00",
                "finished_at": "2026-11-10T14:01:00+00:00",
                "outcome": "passed",
                "model": None,
                "input_tokens": None,
                "output_tokens": None,
                "cost_usd": None,
            }
        ],
    }


def example_oracle_report() -> dict:
    return {
        "format_version": 1,
        "original_tests": {
            "passed": 10,
            "failed": 0,
            "errors": 0,
            "skipped": 1,
            "test_folder_diff_empty": True,
            "missing_test_ids": [],
        },
        "differential": [
            {
                "call_path": "inflection.dasherize",
                "inputs_tried": 200,
                "skipped_reason": None,
                "rust_backed_is_builtin": True,
                "mismatches": [
                    {"shrunk_input": "('a_b',)", "original": "'a-b'", "rust_backed": "'a_b'"}
                ],
            }
        ],
        "fallback": {
            "rust_names_resolving_to_python": [],
            "python_names_without_reason": [],
            "left_in_python": [{"name": "inflection.camelize", "reason": "not swapped in M1a"}],
        },
        "passed": False,
    }


EXAMPLES = {
    "port": example_port,
    "coverage_map": example_coverage_map,
    "checkpoints": example_checkpoints,
    "task_log": example_task_log,
    "oracle_report": example_oracle_report,
}


@pytest.mark.parametrize("kind", sorted(EXAMPLES))
def test_each_kind_round_trips(tmp_path: Path, kind: str) -> None:
    data = EXAMPLES[kind]()
    path = tmp_path / f"{kind}.json"

    state.write_state(path, kind, data)

    assert state.read_state(path, kind) == data


@pytest.mark.parametrize("kind", sorted(EXAMPLES))
def test_unknown_format_version_is_refused(tmp_path: Path, kind: str) -> None:
    data = EXAMPLES[kind]()
    data["format_version"] = 2
    path = tmp_path / f"{kind}.json"
    path.write_text(json.dumps(data))

    with pytest.raises(UnknownFormatVersion, match="format_version 2"):
        state.read_state(path, kind)


def test_missing_required_field_names_the_field(tmp_path: Path) -> None:
    data = example_port()
    del data["commit"]
    path = tmp_path / "port.json"
    path.write_text(json.dumps(data))

    with pytest.raises(InvalidState, match="'commit' is a required property"):
        state.read_state(path, "port")


def test_missing_format_version_is_invalid(tmp_path: Path) -> None:
    data = example_checkpoints()
    del data["format_version"]
    path = tmp_path / "checkpoints.json"
    path.write_text(json.dumps(data))

    with pytest.raises(InvalidState, match="'format_version' is a required property"):
        state.read_state(path, "checkpoints")


def test_write_state_validates_before_writing(tmp_path: Path) -> None:
    data = example_port()
    data["commit"] = "not-a-hash"
    path = tmp_path / "port.json"

    with pytest.raises(InvalidState, match="commit"):
        state.write_state(path, "port", data)

    assert not path.exists()


def test_unknown_kind_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown state kind 'ports'"):
        state.write_state(tmp_path / "x.json", "ports", example_port())


def test_new_coverage_map_starts_every_name_in_python() -> None:
    coverage_map = state.new_coverage_map({"inflection": ["dasherize", "camelize"]})

    assert coverage_map == {
        "format_version": 1,
        "modules": {
            "inflection": {
                "status": "python",
                "coverage_percent": None,
                "public_names": {
                    "camelize": {"implementation": "python", "reason": ""},
                    "dasherize": {"implementation": "python", "reason": ""},
                },
            }
        },
    }


def test_python_name_without_reason_string_is_invalid(tmp_path: Path) -> None:
    coverage_map = example_coverage_map()
    coverage_map["modules"]["inflection"]["public_names"]["camelize"]["reason"] = None

    with pytest.raises(InvalidState):
        state.write_state(tmp_path / "coverage_map.json", "coverage_map", coverage_map)


def test_rust_name_with_reason_is_invalid(tmp_path: Path) -> None:
    coverage_map = example_coverage_map()
    coverage_map["modules"]["inflection"]["public_names"]["camelize"] = {
        "implementation": "rust",
        "reason": "left over",
    }

    with pytest.raises(InvalidState):
        state.write_state(tmp_path / "coverage_map.json", "coverage_map", coverage_map)


def write_example_coverage_map(port: Path) -> None:
    coverage_map = state.new_coverage_map(
        {"inflection": ["camelize", "dasherize", "titleize"], "inflection.extra": ["dasherize"]}
    )
    coverage_map["modules"]["inflection"]["public_names"]["dasherize"]["reason"] = "not yet"
    state.write_state(port_folder.coverage_map_path(port), "coverage_map", coverage_map)


def test_mark_names_swapped_clears_reason(tmp_path: Path) -> None:
    write_example_coverage_map(tmp_path)

    state.mark_names_swapped(tmp_path, "inflection", ["dasherize", "titleize"])

    coverage_map = state.read_state(port_folder.coverage_map_path(tmp_path), "coverage_map")
    names = coverage_map["modules"]["inflection"]["public_names"]
    assert names["dasherize"] == {"implementation": "rust", "reason": None}
    assert names["titleize"] == {"implementation": "rust", "reason": None}
    assert names["camelize"] == {"implementation": "python", "reason": ""}
    other_module = coverage_map["modules"]["inflection.extra"]["public_names"]
    assert other_module["dasherize"] == {"implementation": "python", "reason": ""}


def test_mark_names_swapped_refuses_unknown_name(tmp_path: Path) -> None:
    write_example_coverage_map(tmp_path)
    before = port_folder.coverage_map_path(tmp_path).read_text()

    with pytest.raises(ValueError, match="'pluralise'"):
        state.mark_names_swapped(tmp_path, "inflection", ["dasherize", "pluralise"])

    assert port_folder.coverage_map_path(tmp_path).read_text() == before


def test_mark_names_swapped_refuses_unknown_module(tmp_path: Path) -> None:
    write_example_coverage_map(tmp_path)

    with pytest.raises(ValueError, match="'inflection.missing'"):
        state.mark_names_swapped(tmp_path, "inflection.missing", ["dasherize"])


def test_append_task_log_entry_creates_then_appends(tmp_path: Path) -> None:
    first = example_task_log()["entries"][0]
    second = dict(first, step="run_oracle", outcome="failed")

    state.append_task_log_entry(tmp_path, first)
    state.append_task_log_entry(tmp_path, second)

    task_log = state.read_state(port_folder.task_log_path(tmp_path), "task_log")
    assert task_log == {"format_version": 1, "entries": [first, second]}


def test_append_task_log_entry_refuses_invalid_entry(tmp_path: Path) -> None:
    entry = example_task_log()["entries"][0]
    del entry["outcome"]

    with pytest.raises(InvalidState, match="'outcome' is a required property"):
        state.append_task_log_entry(tmp_path, entry)


def test_record_checkpoint_creates_then_appends(tmp_path: Path) -> None:
    state.record_checkpoint(tmp_path, "start")
    state.record_checkpoint(tmp_path, "prepare_environment")

    checkpoints = state.read_state(port_folder.checkpoints_path(tmp_path), "checkpoints")
    steps = [checkpoint["step"] for checkpoint in checkpoints["checkpoints"]]
    assert steps == ["start", "prepare_environment"]
    assert checkpoints["checkpoints"][0]["completed_at"].endswith("+00:00")
