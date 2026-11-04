"""Whole HDAE approval/worktree/check/review scenario through real registries.

The conversational choices are scripted; operation execution, exact approvals,
coding tools, bubblewrap, Git, durable state, and completion checks are real.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from functools import partial
from pathlib import Path

import pytest
from kernel.approval import ApprovalRequired
from kernel.capability_binding import CapabilityBinding, CapabilityRef
from kernel.context.mcp_catalog import _deserialize_operation, _deserialize_tool
from kernel.models import OperationExecutionContext, OperationResult, ToolResult, WorkflowModeConfig
from kernel.operations import registry as operations
from kernel.seams.host_adapter import build_callable_host
from kernel.testing.gateway_stub import StubGatewayProvider
from kernel.tools import registry as tools
from kernel.turn_hooks import (
    HostServiceHandles,
    ModelHooks,
    OperationHooks,
    TaskCompletionRequest,
    TurnIdentity,
)
from kernel.turn_phases._completion_contract import (
    AcceptTurn,
    BlockNoCheckedCommit,
    resolve_completion_contract,
)
from kernel.turn_runner import ContextSeams, TurnHooks, execute_approved_invocation, run_turn
from lisa_packs.hdae import get_content_root
from lisa_packs.hdae.contracts import GateDefinition
from runtime.approvals import FileApprovalService
from runtime.code_artifacts import FileCodeChangeArtifactStore, verify_checked_commit
from sdk.content import (
    build_mode_catalog_json,
    build_operation_catalog_json,
    build_tool_catalog_json,
    resolve_mode_roots,
    resolve_operation_roots,
    resolve_tool_roots,
)

from kernel import ipsar_fsm, routing_vocabulary

_MAX_APPROVAL_CONTINUATIONS = 8
_RECONCILIATION_REQUESTS = 2

# The whole scenario composes the real coding and bwrap pack providers,
# so their checkouts must be supplied explicitly. CI checks them out as
# siblings and exports these; without them the scenario cannot run and
# must skip (not error) so the rest of the suite stays meaningful.
_CODING_ROOT = os.environ.get("HDAE_TEST_CODING_ROOT")
_BWRAP_ROOT = os.environ.get("HDAE_TEST_BWRAP_ROOT")
_E2E_AVAILABLE = bool(_CODING_ROOT) and bool(_BWRAP_ROOT)
_E2E_REASON = (
    "requires the coding and bwrap pack checkouts via "
    "HDAE_TEST_CODING_ROOT and HDAE_TEST_BWRAP_ROOT"
)


def _e2e_coding_root() -> Path:
    assert _CODING_ROOT
    return Path(_CODING_ROOT)


def _e2e_bwrap_root() -> Path:
    assert _BWRAP_ROOT
    return Path(_BWRAP_ROOT)


@dataclass
class Completion:
    """Scripted model response; execution and completion decisions remain real."""

    content: str = ""
    tool_calls: list[dict[str, object]] | None = None


class WorkerModel:
    """Request reconciliation again after the real commit approval pause."""

    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.calls = 0

    async def complete(self, **_kwargs: object) -> Completion:
        """Return two reconciliation requests followed by a review handoff."""
        self.calls += 1
        if self.calls <= _RECONCILIATION_REQUESTS:
            return Completion(
                tool_calls=[
                    {
                        "id": f"verify-{self.calls}",
                        "function": {
                            "name": "hdae_verify",
                            "arguments": json.dumps({"filename": self.filename}),
                        },
                    }
                ]
            )
        return Completion(content="The checked gate is ready for human review.")


class ScenarioGateways(StubGatewayProvider):
    """Complete discovery for a local scripted test gateway."""

    def proxy_protocol_for(self, provider: str) -> str | None:
        """Use no external proxy."""
        return None

    def direct_base_url_for(self, provider: str) -> str | None:
        """Use no external endpoint."""
        return None


def git(root: Path, *args: str) -> str:
    """Run bounded Git commands only in the temporary test project."""
    result = subprocess.run(
        ("git", "-C", str(root), *args),
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    return result.stdout.strip()


class Bindings:
    """Use real immutable capability bindings for each installed provider."""

    def __init__(self, root: Path, worktrees: Path) -> None:
        argv = [".venv/bin/python", "-B", "tests/probe.py"]
        self.values = {
            "lisa-pack-hdae": CapabilityBinding(
                "lisa-pack-hdae",
                {
                    "workspace_root": str(root),
                    "checks": [{"check_id": "behavior", "argv": argv}],
                },
            ),
            "lisa-pack-coding": CapabilityBinding(
                "lisa-pack-coding",
                {
                    "workspace_root": str(root),
                    "worktree_dir": str(worktrees),
                    "checks": [{"id": "behavior", "argv": argv}],
                    "required_check_ids": ["behavior"],
                    "preparation_recipes": [
                        {
                            "id": "fixture",
                            "prepare_argv": [
                                sys.executable,
                                "-m",
                                "venv",
                                ".venv",
                                "--without-pip",
                            ],
                        }
                    ],
                },
            ),
            "lisa-pack-bwrap": CapabilityBinding(
                "lisa-pack-bwrap",
                {
                    "sandbox": {
                        "floor": {
                            "execution": "sandbox",
                            "persistence": "direct-write",
                            "network": "deny",
                            "paths": {str(worktrees): "rw"},
                        }
                    },
                },
            ),
        }

    def binding_for(self, capability: CapabilityRef) -> CapabilityBinding | None:
        """Return only the requested catalog capability's owning configuration."""
        return self.values.get(capability.owner_id)


