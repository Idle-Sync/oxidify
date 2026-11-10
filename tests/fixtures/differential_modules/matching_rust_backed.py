SEPARATOR = "-"

# A built-in stands in for a compiled function.
size = len


def shout(text: str) -> str:
    words = text.upper().split()
    return SEPARATOR.join(words)


def add(first: int, second: int) -> int:
    return second + first


def describe(text):
    return f"{len(text)} characters"
