import subprocess
from pathlib import Path
from typing import Any

import pytest

from oxidify import command_line, port_folder, state
from oxidify.command_line import main

HAND_SWAP_PROJECT = Path(__file__).parents[1] / "examples" / "inflection_hand_swap"


class RecordingAdapter:
    """Stands in for the real adapter: records each call and fails the ones named in `failing`."""

    name = "python"
    interface_version = 1

    def __init__(self, failing: tuple[str, ...] = ()) -> None:
        self.calls: list[str] = []
        self.failing = failing

    def record(self, method: str) -> None:
        self.calls.append(method)
        if method in self.failing:
            raise RuntimeError(f"{method} was told to fail")

    def prepare_environment(self, port_folder: Path) -> None:
        self.record("prepare_environment")

    def analyse_source(self, port_folder: Path) -> None:
        self.record("analyse_source")

    def build_bridge(self, port_folder: Path) -> None:
        self.record("build_bridge")


@pytest.fixture
def adapter_in_use(monkeypatch: pytest.MonkeyPatch) -> RecordingAdapter:
    adapter = RecordingAdapter()
    monkeypatch.setattr(command_line, "load_adapter", lambda name, version: adapter)
    return adapter


@pytest.fixture
def licensed_repository(tiny_repository: Path) -> Path:
    """The tiny repository with a licence file, which `start` requires."""
    (tiny_repository / "LICENSE").write_text("MIT\n")
    identity = ["-c", "user.name=Oxidify Tests", "-c", "user.email=tests@oxidify.invalid"]
    for git_arguments in (["add", "LICENSE"], ["commit", "--quiet", "-m", "add licence"]):
        subprocess.run(
            ["git", *identity, "-C", str(tiny_repository), *git_arguments],
            check=True,
            capture_output=True,
        )
    return tiny_repository


def task_log_entries(port: Path) -> list[dict[str, Any]]:
    return state.read_state(port_folder.task_log_path(port), "task_log")["entries"]


def checkpoint_steps(port: Path) -> list[str]:
    checkpoints = state.read_state(port_folder.checkpoints_path(port), "checkpoints")
    return [checkpoint["step"] for checkpoint in checkpoints["checkpoints"]]


def test_start_clones_and_prepares_the_environment(
    tmp_path: Path, licensed_repository: Path, adapter_in_use: RecordingAdapter
) -> None:
    port = tmp_path / "ports" / "tiny"
    exit_code = main(["start", str(licensed_repository), "HEAD", str(port), "--test-path", "tests"])
    assert exit_code == 0
    assert adapter_in_use.calls == ["prepare_environment"]
    assert port_folder.port_json_path(port).is_file()


