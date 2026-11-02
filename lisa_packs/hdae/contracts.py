"""Pure HDAE gate definitions and freshness validation."""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def safe_relative_path(value: str) -> str:
    """Validate a canonical project-relative path without traversal."""
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or "\\" in value
        or any(part in ("", ".", "..", ".git") for part in value.split("/"))
        or str(path) != value
    ):
        raise ValueError(f"Unsafe project path: {value!r}")
    return value


def gate_position(filename: str) -> Decimal:
    """Read the upstream decimal execution position without float rounding."""
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?-[a-z0-9-]+\.md", filename):
        raise ValueError(f"Invalid gate filename: {filename!r}")
    return Decimal(filename.split("-", 1)[0])


class Contract(BaseModel):
    """Strict immutable base for published policy contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    def digest(self) -> str:
        """Hash canonical structured content, not model-generated prose claims."""
        encoded = json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode()
        return hashlib.sha256(encoded).hexdigest()


class CheckDefinition(Contract):
    """One session-selected verifier mapped to explicit gate criteria."""

    check_id: str = Field(min_length=1, max_length=80)
    criterion_ids: tuple[str, ...] = Field(min_length=1)
    expected_exit_code: int = 0
    required_stdout: tuple[str, ...] = ()
    forbidden_output: tuple[str, ...] = ()
    input_paths: tuple[str, ...] = ()
    output_paths: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_paths(self) -> CheckDefinition:
        """Reject traversal and ambiguous criterion mapping."""
        for path in (*self.input_paths, *self.output_paths):
            safe_relative_path(path)
        if len(set(self.criterion_ids)) != len(self.criterion_ids):
            raise ValueError("Duplicate check criteria")
        return self


class Criterion(Contract):
    """An observable outcome, automated or explicitly human-evaluated."""

    criterion_id: str = Field(min_length=1, max_length=80)
    outcome: str = Field(min_length=1)
    kind: Literal["automated", "human"] = "automated"


class Delivery(Contract):
    """The approved commit and publication boundary."""

    strategy: Literal["worktree"] = "worktree"
    require_commit: bool = True
    require_pull_request: bool = False


class GateDefinition(Contract):
    """Machine-checkable adjunct to a human-readable upstream gate file."""

    schema_version: Literal[1] = 1
    filename: str
    goal: str = Field(min_length=1)
    scope: tuple[str, ...] = Field(min_length=1)
    non_goals: tuple[str, ...] = Field(min_length=1)
    allowed_paths: tuple[str, ...] = Field(min_length=1)
    governing_paths: tuple[str, ...] = Field(min_length=1)
    dependencies: tuple[str, ...] = ()
    criteria: tuple[Criterion, ...] = Field(min_length=1)
    checks: tuple[CheckDefinition, ...] = Field(min_length=1)
    review: Literal["checkpoint", "delegated"] = "checkpoint"
    delivery: Delivery = Field(default_factory=Delivery)

    @model_validator(mode="after")
    def validate_gate(self) -> GateDefinition:
        """Reject incomplete verification before any execution is authorized."""
        gate_position(self.filename)
        for name in self.dependencies:
            gate_position(name)
            if name == self.filename:
                raise ValueError("A gate cannot depend on itself")
        for path in (*self.allowed_paths, *self.governing_paths):
            safe_relative_path(path)
        criterion_ids = [item.criterion_id for item in self.criteria]
        check_ids = [item.check_id for item in self.checks]
        if len(set(criterion_ids)) != len(criterion_ids):
            raise ValueError("Duplicate criterion IDs")
        if len(set(check_ids)) != len(check_ids):
            raise ValueError("Duplicate check IDs")
        automated = {item.criterion_id for item in self.criteria if item.kind == "automated"}
        covered = {name for check in self.checks for name in check.criterion_ids}
        if covered != automated:
            raise ValueError("Checks must cover exactly the automated criteria")
        if self.review == "delegated" and any(item.kind == "human" for item in self.criteria):
            raise ValueError("Human criteria require checkpoint review")
        return self


class CheckEvidence(Contract):
    """Observation supplied by the execution owner, never by model assertions."""

    check_id: str
    contract_digest: str
    tree_sha: str
    profile_digest: str
    input_digest: str
    output_digest: str
    return_code: int
    timed_out: bool = False
    truncated: bool = False
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = Field(default=0, ge=0)


def verify_observation(
    check: CheckDefinition,
    evidence: CheckEvidence,
    *,
    contract_digest: str,
    tree_sha: str,
    profile_digest: str,
    input_digest: str,
    output_digest: str,
) -> bool:
    """Verify identity, freshness, exit state, and declared output assertions."""
    if (
        evidence.check_id != check.check_id
        or evidence.contract_digest != contract_digest
        or evidence.tree_sha != tree_sha
        or evidence.profile_digest != profile_digest
        or evidence.input_digest != input_digest
        or evidence.output_digest != output_digest
        or evidence.timed_out
        or evidence.truncated
        or evidence.return_code != check.expected_exit_code
    ):
        return False
    combined = evidence.stdout + "\n" + evidence.stderr
    return all(marker in evidence.stdout for marker in check.required_stdout) and not any(
        marker in combined for marker in check.forbidden_output
    )
