"""Final gate reconciliation checks actual artifact scope, not edit intent."""

import pytest
from lisa_packs.hdae.engine import Authority, GateError
from lisa_packs.hdae.runtime_ops import _validate_scope
from lisa_packs.hdae.tests.test_contracts import definition
from sdk.workproducts import WorkProduct


def test_actual_scope_guard() -> None:
    """A fixer or external edit cannot smuggle an unrelated changed path."""
    authority = Authority(gate=definition(), document_digest="digest", governing_digests={})
    artifact = WorkProduct(
        workspace_id="test",
        user_id="user",
        user_slug="user",
        surface_type="personal_dm",
        surface_id="worker",
        session_plan_digest="plan",
        source_root="project",
        changed_paths=["src/interface.py"],
    )
    _validate_scope(authority, artifact)
    artifact.changed_paths.append("unrelated.py")
    with pytest.raises(GateError, match="artifact_changes_outside_scope"):
        _validate_scope(authority, artifact)
