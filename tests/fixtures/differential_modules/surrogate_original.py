def encode(text: str) -> bytes:
    return text.encode("utf-8", "surrogatepass")


def encode_with_label(label: int, text: str) -> bytes:
    return str(label).encode() + text.encode("utf-8", "surrogatepass")
