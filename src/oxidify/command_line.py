"""The `oxidify` command: one subcommand per port step, each over a port folder on disk."""

import argparse
import shutil
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from oxidify import port_folder as paths
from oxidify.adapter import SourceLanguageAdapter, load_adapter
from oxidify.oracle import run_oracle
from oxidify.start_port import first_missing_folder, remove_contents, start_port
from oxidify.state import (
    append_task_log_entry,
    mark_names_swapped,
    read_state,
    record_checkpoint,
)

EXAMPLES_PER_CALL_PATH = 200
MATURIN_PROJECT_FILES = ("Cargo.toml", "pyproject.toml")


def adapter_for(port: Path) -> SourceLanguageAdapter:
    adapter_entry = read_state(paths.port_json_path(port), "port")["adapter"]
    return load_adapter(adapter_entry["name"], adapter_entry["interface_version"])


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def run_logged_step(port: Path, step: str, action: Callable[[], bool]) -> int:
    """Run `action`, log the step, and record a checkpoint when it passed.

    `action` returns False for a step that ran but did not pass; it raises for one that broke.
    A folder without `port.json` is refused before anything is written, so a mistyped path
    leaves no folder behind.
    """
    if not paths.port_json_path(port).is_file():
        print(
            f"oxidify: {step} failed: {port} holds no port.json; run start first", file=sys.stderr
        )
        return 1
    started_at = now()
    try:
        passed = action()
    except Exception as error:
        print(f"oxidify: {step} failed: {error}", file=sys.stderr)
        passed = False
    append_task_log_entry(
        port,
        {
            "step": step,
            "module": None,
            "started_at": started_at,
            "finished_at": now(),
            "outcome": "passed" if passed else "failed",
            "model": None,
            "input_tokens": None,
            "output_tokens": None,
            "cost_usd": None,
        },
    )
    if not passed:
        return 1
    record_checkpoint(port, step)
    return 0


def start_command(arguments: argparse.Namespace) -> int:
    port = arguments.port
    existed_before = port.exists()
    first_created = first_missing_folder(port)
    try:
        start_port(
            arguments.url,
            arguments.commit,
            port,
            arguments.test_path,
            arguments.test_requirement,
            arguments.test_command,
        )
    except Exception as error:
        # start_port refuses a non-empty folder untouched and undoes its own failures.
        print(f"oxidify: start failed: {error}", file=sys.stderr)
        return 1
    try:
        adapter_for(port).prepare_environment(port)
    except Exception as error:
        print(f"oxidify: start failed: {error}", file=sys.stderr)
        # start_port accepted the folder, so it was missing or empty and all it holds is ours.
        remove_port_folder(port, existed_before, first_created)
        return 1
    return 0


def remove_port_folder(port: Path, existed_before: bool, first_created: Path) -> None:
    if existed_before:
        remove_contents(port)
        return
    shutil.rmtree(first_created)


def analyse_command(arguments: argparse.Namespace) -> int:
    def analyse() -> bool:
        adapter_for(arguments.port).analyse_source(arguments.port)
        return True

    return run_logged_step(arguments.port, "analyse_source", analyse)


def mark_swapped_command(arguments: argparse.Namespace) -> int:
    def mark_swapped() -> bool:
        mark_names_swapped(arguments.port, arguments.module, arguments.names)
        return True

    return run_logged_step(arguments.port, "mark_swapped", mark_swapped)


def copy_rust_project(project: Path, rust_backed: Path) -> None:
    """Copy a maturin project into `rust_backed/`, replacing its files but keeping `target/`."""
    for file_name in MATURIN_PROJECT_FILES:
        if not (project / file_name).is_file():
            raise ValueError(f"{project} is not a maturin project: it has no {file_name}")
    # Deleted first so a source file removed from the project is not left behind.
    shutil.rmtree(rust_backed / "src", ignore_errors=True)
    shutil.copytree(project, rust_backed, ignore=skip_top_level_target(project), dirs_exist_ok=True)


def skip_top_level_target(project: Path) -> Callable[[str, list[str]], set[str]]:
    """An `ignore` for `copytree` that skips cargo's `target/` in the project root only."""

    def ignore(folder: str, names: list[str]) -> set[str]:
        if Path(folder) == project and "target" in names:
            return {"target"}
        return set()

    return ignore