def test_failed_environment_removes_port_folder(
    tmp_path: Path, licensed_repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    port = tmp_path / "ports" / "tiny"
    arguments = ["start", str(licensed_repository), "HEAD", str(port), "--test-path", "tests"]
    failing = RecordingAdapter(failing=("prepare_environment",))
    monkeypatch.setattr(command_line, "load_adapter", lambda name, version: failing)

    assert main(arguments) != 0
    assert not port.exists()

    working = RecordingAdapter()
    monkeypatch.setattr(command_line, "load_adapter", lambda name, version: working)
    assert main(arguments) == 0
    assert port_folder.port_json_path(port).is_file()


def test_start_leaves_a_non_empty_port_folder_alone(
    tmp_path: Path, licensed_repository: Path, adapter_in_use: RecordingAdapter
) -> None:
    port = tmp_path / "ports" / "tiny"
    (port / "rust_backed").mkdir(parents=True)
    (port / "port.json").write_text("{}\n")
    (port / "rust_backed" / "lib.rs").write_text("// kept\n")

    exit_code = main(["start", str(licensed_repository), "HEAD", str(port), "--test-path", "tests"])

    assert exit_code != 0
    assert (port / "port.json").read_text() == "{}\n"
    assert (port / "rust_backed" / "lib.rs").read_text() == "// kept\n"
    assert adapter_in_use.calls == []


def test_failed_environment_in_an_empty_port_folder_keeps_the_folder(
    tmp_path: Path, licensed_repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    port = tmp_path / "ports" / "tiny"
    port.mkdir(parents=True)
    failing = RecordingAdapter(failing=("prepare_environment",))
    monkeypatch.setattr(command_line, "load_adapter", lambda name, version: failing)

    assert main(["start", str(licensed_repository), "HEAD", str(port), "--test-path", "tests"]) != 0
    assert port.is_dir()
    assert list(port.iterdir()) == []


@pytest.mark.parametrize(
    "arguments",
    [
        ["analyse"],
        ["mark-swapped", "tiny_package", "alpha"],
        ["build"],
        ["build", "--rust-project", str(HAND_SWAP_PROJECT)],
        ["oracle"],
    ],
)
def test_step_on_a_missing_port_folder_creates_nothing(
    tmp_path: Path,
    adapter_in_use: RecordingAdapter,
    capsys: pytest.CaptureFixture[str],
    arguments: list[str],
) -> None:
    port = tmp_path / "no_such_port"

    exit_code = main([arguments[0], str(port), *arguments[1:]])

    assert exit_code != 0
    assert not port.exists()
    assert "port.json" in capsys.readouterr().err
    assert adapter_in_use.calls == []


def test_each_step_logs_one_entry_and_one_checkpoint(
    tiny_port_folder: Path, adapter_in_use: RecordingAdapter
) -> None:
    assert main(["analyse", str(tiny_port_folder)]) == 0

    (entry,) = task_log_entries(tiny_port_folder)
    assert entry["step"] == "analyse_source"
    assert entry["outcome"] == "passed"
    assert entry["started_at"] <= entry["finished_at"]
    assert entry["model"] is None
    assert entry["input_tokens"] is None
    assert entry["output_tokens"] is None
    assert entry["cost_usd"] is None
    assert checkpoint_steps(tiny_port_folder) == ["analyse_source"]


def test_failing_step_logs_failed_and_exits_non_zero(
    tiny_port_folder: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    failing = RecordingAdapter(failing=("analyse_source",))
    monkeypatch.setattr(command_line, "load_adapter", lambda name, version: failing)

    assert main(["analyse", str(tiny_port_folder)]) != 0

    (entry,) = task_log_entries(tiny_port_folder)
    assert entry["outcome"] == "failed"
    assert not port_folder.checkpoints_path(tiny_port_folder).exists()
    assert "analyse_source was told to fail" in capsys.readouterr().err


def test_mark_swapped_marks_the_names(tiny_port_folder: Path) -> None:
    coverage_map = state.new_coverage_map({"tiny_package": ["alpha", "beta"]})
    state.write_state(port_folder.coverage_map_path(tiny_port_folder), "coverage_map", coverage_map)

    assert main(["mark-swapped", str(tiny_port_folder), "tiny_package", "alpha"]) == 0

    saved = state.read_state(port_folder.coverage_map_path(tiny_port_folder), "coverage_map")
    names = saved["modules"]["tiny_package"]["public_names"]
    assert names["alpha"]["implementation"] == "rust"
    assert names["beta"]["implementation"] == "python"
    assert checkpoint_steps(tiny_port_folder) == ["mark_swapped"]


def test_mark_swapped_with_an_unknown_name_fails_and_logs(tiny_port_folder: Path) -> None:
    coverage_map = state.new_coverage_map({"tiny_package": ["alpha"]})
    state.write_state(port_folder.coverage_map_path(tiny_port_folder), "coverage_map", coverage_map)

    assert main(["mark-swapped", str(tiny_port_folder), "tiny_package", "gamma"]) != 0

    (entry,) = task_log_entries(tiny_port_folder)
    assert entry["outcome"] == "failed"


def test_build_copies_the_rust_project(
    tiny_port_folder: Path, adapter_in_use: RecordingAdapter, tmp_path: Path
) -> None:
    project = tmp_path / "rust_project"
    project.mkdir()
    (project / "Cargo.toml").write_text("[package]\n")
    (project / "pyproject.toml").write_text("[project]\n")
    (project / "src").mkdir()
    (project / "src" / "lib.rs").write_text("// new\n")
    (project / "target").mkdir()
    (project / "target" / "debug_output").write_text("not copied\n")
    (project / "src" / "target").mkdir()
    (project / "src" / "target" / "mod.rs").write_text("// a module named target\n")
    rust_backed = port_folder.rust_backed_folder(tiny_port_folder)
    (rust_backed / "src").mkdir(parents=True)
    (rust_backed / "src" / "stale.rs").write_text("// stale\n")
    (rust_backed / "target").mkdir()
    (rust_backed / "target" / "kept").write_text("kept\n")

    exit_code = main(["build", str(tiny_port_folder), "--rust-project", str(project)])

    assert exit_code == 0
    assert (rust_backed / "Cargo.toml").read_text() == "[package]\n"
    assert (rust_backed / "pyproject.toml").read_text() == "[project]\n"
    assert (rust_backed / "src" / "lib.rs").read_text() == "// new\n"
    assert (rust_backed / "src" / "target" / "mod.rs").read_text() == "// a module named target\n"
    assert not (rust_backed / "src" / "stale.rs").exists()
    assert not (rust_backed / "target" / "debug_output").exists()
    assert (rust_backed / "target" / "kept").read_text() == "kept\n"
    assert adapter_in_use.calls == ["build_bridge"]
    assert checkpoint_steps(tiny_port_folder) == ["build_bridge"]


@pytest.mark.parametrize("missing_file", ["Cargo.toml", "pyproject.toml"])
def test_build_refuses_a_folder_that_is_not_a_maturin_project(
    tiny_port_folder: Path,
    adapter_in_use: RecordingAdapter,
    tmp_path: Path,
    missing_file: str,
) -> None:
    project = tmp_path / "rust_project"
    project.mkdir()
    for file_name in ["Cargo.toml", "pyproject.toml"]:
        if file_name != missing_file:
            (project / file_name).write_text("\n")

    exit_code = main(["build", str(tiny_port_folder), "--rust-project", str(project)])

    assert exit_code != 0
    assert not port_folder.rust_backed_folder(tiny_port_folder).exists()
    assert adapter_in_use.calls == []
    assert task_log_entries(tiny_port_folder)[0]["outcome"] == "failed"


def test_build_without_a_rust_project_names_the_option(
    tiny_port_folder: Path, adapter_in_use: RecordingAdapter, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(["build", str(tiny_port_folder)])

    assert exit_code != 0
    assert "--rust-project" in capsys.readouterr().err
    assert adapter_in_use.calls == []
    assert task_log_entries(tiny_port_folder)[0]["outcome"] == "failed"


def test_build_without_the_option_builds_what_rust_backed_holds(
    tiny_port_folder: Path, adapter_in_use: RecordingAdapter
) -> None:
    rust_backed = port_folder.rust_backed_folder(tiny_port_folder)
    rust_backed.mkdir()
    (rust_backed / "pyproject.toml").write_text("[project]\n")

    assert main(["build", str(tiny_port_folder)]) == 0
    assert adapter_in_use.calls == ["build_bridge"]


def oracle_report(passed: bool) -> dict[str, Any]:
    return {
        "format_version": 1,
        "original_tests": {
            "passed": 38,
            "failed": 0,
            "errors": 0,
            "skipped": 1,
            "test_folder_diff_empty": passed,
            "missing_test_ids": ["test_inflection.py::test_lost"],
        },
        "differential": [
            {
                "call_path": "inflection.dasherize",
                "inputs_tried": 200,
                "skipped_reason": None,
                "rust_backed_is_builtin": True,
                "mismatches": [],
            },
            {
                "call_path": "inflection.camelize",
                "inputs_tried": 7,
                "skipped_reason": None,
                "rust_backed_is_builtin": False,
                "mismatches": [{"shrunk_input": "('a',)", "original": "'A'", "rust_backed": "'a'"}],
            },
        ],
        "fallback": {
            "rust_names_resolving_to_python": ["inflection.underscore"],
            "python_names_without_reason": ["inflection.singularize"],
            "left_in_python": [{"name": "inflection.pluralize", "reason": "uses regex"}],
        },
        "passed": passed,
    }


@pytest.mark.parametrize("passed", [True, False])
def test_oracle_summary_and_exit_code(
    tiny_port_folder: Path,
    adapter_in_use: RecordingAdapter,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    passed: bool,
) -> None:
    monkeypatch.setattr(command_line, "run_oracle", lambda *arguments: oracle_report(passed))

    exit_code = main(["oracle", str(tiny_port_folder)])

    lines = capsys.readouterr().out.splitlines()
    assert (exit_code == 0) == passed
    assert "original tests: passed=38 failed=0 errors=0 skipped=1" in lines
    assert "tests collected: original=40 rust_backed=39 missing=1" in lines
    assert "  original is derived: rust_backed plus missing; oracle.json holds no count" in lines
    assert "  missing: test_inflection.py::test_lost" in lines
    assert f"checkout unchanged: {'yes' if passed else 'no'}" in lines
    assert "inflection.dasherize: inputs tried=200 mismatches=0" in lines
    assert any(
        line.startswith("inflection.camelize: inputs tried=7 mismatches=1") for line in lines
    )
    assert "marked rust but resolves to Python: inflection.underscore" in lines
    assert "left in Python: inflection.pluralize (uses regex)" in lines
    assert "left in Python without a reason: inflection.singularize" in lines
    entry = task_log_entries(tiny_port_folder)[0]
    assert entry["outcome"] == ("passed" if passed else "failed")
