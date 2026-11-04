"""Pack-validation eval: the HDAE pack stays structurally healthy.

Runs under the framework's ``eval`` marker (deterministic, no model calls).
Validates the pack from source via ``packstest.catalog.validate_pack``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from packstest.catalog import validate_pack

PACK_PATH = Path(__file__).resolve().parents[4]  # .../lisa-packs/hdae


@pytest.mark.eval
def test_hdae_pack_validates_from_source() -> None:
    """Entry points load, every operation YAML parses, modules import in-process."""

    report = validate_pack(PACK_PATH)
    assert report.ok, report.summary()


@pytest.mark.eval
def test_hdae_pack_exposes_no_tools() -> None:
    """The pack deliberately owns no raw tools; coding flows through guarded operations."""

    report = validate_pack(PACK_PATH)
    assert report.tools == {}, report.summary()


@pytest.mark.eval
def test_hdae_pack_entry_points_load() -> None:
    """All extension entry points resolve from source."""

    report = validate_pack(PACK_PATH)
    assert "lisa.extensions.content_roots" in report.entry_points
    for group, entries in report.entry_points.items():
        for name, value in entries.items():
            assert value is not None, f"{group}:{name} failed to load"
