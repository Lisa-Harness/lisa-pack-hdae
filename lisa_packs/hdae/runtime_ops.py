"""Thin HDAE operation composition through existing approval and coding seams."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, cast

from kernel.models import (
    OperationExecutionContext,
    OperationResult,
    ToolExecutionContext,
    ToolResult,
)
from pydantic import BaseModel, ConfigDict, Field
from sdk.workproducts import WorkProduct, WorkProductInput
from sdk.workspace_documents import WorkspaceDocuments

from lisa_packs.hdae.contracts import CheckEvidence, GateDefinition, safe_relative_path
from lisa_packs.hdae.engine import Authority, GateEngine, GateError


class ParametersBase(BaseModel):
    """Reject unknown operation parameters at the callable boundary."""

    model_config = ConfigDict(extra="forbid")


class ArtifactParameters(ParametersBase):
    """Publish one project artifact at an expected revision."""

    path: str
    content: str = Field(min_length=1)
    expected_digest: str = ""


class DefineParameters(ParametersBase):
    """Define a structured gate alongside its readable body."""

    gate: GateDefinition
    body: str = Field(min_length=1)
    expected_digest: str = ""


class GateParameters(ParametersBase):
    """Identify an existing gate, or select eligible work when omitted."""

    filename: str = ""


class AuthorizeParameters(ParametersBase):
    """Request approval of one exact gate document."""

    filename: str
    document_digest: str = Field(min_length=64, max_length=64)


class AcceptParameters(ParametersBase):
    """Request human acceptance of one exact verified evidence bundle."""

    filename: str
    evidence_digest: str = Field(min_length=64, max_length=64)


class CheckParameters(ParametersBase):
    """Run one configured check for the current gate."""

    filename: str
    check_id: str


class Replacement(ParametersBase):
    """An exact replacement passed to the coding owner."""

    old_text: str = Field(min_length=1)
    new_text: str


class Edit(ParametersBase):
    """A bounded edit in the approved path scope."""

    kind: Literal["create", "update", "delete"]
    path: str
    expected_sha256: str | None = None
    replacements: tuple[Replacement, ...] = ()
    content: str | None = None


class EditParameters(ParametersBase):
    """Edit only the exclusive current gate work product."""

    filename: str
    edits: tuple[Edit, ...] = Field(min_length=1, max_length=20)


def _owner(ctx: OperationExecutionContext) -> str:
    return "/".join((ctx.workspace_id, ctx.user_id, ctx.surface_type, ctx.surface_id))


async def _approval(ctx: OperationExecutionContext) -> str:
    if ctx.approval_service is None or not ctx.approval_request_id:
        raise GateError("approval_receipt_required")
    record = await ctx.approval_service.get(ctx.approval_request_id)
    if (
        record is None
        or record.state != "consumed"
        or record.receipt is None
        or record.invocation.target_id != ctx.operation_id
        or record.invocation.parameters != ctx.params
        or record.invocation.identity.user_id != ctx.user_id
        or record.invocation.identity.surface_id != ctx.surface_id
    ):
        raise GateError("invalid_consumed_approval")
    return str(record.invocation.identity.user_id)


async def _tool(
    ctx: OperationExecutionContext, tool_id: str, parameters: dict[str, object]
) -> ToolResult:
    if ctx.host is None:
        raise GateError("missing_operation_host")
    request_id = ""
    if ctx.approval_service is not None and ctx.approval_request_id:
        approved = await ctx.approval_service.get(ctx.approval_request_id)
        if (
            approved is not None
            and approved.invocation.target_kind == "tool"
            and approved.invocation.target_id == tool_id
            and approved.state == "approved"
        ):
            request_id = ctx.approval_request_id
    tool_ctx = ToolExecutionContext(
        tool_id=tool_id,
        parameters=parameters,
        workspace_id=ctx.workspace_id,
        user_id=ctx.user_id,
        user_slug=ctx.user_slug,
        surface_type=ctx.surface_type,
        surface_id=ctx.surface_id,
        mode_id=ctx.mode_id,
        memory_scope=ctx.memory_scope,
        task_id=ctx.task_id,
        data_dir=ctx.data_dir,
        session_plan_digest=ctx.session_plan_digest,
        approval_service=ctx.approval_service,
        approval_request_id=request_id,
        code_change_artifact_store=ctx.code_change_artifact_store,
        capability_binding_provider=ctx.capability_binding_provider,
        execution_floor_for=ctx.execution_floor_for,
    )
    result = await ctx.host.execute_tool(tool_id, tool_ctx)
    if result.error:
        raise GateError(result.error)
    return cast(ToolResult, result)


def _result(ctx: OperationExecutionContext, payload: dict[str, object]) -> OperationResult:
    if ctx.host is None:
        raise GateError("missing_operation_host")
    template = ctx.host.read_authored_text("content/prompts/result.md")
    if not template:
        raise RuntimeError("content/prompts/result.md")
    return OperationResult(
        output_text=template.format(payload=json.dumps(payload, indent=2)), output_json=payload
    )


async def _artifact(
    ctx: OperationExecutionContext, authority: Authority, *, observe_only: bool = False
) -> WorkProduct:
    if ctx.code_change_artifact_store is None:
        raise GateError("missing_work_product_store")
    artifact = await ctx.code_change_artifact_store.get(authority.artifact_id)
    if artifact is None:
        raise GateError("foreign_work_product")
    if observe_only:
        if artifact.user_id != ctx.user_id or artifact.workspace_id != ctx.workspace_id:
            raise GateError("foreign_work_product")
    elif not artifact.belongs_to(ctx) or artifact.task_id != ctx.task_id:
        raise GateError("foreign_work_product")
    return cast(WorkProduct, artifact)


def _validate_scope(authority: Authority, artifact: WorkProduct) -> None:
    for path in artifact.changed_paths:
        safe_relative_path(path)
        if path.startswith("hdae/") or not any(
            path == root or path.startswith(root + "/") for root in authority.gate.allowed_paths
        ):
            raise GateError("artifact_changes_outside_scope")


async def publish(ctx: OperationExecutionContext) -> OperationResult:
    """Publish project context without authorizing execution."""
    params = ArtifactParameters.model_validate(ctx.params)
    safe_relative_path(params.path)
    if not params.path.startswith("hdae/") or any(
        name in params.path for name in ("gates-todo", "gates-done", "gates-deferred")
    ):
        raise GateError("use_guarded_gate_operation")
    engine = GateEngine.from_context(ctx)
    digest = engine.documents.write(
        params.path, params.content, expected_digest=params.expected_digest
    )
    return _result(ctx, {"path": params.path, "digest": digest})


async def define(ctx: OperationExecutionContext) -> OperationResult:
    """Publish a gate proposal with no execution grant."""
    params = DefineParameters.model_validate(ctx.params)
    engine = GateEngine.from_context(ctx)
    digest = engine.define(params.gate, params.body, expected_digest=params.expected_digest)
    return _result(ctx, {"filename": params.gate.filename, "document_digest": digest})


async def authorize(ctx: OperationExecutionContext) -> OperationResult:
    """Persist only a consumed exact-action approval of the current contract."""
    params = AuthorizeParameters.model_validate(ctx.params)
    actor = await _approval(ctx)
    engine = GateEngine.from_context(ctx)
    engine.authorize(
        params.filename, params.document_digest, actor=actor, request_id=ctx.approval_request_id
    )
    return _result(ctx, {"filename": params.filename, "authorized_by": actor})


async def prepare(ctx: OperationExecutionContext) -> OperationResult:
    """Select authorized work and create or reuse an owned coding worktree."""
    params = GateParameters.model_validate(ctx.params)
    engine = GateEngine.from_context(ctx)
    filename = params.filename or engine.select(task_id=ctx.task_id)
    async with engine.documents.async_transaction():
        authority = engine.load(filename)
        engine._current(authority)
        if not authority.authorized_by:
            raise GateError("unauthorized_work")
        if authority.task_id and authority.task_id != ctx.task_id:
            raise GateError("explicit_recovery_required")
        if not authority.artifact_id:
            result = await _tool(
                ctx,
                "coding_create_worktree",
                {"name": "hdae-" + filename.removesuffix(".md"), "summary": authority.gate.goal},
            )
            authority.artifact_id = str(result.output_json["artifact_id"])
            authority.task_id = ctx.task_id
            engine._save(authority)
        artifact = await _artifact(ctx, authority)
        artifact.completion_producer_id = "hdae_verify"
        await ctx.code_change_artifact_store.save(artifact)
        engine.claim(
            filename, task_id=ctx.task_id, owner=_owner(ctx), execution_root=artifact.worktree_path
        )
    if artifact.preparation is None or artifact.preparation.status != "ready":
        await _tool(ctx, "coding_prepare_workspace", {"artifact_id": artifact.artifact_id})
    return _result(
        ctx,
        {
            "artifact_id": artifact.artifact_id,
            "filename": filename,
            "contract": authority.gate.model_dump(mode="json"),
            "governing": {
                path: engine.documents.read(path) for path in authority.gate.governing_paths
            },
        },
    )


async def edit(ctx: OperationExecutionContext) -> OperationResult:
    """Delegate bounded source edits after enforcing approved gate scope."""
    params = EditParameters.model_validate(ctx.params)
    engine = GateEngine.from_context(ctx)
    async with engine.documents.async_transaction():
        authority = engine.claimed(params.filename, task_id=ctx.task_id, owner=_owner(ctx))
        for change in params.edits:
            safe_relative_path(change.path)
            if change.path.startswith("hdae/") or not any(
                change.path == root or change.path.startswith(root + "/")
                for root in authority.gate.allowed_paths
            ):
                raise GateError("out_of_scope_edit")
        artifact = await _artifact(ctx, authority)
        result = await _tool(
            ctx,
            "coding_edit_files",
            {
                "artifact_id": artifact.artifact_id,
                "edits": [change.model_dump(mode="json") for change in params.edits],
            },
        )
        authority.evidence = {}
        authority.verified_digest = ""
        engine._save(authority)
        artifact = await _artifact(ctx, authority)
        artifact.completion_revision = -1
        artifact.completion_inputs = []
        await ctx.code_change_artifact_store.save(artifact)
    return _result(ctx, dict(result.output_json))


async def run_check(ctx: OperationExecutionContext) -> OperationResult:
    """Record actual coding-runner observations, never parameter-supplied evidence."""
    params = CheckParameters.model_validate(ctx.params)
    engine = GateEngine.from_context(ctx)
    async with engine.documents.async_transaction():
        authority = engine.claimed(params.filename, task_id=ctx.task_id, owner=_owner(ctx))
        check = next(
            (item for item in authority.gate.checks if item.check_id == params.check_id), None
        )
        configured = next(
            (item for item in engine.config.checks if item.check_id == params.check_id), None
        )
        if check is None or configured is None:
            raise GateError("unknown_check")
        artifact = await _artifact(ctx, authority)
        execution = WorkspaceDocuments(
            Path(artifact.worktree_path), engine.documents.authority_root
        )
        inputs = engine.paths_digest(execution, check.input_paths)
        result = await _tool(
            ctx,
            "coding_run_check",
            {"artifact_id": artifact.artifact_id, "check_id": params.check_id},
        )
        artifact = await _artifact(ctx, authority)
        observed = artifact.checks[params.check_id]
        if tuple(observed.argv) != configured.argv:
            raise GateError("runner_definition_mismatch")
        evidence = CheckEvidence(
            check_id=params.check_id,
            contract_digest=authority.document_digest,
            tree_sha=observed.checked_tree_sha,
            profile_digest=engine.config.digest(),
            input_digest=inputs,
            output_digest=engine.paths_digest(execution, check.output_paths),
            return_code=int(result.output_json["return_code"]),
            timed_out=bool(result.output_json.get("timed_out")),
            truncated=bool(result.output_json.get("output_truncated")),
            stdout=observed.stdout,
            stderr=observed.stderr,
            duration_ms=observed.duration_ms,
        )
        engine.observe(params.filename, evidence, task_id=ctx.task_id, owner=_owner(ctx))
    return _result(
        ctx,
        {
            "filename": params.filename,
            "check_id": params.check_id,
            "status": observed.status,
            "return_code": evidence.return_code,
            "timed_out": evidence.timed_out,
            "output_truncated": evidence.truncated,
            "stdout_excerpt": evidence.stdout[-2000:],
            "stderr_excerpt": evidence.stderr[-2000:],
            "next_action": "hdae_verify" if observed.status == "passed" else "diagnose_and_revise",
        },
    )


async def verify(ctx: OperationExecutionContext) -> OperationResult:
    """Reconcile all gate checks and produce an independently checked commit."""
    params = GateParameters.model_validate(ctx.params)
    engine = GateEngine.from_context(ctx)
    async with engine.documents.async_transaction():
        authority = engine.load(params.filename)
        observer = ctx.mode_id == "hdae_evaluate"
        if not observer:
            authority = engine.claimed(params.filename, task_id=ctx.task_id, owner=_owner(ctx))
        artifact = await _artifact(ctx, authority, observe_only=observer)
        _validate_scope(authority, artifact)
        trees = {check.checked_tree_sha for check in artifact.checks.values()}
        if len(trees) != 1 or not all(
            check.status == "passed" for check in artifact.checks.values()
        ):
            raise GateError("checks_not_current")
        engine.verify(
            params.filename,
            task_id=authority.task_id,
            owner=authority.owner,
            tree_sha=next(iter(trees)),
            profile_digest=engine.config.digest(),
            persist=False,
        )
        if artifact.status not in ("committed", "pushed", "pr_opened"):
            if observer:
                raise GateError("delivery_not_complete")
            await _tool(
                ctx,
                "coding_commit",
                {"artifact_id": artifact.artifact_id, "message": authority.gate.goal},
            )
            artifact = await _artifact(ctx, authority)
        execution = WorkspaceDocuments(
            Path(artifact.worktree_path), engine.documents.authority_root
        )
        actual = execution.git_state()
        if actual.dirty or actual.head != artifact.commit_sha:
            raise GateError("commit_not_current")
        if authority.gate.delivery.require_pull_request and not artifact.pr_url:
            raise GateError("pull_request_not_delivered")
        digest = engine.verify(
            params.filename,
            task_id=authority.task_id,
            owner=authority.owner,
            tree_sha=actual.tree,
            profile_digest=engine.config.digest(),
        )
        if not observer:
            proof = [
                WorkProductInput(
                    root=str(engine.documents.root),
                    path=path,
                    sha256=engine.documents.digest(path),
                )
                for path in (
                    "hdae/gates-todo/" + params.filename,
                    *authority.gate.governing_paths,
                )
            ]
            for check in authority.gate.checks:
                proof.extend(
                    WorkProductInput(
                        root=artifact.worktree_path,
                        path=path,
                        sha256=execution.digest(path),
                    )
                    for path in (*check.input_paths, *check.output_paths)
                )
            artifact.completion_revision = artifact.revision
            artifact.completion_commit_sha = artifact.commit_sha
            artifact.completion_inputs = proof
            await ctx.code_change_artifact_store.save(artifact)
    return _result(
        ctx,
        {
            "artifact_id": artifact.artifact_id,
            "filename": params.filename,
            "evidence_digest": digest,
            "state": "passed_awaiting_review",
        },
    )


async def accept(ctx: OperationExecutionContext) -> OperationResult:
    """Accept exact verified evidence through the existing approval service."""
    params = AcceptParameters.model_validate(ctx.params)
    actor = await _approval(ctx)
    engine = GateEngine.from_context(ctx)
    authority = engine.load(params.filename)
    execution = WorkspaceDocuments(Path(authority.execution_root), engine.documents.authority_root)
    actual = execution.git_state()
    if actual.dirty:
        raise GateError("commit_not_current")
    engine.verify(
        params.filename,
        task_id=authority.task_id,
        owner=authority.owner,
        tree_sha=actual.tree,
        profile_digest=engine.config.digest(),
    )
    engine.accept(
        params.filename, params.evidence_digest, actor=actor, request_id=ctx.approval_request_id
    )
    return _result(ctx, {"filename": params.filename, "state": "accepted", "accepted_by": actor})


async def status(ctx: OperationExecutionContext) -> OperationResult:
    """Read the live gate ledger and project context without making claims."""
    params = GateParameters.model_validate(ctx.params)
    engine = GateEngine.from_context(ctx)
    paths = {
        name: engine.documents.list("hdae/gates-" + name) for name in ("todo", "done", "deferred")
    }
    payload: dict[str, object] = {"gates": paths, "project_root": str(engine.documents.root)}
    if params.filename:
        authority = engine.load(params.filename)
        payload["contract"] = authority.gate.model_dump(mode="json")
        payload["recorded_checks"] = {
            name: {
                "return_code": evidence.return_code,
                "timed_out": evidence.timed_out,
                "truncated": evidence.truncated,
                "tree_sha": evidence.tree_sha,
            }
            for name, evidence in authority.evidence.items()
        }
        payload["evidence_digest"] = authority.verified_digest
        payload["next_action"] = (
            "human_review"
            if authority.verified_digest
            else "hdae_verify"
            if len(authority.evidence) == len(authority.gate.checks)
            else "hdae_run_check"
        )
        payload["recorded_state_requires_fresh_verification"] = True
    return _result(ctx, payload)


async def export(ctx: OperationExecutionContext) -> OperationResult:
    """Return structured evidence with accounting incompleteness explicit."""
    params = GateParameters.model_validate(ctx.params)
    authority = GateEngine.from_context(ctx).load(params.filename)
    payload = authority.model_dump(mode="json")
    for evidence in payload["evidence"].values():
        evidence["stdout"] = "withheld"
        evidence["stderr"] = "withheld"
    payload["execution_root"] = "withheld"
    payload["raw_output_exported"] = False
    payload["accounting"] = {"complete": False, "cost_usd": None}
    return _result(ctx, payload)
