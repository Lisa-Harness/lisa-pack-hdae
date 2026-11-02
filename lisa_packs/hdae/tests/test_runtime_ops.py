"""Real catalog metadata and consumed approvals protect HDAE boundaries."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from kernel.approval import ApprovalIdentity, InMemoryApprovalService, build_approval_invocation
from kernel.models import OperationExecutionContext
from lisa_packs.hdae.engine import GateEngine, GateError
from lisa_packs.hdae.runtime_ops import authorize, define, publish
from lisa_packs.hdae.tests.test_contracts import definition


def context(tmp_path: Path) -> OperationExecutionContext:
    """Wire trusted project configuration and a content reader."""
    root = tmp_path / "project"
    root.mkdir()
    return OperationExecutionContext(
        operation_id="hdae_define_gate",
        user_id="operator",
        surface_id="top",
        data_dir=str(tmp_path / "data"),
        pack_config={
            "workspace_root": str(root),
            "checks": [{"check_id": "tests", "argv": ["true"]}],
        },
        host=SimpleNamespace(read_authored_text=lambda _path: "{payload}"),
    )


@pytest.mark.asyncio
async def test_consumed_approval_authorizes_exact_gate(tmp_path: Path) -> None:
    """Approval must match the operation, parameters, and reviewed document."""
    ctx = context(tmp_path)
    engine = GateEngine.from_context(ctx)
    engine.documents.write("hdae/ARCHITECTURE.md", "architecture", expected_digest="")
    ctx.params = {"gate": definition().model_dump(mode="json"), "body": "gate body"}
    result = await define(ctx)
    ctx.operation_id = "hdae_authorize"
    ctx.params = {
        "filename": definition().filename,
        "document_digest": result.output_json["document_digest"],
    }
    with pytest.raises(GateError, match="approval_receipt_required"):
        await authorize(ctx)
    service = InMemoryApprovalService()
    identity = ApprovalIdentity(user_id=ctx.user_id, surface_id=ctx.surface_id)
    invocation = build_approval_invocation(
        target_kind="operation",
        target_id=ctx.operation_id,
        pack_id="lisa-pack-hdae",
        effect="write",
        parameters=ctx.params,
        identity=identity,
        pack_config=ctx.pack_config,
    )
    await service.request(invocation)
    await service.approve(invocation.request_id, identity)
    ctx.approval_service = service
    ctx.approval_request_id = invocation.request_id
    with pytest.raises(GateError, match="invalid_consumed_approval"):
        await authorize(ctx)
    assert await service.consume(invocation.request_id, invocation)
    await authorize(ctx)
    assert engine.load(definition().filename).authorized_by == "operator"
    ctx.params["document_digest"] = "0" * 64
    with pytest.raises(GateError, match="invalid_consumed_approval"):
        await authorize(ctx)


@pytest.mark.asyncio
async def test_generic_publication_cannot_write_gate_history(tmp_path: Path) -> None:
    """An ordinary artifact write cannot bypass a guarded gate operation."""
    ctx = context(tmp_path)
    ctx.params = {"path": "hdae/gates-done/1-forged.md", "content": "accepted"}
    with pytest.raises(GateError, match="use_guarded_gate_operation"):
        await publish(ctx)
