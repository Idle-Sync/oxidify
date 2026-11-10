#!/usr/bin/env bats

bats_require_minimum_version 1.5.0

HOOK="$BATS_TEST_DIRNAME/../../hooks/check_toolchain.sh"

# Builds a PATH holding jq plus the named tools, so the hook sees only those.
# Both plugin variables are set, as Claude Code sets them for a SessionStart hook.
setup() {
	TOOL_DIR="$BATS_TEST_TMPDIR/tools"
	mkdir -p "$TOOL_DIR"
	ln -s "$(command -v jq)" "$TOOL_DIR/jq"
	export CLAUDE_PLUGIN_DATA="$BATS_TEST_TMPDIR/data"
	export CLAUDE_ENV_FILE="$BATS_TEST_TMPDIR/env_file"
}

with_tools() {
	for tool in "$@"; do
		printf '#!/bin/sh\n' >"$TOOL_DIR/$tool"
		chmod +x "$TOOL_DIR/$tool"
	done
}

# Claude Code reads the JSON from stdout only, so stderr is kept apart.
run_hook() {
	run --separate-stderr env PATH="$TOOL_DIR" "$BASH" "$HOOK"
}

@test "all tools present: emits nothing" {
	with_tools cargo uv maturin
	run_hook
	[ "$status" -eq 0 ]
	[ -z "$output" ]
}

@test "cargo missing: systemMessage names cargo and its install command once" {
	with_tools uv maturin
	run_hook
	[ "$status" -eq 0 ]
	message="$(jq -r '.systemMessage' <<<"$output")"
	[[ "$message" == *"cargo"* ]]
	[[ "$message" == *"https://sh.rustup.rs"* ]]
	[[ "$message" != *"uv"* ]]
	[[ "$message" != *"maturin"* ]]
	[ "$(grep -o 'rustup' <<<"$message" | wc -l)" -eq 1 ]
}

@test "uv missing: systemMessage names uv and its install command" {
	with_tools cargo maturin
	run_hook
	[ "$status" -eq 0 ]
	message="$(jq -r '.systemMessage' <<<"$output")"
	[[ "$message" == *"https://astral.sh/uv/install.sh"* ]]
	[[ "$message" != *"cargo"* ]]
	[[ "$message" != *"maturin"* ]]
}

@test "maturin missing: systemMessage names maturin and its install command" {
	with_tools cargo uv
	run_hook
	[ "$status" -eq 0 ]
	message="$(jq -r '.systemMessage' <<<"$output")"
	[[ "$message" == *"uv tool install maturin"* ]]
	[[ "$message" != *"cargo"* ]]
}

@test "all missing: systemMessage names all three tools" {
	run_hook
	[ "$status" -eq 0 ]
	message="$(jq -r '.systemMessage' <<<"$output")"
	[[ "$message" == *"cargo"* ]]
	[[ "$message" == *"uv tool install maturin"* ]]
	[[ "$message" == *"https://astral.sh/uv/install.sh"* ]]
	[ "$(jq -r 'keys | length' <<<"$output")" -eq 1 ]
	[ "$(wc -l <<<"$message")" -eq 4 ]
}

@test "exports plugin data folder" {
	with_tools cargo uv maturin
	run_hook
	[ "$status" -eq 0 ]
	[ -z "$output" ]
	[ "$(cat "$CLAUDE_ENV_FILE")" = "export CLAUDE_PLUGIN_DATA=$BATS_TEST_TMPDIR/data" ]
}

@test "keeps a path with a space" {
	with_tools cargo uv maturin
	export CLAUDE_PLUGIN_DATA="$BATS_TEST_TMPDIR/plugin data"
	run_hook
	[ "$status" -eq 0 ]
	[ "$(wc -l <"$CLAUDE_ENV_FILE")" -eq 1 ]
	# shellcheck source=/dev/null
	sourced="$(unset CLAUDE_PLUGIN_DATA && . "$CLAUDE_ENV_FILE" && echo "$CLAUDE_PLUGIN_DATA")"
	[ "$sourced" = "$BATS_TEST_TMPDIR/plugin data" ]
}

@test "keeps existing lines" {
	with_tools cargo uv maturin
	echo "export EARLIER=1" >"$CLAUDE_ENV_FILE"
	run_hook
	[ "$status" -eq 0 ]
	[ "$(sed -n 1p "$CLAUDE_ENV_FILE")" = "export EARLIER=1" ]
	[ "$(sed -n 2p "$CLAUDE_ENV_FILE")" = "export CLAUDE_PLUGIN_DATA=$BATS_TEST_TMPDIR/data" ]
	[ "$(wc -l <"$CLAUDE_ENV_FILE")" -eq 2 ]
}

@test "unset CLAUDE_PLUGIN_DATA: writes nothing and says nothing" {
	with_tools cargo uv maturin
	unset CLAUDE_PLUGIN_DATA
	run_hook
	[ "$status" -eq 0 ]
	[ ! -e "$CLAUDE_ENV_FILE" ]
	[ -z "$output" ]
}

@test "unset CLAUDE_ENV_FILE: says nothing" {
	with_tools cargo uv maturin
	unset CLAUDE_ENV_FILE
	run_hook
	[ "$status" -eq 0 ]
	[ ! -e "$BATS_TEST_TMPDIR/env_file" ]
	[ -z "$output" ]
}

@test "env file it cannot write: says nothing on stdout" {
	with_tools cargo uv maturin
	export CLAUDE_ENV_FILE="$BATS_TEST_TMPDIR/no_such_folder/env_file"
	run_hook
	[ "$status" -eq 0 ]
	[ -z "$output" ]
}
