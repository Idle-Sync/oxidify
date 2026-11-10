from tiny_package import words


def count_words(text: str) -> int:
    return len(text.split())


def count_separators(text: str) -> int:
    return words.shout(text).count(words.SEPARATOR)
