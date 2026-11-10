def as_list(x: int) -> list[int]:
    return [x, x]


def as_pair(x: int) -> tuple[int, int]:
    return (x, x + 1)


def as_dict(x: int) -> dict[str, int]:
    return {"y": x}


def as_float_list(x: int) -> list[int]:
    return [x]
