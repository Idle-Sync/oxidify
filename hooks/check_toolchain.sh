#!/usr/bin/env bash
# SessionStart hook: tells the person which build tools are missing, and passes
# CLAUDE_PLUGIN_DATA on to Bash tool calls, where bin/oxidify prefers it.
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
# bin/oxidify finds its data folder without this, so a failure here is not reported.
if [ -n "${CLAUDE_PLUGIN_DATA:-}" ] && [ -n "${CLAUDE_ENV_FILE:-}" ]; then
	printf 'export CLAUDE_PLUGIN_DATA=%q\n' "$CLAUDE_PLUGIN_DATA" >>"$CLAUDE_ENV_FILE" || true
fi

if [ -z "$missing" ]; then
	exit 0
fi

printf '{"systemMessage": "Oxidify is not ready:\\n%s"}\n' "$missing"
