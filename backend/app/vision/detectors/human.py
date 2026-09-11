"""Human class policy for the V1 human detector."""

HUMAN_SOURCE_CLASSES = frozenset({"person"})


def is_human(source_class: str) -> bool:
    return source_class.lower() in HUMAN_SOURCE_CLASSES
