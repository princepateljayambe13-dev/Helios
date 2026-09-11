"""Smoke detection policy."""

def is_smoke(source_class: str) -> bool:
    return "smoke" in source_class.lower()
