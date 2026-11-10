import shutil
import subprocess
from pathlib import Path

import pytest

from oxidify import port_folder, state
from oxidify.python_adapter.bridge import (
    BridgeBuildFailed,
    build_bridge,
    module_file,
    write_python_package,
)
from oxidify.python_adapter.environment import export_pinned_commit

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


def run_in_port_environment(port: Path, code: str) -> str:
    result = subprocess.run(
        [str(port_folder.venv_python(port)), "-c", code],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def checkout_status(port: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(port_folder.checkout_folder(port)), "status", "--porcelain", "--ignored"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


@pytest.mark.end_to_end
def test_swapped_name_is_rust(inflection_port_with_environment: Path) -> None:
    port = inflection_port_with_environment
    hand_swap_dasherize(port)

    build_bridge(port)

    kinds = run_in_port_environment(
        port,
        "import inflection_rs; "
        "print(type(inflection_rs.dasherize).__name__, type(inflection_rs.underscore).__name__)",
    )
    assert kinds == "builtin_function_or_method function"
    assert (
        run_in_port_environment(
            port, "import inflection_rs; print(inflection_rs.dasherize('puni_puni'))"
        )
        == "puni-puni"
    )


@pytest.mark.end_to_end
def test_package_is_the_original_plus_one_rebinding_line(
    inflection_port_with_environment: Path,
) -> None:
    port = inflection_port_with_environment
    hand_swap_dasherize(port)

    build_bridge(port)

    original = port_folder.original_source_folder(port) / "inflection"
    copy = port_folder.rust_backed_python_package_folder(port, "inflection")
    assert sorted(path.name for path in copy.iterdir()) == ["__init__.py", "py.typed"]
    original_text = (original / "__init__.py").read_text()
    assert (copy / "__init__.py").read_text() == (
        original_text + "from inflection_rs._rust import dasherize\n"
    )


@pytest.mark.end_to_end
def test_builtin_keeps_the_original_docstring_and_module(
    inflection_port_with_environment: Path,
) -> None:
    port = inflection_port_with_environment
    hand_swap_dasherize(port)

    build_bridge(port)

    same_docstring = run_in_port_environment(
        port,
        "import inflection, inflection_rs; "
        "print(inflection_rs.dasherize.__doc__ == inflection.dasherize.__doc__)",
    )
    assert same_docstring == "True"
    module = run_in_port_environment(
        port, "import inflection_rs; print(inflection_rs.dasherize.__module__)"
    )
    assert module == "inflection_rs"


@pytest.mark.end_to_end
def test_lone_surrogate_gives_the_original_result(inflection_port_with_environment: Path) -> None:
    port = inflection_port_with_environment
    hand_swap_dasherize(port)

    build_bridge(port)

    results = run_in_port_environment(
        port,
        "import inflection, inflection_rs; word = 'a_\\udc00_b'; "
        "print(ascii(inflection.dasherize(word)), ascii(inflection_rs.dasherize(word)))",
    )
    assert results == "'a-\\udc00-b' 'a-\\udc00-b'"


@pytest.mark.end_to_end
def test_checkout_clean_after_build(inflection_port_with_environment: Path) -> None:
    port = inflection_port_with_environment
    hand_swap_dasherize(port)

    build_bridge(port)

    assert checkout_status(port) == ""


def test_failed_build_raises(tiny_port_folder: Path) -> None:
    port = tiny_port_folder
    coverage_map = state.new_coverage_map({"tiny_package": ["shout"]})
    state.write_state(port_folder.coverage_map_path(port), "coverage_map", coverage_map)
    original_package = port_folder.original_source_folder(port) / "tiny_package"
    original_package.mkdir(parents=True)
    (original_package / "__init__.py").write_text("")
    rust_backed = port_folder.rust_backed_folder(port)
    rust_backed.mkdir()
    (rust_backed / "pyproject.toml").write_text("this is not toml [\n")

    with pytest.raises(BridgeBuildFailed, match="maturin"):
        build_bridge(port)


def test_rebinding_lines_go_to_the_module_that_holds_the_names(tiny_port_folder: Path) -> None:
    port = tiny_port_folder
    commit = state.read_state(port_folder.port_json_path(port), "port")["commit"]
    export_pinned_commit(port, commit)
    original_words = port_folder.original_source_folder(port) / "tiny_package" / "words.py"
    original_words.write_text(original_words.read_text().rstrip("\n"))
    coverage_map = state.new_coverage_map(
        {"tiny_package": ["count_words"], "tiny_package.words": ["shout", "split_after_vowels"]}
    )
    state.write_state(port_folder.coverage_map_path(port), "coverage_map", coverage_map)
    state.mark_names_swapped(port, "tiny_package.words", ["shout", "split_after_vowels"])

    write_python_package(port, "tiny_package")
    write_python_package(port, "tiny_package")

    copy = port_folder.rust_backed_python_package_folder(port, "tiny_package")
    assert (copy / "words.py").read_text() == (
        original_words.read_text()
        + "\nfrom tiny_package_rs._rust import shout\n"
        + "from tiny_package_rs._rust import split_after_vowels\n"
    )
    original_init = port_folder.original_source_folder(port) / "tiny_package" / "__init__.py"
    assert (copy / "__init__.py").read_text() == original_init.read_text()


def test_module_file_of_a_subpackage(tmp_path: Path) -> None:
    (tmp_path / "rules").mkdir()

    assert module_file(tmp_path, "package") == tmp_path / "__init__.py"
    assert module_file(tmp_path, "package.rules") == tmp_path / "rules" / "__init__.py"
    assert module_file(tmp_path, "package.words") == tmp_path / "words.py"


def test_more_than_one_import_name_is_refused(tiny_port_folder: Path) -> None:
    port_json = port_folder.port_json_path(tiny_port_folder)
    port = state.read_state(port_json, "port")
    port["import_names"] = ["tiny_package", "other_package"]
    state.write_state(port_json, "port", port)

    with pytest.raises(BridgeBuildFailed, match="2 import names"):
        build_bridge(tiny_port_folder)
