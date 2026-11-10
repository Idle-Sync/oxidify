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


def append_zero(numbers: list[int]) -> int:
    numbers.append(0)
    return len(numbers)


def join_all(*words: str) -> str:
    return " ".join(words)


def label(text: str, *, loud: bool) -> str:
    return text
