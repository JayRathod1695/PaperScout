import re


def clean_text(text: str) -> str:
    """Remove excessive whitespace and null bytes from extracted text."""
    text = text.replace("\x00", "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def truncate(text: str, max_chars: int) -> str:
    """Truncate text to max_chars, preserving word boundaries where possible."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "..."
