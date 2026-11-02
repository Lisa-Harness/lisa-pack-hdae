"""Recording harness: real execution, scripted or explicitly opted-in live decisions."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any, cast

import httpx2 as httpx
import pytest
from dotenv import dotenv_values
from kernel.approval import ApprovalInvocation, ApprovalRequired
from kernel.models import (
    OperationExecutionContext,
    OperationResult,
    ToolExecutionContext,
    ToolResult,
)
from kernel.operations import registry as operations
from kernel.provider_contracts import CompletionRequest, CompletionResult, ModelDescriptor
from kernel.seams.host_adapter import build_callable_host
from kernel.turn_hooks import HostServiceHandles, ModelHooks, OperationHooks, TurnIdentity
from kernel.turn_phases._completion_contract import AcceptTurn
from kernel.turn_runner import ContextSeams, TurnHooks, execute_approved_invocation, run_turn
from lisa_packs.hdae import get_content_root
from lisa_packs.hdae.engine import GateEngine
from lisa_packs.hdae.tests.test_scenario_e2e import Scenario, git
from openai import AsyncOpenAI
from runtime.code_artifacts import verify_checked_commit
from runtime.model_runtime import StubModelDefinition, resolve_model
from sdk.providers.openai_gateway import OpenAICompatibleGateway

_LIVE_ALIAS = "~z-ai/glm-flash-latest"
_MAX_CALLS = 12
_MAX_OUTPUT_TOKENS = 4096
_MAX_INPUT_BYTES = 262144
_MAX_SECONDS = 1200
_MAX_COST_USD = 5.0


@dataclass
class LiveAccounting:
    """Retain safe aggregate accounting without prompts, responses or credentials."""

    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    started: float = field(default_factory=time.monotonic)
    invocations: int = 0
    completed: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reported_costs: list[float] = field(default_factory=list)
    reserved_estimate_usd: float = 0.0
    tools: list[str] = field(default_factory=list)
    response_models: list[str] = field(default_factory=list)


class BoundedLiveGateway:
    """Use the real SDK gateway with an independent HTTP admission budget."""

    def __init__(self, client: AsyncOpenAI, model: StubModelDefinition) -> None:
        self.gateway = OpenAICompatibleGateway(client_factory=lambda: client)
        self.model = model
        self.accounting = LiveAccounting()
        previous = os.environ.get("HDAE_LIVE_PREVIOUS_RECEIPT")
        if previous:
            receipt = json.loads(Path(previous).read_text())
            assert receipt["provider"] == model.provider
            assert receipt["model_id"] == model.model_id
            assert receipt["state"] == "failed"
            prior = receipt["accounting"]
            for name in asdict(self.accounting):
                if name != "started":
                    setattr(self.accounting, name, prior[name])
            age = (datetime.now(UTC) - datetime.fromisoformat(prior["started_at"])).total_seconds()
            self.accounting.started = time.monotonic() - age

    async def admit(self, request: httpx.Request) -> None:
        """Count every HTTP attempt, including SDK compatibility fallbacks."""
        account = self.accounting
        payload = json.loads(request.content)
        assert payload["model"] == self.model.model_id
        assert len(request.content) <= _MAX_INPUT_BYTES
        assert payload.get("max_tokens", payload.get("max_completion_tokens", 0)) <= (
            _MAX_OUTPUT_TOKENS
        )
        assert account.invocations < _MAX_CALLS
        assert time.monotonic() - account.started < _MAX_SECONDS
        reservation = len(request.content) * max(self.model.prompt_price, 1e-6) + (
            _MAX_OUTPUT_TOKENS * max(self.model.completion_price, 4e-6)
        )
        assert account.reserved_estimate_usd + reservation <= _MAX_COST_USD
        account.reserved_estimate_usd += reservation
        account.invocations += 1

    async def observe(self, response: httpx.Response) -> None:
        """Retain only provider model identity and explicitly reported billing."""
        await response.aread()
        if not response.is_success:
            return
        payload = response.json()
        if isinstance(payload.get("model"), str):
            self.accounting.response_models.append(payload["model"])
        cost = (payload.get("usage") or {}).get("cost")
        if isinstance(cost, (int, float)) and not isinstance(cost, bool) and cost >= 0:
            self.accounting.reported_costs.append(float(cost))

    def gateway_for(self, provider: str) -> BoundedLiveGateway:
        """Reject routing to any unrelated provider."""
        assert provider == "openrouter"
        return self

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        """Cap output, enforce the selected model and redact provider exceptions."""
        assert request.model_def.model_id == self.model.model_id
        bounded = replace(request, max_tokens=min(request.max_tokens, _MAX_OUTPUT_TOKENS))
        try:
            result = await self.gateway.complete(bounded)
        except Exception as error:
            raise RuntimeError(f"Live provider request failed: {type(error).__name__}") from None
        account = self.accounting
        account.completed += 1
        if result.usage is not None:
            account.prompt_tokens += result.usage.prompt_tokens
            account.completion_tokens += result.usage.completion_tokens
        account.tools.extend(call["name"] for call in result.tool_calls)
        assert "hdae_accept" not in account.tools
        return result


def live_configuration(monkeypatch: pytest.MonkeyPatch) -> tuple[StubModelDefinition, str]:
    """Load host dotenv candidates privately and resolve the literal registry alias."""
    import runtime.model_runtime
    from runtime.config import default_data_dir
    from runtime.gateway_provider import _env

    framework = Path(runtime.model_runtime.__file__).resolve().parents[3]
    candidates = (
        Path.cwd() / ".env",
        default_data_dir() / ".env",
        framework / ".env",
        framework / "hosts/little_lisa/.env",
    )
    for candidate in candidates:
        if candidate.is_file():
            for name, value in dotenv_values(candidate).items():
                if value is not None and name in {"LISA_OPENROUTER_API_KEY", "OPENROUTER_API_KEY"}:
                    monkeypatch.setenv(name, value)
    model = resolve_model(_LIVE_ALIAS, runtime_state={}, data_dir=default_data_dir())
    assert model.provider == "openrouter" and "tools" in model.capabilities
    key = _env("LISA_OPENROUTER_API_KEY", "OPENROUTER_API_KEY")
    if not key:
        pytest.skip("Live OpenRouter not run: host OpenRouter credentials are not configured")
    return replace(model, max_completion_tokens=_MAX_OUTPUT_TOKENS), key


class ScriptedGateway:
    """Only decisions are scripted; all operations execute in the real registry."""

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        self.calls += 1
        choices = [
            (
                "hdae_edit",
                {
                    "filename": "1-counter.md",
                    "edits": [
                        {
                            "kind": "update",
                            "path": "src/count.py",
                            "expected_sha256": hashlib.sha256(b"VALUE = 0\n").hexdigest(),
                            "replacements": [{"old_text": "VALUE = 0", "new_text": "VALUE = 1"}],
                        }
                    ],
                },
            ),
            ("hdae_run_check", {"filename": "1-counter.md", "check_id": "behavior"}),
            ("hdae_verify", {"filename": "1-counter.md"}),
            ("hdae_verify", {"filename": "1-counter.md"}),
        ]
        calls: list[dict[str, Any]] = []
        if self.calls <= len(choices):
            name, arguments = choices[self.calls - 1]
            calls = [
                {
                    "id": f"scripted-{self.calls}",
                    "function": {
                        "name": name,
                        "arguments": json.dumps(arguments),
                    },
                }
            ]
        return CompletionResult(
            content="" if calls else "Checked commit ready; human acceptance is pending.",
            provider="scripted",
            model_id="scripted-decisions",
            display_name="Scripted decisions / real execution",
            tool_calls=calls,
        )

    def gateway_for(self, provider: str) -> ScriptedGateway:
        return self


class ApprovedOperationDriver:
    """Finish suspended wrappers using only their exact approved execution result."""

    def __init__(self, scenario: Scenario) -> None:
        self.scenario = scenario
        self.pending: tuple[str, OperationExecutionContext] | None = None

    async def execute(self, name: str, ctx: OperationExecutionContext) -> OperationResult:
        """Dispatch unchanged operations and retain their suspended wrapper frame."""
        try:
            return await operations.execute_operation(name, ctx)
        except ApprovalRequired:
            self.pending = (name, ctx)
            raise

    async def reconcile(self, pending: ApprovalInvocation, result: ToolResult) -> None:
        """Consume a delivered result once, never execute or approve another action."""
        assert self.pending is not None
        name, suspended = self.pending
        ctx = self.scenario.context(suspended.mode_id, dict(suspended.params))
        original_host = ctx.host
        consumed = False

        async def replay(tool_id: str, source: ToolExecutionContext) -> ToolResult:
            nonlocal consumed
            assert not consumed
            assert tool_id == pending.target_id
            assert source.parameters == pending.parameters
            assert source.task_id == ctx.task_id
            consumed = True
            return result

        ctx.host = build_callable_host(
            execute_tool_fn=replay,
            read_authored_text_fn=lambda path: (get_content_root() / path).read_text(),
        )
        try:
            reconciled = await operations.execute_operation(name, ctx)
            assert isinstance(reconciled, OperationResult)
            if not consumed:
                assert pending.target_id == "coding_commit"
                assert reconciled.output_json["artifact_id"] == pending.parameters["artifact_id"]
                assert reconciled.output_json["evidence_digest"]
        finally:
            ctx.host = original_host
        self.pending = None


async def prepare_scenario(scenario: Scenario) -> str:
    """Publish, authorize, prepare, and establish an actual failing baseline."""
    print("STAGE proposal: disposable repository; scripted operator authorization")
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
            "body": "Fix the counter; verify behavior.\n",
        },
    )
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
    failed = await scenario.run(
        "hdae_run_check",
        "hdae_execute",
        {
            "filename": gate.filename,
            "check_id": "behavior",
        },
    )
    assert failed.output_json["status"] == "failed"
    return artifact_id


async def exercise(
    scenario: Scenario, gateways: Any, model_descriptor: Any = None
) -> dict[str, object]:
    """Run the generated action mode and stop before human checkpoint acceptance."""
    artifact_id = await prepare_scenario(scenario)
    gate = scenario.gate()
    identity = TurnIdentity(
        user_id="operator",
        user_slug="operator",
        workspace_id="fixture",
        surface_id="worker",
        task_id="implementation",
        session_plan_digest="fixture-plan",
    )
    driver = ApprovedOperationDriver(scenario)
    hooks = TurnHooks(
        models=ModelHooks(
            resolve_model=(lambda _reference: model_descriptor) if model_descriptor else None
        ),
        operations=OperationHooks(execute_operation=driver.execute),
        identity=identity,
        services=HostServiceHandles(
            approval_service=scenario.approvals,
            capability_binding_provider=scenario.bindings,
            code_change_artifact_store=scenario.artifacts,
            data_dir=str(scenario.data),
            verify_task_completion=partial(
                verify_checked_commit,
                store=scenario.artifacts,
                identity=identity,
            ),
        ),
        context_seams=ContextSeams(
            provider_gateways=gateways,
            content_registry=build_callable_host(
                read_authored_text_fn=lambda path: (get_content_root() / path).read_text(),
            ),
        ),
    )
    snapshot = "VALUE = 0\n"
    query = (
        "Implement authorized gate 1-counter.md. Source snapshot src/count.py is "
        f"{snapshot!r}; expected_sha256={hashlib.sha256(snapshot.encode()).hexdigest()}. "
        "tests/probe.py imports VALUE and asserts VALUE == 1, prints behavior verified. "
        "The real behavior check already failed. Use hdae_edit to update only VALUE = 0 "
        "to VALUE = 1; hdae_run_check filename=1-counter.md check_id=behavior; then "
        "hdae_verify filename=1-counter.md. Use function calls, not prose descriptions. "
        "Do not accept the gate. After commit approval, call hdae_verify again."
    )
    print("STAGE execution: generated hdae_execute; HDAE operations only")
    approved_targets: list[str] = []
    for _continuation in range(8):
        completed = await run_turn(mode_id="hdae_execute", query=query, hooks=hooks)
        pending = completed.pending_approval
        if pending is None:
            break
        assert pending.target_id in {"coding_edit_files", "coding_run_check", "coding_commit"}
        print(
            f"STAGE approval: scripted operator approves exact {pending.target_id}; NOT acceptance"
        )
        assert await scenario.approvals.approve(pending.request_id, pending.identity)
        delivered = await execute_approved_invocation(invocation=pending, hooks=hooks)
        assert isinstance(delivered, ToolResult)
        assert not delivered.error
        await driver.reconcile(pending, delivered)
        approved_targets.append(pending.target_id)
        bound = scenario.context("hdae_execute", {})
        bound.pack_config = scenario.bindings.values["lisa-pack-hdae"].configuration
        authority = GateEngine.from_context(bound).load(gate.filename)
        if authority.verified_digest:
            assert pending.target_id == "coding_commit"
            assert isinstance(await scenario.completion(artifact_id), AcceptTurn)
            break
        query = (
            f"Exact {pending.target_id} approved and executed. "
            "Continue remaining steps only: run behavior check if not yet passed, "
            "then hdae_verify filename=1-counter.md. Do not edit again. Stop for review."
        )
    else:
        raise AssertionError("Approval continuation limit reached")
    assert {"coding_edit_files", "coding_run_check", "coding_commit"} <= set(approved_targets)
    if not authority.verified_digest:
        assert completed.pending_approval is None
        assert not completed.blocked
    assert isinstance(await scenario.completion(artifact_id), AcceptTurn)
    artifact = await scenario.artifacts.get(artifact_id)
    assert artifact is not None
    worktree = Path(artifact.worktree_path)
    assert (worktree / "src/count.py").read_text() == "VALUE = 1\n"
    assert git(worktree, "show", "HEAD:src/count.py") == "VALUE = 1"
    assert artifact.commit_sha == git(worktree, "rev-parse", "HEAD")
    assert git(worktree, "status", "--porcelain") == ""
    reviewed = await scenario.run("hdae_verify", "hdae_evaluate", {"filename": gate.filename})
    exported = await scenario.run("hdae_export", "hdae_evaluate", {"filename": gate.filename})
    assert (scenario.root / "hdae/gates-todo" / gate.filename).exists()
    assert not (scenario.root / "hdae/gates-done" / gate.filename).exists()
    assert "hdae_accept" not in scenario.requests
    receipt: dict[str, object] = {
        "state": "passed_awaiting_review",
        "human_accepted": False,
        "operator_choices": "scripted authorization and commit approval only",
        "commit_sha": artifact.commit_sha,
        "evidence_digest": reviewed.output_json["evidence_digest"],
        "source_fix": "VALUE = 0 -> VALUE = 1",
        "check": "behavior passed",
        "approved_targets": approved_targets,
        "export": exported.output_json,
        "completion_contract": "AcceptTurn",
        "clean_worktree": True,
        "fixture_root": str(scenario.root),
        "worktree": str(worktree),
        "next_decision": "Separate authenticated hdae_accept approval required",
    }
    print("STAGE review: verified checked commit; acceptance PENDING")
    return receipt


@pytest.mark.asyncio
async def test_scripted_demo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Prove the recording path without network calls or accepting the gate."""
    receipt = await exercise(Scenario(tmp_path, monkeypatch), ScriptedGateway())
    assert receipt["human_accepted"] is False


