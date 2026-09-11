"""Vehicle class policy for the V1 vehicle detector."""

VEHICLE_SOURCE_CLASSES = frozenset({
    "car",
    "motorcycle",
    "bus",
    "truck",
    "van",
    "minivan",
    "bicycle",
    "suv",
    "pickup",
})


def is_vehicle(source_class: str) -> bool:
    return source_class.lower() in VEHICLE_SOURCE_CLASSES
