---
name: port
description: Port a Python library from a GitHub URL and commit to a Rust-backed drop-in package and check it against the original tests. Use when asked to port, oxidise or speed up a Python package with Rust.
argument-hint: <repository-url> <commit>
---

# Port a Python library to Rust

Inputs: the repository URL and a commit (a full hash or a tag). The port folder defaults to
`./ports/<repository name>`, where the repository name is the last part of the URL without `.git`.

Every step is a command of the `oxidify` wrapper in the plugin's `bin/` folder. Run them with the
Bash tool, in this order, and stop at the first one that exits non-zero: its message says what to fix.

1. `oxidify start <url> <commit> <port> --test-path <test file or folder>` clones the repository at the
   commit, copies the licence files and builds the port's own environment. Pass `--test-path` once per
   test file or folder (default `tests`) and `--test-requirement` once per extra package the tests need.
2. `oxidify analyse <port>` writes the import graph, swap order, coverage and unsupported-construct
   files under `<port>/analysis/` and the coverage map under `<port>/state/`.
3. `oxidify mark-swapped <port> <module> <name> [<name> ...]` marks public names of a module as
   implemented in Rust. Do it only for names the Rust code provides.
4. `oxidify build <port> --rust-project <folder>` copies a maturin project (`Cargo.toml`,
   `pyproject.toml`, `src/`) into `<port>/rust_backed/` and installs the built package. Without
   `--rust-project` it builds what `<port>/rust_backed/` already holds.
5. `oxidify oracle <port>` runs the unchanged original tests against the Rust-backed package, compares
   both on generated inputs and checks that no name marked Rust still runs Python. It exits 0 only
   when everything passes.

The oracle prints a summary and writes `<port>/report/oracle.json`; the differential run is in
`<port>/report/differential.json`. A name left in Python needs a reason in
`<port>/state/coverage_map.json`, otherwise the oracle fails.

This skill does not write the Rust code. Until a port loop exists, the maturin project comes from the
person or from an example such as `examples/inflection_hand_swap`.
