def check_positive(number: int) -> int:
    if number < 0:
        raise ValueError(f"negative: {number}")
    return number
