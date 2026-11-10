import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from oxidify import port_folder, state
from oxidify.python_adapter.bridge import build_bridge
from oxidify.python_adapter.fallback_check import names_resolving_to_source_language
from oxidify.python_adapter.original_tests import (
    OriginalTestsFailedToRun,
    counts_from_junit_xml,
    ids_from_collect_output,
    run_original_tests,
    run_pytest,
)

HAND_SWAP_PROJECT = Path(__file__).parents[1] / "examples" / "inflection_hand_swap"
INFLECTION_PUBLIC_NAMES = [
    "PLURALS",
    "SINGULARS",
    "UNCOUNTABLES",
    "camelize",
    "dasherize",
    "humanize",
    "ordinal",
    "ordinalize",
    "parameterize",
    "pluralize",
    "singularize",
    "tableize",
    "titleize",
    "transliterate",
    "underscore",
]
# Written by pytest 9.2 for a file with one passing, failing, skipped and erroring test.
JUNIT_XML_WITH_EACH_OUTCOME = """\
<?xml version="1.0" encoding="utf-8"?><testsuites name="pytest tests"><testsuite name="pytest" \
errors="1" failures="1" skipped="1" tests="4" time="0.107" \
timestamp="2026-11-10T16:09:04.296190+05:30" hostname="host">\
<testcase classname="test_outcomes" name="test_passes" time="0.001" />\
<testcase classname="test_outcomes" name="test_fails" time="0.005">\
<failure message="assert 1 == 2">E   assert 1 == 2</failure></testcase>\
<testcase classname="test_outcomes" name="test_skipped" time="0.001">\
<skipped type="pytest.skip" message="not here">test_outcomes.py:7: not here</skipped></testcase>\
<testcase classname="test_outcomes" name="test_errors" time="0.006">\
<error message="failed on setup with &quot;RuntimeError: setup broke&quot;">\
E       RuntimeError: setup broke</error></testcase></testsuite></testsuites>
"""


def hand_swap_dasherize(port: Path) -> None:
    """Mark `dasherize` as Rust in a fresh coverage map and copy in the Rust project for it."""
    coverage_map = state.new_coverage_map({"inflection": INFLECTION_PUBLIC_NAMES})
    state.write_state(port_folder.coverage_map_path(port), "coverage_map", coverage_map)
    state.mark_names_swapped(port, "inflection", ["dasherize"])
    rust_backed = port_folder.rust_backed_folder(port)
    rust_backed.mkdir()
    for file_name in ["Cargo.toml", "Cargo.lock", "pyproject.toml"]:
        shutil.copy(HAND_SWAP_PROJECT / file_name, rust_backed / file_name)
    shutil.copytree(HAND_SWAP_PROJECT / "src", rust_backed / "src")


def checkout_status(port: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(port_folder.checkout_folder(port)), "status", "--porcelain", "--ignored"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def test_counts_parsed_from_junit_xml(tmp_path: Path) -> None:
    report = tmp_path / "report.xml"
    report.write_text(JUNIT_XML_WITH_EACH_OUTCOME)

    counts = counts_from_junit_xml(report)

    assert counts == {"passed": 1, "failed": 1, "errors": 1, "skipped": 1}


def test_collected_ids_use_original_import_name() -> None:
    output = (
        "inflection/__init__.py::inflection_rs.dasherize\n"
        "inflection/__init__.py::inflection_rs\n"
        "test_inflection.py::test_dasherize[inflection_rs_word-inflection_rs-word]\n"
        "test_inflection.py::test_inflection_rs_helper\n"
        "\n"
        "=============================== warnings summary ===============================\n"
        "test_inflection.py::test_inflection_rs_helper\n"
        "  DeprecationWarning: old\n"
        "\n"
        "4 tests collected in 0.05s\n"
    )

    ids = ids_from_collect_output(output, ["inflection"])

    assert ids == [
        "inflection/__init__.py::inflection.dasherize",
        "inflection/__init__.py::inflection",
        "test_inflection.py::test_dasherize[inflection_rs_word-inflection_rs-word]",
        "test_inflection.py::test_inflection_rs_helper",
    ]


def test_collect_output_without_ids_gives_no_ids() -> None:
    assert ids_from_collect_output("no tests collected in 0.01s\n", ["inflection"]) == []


def test_usage_error_raises(tmp_path: Path) -> None:
    arguments = [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "--no-such-option"]

    with pytest.raises(OriginalTestsFailedToRun, match="exited 4"):
        run_pytest(arguments, tmp_path, dict(os.environ))


@pytest.mark.end_to_end
def test_counts_against_rust_backed(inflection_port_with_environment: Path) -> None:
    port = inflection_port_with_environment
    hand_swap_dasherize(port)
    build_bridge(port)

    result = run_original_tests(port, "rust_backed")

    print(
        f"passed {result['passed']}, failed {result['failed']}, errors {result['errors']}, "
        f"skipped {result['skipped']}, collected ids {len(result['collected_test_ids'])}"
    )
    assert result["failed"] == 0
    assert result["errors"] == 0
    assert result["passed"] + result["skipped"] == len(result["collected_test_ids"])
    assert "inflection/__init__.py::inflection.dasherize" in result["collected_test_ids"]
    assert port_folder.original_tests_report_path(port, "rust_backed").is_file()


@pytest.mark.end_to_end
def test_rust_backed_run_uses_the_rust_function(inflection_port_with_environment: Path) -> None:
    port = inflection_port_with_environment
    hand_swap_dasherize(port)
    build_bridge(port)
    # A Rust function that dasherizes nothing must make the original dasherize tests fail.
    rust_source = port_folder.rust_backed_folder(port) / "src" / "lib.rs"
    rust_source.write_text(
        rust_source.read_text().replace("if byte == b'_' { b'-' }", "if byte == b'_' { b'_' }")
    )
    build_bridge(port)

    result = run_original_tests(port, "rust_backed")

    assert result["failed"] > 0


@pytest.mark.end_to_end
def test_no_test_lost_after_swap(inflection_port_with_environment: Path) -> None:
    port = inflection_port_with_environment
    hand_swap_dasherize(port)
    build_bridge(port)

    original = run_original_tests(port, "original")
    rust_backed = run_original_tests(port, "rust_backed")

    print(
        f"collected against the original: {len(original['collected_test_ids'])}, "
        f"against the Rust-backed build: {len(rust_backed['collected_test_ids'])}"
    )
    assert len(original["collected_test_ids"]) == 467
    assert rust_backed["collected_test_ids"] == original["collected_test_ids"]
    assert "inflection/__init__.py::inflection.dasherize" in rust_backed["collected_test_ids"]


@pytest.mark.end_to_end
def test_checkout_clean_after_test_runs(inflection_port_with_environment: Path) -> None:
    port = inflection_port_with_environment
    hand_swap_dasherize(port)

    build_bridge(port)
    run_original_tests(port, "original")
    run_original_tests(port, "rust_backed")
    names_resolving_to_source_language(port)

    assert checkout_status(port) == ""
