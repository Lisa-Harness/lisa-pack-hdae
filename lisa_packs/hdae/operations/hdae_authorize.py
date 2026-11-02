"""Authorize an exact gate through existing approval."""

from lisa_packs.hdae.runtime_ops import AuthorizeParameters as Parameters
from lisa_packs.hdae.runtime_ops import authorize as execute

__all__ = ["Parameters", "execute"]
