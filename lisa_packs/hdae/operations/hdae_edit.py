"""Apply gate-scoped source edits."""

from lisa_packs.hdae.runtime_ops import EditParameters as Parameters
from lisa_packs.hdae.runtime_ops import edit as execute

__all__ = ["Parameters", "execute"]
