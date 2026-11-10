#!/usr/bin/env bash
# SessionStart hook: tells the person which build tools are missing, and passes
# CLAUDE_PLUGIN_DATA on to Bash tool calls, where bin/oxidify needs it.
# The JSON `systemMessage` field is what Claude Code shows to the person.
# Messages contain no quotes or backslashes, so they embed in JSON as they are.

missing=""

add_missing() {
	missing="${missing}${missing:+\\n}$1"
}

command -v cargo >/dev/null || add_missing "cargo is missing. Install Rust: curl -sSf https://sh.rustup.rs | sh"
command -v uv >/dev/null || add_missing "uv is missing. Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
command -v maturin >/dev/null || add_missing "maturin is missing. Install: uv tool install maturin"

# Claude Code sources CLAUDE_ENV_FILE before each Bash tool call; SessionStart
# fires again on resume, clear and compact, and a repeated export is harmless.
no_data_folder="The oxidify command cannot find its data folder:"
if [ -z "${CLAUDE_PLUGIN_DATA:-}" ]; then
	add_missing "$no_data_folder CLAUDE_PLUGIN_DATA is not set."
elif [ -z "${CLAUDE_ENV_FILE:-}" ]; then
	add_missing "$no_data_folder CLAUDE_ENV_FILE is not set."
elif ! printf 'export CLAUDE_PLUGIN_DATA=%q\n' "$CLAUDE_PLUGIN_DATA" >>"$CLAUDE_ENV_FILE"; then
	add_missing "$no_data_folder could not write to CLAUDE_ENV_FILE."
fi

if [ -z "$missing" ]; then
	exit 0
fi

printf '{"systemMessage": "Oxidify is not ready:\\n%s"}\n' "$missing"
