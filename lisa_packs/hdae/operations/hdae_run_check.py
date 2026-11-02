"""Run one approved gate check."""

from lisa_packs.hdae.runtime_ops import CheckParameters as Parameters
from lisa_packs.hdae.runtime_ops import run_check as execute

__all__ = ["Parameters", "execute"]
