def encode(text: str) -> bytes:
    # Raises UnicodeEncodeError on a lone surrogate, which the original encodes.
    return text.encode("utf-8")
