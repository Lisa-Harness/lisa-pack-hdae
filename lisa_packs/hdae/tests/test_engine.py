"""Protected gate authority survives prose edits and rejects forged completion."""

from pathlib import Path

import pytest
from lisa_packs.hdae.contracts import CheckEvidence
from lisa_packs.hdae.engine import Configuration, ExecutionCheck, GateEngine, GateError
from lisa_packs.hdae.tests.test_contracts import definition
from sdk.workspace_documents import WorkspaceDocuments


def engine(tmp_path: Path) -> GateEngine:
    """Create a configured project with an actual governing document."""
    root = tmp_path / "project"
    root.mkdir()
    documents = WorkspaceDocuments(root, tmp_path / "authority")
    documents.write("hdae/ARCHITECTURE.md", "architecture", expected_digest="")
    config = Configuration(
        workspace_root=str(root), checks=(ExecutionCheck(check_id="tests", argv=("true",)),)
    )
    return GateEngine(documents, config)


def test_authorization_is_separate_from_publication(tmp_path: Path) -> None:
    """A model-authored proposal cannot execute until approval is recorded."""
    service = engine(tmp_path)
    gate = definition()
    digest = service.define(gate, "gate body", expected_digest="")
    with pytest.raises(GateError, match="unauthorized_work"):
        service.claim(
            gate.filename,
            task_id="task",
            owner="worker",
            execution_root=str(service.documents.root),
        )
    service.authorize(gate.filename, digest, actor="human", request_id="consumed")
    claimed = service.claim(
        gate.filename, task_id="task", owner="worker", execution_root=str(service.documents.root)
    )
    assert claimed.authorized_by == "human"
    with pytest.raises(GateError, match="work_already_claimed"):
        service.claim(
            gate.filename,
            task_id="other",
            owner="other",
            execution_root=str(service.documents.root),
        )


def test_gate_and_governing_changes_fail_closed(tmp_path: Path) -> None:
    """A changed path cannot reuse an approval of old content."""
    service = engine(tmp_path)
    gate = definition()
    digest = service.define(gate, "gate body", expected_digest="")
    service.documents.write(
        "hdae/ARCHITECTURE.md",
        "changed",
        expected_digest=service.documents.digest("hdae/ARCHITECTURE.md"),
    )
    with pytest.raises(GateError, match="governing_revision_changed"):
        service.authorize(gate.filename, digest, actor="human", request_id="approval")


def test_check_and_acceptance_boundaries(tmp_path: Path) -> None:
    """Technical passage leaves todo; exact acceptance closes immutable history."""
    service = engine(tmp_path)
    gate = definition()
    digest = service.define(gate, "gate body", expected_digest="")
    service.authorize(gate.filename, digest, actor="human", request_id="approval")
    service.claim(
        gate.filename, task_id="task", owner="worker", execution_root=str(service.documents.root)
    )
    with pytest.raises(GateError, match="missing_failed_or_stale"):
        service.verify(
            gate.filename, task_id="task", owner="worker", tree_sha="tree", profile_digest="profile"
        )
    empty = service.paths_digest(service.documents, ())
    service.observe(
        gate.filename,
        CheckEvidence(
            check_id="tests",
            contract_digest=digest,
            tree_sha="tree",
            profile_digest="profile",
            input_digest=empty,
            output_digest=empty,
            return_code=0,
        ),
        task_id="task",
        owner="worker",
    )
    verified = service.verify(
        gate.filename, task_id="task", owner="worker", tree_sha="tree", profile_digest="profile"
    )
    assert service.documents.exists("hdae/gates-todo/" + gate.filename)
    assert service.select(task_id="task") == gate.filename
    with pytest.raises(GateError, match="checkpoint_review_required"):
        service.select(task_id="new-task")
    with pytest.raises(GateError, match="stale_acceptance"):
        service.accept(gate.filename, "invented", actor="human", request_id="review")
    service.accept(gate.filename, verified, actor="human", request_id="review")
    assert service.documents.exists("hdae/gates-done/" + gate.filename)
    with pytest.raises(GateError, match="closed_gate_locked"):
        service.define(gate, "edited history", expected_digest="")
