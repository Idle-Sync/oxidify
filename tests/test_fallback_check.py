import shutil
from pathlib import Path

import pytest

from oxidify import port_folder, state
from oxidify.python_adapter.bridge import build_bridge
from oxidify.python_adapter.fallback_check import names_resolving_to_source_language

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
PYTHON_NAMES_AFTER_HAND_SWAP = [
    "inflection.camelize",
    "inflection.humanize",
    "inflection.ordinal",
    "inflection.ordinalize",
    "inflection.parameterize",
    "inflection.pluralize",
    "inflection.singularize",
    "inflection.tableize",
    "inflection.titleize",
    "inflection.transliterate",
    "inflection.underscore",
    "inflection.PLURALS",
    "inflection.SINGULARS",
    "inflection.UNCOUNTABLES",
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


@pytest.mark.end_to_end
def test_exact_python_names(inflection_port_with_environment: Path) -> None:
    port = inflection_port_with_environment
    hand_swap_dasherize(port)
    build_bridge(port)

    names = names_resolving_to_source_language(port)

    print(f"{len(names)} names resolve to Python: {' '.join(names)}")
    assert sorted(names) == sorted(PYTHON_NAMES_AFTER_HAND_SWAP)


@pytest.mark.end_to_end
def test_marked_rust_but_python_is_returned(inflection_port_with_environment: Path) -> None:
    port = inflection_port_with_environment
    hand_swap_dasherize(port)
    build_bridge(port)
    state.mark_names_swapped(port, "inflection", ["underscore"])

    names = names_resolving_to_source_language(port)

    assert "inflection.underscore" in names
    assert "inflection.dasherize" not in names
