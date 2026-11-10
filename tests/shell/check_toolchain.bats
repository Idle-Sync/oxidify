#!/usr/bin/env bats

HOOK="$BATS_TEST_DIRNAME/../../hooks/check_toolchain.sh"

# Builds a PATH holding jq plus the named tools, so the hook sees only those.
setup() {
	TOOL_DIR="$BATS_TEST_TMPDIR/tools"
	mkdir -p "$TOOL_DIR"
	ln -s "$(command -v jq)" "$TOOL_DIR/jq"
}

with_tools() {
	for tool in "$@"; do
		printf '#!/bin/sh\n' >"$TOOL_DIR/$tool"
		chmod +x "$TOOL_DIR/$tool"
	done
}

run_hook() {
	PATH="$TOOL_DIR" run "$BASH" "$HOOK"
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
