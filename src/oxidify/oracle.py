"""Decide whether the Rust-backed package behaves like the original, and write `report/oracle.json`.

This module is language-neutral: it reads the checkout through git and asks the adapter for
everything else. It is the only place that decides pass or fail.
"""

import subprocess
from pathlib import Path
from typing import Any

from oxidify import port_folder as paths
from oxidify.adapter import SourceLanguageAdapter
from oxidify.state import FORMAT_VERSION, read_state, write_state


def checkout_matches_pinned_commit(port_folder: Path, commit: str) -> bool:
    """True when the checkout is at `commit` with no tracked change and no untracked file."""
    checkout = str(paths.checkout_folder(port_folder))
    head = subprocess.run(
        ["git", "-C", checkout, "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    )
    if head.stdout.strip() != commit:
        return False
    status = subprocess.run(
        ["git", "-C", checkout, "status", "--porcelain", "--untracked-files=all"],
        capture_output=True,
        text=True,
        check=True,
    )
    return status.stdout == ""


def marked_names(coverage_map: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Coverage map entry of every public name, keyed by its dotted name."""
    names = {}
    for module, module_entry in coverage_map["modules"].items():
        for name, entry in module_entry["public_names"].items():
            names[f"{module}.{name}"] = entry
    return names


def fallback_report(
    coverage_map: dict[str, Any], python_resolving_names: list[str]
) -> dict[str, list[Any]]:
    """Sort the names that resolve to Python into those marked Rust and those left in Python."""
    entries = marked_names(coverage_map)
    rust_names_resolving_to_python = []
    python_names_without_reason = []
    left_in_python = []
    for name in python_resolving_names:
        if name not in entries:
            raise ValueError(f"the adapter returned {name!r}, which the coverage map does not hold")
        entry = entries[name]
        if entry["implementation"] == "rust":
            rust_names_resolving_to_python.append(name)
            continue
        left_in_python.append({"name": name, "reason": entry["reason"]})
        if entry["reason"].strip() == "":
            python_names_without_reason.append(name)
    return {
        "rust_names_resolving_to_python": rust_names_resolving_to_python,
        "python_names_without_reason": python_names_without_reason,
        "left_in_python": left_in_python,
    }


def original_tests_report(
    port_folder: Path, adapter: SourceLanguageAdapter, commit: str
) -> dict[str, Any]:
    """Counts of the Rust-backed run, the ids it lost and whether the checkout is unchanged."""
    original = adapter.run_original_tests(port_folder, "original")
    rust_backed = adapter.run_original_tests(port_folder, "rust_backed")
    rust_backed_ids = set(rust_backed["collected_test_ids"])
    missing_test_ids = []
    for test_id in original["collected_test_ids"]:
        if test_id not in rust_backed_ids:
            missing_test_ids.append(test_id)
    return {
        "passed": rust_backed["passed"],
        "failed": rust_backed["failed"],
        "errors": rust_backed["errors"],
        "skipped": rust_backed["skipped"],
        "test_folder_diff_empty": checkout_matches_pinned_commit(port_folder, commit),
        "missing_test_ids": missing_test_ids,
    }


def run_oracle(
    port_folder: Path, adapter: SourceLanguageAdapter, examples_per_call_path: int
) -> dict[str, Any]:
    """Run every oracle check, write `report/oracle.json` and return the report."""
    port = read_state(paths.port_json_path(port_folder), "port")
    original_tests = original_tests_report(port_folder, adapter, port["commit"])
    differential = adapter.run_differential(port_folder, examples_per_call_path)
    coverage_map = read_state(paths.coverage_map_path(port_folder), "coverage_map")
    fallback = fallback_report(
        coverage_map, adapter.names_resolving_to_source_language(port_folder)
    )

    original_tests_passed = (
        original_tests["failed"] == 0
        and original_tests["errors"] == 0
        and original_tests["test_folder_diff_empty"]
        and not original_tests["missing_test_ids"]
    )
    differential_passed = all(not entry["mismatches"] for entry in differential)
    fallback_passed = (
        not fallback["rust_names_resolving_to_python"]
        and not fallback["python_names_without_reason"]
    )
    report = {
        "format_version": FORMAT_VERSION,
        "original_tests": original_tests,
        "differential": differential,
        "fallback": fallback,
        "passed": original_tests_passed and differential_passed and fallback_passed,
    }
    write_state(paths.oracle_report_path(port_folder), "oracle_report", report)
    return report
