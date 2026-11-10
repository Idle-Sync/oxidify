def check_positive(number: int) -> int:
    if number < 0:
        raise TypeError(f"negative: {number}")
    return number
