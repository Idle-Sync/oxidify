import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from oxidify import port_folder, state
from oxidify.python_adapter.analysis import (
    AnalysisFailed,
    analyse_source,
    file_matches,
    scan_source,
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def checkout_status(port: Path) -> str:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(port_folder.checkout_folder(port)),
            "status",
            "--porcelain",
            # Ignored files too: a cache folder with its own .gitignore would otherwise hide.
            "--ignored",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


@pytest.fixture
def analysed_tiny_port(tiny_port_with_environment: Path) -> Path:
    analyse_source(tiny_port_with_environment)
    return tiny_port_with_environment


def test_import_graph(analysed_tiny_port: Path) -> None:
    graph = read_json(port_folder.import_graph_path(analysed_tiny_port))

    assert graph["format_version"] == 1
    assert graph["modules"] == [
        "tiny_package",
        "tiny_package.counting",
        "tiny_package.expressions",
        "tiny_package.words",
    ]
    assert graph["edges"] == [
        {"importer": "tiny_package", "imported": "tiny_package.counting"},
        {"importer": "tiny_package", "imported": "tiny_package.expressions"},
        {"importer": "tiny_package", "imported": "tiny_package.words"},
        {"importer": "tiny_package.counting", "imported": "tiny_package.words"},
        {"importer": "tiny_package.words", "imported": "tiny_package.counting"},
    ]


def test_swap_order_marks_coupled_group(analysed_tiny_port: Path) -> None:
    swap_order = read_json(port_folder.swap_order_path(analysed_tiny_port))

    assert swap_order["format_version"] == 1
    assert swap_order["groups"] == [
        {"modules": ["tiny_package.counting", "tiny_package.words"], "coupled": True},
        {"modules": ["tiny_package.expressions"], "coupled": False},
        {"modules": ["tiny_package"], "coupled": False},
    ]


def test_coverage_per_module(analysed_tiny_port: Path) -> None:
    coverage = read_json(port_folder.coverage_path(analysed_tiny_port))

    assert coverage["format_version"] == 1
    assert set(coverage["modules"]) == {
        "tiny_package",
        "tiny_package.counting",
        "tiny_package.expressions",
        "tiny_package.words",
    }
    # The fixture's tests call every function in every module.
    for module, percent in coverage["modules"].items():
        assert percent == 100.0, module


def test_failing_tests_stop_analysis(tiny_port_with_environment: Path) -> None:
    port = tiny_port_with_environment
    port_data = state.read_state(port_folder.port_json_path(port), "port")
    port_data["test_command"] = ["python", "-m", "pytest", "-k", "no_test_has_this_name"]
    state.write_state(port_folder.port_json_path(port), "port", port_data)

    with pytest.raises(AnalysisFailed, match="exited 5"):
        analyse_source(port)

    assert not port_folder.import_graph_path(port).exists()
    assert not port_folder.swap_order_path(port).exists()
    assert not port_folder.coverage_path(port).exists()
    assert not port_folder.unsupported_path(port).exists()
    assert not port_folder.coverage_map_path(port).exists()


def test_analysis_needs_the_port_environment(tiny_port_folder: Path) -> None:
    with pytest.raises(AnalysisFailed, match="prepare_environment"):
        analyse_source(tiny_port_folder)


def test_unsupported_constructs_and_regex_cases(analysed_tiny_port: Path) -> None:
    unsupported = read_json(port_folder.unsupported_path(analysed_tiny_port))

    assert unsupported["format_version"] == 1
    assert unsupported["constructs"] == [
        {
            "kind": "eval",
            "module": "tiny_package.expressions",
            "file": "tiny_package/expressions.py",
            "line": 5,
        }
    ]
    assert unsupported["regex_patterns"] == [
        {
            "module": "tiny_package.words",
            "file": "tiny_package/words.py",
            "line": 8,
            "pattern": "(?<=[aeiou])",
            "features": ["lookaround"],
        }
    ]


def test_regex_features_are_flagged() -> None:
    source = "\n".join(
        [
            "import re",
            "re.compile(r'(?<!a)b')",
            "re.compile(r'(a)\\1')",
            "re.compile(r'abc\\Z')",
            "re.compile(r'(?i)abc$')",
            "re.compile(r'\\bword')",
            "re.compile(r'\\w+')",
            "re.compile(r'(?P<name>a)(?P=name)')",
            "re.compile(r'(?x) a b')",
            "re.compile(r'a b # note', re.VERBOSE)",
            "re.compile(r'a\\$')",
            "re.sub(rule, '', word)",
        ]
    )

    _, patterns = scan_source(source, "module.py", "module")

    features = [pattern["features"] for pattern in patterns]
    assert features == [
        ["lookaround"],
        ["backreference"],
        ["end_of_string_Z"],
        ["inline_ignore_case", "trailing_dollar"],
        ["word_class_or_boundary"],
        ["word_class_or_boundary"],
        ["backreference"],
        ["verbose"],
        ["verbose"],
        [],
        ["built_at_runtime"],
    ]
    assert patterns[-1]["pattern"] is None


def test_unsupported_constructs_are_found() -> None:
    source = "\n".join(
        [
            "import importlib",
            "exec('x = 1')",
            "compile('x', 'f', 'eval')",
            "__import__('os')",
            "importlib.import_module('os')",
            "class Meta(type): pass",
            "class Thing(metaclass=Meta): pass",
            "def __getattr__(name): return name",
            "globals()['x'] = 1",
            "locals().update({})",
            "def fine(): return globals()['x']",
            "class Holder:",
            "    def __getattr__(self, name): return name",
        ]
    )

    constructs, _ = scan_source(source, "module.py", "module")

    kinds_and_lines = [(item["kind"], item["line"]) for item in constructs]
    assert kinds_and_lines == [
        ("exec", 2),
        ("compile", 3),
        ("__import__", 4),
        ("import_module", 5),
        ("metaclass", 7),
        ("module_getattr", 8),
        ("globals_write", 9),
        ("locals_write", 10),
    ]


def test_coverage_file_matches_on_whole_path_parts() -> None:
    assert file_matches("/site/tiny_package/words.py", "tiny_package/words.py")
    assert file_matches("tiny_package/words.py", "tiny_package/words.py")
    assert not file_matches("/site/other_tiny_package/words.py", "tiny_package/words.py")


def test_coverage_map_initialised(analysed_tiny_port: Path) -> None:
    coverage_map = state.read_state(
        port_folder.coverage_map_path(analysed_tiny_port), "coverage_map"
    )

    words = coverage_map["modules"]["tiny_package.words"]
    assert words["coverage_percent"] == 100.0
    assert words["status"] == "python"
    not_ported = {"implementation": "python", "reason": "not yet ported"}
    data = {"implementation": "python", "reason": "data, not a call path"}
    assert words["public_names"] == {
        "AFTER_VOWEL": data,
        "SEPARATOR": data,
        "describe": not_ported,
        "shout": not_ported,
        "split_after_vowels": not_ported,
    }
    package = coverage_map["modules"]["tiny_package"]
    assert package["public_names"] == {
        "count_words": not_ported,
        "evaluate_sum": not_ported,
        "shout": not_ported,
        "split_after_vowels": not_ported,
    }


def test_imported_modules_are_not_public_names(analysed_tiny_port: Path) -> None:
    coverage_map = state.read_state(
        port_folder.coverage_map_path(analysed_tiny_port), "coverage_map"
    )

    counting_names = coverage_map["modules"]["tiny_package.counting"]["public_names"]
    words_names = coverage_map["modules"]["tiny_package.words"]["public_names"]
    assert sorted(counting_names) == ["count_separators", "count_words"]
    assert "words" not in counting_names
    assert "re" not in words_names
    assert "counting" not in words_names


def test_checkout_clean_after_analysis(analysed_tiny_port: Path) -> None:
    assert checkout_status(analysed_tiny_port) == ""
    assert port_folder.coverage_data_path(analysed_tiny_port).is_file()


@pytest.mark.end_to_end
def test_analysis_on_inflection(inflection_port_with_environment: Path) -> None:
    port = inflection_port_with_environment

    analyse_source(port)

    for path in (
        port_folder.import_graph_path(port),
        port_folder.swap_order_path(port),
        port_folder.coverage_path(port),
        port_folder.unsupported_path(port),
    ):
        assert path.is_file()
    assert read_json(port_folder.unsupported_path(port))["regex_patterns"]
    coverage_map = state.read_state(port_folder.coverage_map_path(port), "coverage_map")
    assert sorted(coverage_map["modules"]["inflection"]["public_names"]) == sorted(
        [
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
            "PLURALS",
            "SINGULARS",
            "UNCOUNTABLES",
        ]
    )
    assert checkout_status(port) == ""
    assert port_folder.coverage_data_path(port).is_file()
