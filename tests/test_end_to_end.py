import contextlib
import io
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from conftest import INFLECTION_COMMIT, INFLECTION_URL

from oxidify import port_folder, state
from oxidify.command_line import main

HAND_SWAP_PROJECT = Path(__file__).parents[1] / "examples" / "inflection_hand_swap"

pytestmark = pytest.mark.end_to_end


def run_command(*arguments: str) -> tuple[int, str]:
    """Run the command line in this process; return the exit code and what it printed."""
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        exit_code = main(list(arguments))
    return exit_code, printed.getvalue()


@pytest.fixture(scope="module")
def built_port(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """The inflection port after the five commands, with the oracle's exit code and output.

    Read-only: tests that change a port work on `copy_of_built_port`.
    """
    port = tmp_path_factory.mktemp("built_port") / "inflection"
    for arguments in (
        (
            "start",
            INFLECTION_URL,
            INFLECTION_COMMIT,
            str(port),
            "--test-path",
            "test_inflection.py",
        ),
        ("analyse", str(port)),
        ("mark-swapped", str(port), "inflection", "dasherize"),
        ("build", str(port), "--rust-project", str(HAND_SWAP_PROJECT)),
    ):
        exit_code, _ = run_command(*arguments)
        assert exit_code == 0, arguments
    exit_code, summary = run_command("oracle", str(port))
    return {"port": port, "oracle_exit_code": exit_code, "oracle_summary": summary}


@pytest.fixture
def copy_of_built_port(tmp_path: Path, built_port: dict[str, Any]) -> Path:
    copy = tmp_path / "inflection"
    shutil.copytree(built_port["port"], copy, symlinks=True)
    return copy


def test_inflection_port_passes_the_oracle(built_port: dict[str, Any]) -> None:
    port: Path = built_port["port"]
    print(built_port["oracle_summary"])
    assert built_port["oracle_exit_code"] == 0

    report = state.read_state(port_folder.oracle_report_path(port), "oracle_report")
    tests = report["original_tests"]
    assert tests["failed"] == 0
    assert tests["errors"] == 0
    assert tests["passed"] > 0
    assert tests["missing_test_ids"] == []

    status = subprocess.run(
        ["git", "-C", str(port_folder.checkout_folder(port)), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert status.stdout == ""

    (dasherize,) = [
        entry for entry in report["differential"] if entry["call_path"].endswith("dasherize")
    ]
    assert dasherize["inputs_tried"] > 0
    assert dasherize["mismatches"] == []
    assert dasherize["rust_backed_is_builtin"] is True

    differential = json.loads(port_folder.differential_report_path(port).read_text())
    assert isinstance(differential["process_id"], int)
    assert {"inflection", "inflection_rs"} <= set(differential["modules_loaded"])

    left_in_python = {
        entry["name"]: entry["reason"] for entry in report["fallback"]["left_in_python"]
    }
    assert "inflection.dasherize" not in left_in_python
    assert len(left_in_python) == 14
    assert all(reason.strip() for reason in left_in_python.values())

    state.read_state(port_folder.coverage_map_path(port), "coverage_map")
    state.read_state(port_folder.checkpoints_path(port), "checkpoints")
    state.read_state(port_folder.task_log_path(port), "task_log")


def test_python_name_without_reason_fails_the_port(
    copy_of_built_port: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = port_folder.coverage_map_path(copy_of_built_port)
    coverage_map = state.read_state(path, "coverage_map")
    coverage_map["modules"]["inflection"]["public_names"]["pluralize"]["reason"] = ""
    state.write_state(path, "coverage_map", coverage_map)

    exit_code = main(["oracle", str(copy_of_built_port)])

    assert exit_code != 0
    report = state.read_state(port_folder.oracle_report_path(copy_of_built_port), "oracle_report")
    assert report["fallback"]["python_names_without_reason"] == ["inflection.pluralize"]
    assert "inflection.pluralize" in capsys.readouterr().out


def test_rust_marked_name_resolving_to_python_fails_the_port(
    copy_of_built_port: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["mark-swapped", str(copy_of_built_port), "inflection", "underscore"]) == 0

    exit_code = main(["oracle", str(copy_of_built_port)])

    assert exit_code != 0
    output = capsys.readouterr().out
    assert "marked rust but resolves to Python: inflection.underscore" in output
