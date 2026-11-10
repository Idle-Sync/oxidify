import json
import subprocess
from pathlib import Path
from typing import Any, Literal

import pytest

from oxidify import port_folder, state
from oxidify.oracle import run_oracle

TEST_IDS = ["tests/test_tiny_package.py::test_shout", "tests/test_tiny_package.py::test_count"]
COUNT_WORDS_REASON = "kept in Python until the counting module is ported"


class FakeAdapter:
    """Adapter whose answers each test sets; it records which test runs were asked for."""

    name = "fake"
    interface_version = 1

    def __init__(self) -> None:
        self.test_results: dict[str, dict[str, Any]] = {
            "original": {
                "passed": 2,
                "failed": 0,
                "errors": 0,
                "skipped": 0,
                "collected_test_ids": list(TEST_IDS),
            },
            "rust_backed": {
                "passed": 2,
                "failed": 0,
                "errors": 0,
                "skipped": 0,
                "collected_test_ids": list(TEST_IDS),
            },
        }
        self.differential: list[dict[str, Any]] = [
            {
                "call_path": "tiny_package.shout",
                "inputs_tried": 100,
                "skipped_reason": None,
                "rust_backed_is_builtin": True,
                "mismatches": [],
            }
        ]
        self.python_names = ["tiny_package.count_words"]
        self.test_runs_asked_for: list[str] = []

    def prepare_environment(self, port_folder: Path) -> None:
        raise NotImplementedError("the oracle does not prepare environments")

    def analyse_source(self, port_folder: Path) -> None:
        raise NotImplementedError("the oracle does not analyse source")

    def build_bridge(self, port_folder: Path) -> None:
        raise NotImplementedError("the oracle does not build")

    def run_original_tests(
        self, port_folder: Path, against: Literal["original", "rust_backed"]
    ) -> dict[str, Any]:
        self.test_runs_asked_for.append(against)
        return self.test_results[against]

    def run_differential(
        self, port_folder: Path, examples_per_call_path: int
    ) -> list[dict[str, Any]]:
        return self.differential

    def names_resolving_to_source_language(self, port_folder: Path) -> list[str]:
        return self.python_names


@pytest.fixture
def port(tiny_port_folder: Path) -> Path:
    """Tiny port with `shout` in Rust and `count_words` left in Python with a reason."""
    coverage_map = state.new_coverage_map({"tiny_package": ["count_words", "shout"]})
    coverage_map["modules"]["tiny_package"]["public_names"]["count_words"]["reason"] = (
        COUNT_WORDS_REASON
    )
    state.write_state(port_folder.coverage_map_path(tiny_port_folder), "coverage_map", coverage_map)
    state.mark_names_swapped(tiny_port_folder, "tiny_package", ["shout"])
    return tiny_port_folder


def test_passes_when_every_check_passes(port: Path) -> None:
    adapter = FakeAdapter()

    report = run_oracle(port, adapter, examples_per_call_path=100)

    assert report["passed"] is True
    assert adapter.test_runs_asked_for == ["original", "rust_backed"]
    assert report["original_tests"] == {
        "passed": 2,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "test_folder_diff_empty": True,
        "missing_test_ids": [],
    }
    assert report["differential"] == adapter.differential
    assert report["fallback"] == {
        "rust_names_resolving_to_python": [],
        "python_names_without_reason": [],
        "left_in_python": [{"name": "tiny_package.count_words", "reason": COUNT_WORDS_REASON}],
    }
    assert state.read_state(port_folder.oracle_report_path(port), "oracle_report") == report


@pytest.mark.parametrize("outcome", ["failed", "errors"])
def test_failing_test_fails_the_oracle(port: Path, outcome: str) -> None:
    adapter = FakeAdapter()
    adapter.test_results["rust_backed"]["passed"] = 1
    adapter.test_results["rust_backed"][outcome] = 1

    report = run_oracle(port, adapter, examples_per_call_path=100)

    assert report["original_tests"][outcome] == 1
    assert report["original_tests"]["passed"] == 1
    assert report["passed"] is False


def test_counts_not_adding_up_to_the_collected_ids_fail_the_oracle(port: Path) -> None:
    adapter = FakeAdapter()
    adapter.test_results["rust_backed"]["passed"] = 1

    report = run_oracle(port, adapter, examples_per_call_path=100)

    assert report["passed"] is False


