#!/usr/bin/env bash
# SessionStart hook: tells the person which build tools are missing.
# The JSON `systemMessage` field is what Claude Code shows to the person.
# Install commands contain no quotes or backslashes, so they embed in JSON as they are.

missing=""

add_missing() {
	missing="${missing}${missing:+\\n}$1"
}

command -v cargo >/dev/null || add_missing "cargo is missing. Install Rust: curl -sSf https://sh.rustup.rs | sh"
command -v uv >/dev/null || add_missing "uv is missing. Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
command -v maturin >/dev/null || add_missing "maturin is missing. Install: uv tool install maturin"

if [ -z "$missing" ]; then
	exit 0
fi

printf '{"systemMessage": "Oxidify needs these tools:\\n%s"}\n' "$missing"
