#!/usr/bin/env bats

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
OUTPUTS="$BATS_TEST_DIRNAME/validator_outputs"
ALLOWED_WARNING="CLAUDE.md at the plugin root is not loaded as project context"

# Reads validator output on stdin and succeeds when the part above the plugin
# directory checks holds no error and no warning other than the allowed one.
# The exit code of `claude plugin validate --strict` cannot be the verdict:
# strict mode exits 1 on the allowed warning.
check_validator_output() {
	local output upper warnings unexpected
	output="$(cat)"
	if ! grep -q '^Plugin directory checks for' <<<"$output"; then
		echo "cannot find the line starting 'Plugin directory checks for'"
		return 1
	fi
	upper="$(sed '/^Plugin directory checks for/,$d' <<<"$output")"
	if grep -q '✘' <<<"$upper"; then
		echo "errors found:"
		grep -A2 '✘' <<<"$upper"
		return 1
	fi
	warnings="$(grep '^ *❯' <<<"$upper" || true)"
	echo "warning items found:"
	echo "${warnings:-(none)}"
	unexpected="$(grep -v -F "$ALLOWED_WARNING" <<<"$warnings" || true)"
	if [ -n "$unexpected" ]; then
		echo "unexpected warning items:"
		echo "$unexpected"
		return 1
	fi
}

@test "plugin validates with only the allowed warning" {
	if ! command -v claude >/dev/null; then
		skip "claude is not on PATH"
	fi
	cd "$REPO_ROOT"
	run claude plugin validate --strict .
	run check_validator_output <<<"$output"
	# File descriptor 3 reaches the terminal even when the case passes.
	printf '# %s\n' "${lines[@]}" >&3
	[ "$status" -eq 0 ]
}

@test "stored current output passes" {
	run check_validator_output <"$OUTPUTS/current.txt"
	echo "$output"
	[ "$status" -eq 0 ]
	[[ "$output" == *"$ALLOWED_WARNING"* ]]
}

@test "stored output with the version warning added fails" {
	run check_validator_output <"$OUTPUTS/version_warning_added.txt"
	echo "$output"
	[ "$status" -ne 0 ]
	[[ "$output" == *"version: No version specified"* ]]
}

@test "stored output with an error block fails" {
	run check_validator_output <"$OUTPUTS/error_block.txt"
	echo "$output"
	[ "$status" -ne 0 ]
	[[ "$output" == *"errors found"* ]]
}

@test "stored output with no warning passes" {
	run check_validator_output <"$OUTPUTS/no_warning.txt"
	echo "$output"
	[ "$status" -eq 0 ]
}

@test "stored output without the plugin directory line fails" {
	run check_validator_output <"$OUTPUTS/no_directory_checks.txt"
	echo "$output"
	[ "$status" -ne 0 ]
	[[ "$output" == *"cannot find"* ]]
}
