def check_positive(number: int) -> int:
    if number < 0:
        raise ValueError(f"below zero: {number}")
    return number