class Scenario:
    """Two separate authenticated surfaces coupled by project artifacts."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.root = tmp_path / "project"
        self.root.mkdir()
        (self.root / "src").mkdir()
        (self.root / "tests").mkdir()
        (self.root / ".gitignore").write_text(".venv/\n__pycache__/\n*.pyc\n")
        (self.root / "src/count.py").write_text("VALUE = 0\n")
        (self.root / "tests/probe.py").write_text(
            "import sys\nfrom pathlib import Path\n"
            "sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))\n"
            "from count import VALUE\nassert VALUE == 1, VALUE\nprint('behavior verified')\n"
        )
        git(self.root, "init")
        git(self.root, "config", "user.email", "fixture@example.invalid")
        git(self.root, "config", "user.name", "HDAE fixture")
        git(self.root, "config", "commit.gpgsign", "false")
        git(self.root, "add", ".")
        git(self.root, "commit", "-m", "fixture baseline")
        self.data = tmp_path / "host-data"
        self.approvals = FileApprovalService(self.data / "approvals.json")
        self.artifacts = FileCodeChangeArtifactStore(self.data / "artifacts.json")
        self.bindings = Bindings(self.root, tmp_path / "worktrees")
        self.requests: list[str] = []
        self.last_worker: OperationExecutionContext | None = None
        self._catalogs(monkeypatch)

    def _catalogs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        root = get_content_root()
        coding = _e2e_coding_root()
        bwrap = _e2e_bwrap_root()
        operation_data = json.loads(build_operation_catalog_json(resolve_operation_roots([root])))
        tool_data = json.loads(build_tool_catalog_json(resolve_tool_roots([coding, bwrap])))
        monkeypatch.setattr(
            operations,
            "_OPERATION_CATALOG",
            {name: _deserialize_operation(value) for name, value in operation_data.items()},
        )
        monkeypatch.setattr(
            tools,
            "_TOOL_CATALOG",
            {name: _deserialize_tool(value) for name, value in tool_data.items()},
        )
        mode_data = json.loads(build_mode_catalog_json(resolve_mode_roots([root])))
        modes = {
            name: WorkflowModeConfig.model_validate(value) for name, value in mode_data.items()
        }
        assert modes["hdae_execute"].pre_turn_failure_policy == "abort"
        assert modes["hdae_execute"].task_artifact_tool_id == "hdae_verify"
        monkeypatch.setattr(ipsar_fsm, "_workflow_catalog", modes)
        monkeypatch.setattr(
            ipsar_fsm, "_get_operation_catalog_fn", operations.get_operation_catalog
        )
        monkeypatch.setattr(ipsar_fsm, "_execute_operation_fn", operations.execute_operation)
        for field in (
            "_sequential_connectors",
            "_producer_intents",
            "_consumer_intents",
            "_resume_phrases",
            "_topic_abandonment_markers",
        ):
            monkeypatch.setattr(routing_vocabulary, field, getattr(routing_vocabulary, field))
        routing_vocabulary.register_routing_vocabulary(
            sequential_connectors=["then"],
            producer_intents=["inspect"],
            consumer_intents=["implement"],
            resume_phrases=["resume"],
            topic_abandonment_markers=["different topic"],
        )

    def context(
        self, mode: str, params: dict[str, object], request_id: str = ""
    ) -> OperationExecutionContext:
        """Build a fresh dispatch frame, not a shared conversation/context object."""
        worker = mode == "hdae_execute"
        ctx = OperationExecutionContext(
            user_id="operator",
            user_slug="operator",
            workspace_id="fixture",
            surface_id="worker" if worker else "director",
            mode_id=mode,
            task_id="implementation" if worker else "steering",
            params=params,
            data_dir=str(self.data),
            session_plan_digest="fixture-plan",
            approval_service=self.approvals,
            approval_request_id=request_id,
            code_change_artifact_store=self.artifacts,
            capability_binding_provider=self.bindings,
            host=build_callable_host(
                execute_tool_fn=tools.execute_tool,
                read_authored_text_fn=lambda path: (get_content_root() / path).read_text(),
            ),
        )
        if worker:
            self.last_worker = ctx
        return ctx

    async def run(self, operation: str, mode: str, params: dict[str, object]) -> OperationResult:
        """Execute real approval continuations, with explicit simulated operator decisions."""
        request_id = ""
        for _attempt in range(_MAX_APPROVAL_CONTINUATIONS):
            try:
                return await operations.execute_operation(
                    operation, self.context(mode, params, request_id)
                )
            except ApprovalRequired as pending:
                self.requests.append(pending.invocation.target_id)
                receipt = await self.approvals.approve(
                    pending.invocation.request_id, pending.invocation.identity
                )
                assert receipt is not None
                request_id = pending.invocation.request_id
        raise AssertionError("Approval continuation failed to converge")

    def gate(self) -> GateDefinition:
        """Describe one bounded source fix with a falsifiable real subprocess test."""
        return GateDefinition.model_validate(
            {
                "filename": "1-counter.md",
                "goal": "Counter reports one",
                "scope": ["Fix the counter value"],
                "non_goals": ["Other source changes"],
                "allowed_paths": ["src/count.py"],
                "governing_paths": ["hdae/ARCHITECTURE.md"],
                "criteria": [{"criterion_id": "counter", "outcome": "VALUE is one"}],
                "checks": [
                    {
                        "check_id": "behavior",
                        "criterion_ids": ["counter"],
                        "required_stdout": ["behavior verified"],
                    }
                ],
            }
        )

    async def completion(self, artifact_id: str) -> object:
        """Run the actual host checked-commit verifier and kernel finish contract."""
        assert self.last_worker is not None
        evidence = await verify_checked_commit(
            TaskCompletionRequest(
                task_id="implementation",
                origin_tool_id="hdae_verify",
                receipt_artifact_ids=(artifact_id,),
            ),
            store=self.artifacts,
            identity=self.last_worker,
        )
        return resolve_completion_contract(
            mode_id="hdae_execute",
            task_completion="checked_commit",
            checked_commit_verified=evidence.verified,
            checked_commit_reason=evidence.reason,
        )

    async def worker_turn(self, filename: str) -> object:
        """Run actual model/tool iterations and the host's approved-action resume."""
        identity = TurnIdentity(
            user_id="operator",
            user_slug="operator",
            workspace_id="fixture",
            surface_id="worker",
            task_id="implementation",
            session_plan_digest="fixture-plan",
        )
        model = WorkerModel(filename)
        hooks = TurnHooks(
            models=ModelHooks(complete=model.complete),
            operations=OperationHooks(execute_operation=operations.execute_operation),
            identity=identity,
            services=HostServiceHandles(
                approval_service=self.approvals,
                capability_binding_provider=self.bindings,
                code_change_artifact_store=self.artifacts,
                data_dir=str(self.data),
                verify_task_completion=partial(
                    verify_checked_commit, store=self.artifacts, identity=identity
                ),
            ),
            context_seams=ContextSeams(
                provider_gateways=ScenarioGateways(model.complete),
                content_registry=build_callable_host(
                    read_authored_text_fn=lambda path: (get_content_root() / path).read_text(),
                ),
            ),
        )
        paused = await run_turn(mode_id="hdae_execute", query="Reconcile this gate", hooks=hooks)
        assert paused.pending_approval is not None
        assert paused.pending_approval.target_id == "coding_commit"
        assert await self.approvals.approve(
            paused.pending_approval.request_id, paused.pending_approval.identity
        )
        delivered = await execute_approved_invocation(
            invocation=paused.pending_approval, hooks=hooks
        )
        assert isinstance(delivered, ToolResult)
        assert not delivered.error
        completed = await run_turn(
            mode_id="hdae_execute", query="Resume reconciliation", hooks=hooks
        )
        assert not completed.blocked
        assert completed.pending_approval is None
        assert any(receipt.capability_id == "hdae_verify" for receipt in completed.effect_receipts)
        return completed


