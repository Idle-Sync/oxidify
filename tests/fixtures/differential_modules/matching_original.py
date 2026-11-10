SEPARATOR = "-"


def shout(text: str) -> str:
    return SEPARATOR.join(text.upper().split())


def add(first: int, second: int) -> int:
    return first + second


def size(text: str) -> int:
    return len(text)


def describe(text):
    return f"{len(text)} characters"


def append_zero(numbers: list[int]) -> int:
    numbers.append(0)
    return len(numbers)


def join_all(*words: str) -> str:
    return " ".join(words)


def label(text: str, *, loud: bool) -> str:
    return text
