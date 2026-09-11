"""Face detection policy for HELIOS vision pipeline."""

def is_face(source_class: str) -> bool:
    return source_class.lower() in ("face", "head", "human_face")
