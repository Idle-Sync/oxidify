#!/usr/bin/env bats

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

@test "CLAUDE_PLUGIN_DATA unset: exits non-zero and says so" {
	unset CLAUDE_PLUGIN_DATA
	PATH="$FAKE_BIN:$PATH" run "$WRAPPER" analyse x
	[ "$status" -ne 0 ]
	[[ "$output" == *"CLAUDE_PLUGIN_DATA"* ]]
}
