"""Artifact-centered HDAE policy over the SDK's transactional document backend."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field
from sdk.filelock import is_process_alive
from sdk.workspace_documents import WorkspaceDocuments

from lisa_packs.hdae.contracts import (
    CheckEvidence,
    GateDefinition,
    gate_position,
    verify_observation,
)


class GateError(ValueError):
    """A requested action violates the current gate contract."""


class ExecutionCheck(BaseModel):
    """An immutable session-configured command, not a gate-provided executable."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    check_id: str
    argv: tuple[str, ...] = Field(min_length=1)
    timeout_seconds: int = Field(default=300, ge=1, le=1800)


class Configuration(BaseModel):
    """Trusted session configuration for a project and execution provider."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    workspace_root: str
    checks: tuple[ExecutionCheck, ...] = ()
    execution_provider: Literal["bwrap"] = "bwrap"
    execution_root: str = ""

    def digest(self) -> str:
        """Hash execution configuration without exposing sensitive parameters."""
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


class Authority(BaseModel):
    """Private authorization and observation record for one gate revision."""

    model_config = ConfigDict(extra="forbid")
    gate: GateDefinition
    document_digest: str
    governing_digests: dict[str, str]
    authorized_by: str = ""
    approval_request_id: str = ""
    authorized_at: str = ""
    authorized_profile: str = ""
    task_id: str = ""
    owner: str = ""
    process_id: int = 0
    execution_root: str = ""
    artifact_id: str = ""
    created_by: str = ""
    evidence: dict[str, CheckEvidence] = Field(default_factory=dict)
    verified_digest: str = ""
    accepted_by: str = ""
    acceptance_request_id: str = ""
    closed_digest: str = ""


class GateEngine:
    """Validate file-backed work against host-protected authorization records."""

    def __init__(
        self, documents: WorkspaceDocuments, config: Configuration, *, actor: str = ""
    ) -> None:
        self.documents = documents
        self.config = config
        self.actor = actor

    @classmethod
    def from_context(cls, ctx: object) -> GateEngine:
        """Create an SDK backend from trusted host/session configuration."""
        config = Configuration.model_validate(getattr(ctx, "pack_config", {}))
        data_dir = str(getattr(ctx, "data_dir", ""))
        if not data_dir:
            raise GateError("missing_data_dir")
        root = Path(config.workspace_root).expanduser().resolve()
        key = hashlib.sha256(str(root).encode()).hexdigest()
        private = Path(data_dir) / "data" / "verified-work" / key
        return cls(
            WorkspaceDocuments(root, private), config, actor=str(getattr(ctx, "user_id", ""))
        )

    def _record_path(self, filename: str) -> str:
        gate_position(filename)
        return filename + ".json"

    def _save(self, authority: Authority) -> None:
        relative = self._record_path(authority.gate.filename)
        self.documents.write(
            relative,
            authority.model_dump_json(indent=2),
            private=True,
            expected_digest=self.documents.digest(relative, private=True),
        )

    def load(self, filename: str) -> Authority:
        """Load protected authority rather than trust editable gate prose."""
        authority = Authority.model_validate_json(
            self.documents.read(self._record_path(filename), private=True)
        )
        if self.actor and authority.created_by and self.actor != authority.created_by:
            raise GateError("foreign_gate_authority")
        return authority

    def _governing(self, gate: GateDefinition) -> dict[str, str]:
        digests = {path: self.documents.digest(path) for path in gate.governing_paths}
        if not all(digests.values()):
            raise GateError("missing_governing_artifact")
        return digests

    def define(self, gate: GateDefinition, body: str, *, expected_digest: str) -> str:
        """Publish a complete gate proposal without granting execution authority."""
        path = "hdae/gates-todo/" + gate.filename
        with self.documents.transaction():
            governing = self._governing(gate)
            if self.documents.exists("hdae/gates-done/" + gate.filename):
                raise GateError("closed_gate_locked")
            if self.documents.exists("hdae/gates-deferred/" + gate.filename):
                raise GateError("deferred_gate_locked")
            if self.documents.exists(self._record_path(gate.filename), private=True):
                existing = self.load(gate.filename)
                if existing.authorized_by or existing.task_id:
                    raise GateError("authorized_contract_locked")
            if not body.strip():
                raise GateError("missing_gate_body")
            content = "---\n" + yaml.safe_dump(
                gate.model_dump(mode="json", exclude={"filename"}), sort_keys=True
            )
            content += "---\n\n" + body.rstrip() + "\n"
            document_digest = self.documents.write(path, content, expected_digest=expected_digest)
            self._save(
                Authority(
                    gate=gate,
                    document_digest=document_digest,
                    governing_digests=governing,
                    created_by=self.actor,
                )
            )
            return document_digest

    def authorize(self, filename: str, digest: str, *, actor: str, request_id: str) -> None:
        """Record an already-consumed exact-action human approval."""
        with self.documents.transaction():
            authority = self.load(filename)
            self._current(authority)
            if not actor or not request_id or digest != authority.document_digest:
                raise GateError("invalid_authorization")
            configured = {check.check_id for check in self.config.checks}
            if not {check.check_id for check in authority.gate.checks}.issubset(configured):
                raise GateError("unknown_configured_check")
            authority.authorized_by = actor
            authority.approval_request_id = request_id
            authority.authorized_at = datetime.now(UTC).isoformat()
            authority.authorized_profile = self.config.digest()
            self._save(authority)

    def _current(self, authority: Authority) -> None:
        if authority.authorized_profile and authority.authorized_profile != self.config.digest():
            raise GateError("execution_profile_changed")
        if (
            self.documents.digest("hdae/gates-todo/" + authority.gate.filename)
            != authority.document_digest
        ):
            raise GateError("gate_revision_changed")
        if self._governing(authority.gate) != authority.governing_digests:
            raise GateError("governing_revision_changed")

    def select(self, *, task_id: str = "") -> str:
        """Find the earliest authorized runnable gate without skipping dependencies."""
        paths = self.documents.list("hdae/gates-todo")
        names = sorted((Path(path).name for path in paths), key=gate_position)
        for name in names:
            authority = self.load(name)
            if authority.authorized_by and not authority.verified_digest:
                return name
            if authority.authorized_by and authority.verified_digest:
                if task_id and authority.task_id == task_id:
                    return name
                raise GateError("checkpoint_review_required")
        raise GateError("no_authorized_work")

    def claim(self, filename: str, *, task_id: str, owner: str, execution_root: str) -> Authority:
        """Acquire one current gate for a task without overriding a live worker."""
        with self.documents.transaction():
            authority = self.load(filename)
            self._current(authority)
            if not authority.authorized_by or not task_id or not owner:
                raise GateError("unauthorized_work")
            if self.select(task_id=task_id) != filename:
                raise GateError("out_of_order_gate")
            for dependency in authority.gate.dependencies:
                completed = self.load(dependency)
                path = "hdae/gates-done/" + dependency
                if (
                    not completed.closed_digest
                    or self.documents.digest(path) != completed.closed_digest
                ):
                    raise GateError("dependency_not_closed")
            if authority.task_id and authority.task_id != task_id:
                if authority.process_id and is_process_alive(authority.process_id):
                    raise GateError("work_already_claimed")
                raise GateError("explicit_recovery_required")
            authority.task_id = task_id
            authority.owner = owner
            authority.process_id = os.getpid()
            authority.execution_root = execution_root
            self._save(authority)
            return authority

    def claimed(self, filename: str, *, task_id: str, owner: str) -> Authority:
        """Require a matching exclusive execution claim and current contract."""
        authority = self.load(filename)
        self._current(authority)
        if not task_id or authority.task_id != task_id or authority.owner != owner:
            raise GateError("foreign_execution_claim")
        return authority

    def observe(self, filename: str, evidence: CheckEvidence, *, task_id: str, owner: str) -> None:
        """Persist a runner-created observation under the exclusive task claim."""
        with self.documents.transaction():
            authority = self.claimed(filename, task_id=task_id, owner=owner)
            if evidence.check_id not in {check.check_id for check in authority.gate.checks}:
                raise GateError("unknown_gate_check")
            authority.evidence[evidence.check_id] = evidence
            authority.verified_digest = ""
            self._save(authority)

    def verify(
        self,
        filename: str,
        *,
        task_id: str,
        owner: str,
        tree_sha: str,
        profile_digest: str,
        persist: bool = True,
    ) -> str:
        """Require every objective criterion and exact current runner evidence."""
        with self.documents.transaction():
            authority = self.claimed(filename, task_id=task_id, owner=owner)
            execution = WorkspaceDocuments(
                Path(authority.execution_root), self.documents.authority_root
            )
            if any(criterion.kind == "human" for criterion in authority.gate.criteria):
                raise GateError("human_criteria_not_recorded")
            for check in authority.gate.checks:
                observed = authority.evidence.get(check.check_id)
                if observed is None or not verify_observation(
                    check,
                    observed,
                    contract_digest=authority.document_digest,
                    tree_sha=tree_sha,
                    profile_digest=profile_digest,
                    input_digest=self.paths_digest(execution, check.input_paths),
                    output_digest=self.paths_digest(execution, check.output_paths),
                ):
                    raise GateError("missing_failed_or_stale_check")
            digest = self.evidence_digest(authority)
            if persist:
                authority.verified_digest = digest
                self._save(authority)
            return digest

    @staticmethod
    def paths_digest(documents: WorkspaceDocuments, paths: tuple[str, ...]) -> str:
        """Hash explicit build inputs/outputs, rejecting absent named files."""
        values = {path: documents.digest(path) for path in paths}
        if not all(values.values()):
            raise GateError("missing_build_artifact")
        return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()

    @staticmethod
    def evidence_digest(authority: Authority) -> str:
        """Fingerprint the observations that a human or delegate would close."""
        data = {
            name: evidence.model_dump(mode="json") for name, evidence in authority.evidence.items()
        }
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

    def accept(self, filename: str, digest: str, *, actor: str, request_id: str) -> None:
        """Close an exact verified checkpoint only after authenticated approval."""
        with self.documents.transaction():
            authority = self.load(filename)
            self._current(authority)
            if not actor or not request_id or not authority.verified_digest:
                raise GateError("unverified_acceptance")
            if digest != authority.verified_digest or digest != self.evidence_digest(authority):
                raise GateError("stale_acceptance")
            authority.accepted_by = actor
            authority.acceptance_request_id = request_id
            self.documents.move(
                "hdae/gates-todo/" + filename,
                "hdae/gates-done/" + filename,
                expected_digest=authority.document_digest,
            )
            authority.closed_digest = authority.document_digest
            authority.task_id = ""
            authority.process_id = 0
            self._save(authority)
