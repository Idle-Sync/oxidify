import json
import subprocess
from pathlib import Path

import pytest

from oxidify import port_folder, state
from oxidify.adapter import load_adapter
from oxidify.python_adapter.environment import EnvironmentSetupFailed, prepare_environment

# Fixed identity and no signing, so the commit does not depend on the developer's git config.
GIT_IDENTITY = [
    "-c",
    "user.name=Oxidify Tests",
    "-c",
    "user.email=tests@oxidify.invalid",
    "-c",
    "commit.gpgsign=false",
]


def run_in_port_environment(port: Path, code: str) -> str:
    result = subprocess.run(
        [str(port_folder.venv_python(port)), "-c", code],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def checkout_status(port: Path) -> str:
    # --ignored as well: a build/ or *.egg-info the target ignores would still be a write.
    result = subprocess.run(
        ["git", "-C", str(port_folder.checkout_folder(port)), "status", "--porcelain", "--ignored"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def test_port_environment_imports(tiny_port_with_environment: Path) -> None:
    port = tiny_port_with_environment

    run_in_port_environment(port, "import tiny_package, pytest, coverage, grimp, hypothesis")

    imported_from = run_in_port_environment(
        port, "import tiny_package; print(tiny_package.__file__)"
    )
    assert Path(imported_from).is_relative_to(port_folder.venv_folder(port))


def test_original_is_exported_from_the_pinned_commit(tiny_port_with_environment: Path) -> None:
    port = tiny_port_with_environment
    original_source = port_folder.original_source_folder(port)

    assert (original_source / "pyproject.toml").is_file()
    assert (original_source / "tiny_package" / "words.py").is_file()
    assert not (original_source / ".git").exists()


def test_original_is_installed_from_original_source(tiny_port_with_environment: Path) -> None:
    port = tiny_port_with_environment

    direct_url = run_in_port_environment(
        port,
        "import importlib.metadata as metadata; "
        "print(metadata.distribution('tiny-package').read_text('direct_url.json'))",
    )

    assert json.loads(direct_url)["url"] == port_folder.original_source_folder(port).as_uri()


def test_checkout_clean_after_prepare(tiny_port_with_environment: Path) -> None:
    assert checkout_status(tiny_port_with_environment) == ""


def test_export_follows_the_pinned_commit_not_the_checkout(tiny_port_folder: Path) -> None:
    checkout = port_folder.checkout_folder(tiny_port_folder)
    (checkout / "tiny_package" / "words.py").write_text("raise RuntimeError('edited checkout')\n")
    commit = ["commit", "--quiet", "--all", "-m", "move HEAD off the pin"]
    subprocess.run(["git", "-C", str(checkout), *GIT_IDENTITY, *commit], check=True)

    prepare_environment(tiny_port_folder)

    exported = port_folder.original_source_folder(tiny_port_folder) / "tiny_package" / "words.py"
    assert "edited checkout" not in exported.read_text()


def test_prepare_twice_replaces_the_previous_export(tiny_port_with_environment: Path) -> None:
    port = tiny_port_with_environment
    leftover = port_folder.original_source_folder(port) / "leftover.txt"
    leftover.write_text("from an earlier run\n")

    prepare_environment(port)

    assert not leftover.exists()
    run_in_port_environment(port, "import tiny_package")


def test_import_name_the_install_does_not_provide_fails(tiny_port_folder: Path) -> None:
    port_json_path = port_folder.port_json_path(tiny_port_folder)
    port = state.read_state(port_json_path, "port")
    port["import_names"] = ["tiny_package", "not_installed_anywhere"]
    state.write_state(port_json_path, "port", port)

    with pytest.raises(EnvironmentSetupFailed, match="not_installed_anywhere"):
        prepare_environment(tiny_port_folder)


def test_test_requirements_are_installed(tiny_port_folder: Path) -> None:
    port_json_path = port_folder.port_json_path(tiny_port_folder)
    port = state.read_state(port_json_path, "port")
    port["test_requirements"] = ["pytest", "six"]
    state.write_state(port_json_path, "port", port)

    prepare_environment(tiny_port_folder)

    run_in_port_environment(tiny_port_folder, "import six")


def test_python_adapter_prepares_the_environment(tiny_port_folder: Path) -> None:
    load_adapter("python", 1).prepare_environment(tiny_port_folder)

    run_in_port_environment(tiny_port_folder, "import tiny_package")


@pytest.mark.end_to_end
def test_inflection_checkout_clean_after_prepare(inflection_port_with_environment: Path) -> None:
    port = inflection_port_with_environment

    run_in_port_environment(port, "import inflection, pytest, coverage, grimp, hypothesis")
    assert checkout_status(port) == ""


@pytest.mark.end_to_end
def test_inflection_copy_is_isolated(
    tmp_path: Path, inflection_port_folder: Path, inflection_port_copy: Path
) -> None:
    assert inflection_port_copy.parent == tmp_path
    written = port_folder.checkout_folder(inflection_port_copy) / "written_by_test.txt"
    written.write_text("only in the copy\n")
    port_folder.port_json_path(inflection_port_copy).write_text("{}\n")

    assert checkout_status(inflection_port_folder) == ""
    assert not (
        port_folder.checkout_folder(inflection_port_folder) / "written_by_test.txt"
    ).exists()
    port = state.read_state(port_folder.port_json_path(inflection_port_folder), "port")
    assert port["import_names"] == ["inflection"]
