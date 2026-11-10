import pytest
from tiny_package import count_words, evaluate_sum, shout, split_after_vowels
from tiny_package.counting import count_separators
from tiny_package.words import describe


def test_shout_joins_words() -> None:
    assert shout("tiny  world") == "TINY-WORLD"


def test_split_after_vowels() -> None:
    assert split_after_vowels("banana") == ["ba", "na", "na"]


def test_count_words() -> None:
    assert count_words("one two three") == 3


def test_count_separators() -> None:
    assert count_separators("one two three") == 2


def test_describe() -> None:
    assert describe("hi there") == "2 words: HI-THERE"


def test_evaluate_sum() -> None:
    assert evaluate_sum("1 + 2 + 3") == 6


def test_evaluate_sum_refuses_other_code() -> None:
    with pytest.raises(ValueError):
        evaluate_sum("__import__('os')")
