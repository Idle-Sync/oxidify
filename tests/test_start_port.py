import shutil
from pathlib import Path

import pytest
from conftest import run_git

from oxidify import port_folder, state
from oxidify.start_port import StartFailed, start_port

TEST_COMMAND = ["python", "-m", "pytest"]


def commit_symlink(repository: Path, name: str, target: Path) -> None:
    (repository / name).symlink_to(target)
    run_git("-C", str(repository), "add", name)
    run_git("-C", str(repository), "commit", "--quiet", "-m", f"link {name}")


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
    commit_file(licensed_repository, "copying.md", b"lowercase licence\n", "lowercase licence")
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

    for name in ["LICENSE", "LICENCE-extra", "NOTICE.txt", "AUTHORS.rst", "copying.md"]:
        original = (licensed_repository / name).read_bytes()
        assert (port_folder.licence_folder(port) / name).read_bytes() == original
    credits = port_folder.credits_path(port).read_text()
    assert str(licensed_repository) in credits
    assert head_of(licensed_repository) in credits
    for name in ["LICENSE", "LICENCE-extra", "NOTICE.txt", "copying.md"]:
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
    assert not (tmp_path / "new").exists()


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


def test_symlinked_licence_file_is_not_copied(licensed_repository: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("private file outside the repository\n")
    commit_symlink(licensed_repository, "COPYING", outside)
    port = tmp_path / "port"

    start(licensed_repository, port)

    assert not (port_folder.licence_folder(port) / "COPYING").exists()
    assert "COPYING" not in port_folder.credits_path(port).read_text()


def test_refuses_checkout_whose_only_licence_is_a_symlink(
    tiny_repository: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("private file outside the repository\n")
    commit_symlink(tiny_repository, "LICENSE", outside)

    with pytest.raises(StartFailed, match="no licence file"):
        start(tiny_repository, tmp_path / "port")


def test_password_in_url_is_not_saved(licensed_repository: Path, tmp_path: Path) -> None:
    url = f"file://user:s3cr3t-token@localhost{licensed_repository}"
    port = tmp_path / "port"

    start_port(url, head_of(licensed_repository), port, ["tests"], ["pytest"], TEST_COMMAND)

    saved = state.read_state(port_folder.port_json_path(port), "port")
    assert saved["source_url"] == f"file://localhost{licensed_repository}"
    for path in port.rglob("*"):
        if path.is_file():
            assert b"s3cr3t-token" not in path.read_bytes(), path


def test_password_in_url_is_not_in_error_messages(
    licensed_repository: Path, tmp_path: Path
) -> None:
    good_url = f"file://user:s3cr3t-token@localhost{licensed_repository}"
    missing_url = f"file://user:s3cr3t-token@localhost{tmp_path / 'missing'}"
    unknown_commit = "0123456789abcdef0123456789abcdef01234567"

    with pytest.raises(StartFailed) as unknown_commit_refusal:
        start_port(good_url, unknown_commit, tmp_path / "a", ["tests"], ["pytest"], TEST_COMMAND)
    with pytest.raises(StartFailed) as missing_repository_refusal:
        start_port(missing_url, unknown_commit, tmp_path / "b", ["tests"], [], TEST_COMMAND)

    assert "s3cr3t-token" not in str(unknown_commit_refusal.value)
    assert "s3cr3t-token" not in str(missing_repository_refusal.value)


def test_url_starting_with_dash_is_not_read_as_an_option(tmp_path: Path) -> None:
    port = tmp_path / "port"

    with pytest.raises(StartFailed, match="repository '--bare' does not exist"):
        start_port("--bare", "HEAD", port, ["tests"], ["pytest"], TEST_COMMAND)

    assert not port.exists()


def test_interrupted_start_removes_created_folder(
    licensed_repository: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def interrupt(checkout: Path) -> list[str]:
        raise KeyboardInterrupt

    monkeypatch.setattr("oxidify.start_port.contributors_at", interrupt)
    port = tmp_path / "port"

    with pytest.raises(KeyboardInterrupt):
        start(licensed_repository, port)

    assert not port.exists()


def test_failed_cleanup_keeps_the_original_cause(
    tiny_repository: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse_removal(path: Path) -> None:
        raise PermissionError(f"cannot remove {path}")

    monkeypatch.setattr("oxidify.start_port.shutil.rmtree", refuse_removal)

    with pytest.raises(StartFailed) as refusal:
        start(tiny_repository, tmp_path / "port")

    assert "no licence file" in str(refusal.value)
    assert "cannot remove" in str(refusal.value)
