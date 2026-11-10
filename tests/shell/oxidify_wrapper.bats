#!/usr/bin/env bats

bats_require_minimum_version 1.5.0

WRAPPER="$BATS_TEST_DIRNAME/../../bin/oxidify"

# A fake uv that records its arguments and the environment folder.
setup() {
	FAKE_BIN="$BATS_TEST_TMPDIR/bin"
	mkdir -p "$FAKE_BIN"
	cat >"$FAKE_BIN/uv" <<'FAKE'
#!/bin/sh
echo "args: $*"
echo "env: $UV_PROJECT_ENVIRONMENT"
FAKE
	chmod +x "$FAKE_BIN/uv"
	PLUGIN_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
}

@test "runs python -m oxidify through uv from the plugin project" {
	PATH="$FAKE_BIN:$PATH" CLAUDE_PLUGIN_DATA="$BATS_TEST_TMPDIR/data" run "$WRAPPER" analyse x
	[ "$status" -eq 0 ]
	[[ "$output" == *"args: run --project $PLUGIN_ROOT python -m oxidify analyse x"* ]]
}

@test "environment folder is outside the plugin root" {
	PATH="$FAKE_BIN:$PATH" CLAUDE_PLUGIN_DATA="$BATS_TEST_TMPDIR/data" run "$WRAPPER" analyse x
	[ "$status" -eq 0 ]
	[[ "$output" == *"env: $BATS_TEST_TMPDIR/data/"* ]]
	[[ "$output" != *"env: $PLUGIN_ROOT"* ]]
}

# Runs a copy of the wrapper placed at the given path under the temporary folder.
copy_wrapper_to() {
	mkdir -p "$(dirname "$1")"
	cp "$WRAPPER" "$1"
}

@test "CLAUDE_PLUGIN_DATA unset in a checkout: uses the inline data folder" {
	export HOME="$BATS_TEST_TMPDIR/home"
	unset CLAUDE_PLUGIN_DATA CLAUDE_CONFIG_DIR
	PATH="$FAKE_BIN:$PATH" run "$WRAPPER" --help
	[ "$status" -eq 0 ]
	[[ "$output" == *"args: run --project $PLUGIN_ROOT python -m oxidify --help"* ]]
	[[ "$output" == *"env: $HOME/.claude/plugins/data/oxidify-inline/venv"* ]]
}

@test "CLAUDE_PLUGIN_DATA empty: same as unset" {
	export HOME="$BATS_TEST_TMPDIR/home"
	unset CLAUDE_CONFIG_DIR
	PATH="$FAKE_BIN:$PATH" CLAUDE_PLUGIN_DATA="" run "$WRAPPER" --help
	[ "$status" -eq 0 ]
	[[ "$output" == *"args: run --project $PLUGIN_ROOT python -m oxidify --help"* ]]
	[[ "$output" == *"env: $HOME/.claude/plugins/data/oxidify-inline/venv"* ]]
}

@test "marketplace install: data folder named from the cache path" {
	config="$BATS_TEST_TMPDIR/config"
	copy="$config/plugins/cache/some-market/oxidify/0.1.0/bin/oxidify"
	copy_wrapper_to "$copy"
	export HOME="$BATS_TEST_TMPDIR/elsewhere"
	unset CLAUDE_PLUGIN_DATA CLAUDE_CONFIG_DIR
	PATH="$FAKE_BIN:$PATH" run "$copy" analyse x
	[ "$status" -eq 0 ]
	[[ "$output" == *"env: $config/plugins/data/oxidify-some-market/venv"* ]]
	[[ "$output" != *"$HOME"* ]]
}

@test "marketplace name with a dot: dot becomes a dash" {
	config="$BATS_TEST_TMPDIR/config"
	copy="$config/plugins/cache/some.market/oxidify/0.1.0/bin/oxidify"
	copy_wrapper_to "$copy"
	export HOME="$BATS_TEST_TMPDIR/elsewhere"
	unset CLAUDE_PLUGIN_DATA CLAUDE_CONFIG_DIR
	PATH="$FAKE_BIN:$PATH" run "$copy" analyse x
	[ "$status" -eq 0 ]
	[[ "$output" == *"env: $config/plugins/data/oxidify-some-market/venv"* ]]
}

@test "CLAUDE_CONFIG_DIR set: inline data folder sits under it" {
	export HOME="$BATS_TEST_TMPDIR/home"
	unset CLAUDE_PLUGIN_DATA
	PATH="$FAKE_BIN:$PATH" CLAUDE_CONFIG_DIR="$BATS_TEST_TMPDIR/elsewhere" run "$WRAPPER" analyse x
	[ "$status" -eq 0 ]
	[[ "$output" == *"env: $BATS_TEST_TMPDIR/elsewhere/plugins/data/oxidify-inline/venv"* ]]
}

@test "CLAUDE_PLUGIN_DATA set: wins over the cache path" {
	copy="$BATS_TEST_TMPDIR/config/plugins/cache/some-market/oxidify/0.1.0/bin/oxidify"
	copy_wrapper_to "$copy"
	PATH="$FAKE_BIN:$PATH" CLAUDE_PLUGIN_DATA="$BATS_TEST_TMPDIR/data" run "$copy" analyse x
	[ "$status" -eq 0 ]
	[[ "$output" == *"env: $BATS_TEST_TMPDIR/data/venv"* ]]
}

@test "no CLAUDE_PLUGIN_DATA, CLAUDE_CONFIG_DIR or HOME: exits non-zero and does not call uv" {
	PATH="$FAKE_BIN:$PATH" run --separate-stderr env -u CLAUDE_PLUGIN_DATA -u CLAUDE_CONFIG_DIR -u HOME "$WRAPPER" analyse x
	[ "$status" -ne 0 ]
	[[ "$stderr" == *"HOME"* ]]
	[[ "$stderr" == *"CLAUDE_PLUGIN_DATA"* ]]
	[[ "$output" != *"args:"* ]]
}
