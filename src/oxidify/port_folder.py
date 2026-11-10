"""Paths inside a port folder. Every step finds its files through these functions."""

from pathlib import Path


def port_json_path(port: Path) -> Path:
    return port / "port.json"


def checkout_folder(port: Path) -> Path:
    """Git checkout detached at the pinned commit; read-only once the port has started."""
    return port / "checkout"


def licence_folder(port: Path) -> Path:
    return port / "licence"


def credits_path(port: Path) -> Path:
    return port / "CREDITS.md"


def original_source_folder(port: Path) -> Path:
    """`git archive` export of the pinned commit; the original is installed from here."""
    return port / "original_source"


def venv_folder(port: Path) -> Path:
    return port / ".venv"


def venv_python(port: Path) -> Path:
    return venv_folder(port) / "bin" / "python"


def analysis_folder(port: Path) -> Path:
    return port / "analysis"


def import_graph_path(port: Path) -> Path:
    return analysis_folder(port) / "import_graph.json"


def swap_order_path(port: Path) -> Path:
    return analysis_folder(port) / "swap_order.json"


def coverage_path(port: Path) -> Path:
    return analysis_folder(port) / "coverage.json"


def unsupported_path(port: Path) -> Path:
    return analysis_folder(port) / "unsupported.json"


def coverage_data_path(port: Path) -> Path:
    """coverage.py data file; passed as COVERAGE_FILE so nothing lands in the checkout."""
    return analysis_folder(port) / ".coverage"


def state_folder(port: Path) -> Path:
    return port / "state"


def coverage_map_path(port: Path) -> Path:
    return state_folder(port) / "coverage_map.json"


def checkpoints_path(port: Path) -> Path:
    return state_folder(port) / "checkpoints.json"


def task_log_path(port: Path) -> Path:
    return state_folder(port) / "task_log.json"


def rust_backed_folder(port: Path) -> Path:
    """maturin project of the Rust-backed package."""
    return port / "rust_backed"


def rust_backed_python_package_folder(port: Path, import_name: str) -> Path:
    return rust_backed_folder(port) / "python" / f"{import_name}_rs"


def wheels_folder(port: Path) -> Path:
    return rust_backed_folder(port) / "target" / "wheels"


def report_folder(port: Path) -> Path:
    return port / "report"


def oracle_report_path(port: Path) -> Path:
    return report_folder(port) / "oracle.json"


def differential_report_path(port: Path) -> Path:
    return report_folder(port) / "differential.json"


def original_tests_report_path(port: Path, against: str) -> Path:
    """JUnit XML of the original tests run against "original" or "rust_backed"."""
    if against not in ("original", "rust_backed"):
        raise ValueError(f"against must be 'original' or 'rust_backed', not {against!r}")
    return report_folder(port) / f"original_tests_{against}.xml"
