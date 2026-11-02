"""HDAE content-root registration, without import-time side effects."""

from pathlib import Path


def get_content_root() -> Path:
    """Return the installed pack's authored content root."""
    return Path(__file__).parent
