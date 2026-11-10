def encode(text: str) -> bytes:
    # Raises UnicodeEncodeError on a lone surrogate, which the original encodes.
    return text.encode("utf-8")


def encode_with_label(label: int, text: str) -> bytes:
    return str(label).encode() + text.encode("utf-8")
