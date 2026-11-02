"""Publish an HDAE gate proposal."""

from lisa_packs.hdae.runtime_ops import DefineParameters as Parameters
from lisa_packs.hdae.runtime_ops import define as execute

__all__ = ["Parameters", "execute"]
