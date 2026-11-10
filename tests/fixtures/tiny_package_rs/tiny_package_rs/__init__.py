"""Stand-in for the Rust-backed package: two names reimplemented, two taken from the original."""

from tiny_package import evaluate_sum, split_after_vowels

__all__ = ["count_words", "evaluate_sum", "shout", "split_after_vowels"]


def count_words(text: str) -> int:
    return len(text.split())


def shout(text: str) -> str:
    return "-".join(text.upper().split())
