import shutil
from pathlib import Path

import pytest

from oxidify import port_folder, state
from oxidify.start_port import StartFailed, start_port
from conftest import run_git

TEST_COMMAND = ["python", "-m", "pytest"]


def commit_file(repository: Path, name: str, content: bytes, message: str) -> str:
    (repository / name).write_bytes(content)
    run_git("-C", str(repository), "add", name)
    run_git("-C", str(repository), "commit", "--quiet", "-m", message)
    return run_git("-C", str(repository), "rev-parse", "HEAD")


@pytest.fixture
def licensed_repository(tiny_repository: Path) -> Path:
    commit_file(tiny_repository, "LICENSE", b"MIT licence text\r\nsecond line\n", "add licence")
    commit_file(tiny_repository, "NOTICE.txt", b"notice\n", "add notice")
    commit_file(tiny_repository, "AUTHORS.rst", b"Ada\n", "add authors")
    return tiny_repository


def head_of(repository: Path) -> str:
    return run_git("-C", str(repository), "rev-parse", "HEAD")


def start(repository: Path, port: Path, commit: str | None = None) -> None:
    start_port(
        str(repository),
        commit or head_of(repository),
        port,
        ["tests"],
        ["pytest"],
        TEST_COMMAND,
    )


def test_checkout_is_at_pinned_commit(licensed_repository: Path, tmp_path: Path) -> None:
    pinned = head_of(licensed_repository)
    commit_file(licensed_repository, "later.txt", b"after the pin\n", "later commit")
    port = tmp_path / "port"

    start(licensed_repository, port, pinned)

    checkout = str(port_folder.checkout_folder(port))
    assert run_git("-C", checkout, "rev-parse", "HEAD") == pinned
    assert run_git("-C", checkout, "status", "--porcelain") == ""
    saved = state.read_state(port_folder.port_json_path(port), "port")
    assert saved["commit"] == pinned
    assert len(saved["commit"]) == 40
    assert saved["source_url"] == str(licensed_repository)
    assert saved["test_paths"] == ["tests"]
    assert saved["test_requirements"] == ["pytest"]
    assert saved["test_command"] == TEST_COMMAND
    assert saved["import_names"] == ["tiny_package"]
    assert saved["adapter"] == {"name": "python", "interface_version": 1}


def test_licence_and_credits_copied(licensed_repository: Path, tmp_path: Path) -> None:
    commit_file(licensed_repository, "LICENCE-extra", b"\x00\xffbinary\n", "extra licence")
    run_git(
        "-C",
        str(licensed_repository),
        "-c",
        "user.name=Grace Hopper",
        "-c",
        "user.email=grace@example.invalid",
        "commit",
        "--quiet",
        "--allow-empty",
        "-m",
        "empty commit by a second author",
    )
    port = tmp_path / "port"

    start(licensed_repository, port)

    for name in ["LICENSE", "LICENCE-extra", "NOTICE.txt", "AUTHORS.rst"]:
        original = (licensed_repository / name).read_bytes()
        assert (port_folder.licence_folder(port) / name).read_bytes() == original
    credits = port_folder.credits_path(port).read_text()
    assert str(licensed_repository) in credits
    assert head_of(licensed_repository) in credits
    for name in ["LICENSE", "LICENCE-extra", "NOTICE.txt"]:
        assert name in credits
    assert "Oxidify Tests" in credits
    assert "Grace Hopper" in credits


def test_refuses_commit_that_does_not_exist(licensed_repository: Path, tmp_path: Path) -> None:
    port = tmp_path / "port"

    with pytest.raises(StartFailed, match="no commit"):
        start(licensed_repository, port, "0123456789abcdef0123456789abcdef01234567")


def test_refuses_checkout_without_licence_file(tiny_repository: Path, tmp_path: Path) -> None:
    port = tmp_path / "port"

    with pytest.raises(StartFailed, match="no licence file"):
        start(tiny_repository, port)


def test_refuses_non_empty_port_folder(licensed_repository: Path, tmp_path: Path) -> None:
    port = tmp_path / "port"
    port.mkdir()
    (port / "keep.txt").write_text("mine")

    with pytest.raises(StartFailed, match="not empty") as refusal:
        start(licensed_repository, port)

    assert str(port) in str(refusal.value)


def test_short_hash_recorded_in_full(licensed_repository: Path, tmp_path: Path) -> None:
    full = head_of(licensed_repository)
    port = tmp_path / "port"

    start(licensed_repository, port, full[:8])

    saved = state.read_state(port_folder.port_json_path(port), "port")
    assert saved["commit"] == full
    assert run_git("-C", str(port_folder.checkout_folder(port)), "rev-parse", "HEAD") == full


def test_failed_start_removes_created_folder(tiny_repository: Path, tmp_path: Path) -> None:
    port = tmp_path / "new" / "port"

    with pytest.raises(StartFailed):
        start(tiny_repository, port)

    assert not port.exists()


def test_failed_start_keeps_existing_folder(tiny_repository: Path, tmp_path: Path) -> None:
    port = tmp_path / "port"
    port.mkdir()

    with pytest.raises(StartFailed, match=str(port)):
        start(tiny_repository, port)

    assert port.is_dir()
    assert list(port.iterdir()) == []


def test_retry_after_failure_succeeds(tiny_repository: Path, tmp_path: Path) -> None:
    port = tmp_path / "port"
    with pytest.raises(StartFailed):
        start(tiny_repository, port)
    shutil.rmtree(tiny_repository / "tests" / "__pycache__", ignore_errors=True)
    commit_file(tiny_repository, "LICENSE", b"licence\n", "add licence")

    start(tiny_repository, port)

    assert port_folder.port_json_path(port).is_file()
