import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from oxidify import port_folder, state
from oxidify.python_adapter.environment import prepare_environment

TINY_PACKAGE_FOLDER = Path(__file__).parent / "fixtures" / "tiny_package"
INFLECTION_URL = "https://github.com/jpvanhal/inflection.git"
INFLECTION_COMMIT = "b00d4d348b32ef5823221b20ee4cbd1d2d924462"
# Fixed identity and no signing, so commits do not depend on the developer's git config.
GIT_IDENTITY = [
    "-c",
    "user.name=Oxidify Tests",
    "-c",
    "user.email=tests@oxidify.invalid",
    "-c",
    "commit.gpgsign=false",
]


def run_git(*arguments: str) -> str:
    result = subprocess.run(
        ["git", *GIT_IDENTITY, *arguments], capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def clone_at_commit(source: str, commit: str, checkout: Path) -> None:
    run_git("clone", "--quiet", source, str(checkout))
    run_git("-C", str(checkout), "checkout", "--quiet", "--detach", commit)


def write_port_json(port: Path, **fields: object) -> None:
    data = {
        "format_version": 1,
        "adapter": {"name": "python", "interface_version": 1},
        "test_command": ["python", "-m", "pytest"],
        "test_requirements": ["pytest"],
    }
    data.update(fields)
    state.write_state(port_folder.port_json_path(port), "port", data)


@pytest.fixture(scope="session", autouse=True)
def shared_cargo_target_folder(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """Every maturin build in the session reuses one target folder and its compiled crates."""
    target = tmp_path_factory.mktemp("cargo_target")
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("CARGO_TARGET_DIR", str(target))
        yield target


@pytest.fixture
def tiny_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "tiny_repository"
    shutil.copytree(TINY_PACKAGE_FOLDER, repository)
    run_git("-C", str(repository), "init", "--quiet")
    run_git("-C", str(repository), "add", ".")
    run_git("-C", str(repository), "commit", "--quiet", "-m", "tiny package")
    return repository


@pytest.fixture
def tiny_port_folder(tmp_path: Path, tiny_repository: Path) -> Path:
    port = tmp_path / "tiny_port"
    commit = run_git("-C", str(tiny_repository), "rev-parse", "HEAD")
    clone_at_commit(str(tiny_repository), commit, port_folder.checkout_folder(port))
    write_port_json(
        port,
        source_url=str(tiny_repository),
        commit=commit,
        test_paths=["tests"],
        import_names=["tiny_package"],
    )
    return port


@pytest.fixture
def tiny_port_with_environment(tiny_port_folder: Path) -> Path:
    prepare_environment(tiny_port_folder)
    return tiny_port_folder


@pytest.fixture(scope="session")
def inflection_port_folder(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Read-only: tests work on `inflection_port_copy`, never on this folder."""
    port = tmp_path_factory.mktemp("inflection_port")
    checkout = port_folder.checkout_folder(port)
    clone_at_commit(INFLECTION_URL, INFLECTION_COMMIT, checkout)
    assert run_git("-C", str(checkout), "rev-parse", "HEAD") == INFLECTION_COMMIT
    write_port_json(
        port,
        source_url=INFLECTION_URL,
        commit=INFLECTION_COMMIT,
        test_paths=["test_inflection.py"],
        import_names=["inflection"],
    )
    return port


@pytest.fixture
def inflection_port_copy(tmp_path: Path, inflection_port_folder: Path) -> Path:
    copy = tmp_path / "inflection_port"
    shutil.copytree(inflection_port_folder, copy, symlinks=True)
    return copy


@pytest.fixture
def inflection_port_with_environment(inflection_port_copy: Path) -> Path:
    prepare_environment(inflection_port_copy)
    return inflection_port_copy
