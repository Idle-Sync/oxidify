import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

SCHEMAS_FOLDER = Path(__file__).parent.parent / "schemas"
SCHEMA_PATHS = sorted(SCHEMAS_FOLDER.glob("*.schema.json"))


def properties_without_description(schema: object, location: str) -> list[str]:
    """Walk a schema and list every property whose definition has no description."""
    if isinstance(schema, list):
        missing = []
        for index, item in enumerate(schema):
            missing.extend(properties_without_description(item, f"{location}[{index}]"))
        return missing
    if not isinstance(schema, dict):
        return []
    missing = []
    for name, definition in schema.get("properties", {}).items():
        if "description" not in definition:
            missing.append(f"{location}.properties.{name}")
    for key, value in schema.items():
        missing.extend(properties_without_description(value, f"{location}.{key}"))
    return missing


def test_one_schema_per_state_kind() -> None:
    names = [path.name for path in SCHEMA_PATHS]

    assert names == [
        "checkpoints.schema.json",
        "coverage_map.schema.json",
        "oracle_report.schema.json",
        "port.schema.json",
        "task_log.schema.json",
    ]


@pytest.mark.parametrize("schema_path", SCHEMA_PATHS, ids=lambda path: path.name)
def test_every_property_has_a_description(schema_path: Path) -> None:
    schema = json.loads(schema_path.read_text())

    assert properties_without_description(schema, schema_path.name) == []


@pytest.mark.parametrize("schema_path", SCHEMA_PATHS, ids=lambda path: path.name)
def test_schema_is_valid(schema_path: Path) -> None:
    schema = json.loads(schema_path.read_text())

    Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize("schema_path", SCHEMA_PATHS, ids=lambda path: path.name)
def test_schema_pins_format_version_one(schema_path: Path) -> None:
    schema = json.loads(schema_path.read_text())

    assert schema["properties"]["format_version"]["const"] == 1
    assert "format_version" in schema["required"]
