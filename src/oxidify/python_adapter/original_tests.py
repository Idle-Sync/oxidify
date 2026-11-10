"""Run the original's unchanged tests against the original or the Rust-backed package."""

import os
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from typing import Any, Literal

from oxidify import port_folder as paths
from oxidify.state import read_state

ALIAS_PLUGIN = Path(__file__).parent / "alias_plugin.py"
ALIAS_PLUGIN_MODULE = "oxidify_alias_plugin"
# pytest exit codes for an internal error and a usage error: no test result exists then.
PYTEST_INTERNAL_ERROR = 3
PYTEST_USAGE_ERROR = 4


class OriginalTestsFailedToRun(Exception):
    """The test command could not run the tests at all."""


def counts_from_junit_xml(report: Path) -> dict[str, int]:
    """`passed`, `failed`, `errors` and `skipped` summed over the test suites of a JUnit report."""
    counts = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    for suite in ElementTree.parse(report).getroot().iter("testsuite"):
        failed = int(suite.get("failures", "0"))
        errors = int(suite.get("errors", "0"))
        skipped = int(suite.get("skipped", "0"))
        # JUnit stores no passed count; it is what is left of the total.
        counts["passed"] += int(suite.get("tests", "0")) - failed - errors - skipped
        counts["failed"] += failed
        counts["errors"] += errors
        counts["skipped"] += skipped
    return counts


def with_original_import_names(test_id: str, import_names: list[str]) -> str:
    """`test_id` with each `<import name>_rs` written as the import name.

    Only the part before any `[` is rewritten: test parameters are the test's own data.
    """
    name_part, bracket, parameters = test_id.partition("[")
    for import_name in import_names:
        name_part = re.sub(rf"\b{re.escape(import_name)}_rs\b", import_name, name_part)
    return name_part + bracket + parameters


def ids_from_collect_output(output: str, import_names: list[str]) -> list[str]:
    """Test ids listed by `pytest --collect-only -q`, which ends its list with a blank line."""
    ids = []
    for line in output.splitlines():
        if line.strip() == "":
            break
        if "::" not in line:
            continue
        ids.append(with_original_import_names(line.strip(), import_names))
    return ids


def run_pytest(arguments: list[str], checkout: Path, environment: dict[str, str]) -> str:
    """Run the test command in the checkout and return its output; refuse a run with no result."""
    result = subprocess.run(
        arguments, cwd=checkout, env=environment, capture_output=True, text=True
    )
    if result.returncode in (PYTEST_INTERNAL_ERROR, PYTEST_USAGE_ERROR):
        raise OriginalTestsFailedToRun(
            f"{' '.join(arguments)} exited {result.returncode}: "
            f"{result.stderr.strip()} {result.stdout.strip()}"
        )
    return result.stdout


def pytest_arguments(port_folder: Path, port: dict[str, Any]) -> list[str]:
    """The port's test command with the port interpreter in place of `python`.

    The cache provider is off so pytest writes no `.pytest_cache` into the checkout.
    """
    command = list(port["test_command"])
    if command[0] == "python":
        command[0] = str(paths.venv_python(port_folder))
    return [*command, "-p", "no:cacheprovider"]


def child_environment(plugin_folder: Path | None, import_names: list[str]) -> dict[str, str]:
    """Environment of the test run: no bytecode files, and the alias plugin when one is given."""
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    if plugin_folder is not None:
        environment["PYTHONPATH"] = str(plugin_folder)
        environment["OXIDIFY_ALIASED_IMPORT_NAMES"] = " ".join(import_names)
    return environment


def run_tests_and_count(
    port_folder: Path,
    against: Literal["original", "rust_backed"],
    arguments: list[str],
    environment: dict[str, str],
    import_names: list[str],
) -> dict[str, Any]:
    """Collect the test ids, then run the tests with a JUnit report under `report/`."""
    checkout = paths.checkout_folder(port_folder)
    collect_output = run_pytest([*arguments, "--collect-only", "-q"], checkout, environment)
    report = paths.original_tests_report_path(port_folder, against)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.unlink(missing_ok=True)
    run_pytest([*arguments, f"--junit-xml={report}"], checkout, environment)
    if not report.is_file():
        raise OriginalTestsFailedToRun(f"{' '.join(arguments)} wrote no JUnit report to {report}")
    result: dict[str, Any] = counts_from_junit_xml(report)
    # Sorted because parameters taken from a set come in a different order in every process.
    result["collected_test_ids"] = sorted(ids_from_collect_output(collect_output, import_names))
    return result


def run_original_tests(
    port_folder: Path, against: Literal["original", "rust_backed"]
) -> dict[str, Any]:
    """Counts `{passed, failed, errors, skipped, collected_test_ids}` from the JUnit XML report.

    Against `rust_backed`, `import <name>` gives `<name>_rs` through the alias plugin.
    """
    port = read_state(paths.port_json_path(port_folder), "port")
    arguments = pytest_arguments(port_folder, port)
    import_names = port["import_names"]
    if against == "original":
        environment = child_environment(None, import_names)
        return run_tests_and_count(port_folder, against, arguments, environment, import_names)
    with tempfile.TemporaryDirectory() as plugin_folder:
        shutil.copy(ALIAS_PLUGIN, Path(plugin_folder) / f"{ALIAS_PLUGIN_MODULE}.py")
        environment = child_environment(Path(plugin_folder), import_names)
        arguments = [*arguments, "-p", ALIAS_PLUGIN_MODULE]
        return run_tests_and_count(port_folder, against, arguments, environment, import_names)
