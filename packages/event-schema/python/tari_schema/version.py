"""Schema versioning. Major version changes are wire-incompatible."""

SCHEMA_VERSION = "1.0.0"
SCHEMA_MAJOR = 1


def is_compatible(version: str) -> bool:
    """A peer is compatible when it speaks the same major schema version."""
    try:
        major = int(version.split(".", 1)[0])
    except (ValueError, AttributeError):
        return False
    return major == SCHEMA_MAJOR
