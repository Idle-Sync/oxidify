"""Start a port: clone the repository at a pinned commit and record where it came from."""

import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from oxidify import port_folder as port_layout
from oxidify import state
from oxidify.adapter import ADAPTER_INTERFACE_VERSION

LICENCE_PREFIXES = ("LICENSE", "LICENCE", "COPYING", "NOTICE")
AUTHOR_PREFIXES = ("AUTHORS", "CREDITS", "CONTRIBUTORS")


class StartFailed(Exception):
    """The port could not be started; the message names the port folder or the cause."""


def run_git(*arguments: str) -> str:
    result = subprocess.run(["git", *arguments], capture_output=True, text=True)
    if result.returncode != 0:
        raise StartFailed(f"git {' '.join(arguments)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def files_with_prefix(checkout: Path, prefixes: tuple[str, ...]) -> list[Path]:
    matches = []
    for path in sorted(checkout.iterdir()):
        # A symlink could point at any local file, which would then be copied and published.
        if path.is_symlink():
            continue
        if path.is_file() and path.name.upper().startswith(prefixes):
            matches.append(path)
    return matches


def url_without_credentials(repository_url: str) -> str:
    """`repository_url` with any `user:password@` removed, so no token is saved or shown."""
    parts = urlsplit(repository_url)
    # An ssh user name such as `git@` is part of the address, not a secret.
    if parts.scheme == "ssh" or "@" not in parts.netloc:
        return repository_url
    host = parts.netloc.rpartition("@")[2]
    return urlunsplit(parts._replace(netloc=host))


def clone_repository(repository_url: str, public_url: str, checkout: Path) -> None:
    """Clone with the given URL, then point `origin` at `public_url` so no token stays behind."""
    result = subprocess.run(
        ["git", "clone", "--quiet", "--no-checkout", "--", repository_url, str(checkout)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        error = result.stderr.strip().replace(repository_url, public_url)
        raise StartFailed(f"git clone of {public_url} failed: {error}")
    run_git("-C", str(checkout), "remote", "set-url", "origin", public_url)


def resolve_commit(checkout: Path, commit: str, repository_url: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise StartFailed(f"no commit {commit} in {repository_url}")
    return result.stdout.strip()


def contributors_at(checkout: Path) -> list[str]:
    names = run_git("-C", str(checkout), "log", "--format=%aN", "HEAD").splitlines()
    return sorted(set(names))


def find_import_names(checkout: Path, test_paths: list[str]) -> list[str]:
    """Top-level packages (folders with `__init__.py`) that are not test folders."""
    test_folders = {Path(test_path).parts[0] for test_path in test_paths}
    names = []
    for path in sorted(checkout.iterdir()):
        if path.is_dir() and (path / "__init__.py").is_file() and path.name not in test_folders:
            names.append(path.name)
    if not names:
        raise StartFailed(f"no top-level package with an __init__.py in {checkout}")
    return names


def write_credits(
    port: Path, repository_url: str, commit: str, licence_files: list[Path], contributors: list[str]
) -> None:
    lines = [
        "# Credits",
        "",
        f"Ported from {repository_url} at commit {commit}.",
        "",
        "## Licence files",
        "",
    ]
    for licence_file in licence_files:
        lines.append(f"- {licence_file.name} (copied to licence/)")
    lines.extend(["", "## Contributors at this commit", ""])
    for name in contributors:
        lines.append(f"- {name}")
    port_layout.credits_path(port).write_text("\n".join(lines) + "\n")


def build_port(
    repository_url: str,
    commit: str,
    port: Path,
    test_paths: list[str],
    test_requirements: list[str],
    test_command: list[str],
) -> None:
    public_url = url_without_credentials(repository_url)
    checkout = port_layout.checkout_folder(port)
    clone_repository(repository_url, public_url, checkout)
    full_commit = resolve_commit(checkout, commit, public_url)
    run_git("-C", str(checkout), "checkout", "--quiet", "--detach", full_commit)

    licence_files = files_with_prefix(checkout, LICENCE_PREFIXES)
    if not licence_files:
        raise StartFailed(f"no licence file in the root of {public_url} at {full_commit}")
    licence_folder = port_layout.licence_folder(port)
    licence_folder.mkdir()
    for path in licence_files + files_with_prefix(checkout, AUTHOR_PREFIXES):
        shutil.copy2(path, licence_folder / path.name)
    write_credits(port, public_url, full_commit, licence_files, contributors_at(checkout))

    state.write_state(
        port_layout.port_json_path(port),
        "port",
        {
            "format_version": state.FORMAT_VERSION,
            "source_url": public_url,
            "commit": full_commit,
            "adapter": {"name": "python", "interface_version": ADAPTER_INTERFACE_VERSION},
            "test_command": test_command,
            "test_paths": test_paths,
            "test_requirements": test_requirements,
            "import_names": find_import_names(checkout, test_paths),
        },
    )


def remove_contents(folder: Path) -> None:
    for path in folder.iterdir():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def first_missing_folder(path: Path) -> Path:
    """The highest folder on the way to `path` that does not exist yet."""
    while not path.parent.exists():
        path = path.parent
    return path


def undo_start(port_folder: Path, existed_before: bool, first_created: Path) -> None:
    if existed_before:
        remove_contents(port_folder)
    else:
        shutil.rmtree(first_created)


def start_port(
    repository_url: str,
    commit: str,
    port_folder: Path,
    test_paths: list[str],
    test_requirements: list[str],
    test_command: list[str],
) -> None:
    """Clone `repository_url` detached at `commit` into `<port_folder>/checkout`.

    A failure leaves no trace: a port folder created by this call is removed with any parent folders
    the call created, a pre-existing empty one is emptied. A non-empty port folder is refused and
    left alone.
    """
    existed_before = port_folder.exists()
    if existed_before and any(port_folder.iterdir()):
        raise StartFailed(f"port folder {port_folder} is not empty; choose a new folder")
    first_created = first_missing_folder(port_folder)
    port_folder.mkdir(parents=True, exist_ok=True)
    try:
        build_port(repository_url, commit, port_folder, test_paths, test_requirements, test_command)
    except BaseException as error:
        message = f"could not start the port in {port_folder}: {error}"
        try:
            undo_start(port_folder, existed_before, first_created)
        except OSError as cleanup_error:
            raise StartFailed(
                f"{message}; removing what it created failed: {cleanup_error}"
            ) from error
        # KeyboardInterrupt and SystemExit pass through unchanged once the folder is cleaned up.
        if not isinstance(error, Exception):
            raise
        raise StartFailed(message) from error
