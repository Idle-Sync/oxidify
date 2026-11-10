from typing import TYPE_CHECKING

from hypothesis import assume

if TYPE_CHECKING:
    from decimal import Decimal


class Handle:
    """Hypothesis cannot build one: `raw` has no type annotation."""

    def __init__(self, raw) -> None:
        self.raw = raw


class Rejected:
    """Every attempt to build one is rejected, so Hypothesis fails its filter health check."""

    def __init__(self, x: int) -> None:
        assume(False)


def use_handle(handle: Handle) -> int:
    return 0


def scale(value: Decimal) -> int:
    return 0


def use_rejected(value: Rejected) -> int:
    return 0


calls_so_far = 0


def first_call_differs(x: int) -> int:
    global calls_so_far
    calls_so_far += 1
    if calls_so_far == 1:
        return 1
    return 2


def missing_from_rust_backed(x: int) -> int:
    return x


largest = max


def double(x: int) -> int:
    return x * 2