def test_more_skipped_than_the_original_fails_the_oracle(port: Path) -> None:
    adapter = FakeAdapter()
    adapter.test_results["rust_backed"]["passed"] = 0
    adapter.test_results["rust_backed"]["skipped"] = 2

    report = run_oracle(port, adapter, examples_per_call_path=100)

    assert report["original_tests"]["skipped"] == 2
    assert report["passed"] is False


def test_lost_test_id_fails_the_oracle(port: Path) -> None:
    adapter = FakeAdapter()
    adapter.test_results["rust_backed"]["passed"] = 1
    adapter.test_results["rust_backed"]["collected_test_ids"] = TEST_IDS[:1]

    report = run_oracle(port, adapter, examples_per_call_path=100)

    assert report["original_tests"]["missing_test_ids"] == TEST_IDS[1:]
    assert report["passed"] is False


@pytest.mark.parametrize(
    "change", ["tracked file edited", "untracked file added", "ignored file added"]
)
def test_changed_checkout_fails_the_oracle(port: Path, change: str) -> None:
    checkout = port_folder.checkout_folder(port)
    if change == "tracked file edited":
        test_file = checkout / "tests" / "test_tiny_package.py"
        test_file.write_text(test_file.read_text() + "\n# edited\n")
    elif change == "untracked file added":
        (checkout / "tests" / "test_extra.py").write_text("def test_extra():\n    pass\n")
    else:
        # A file the checkout ignores can still change the run, as a conftest.py or .pth can.
        (checkout / ".git" / "info" / "exclude").write_text("conftest.py\n")
        (checkout / "conftest.py").write_text("collect_ignore = ['tests']\n")

    report = run_oracle(port, FakeAdapter(), examples_per_call_path=100)

    assert report["original_tests"]["test_folder_diff_empty"] is False
    assert report["passed"] is False


def test_checkout_at_another_commit_fails_the_oracle(port: Path) -> None:
    checkout = str(port_folder.checkout_folder(port))
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Oxidify Tests",
            "-c",
            "user.email=tests@oxidify.invalid",
            "-c",
            "commit.gpgsign=false",
            "-C",
            checkout,
            "commit",
            "--quiet",
            "--allow-empty",
            "-m",
            "moved",
        ],
        check=True,
    )

    report = run_oracle(port, FakeAdapter(), examples_per_call_path=100)

    assert report["original_tests"]["test_folder_diff_empty"] is False
    assert report["passed"] is False


def test_mismatch_fails_the_oracle(port: Path) -> None:
    adapter = FakeAdapter()
    adapter.differential[0]["mismatches"] = [
        {"shrunk_input": "('a',)", "original": "'A'", "rust_backed": "'a'"}
    ]

    report = run_oracle(port, adapter, examples_per_call_path=100)

    assert report["differential"][0]["mismatches"] == adapter.differential[0]["mismatches"]
    assert report["passed"] is False


def test_rust_name_resolving_to_python_fails_the_oracle(port: Path) -> None:
    adapter = FakeAdapter()
    adapter.python_names = ["tiny_package.count_words", "tiny_package.shout"]

    report = run_oracle(port, adapter, examples_per_call_path=100)

    assert report["fallback"]["rust_names_resolving_to_python"] == ["tiny_package.shout"]
    assert report["passed"] is False


def test_python_name_without_reason_fails_the_oracle(port: Path) -> None:
    coverage_map_path = port_folder.coverage_map_path(port)
    coverage_map = json.loads(coverage_map_path.read_text())
    coverage_map["modules"]["tiny_package"]["public_names"]["count_words"]["reason"] = ""
    state.write_state(coverage_map_path, "coverage_map", coverage_map)

    report = run_oracle(port, FakeAdapter(), examples_per_call_path=100)

    assert report["fallback"]["python_names_without_reason"] == ["tiny_package.count_words"]
    assert report["fallback"]["left_in_python"] == [
        {"name": "tiny_package.count_words", "reason": ""}
    ]
    assert report["passed"] is False


def test_name_the_coverage_map_does_not_hold_is_refused(port: Path) -> None:
    adapter = FakeAdapter()
    adapter.python_names = ["tiny_package.not_public"]

    with pytest.raises(ValueError, match="tiny_package.not_public"):
        run_oracle(port, adapter, examples_per_call_path=100)
