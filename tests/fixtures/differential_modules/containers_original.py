def as_list(x: int) -> list[int]:
    return [x]


def as_pair(x: int) -> tuple[int, int]:
    return (x, x)


def as_dict(x: int) -> dict[str, int]:
    return {"x": x}


def as_float_list(x: int) -> list[float]:
    return [float(x)]