@pytest.mark.asyncio
@pytest.mark.skipif(not _E2E_AVAILABLE, reason=_E2E_REASON)
async def test_whole_hdae_scenario(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise publication, exact approval, worker failure/fix, completion, and human review."""
    scenario = Scenario(tmp_path, monkeypatch)
    await scenario.run(
        "hdae_publish_artifact",
        "hdae_architect",
        {
            "path": "hdae/ARCHITECTURE.md",
            "content": "Counter must report one.\n",
        },
    )
    gate = scenario.gate()
    proposed = await scenario.run(
        "hdae_define_gate",
        "hdae_plan",
        {
            "gate": gate.model_dump(mode="json"),
            "body": "Counter gate and verification plan.\n",
        },
    )
    with pytest.raises(operations.OperationExecutionError, match="no_authorized_work"):
        await scenario.run("hdae_prepare", "hdae_execute", {})
    await scenario.run(
        "hdae_authorize",
        "hdae_plan",
        {
            "filename": gate.filename,
            "document_digest": proposed.output_json["document_digest"],
        },
    )
    prepared = await scenario.run("hdae_prepare", "hdae_execute", {})
    artifact_id = str(prepared.output_json["artifact_id"])
    assert isinstance(await scenario.completion(artifact_id), BlockNoCheckedCommit)
    failed = await scenario.run(
        "hdae_run_check", "hdae_execute", {"filename": gate.filename, "check_id": "behavior"}
    )
    assert failed.output_json["status"] == "failed"
    with pytest.raises(operations.OperationExecutionError, match="checks_not_current"):
        await scenario.run("hdae_verify", "hdae_execute", {"filename": gate.filename})
    await scenario.run(
        "hdae_edit",
        "hdae_execute",
        {
            "filename": gate.filename,
            "edits": [
                {
                    "kind": "update",
                    "path": "src/count.py",
                    "expected_sha256": hashlib.sha256(
                        (scenario.root / "src/count.py").read_bytes()
                    ).hexdigest(),
                    "replacements": [{"old_text": "VALUE = 0", "new_text": "VALUE = 1"}],
                }
            ],
        },
    )
    passed = await scenario.run(
        "hdae_run_check", "hdae_execute", {"filename": gate.filename, "check_id": "behavior"}
    )
    assert passed.output_json["status"] == "passed"
    await scenario.worker_turn(gate.filename)
    assert isinstance(await scenario.completion(artifact_id), AcceptTurn)
    assert (scenario.root / "hdae/gates-todo" / gate.filename).exists()
    reviewed = await scenario.run("hdae_verify", "hdae_evaluate", {"filename": gate.filename})
    assert reviewed.output_json["evidence_digest"]
    await scenario.run(
        "hdae_accept",
        "hdae_evaluate",
        {
            "filename": gate.filename,
            "evidence_digest": reviewed.output_json["evidence_digest"],
        },
    )
    assert (scenario.root / "hdae/gates-done" / gate.filename).exists()
    assert not (scenario.root / "hdae/gates-todo" / gate.filename).exists()
    exported = await scenario.run("hdae_export", "hdae_evaluate", {"filename": gate.filename})
    assert exported.output_json["accepted_by"] == "operator"
    assert exported.output_json["accounting"]["cost_usd"] is None
    assert exported.output_json["raw_output_exported"] is False
    assert "hdae_authorize" in scenario.requests and "hdae_accept" in scenario.requests
