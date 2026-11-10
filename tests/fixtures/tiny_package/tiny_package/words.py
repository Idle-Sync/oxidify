import re

from tiny_package import counting

SEPARATOR = "-"

# Lookbehind: split after a vowel, keeping the vowel on the left part.
AFTER_VOWEL = re.compile(r"(?<=[aeiou])")


def shout(text: str) -> str:
    """Upper-case the text and join its words with the separator.

    >>> shout("hello tiny world")
    'HELLO-TINY-WORLD'
    """
    return SEPARATOR.join(text.upper().split())


def split_after_vowels(word: str) -> list[str]:
    return [part for part in AFTER_VOWEL.split(word) if part]


def describe(text: str) -> str:
    return f"{counting.count_words(text)} words: {shout(text)}"
