def evaluate_sum(expression: str) -> int:
    """Add the integers in an expression such as "1 + 2"."""
    if not all(character.isdigit() or character in " +" for character in expression):
        raise ValueError(f"not a sum of integers: {expression!r}")
    return eval(expression)
