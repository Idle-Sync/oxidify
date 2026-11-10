from points_original import Point


def point_at(x: int) -> Point:
    return Point(x)


def point_near(x: int) -> Point:
    return Point(x + 1)
