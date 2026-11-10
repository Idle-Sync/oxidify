rust_manifest := "examples/inflection_hand_swap/Cargo.toml"

# Rewrite Python, Rust and shell sources in their standard format.
format:
    uv run ruff format .
    uv run ruff check --fix .
    cargo fmt --manifest-path {{rust_manifest}}
    shfmt --write hooks/*.sh bin/*

lint: lint-python lint-rust lint-shell

lint-python:
    uv run ruff format --check .
    uv run ruff check .
    uv run pyright

lint-rust:
    cargo fmt --check --manifest-path {{rust_manifest}}
    cargo clippy --manifest-path {{rust_manifest}} --all-targets -- -D warnings

lint-shell:
    shfmt --diff hooks/*.sh bin/*
    shellcheck hooks/*.sh bin/*

test: test-python test-rust test-shell

# -rP prints the output of passing tests, so values the tests print stay visible.
test-python:
    uv run pytest -rP

test-rust:
    cargo test --manifest-path {{rust_manifest}}

test-shell:
    bats tests/shell/*.bats

build:
    cargo build --manifest-path {{rust_manifest}}
