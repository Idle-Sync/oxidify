def shout(text: str) -> str:
    if "_" in text:
        return text.upper() + "!"
    return text.upper()
