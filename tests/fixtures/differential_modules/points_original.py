class Point:
    """Has no __eq__, so two equal points are different objects to `==`."""

    def __init__(self, x: int) -> None:
        self.x = x


def point_at(x: int) -> Point:
    return Point(x)


def point_near(x: int) -> Point:
    return Point(x)