@pytest.mark.asyncio
async def test_live_gateway_normalized_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """Account the SDK's flat tool-call shape without making network requests."""
    model = StubModelDefinition(model_id="fixture", provider="openrouter")

    async def completed(request: CompletionRequest) -> CompletionResult:
        assert request.max_tokens == _MAX_OUTPUT_TOKENS
        return CompletionResult(
            content="",
            provider="openrouter",
            model_id="fixture",
            display_name="fixture",
            tool_calls=[{"name": "hdae_edit", "arguments": "{}", "id": "fixture"}],
        )

    async with AsyncOpenAI(api_key="offline-fixture") as client:
        gateway = BoundedLiveGateway(client, model)
        monkeypatch.setattr(gateway.gateway, "complete", completed)
        await gateway.complete(CompletionRequest([], cast(ModelDescriptor, model), 8192, 0))
        assert gateway.accounting.tools == ["hdae_edit"]
        assert gateway.accounting.invocations == 0


@pytest.mark.live
@pytest.mark.skipif(
    os.environ.get("HDAE_RUN_LIVE") != "1",
    reason="Paid OpenRouter E2E requires explicit HDAE_RUN_LIVE=1 and host credentials",
)
@pytest.mark.asyncio
async def test_live_openrouter_demo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Let the opted-in live model choose HDAE tools, leaving human acceptance pending."""
    previous_logging = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    receipt: dict[str, Any] = {
        "schema_version": 2,
        "state": "not_run",
        "requested_alias": _LIVE_ALIAS,
        "provider": "openrouter",
        "human_accepted": False,
        "dogfooding_implemented": False,
        "driver": "local exact-child-result reconciliation; not production recovery",
        "previous_evidence_receipt": os.environ.get("HDAE_LIVE_PREVIOUS_RECEIPT"),
        "limits": {
            "calls": _MAX_CALLS,
            "output_tokens_per_call": _MAX_OUTPUT_TOKENS,
            "wall_seconds": _MAX_SECONDS,
            "cost_usd": _MAX_COST_USD,
        },
    }
    failure = ""
    gateway: BoundedLiveGateway | None = None
    try:
        model, key = live_configuration(monkeypatch)
        receipt["model_id"] = model.model_id
        async with (
            httpx.AsyncClient() as transport,
            AsyncOpenAI(
                api_key=key,
                base_url="https://openrouter.ai/api/v1",
                max_retries=0,
                timeout=120,
                http_client=transport,
            ) as client,
        ):
            gateway = BoundedLiveGateway(client, model)
            transport.event_hooks["request"].append(gateway.admit)
            transport.event_hooks["response"].append(gateway.observe)
            receipt["state"] = "running"
            remaining = _MAX_SECONDS - (time.monotonic() - gateway.accounting.started)
            async with asyncio.timeout(max(0, remaining)):
                result = await exercise(Scenario(tmp_path, monkeypatch), gateway, model)
            assert {"hdae_edit", "hdae_run_check", "hdae_verify"} <= set(gateway.accounting.tools)
            receipt.update(result)
    except Exception as error:
        failure = type(error).__name__
        receipt.update(state="failed", failure_type=failure)
    finally:
        if gateway is not None:
            account = gateway.accounting
            receipt["accounting"] = {
                **{name: value for name, value in asdict(account).items() if name != "started"},
                "finished_at": datetime.now(UTC).isoformat(),
                "elapsed_seconds": round(time.monotonic() - account.started, 3),
                "provider_reported_cost_usd": (
                    sum(account.reported_costs)
                    if len(account.reported_costs) == account.invocations
                    else None
                ),
                "cost_attribution": "provider usage.cost; null when incomplete or unavailable",
                "reservation_attribution": (
                    "conservative estimate, not billed cost: all input bytes charged as tokens; "
                    "max(manifest, $1/M input), max(manifest, $4/M output); full output allowance"
                ),
                "manifest_input_usd_per_token": gateway.model.prompt_price,
                "manifest_output_usd_per_token": gateway.model.completion_price,
            }
        receipt["evidence_directory"] = str(tmp_path)
        (tmp_path / "live-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        logging.disable(previous_logging)
    if failure:
        pytest.fail(f"Live E2E failed ({failure}); sanitized receipt: {tmp_path}", pytrace=False)
