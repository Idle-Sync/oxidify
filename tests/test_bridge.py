import shutil
import subprocess
from pathlib import Path

import pytest

from oxidify import port_folder, state
from oxidify.python_adapter.bridge import BridgeBuildFailed, build_bridge

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
