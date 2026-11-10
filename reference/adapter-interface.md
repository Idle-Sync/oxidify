# Source-language adapter interface

Interface version: 1

Every step that depends on the language of the package being ported goes through one adapter.
The language-neutral code (`src/oxidify/` outside `python_adapter/`) never imports a language's
tools (`grimp`, `coverage`, `hypothesis`, `pytest`, `ast`) and reaches an adapter only through
`load_adapter(name, interface_version)` in `src/oxidify/adapter.py`. The protocol is
`SourceLanguageAdapter` in the same file; `ADAPTER_INTERFACE_VERSION` is the version below.

## Loading

`load_adapter(name, interface_version)` returns the adapter registered under `name` in the
`ADAPTERS` dictionary. It raises `ValueError` naming the name when no adapter is registered
under it, and naming both versions when the adapter implements a different interface version.
`port.json` records the adapter name and interface version a port was started with.

Registered adapters:

| name | class | interface version |
|---|---|---|
| `python` | `oxidify.python_adapter.PythonAdapter` | 1 |

## Attributes

- `name: str` — the registry name.
- `interface_version: int` — the interface version the adapter implements.

## Methods

Each method takes the port folder (layout in `src/oxidify/port_folder.py`). No method writes
inside `<port>/checkout/`. Steps that need the original importable run as child processes on
`<port>/.venv/bin/python` and exchange JSON files with the parent.

### `prepare_environment(port_folder) -> None`

Exports the pinned commit from `port.json` to `<port>/original_source/` with `git archive`
(replacing an earlier export), creates `<port>/.venv`, and installs into it the original from
`original_source/`, the port's test requirements and the pinned tools in
`src/oxidify/python_adapter/port_requirements.txt`. Raises `EnvironmentSetupFailed` with the
failing command and its stderr, including when an import name in `port.json` does not import.

### `analyse_source(port_folder) -> None`

Writes `analysis/import_graph.json`, `analysis/swap_order.json`, `analysis/coverage.json`,
`analysis/unsupported.json` and the initial `state/coverage_map.json`.

### `build_bridge(port_folder) -> None`

Builds the Rust-backed package in `<port>/rust_backed/` and installs its wheel into the port
environment.

### `run_original_tests(port_folder, against) -> dict`

Runs the original's unchanged tests against `"original"` or `"rust_backed"` and returns
`{passed, failed, errors, skipped, collected_test_ids}`. Test ids are written with the original
import name on both sides. The JUnit XML report goes to
`report/original_tests_<against>.xml`.

### `run_differential(port_folder, examples_per_call_path) -> list[dict]`

Compares each public call path of the original and the Rust-backed package on generated inputs
and returns one entry per call path in the `differential` shape of
`schemas/oracle_report.schema.json`.

### `names_resolving_to_source_language(port_folder) -> list[str]`

Returns the dotted public names the coverage map marks `rust` whose Rust-backed object is still
source-language code.

## Changing the interface

A change to a method's name, arguments or return shape raises `ADAPTER_INTERFACE_VERSION` and the
version line at the top of this file, and every registered adapter is updated with it.
