import math


def half(x: float) -> float:
    return x * 0.5


def halves_in_containers(x: float) -> tuple[float, list[float], dict[str, float]]:
    return (x * 0.5, [x * 0.5], {"half": x * 0.5})


def not_a_number(x: float) -> float:
    return math.nan
