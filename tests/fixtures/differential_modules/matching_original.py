SEPARATOR = "-"


def shout(text: str) -> str:
    return SEPARATOR.join(text.upper().split())


def add(first: int, second: int) -> int:
    return first + second


def size(text: str) -> int:
    return len(text)


def describe(text):
    return f"{len(text)} characters"