def build_command(arguments: argparse.Namespace) -> int:
    port = arguments.port

    def build() -> bool:
        adapter = adapter_for(port)
        rust_backed = paths.rust_backed_folder(port)
        if arguments.rust_project is not None:
            copy_rust_project(arguments.rust_project, rust_backed)
        if not (rust_backed / "pyproject.toml").is_file():
            raise ValueError(
                f"{rust_backed} holds no pyproject.toml: pass --rust-project <folder> "
                f"to copy a maturin project there"
            )
        adapter.build_bridge(port)
        return True

    return run_logged_step(port, "build_bridge", build)


def print_oracle_summary(report: dict[str, Any]) -> None:
    tests = report["original_tests"]
    missing = tests["missing_test_ids"]
    # The report holds the Rust-backed counts and the lost ids; the original's total is their sum.
    rust_backed_collected = tests["passed"] + tests["failed"] + tests["errors"] + tests["skipped"]
    print(
        f"original tests: passed={tests['passed']} failed={tests['failed']} "
        f"errors={tests['errors']} skipped={tests['skipped']}"
    )
    print(
        f"tests collected: original={rust_backed_collected + len(missing)} "
        f"rust_backed={rust_backed_collected} missing={len(missing)}"
    )
    print("  original is derived: rust_backed plus missing; oracle.json holds no count")
    for test_id in missing:
        print(f"  missing: {test_id}")
    print(f"checkout unchanged: {'yes' if tests['test_folder_diff_empty'] else 'no'}")
    for entry in report["differential"]:
        mismatches = entry["mismatches"]
        line = (
            f"{entry['call_path']}: inputs tried={entry['inputs_tried']} "
            f"mismatches={len(mismatches)}"
        )
        if entry["skipped_reason"] is not None:
            line += f" (skipped: {entry['skipped_reason']})"
        print(line)
        for mismatch in mismatches:
            print(
                f"  input {mismatch['shrunk_input']}: original {mismatch['original']}, "
                f"rust_backed {mismatch['rust_backed']}"
            )
    fallback = report["fallback"]
    for name in fallback["rust_names_resolving_to_python"]:
        print(f"marked rust but resolves to Python: {name}")
    for entry in fallback["left_in_python"]:
        print(f"left in Python: {entry['name']} ({entry['reason']})")
    for name in fallback["python_names_without_reason"]:
        print(f"left in Python without a reason: {name}")
    print(f"oracle {'passed' if report['passed'] else 'failed'}")


def oracle_command(arguments: argparse.Namespace) -> int:
    port = arguments.port

    def check() -> bool:
        report = run_oracle(port, adapter_for(port), arguments.examples)
        print_oracle_summary(report)
        return report["passed"]

    return run_logged_step(port, "oracle", check)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oxidify", description="Port a Python package to Rust behind PyO3."
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    start = subcommands.add_parser("start", help="clone a repository at a commit and set up a port")
    start.add_argument("url")
    start.add_argument("commit")
    start.add_argument("port", type=Path)
    start.add_argument(
        "--test-path", action="append", default=None, help="test file or folder; repeatable"
    )
    start.add_argument(
        "--test-requirement", action="append", default=None, help="package the tests need"
    )
    start.add_argument("--test-command", nargs="+", default=["python", "-m", "pytest"])
    start.set_defaults(run=start_command)

    analyse = subcommands.add_parser(
        "analyse", help="analyse the source and write the coverage map"
    )
    analyse.add_argument("port", type=Path)
    analyse.set_defaults(run=analyse_command)

    mark_swapped = subcommands.add_parser("mark-swapped", help="mark public names as Rust")
    mark_swapped.add_argument("port", type=Path)
    mark_swapped.add_argument("module")
    mark_swapped.add_argument("names", nargs="+")
    mark_swapped.set_defaults(run=mark_swapped_command)

    build = subcommands.add_parser("build", help="build the Rust-backed package")
    build.add_argument("port", type=Path)
    build.add_argument("--rust-project", type=Path, help="maturin project to copy in first")
    build.set_defaults(run=build_command)

    oracle = subcommands.add_parser(
        "oracle", help="check the Rust-backed package against the original"
    )
    oracle.add_argument("port", type=Path)
    oracle.add_argument("--examples", type=int, default=EXAMPLES_PER_CALL_PATH)
    oracle.set_defaults(run=oracle_command)
    return parser


def main(arguments: list[str]) -> int:
    parsed = build_parser().parse_args(arguments)
    if parsed.command == "start":
        parsed.test_path = parsed.test_path or ["tests"]
        parsed.test_requirement = parsed.test_requirement or ["pytest"]
    return parsed.run(parsed)
