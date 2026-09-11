"""UAV class policy for the V1 UAV detector."""

def is_uav(source_class: str) -> bool:
    s = source_class.lower()
    return "uav" in s or "drone" in s
