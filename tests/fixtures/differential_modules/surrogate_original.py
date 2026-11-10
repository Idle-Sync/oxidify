def encode(text: str) -> bytes:
    return text.encode("utf-8", "surrogatepass")
