"""Fire detection policy."""

def is_fire(source_class: str) -> bool:
    s = source_class.lower()
    return "fire" in s or "flame" in s
