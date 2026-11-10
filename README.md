# Oxidify

A Claude Code plugin that ports a pure-Python library to a behaviour-identical, Rust-backed drop-in Python package.

For Python library maintainers and developers who want a faster package without changing its behaviour.

## Prerequisites

- `cargo` (Rust toolchain)
- `uv`
- `maturin` (`uv tool install maturin`)

At session start the plugin names any of these that is missing and how to install it.

## Install

Inside Claude Code:

```
/plugin marketplace add Idle-Sync/oxidify
/plugin install oxidify@idle-sync
```

To work on the plugin itself, clone this repository and start Claude Code with
`claude --plugin-dir <path to the clone>`.

## Commands

Inside a Claude Code session with the plugin loaded, `oxidify` is on the Bash tool's path. From a
checkout of this repository, use `uv run python -m oxidify` instead.

```
oxidify start <url> <commit> <port> [--test-path <file or folder>]... [--test-requirement <package>]... [--test-command <command> ...]
oxidify analyse <port>
oxidify mark-swapped <port> <module> <name> [<name> ...]
oxidify build <port> [--rust-project <folder>]
oxidify oracle <port> [--examples <inputs per call path>]
```

- `start` clones the repository at the commit into `<port>/checkout/`, copies the licence files and
  builds the port's environment in `<port>/.venv/`. `--test-path` defaults to `tests`; `--test-command` defaults to `python -m pytest`. A port
  folder that already holds files is refused and left as it is.
- `analyse` writes the files under `<port>/analysis/` and the coverage map.
- `mark-swapped` marks public names of one module as implemented in Rust.
- `build` copies the maturin project in `--rust-project` (`Cargo.toml`, `pyproject.toml`, `src/`;
  never `target/`) into `<port>/rust_backed/`, then builds it and installs the wheel into the port
  environment. Without the option it builds what `rust_backed/` already holds.
- `oracle` runs the original tests against the Rust-backed package, compares both on generated
  inputs and checks for names that silently run Python. It exits 0 only when all of it passes.

Example, with the hand-written `dasherize` in `examples/inflection_hand_swap`:

```
oxidify start https://github.com/jpvanhal/inflection.git b00d4d348b32ef5823221b20ee4cbd1d2d924462 ports/inflection --test-path test_inflection.py
oxidify analyse ports/inflection
oxidify mark-swapped ports/inflection inflection dasherize
oxidify build ports/inflection --rust-project examples/inflection_hand_swap
oxidify oracle ports/inflection
```

## Port folder

```
<port>/port.json            source URL, commit, adapter, test command, test paths, import names
<port>/checkout/            git checkout at the commit; unchanged after `start`
<port>/licence/  <port>/CREDITS.md
<port>/original_source/     export of the commit; the original is installed from here
<port>/.venv/               the port's environment
<port>/analysis/            import_graph.json  swap_order.json  coverage.json  unsupported.json  .coverage
<port>/state/               coverage_map.json  checkpoints.json  task_log.json
<port>/rust_backed/         maturin project: Cargo.toml, pyproject.toml, src/, python/<import name>_rs/, target/wheels/
<port>/report/              oracle.json  differential.json  original_tests_original.xml  original_tests_rust_backed.xml
```

## Development

`just lint`, `just test` and `bats tests/shell/plugin_validate.bats` check the repository.
