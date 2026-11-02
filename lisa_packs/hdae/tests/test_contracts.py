"""Gate contracts reject incomplete policy and stale observations."""

from decimal import Decimal

import pytest
from lisa_packs.hdae.contracts import (
    CheckDefinition,
    CheckEvidence,
    GateDefinition,
    gate_position,
    safe_relative_path,
    verify_observation,
)
from pydantic import ValidationError


def definition() -> GateDefinition:
    """Return a minimal complete automated gate."""
    return GateDefinition.model_validate(
        {
            "filename": "1-foundation.md",
            "goal": "Exercise the implemented interface",
            "scope": ["Implement the interface"],
            "non_goals": ["Unrelated interfaces"],
            "allowed_paths": ["src/interface.py", "tests/test_interface.py"],
            "governing_paths": ["hdae/ARCHITECTURE.md"],
            "criteria": [{"criterion_id": "behavior", "outcome": "Interface works"}],
            "checks": [{"check_id": "tests", "criterion_ids": ["behavior"]}],
        }
    )


def test_complete_contract() -> None:
    """A complete policy has a stable structured fingerprint."""
    gate = definition()
    assert gate.digest() == GateDefinition.model_validate(gate.model_dump()).digest()


@pytest.mark.parametrize("field", ["checks", "criteria", "allowed_paths", "governing_paths"])
def test_empty_required_sets_fail(field: str) -> None:
    """Empty mandatory sets cannot authorize execution."""
    payload = definition().model_dump()
    payload[field] = []
    with pytest.raises(ValidationError):
        GateDefinition.model_validate(payload)


def test_unmapped_criterion_fails() -> None:
    """Missing verification cannot be represented as a complete contract."""
    payload = definition().model_dump()
    payload["checks"] = [{"check_id": "tests", "criterion_ids": ["invented"]}]
    with pytest.raises(ValidationError, match="cover exactly"):
        GateDefinition.model_validate(payload)


@pytest.mark.parametrize(
    "path", ["../escape", "/absolute", "src/../escape", ".git/config", "a//b", "a\\b"]
)
def test_unsafe_paths_fail(path: str) -> None:
    """Canonical relative paths cannot name traversal or Git internals."""
    with pytest.raises(ValueError):
        safe_relative_path(path)


def test_decimal_order_is_exact() -> None:
    """Inserted checkpoints sort numerically without float precision loss."""
    assert gate_position("1.00000000000000001-probe.md") == Decimal("1.00000000000000001")
    assert gate_position("2-work.md") < gate_position("10-work.md")


@pytest.mark.parametrize("filename", ["01-work.md", "1.0-work.md", "../1-work.md"])
def test_noncanonical_gate_names_fail(filename: str) -> None:
    """Filesystem identity has exactly one canonical representation."""
    with pytest.raises(ValueError):
        gate_position(filename)


def test_stale_or_failed_evidence_cannot_pass() -> None:
    """Tree, contract, profile, and output fingerprints control passage."""
    check = CheckDefinition(
        check_id="boot", criterion_ids=("console",), required_stdout=("executed",)
    )
    fingerprints = {
        "contract_digest": "contract",
        "tree_sha": "tree",
        "profile_digest": "profile",
        "input_digest": "inputs",
        "output_digest": "image",
    }
    observed = CheckEvidence.model_validate(
        {
            "check_id": "boot",
            "return_code": 0,
            "stdout": "executed",
            **fingerprints,
        }
    )
    assert verify_observation(check, observed, **fingerprints)
    for field in fingerprints:
        assert not verify_observation(
            check, observed.model_copy(update={field: "stale"}), **fingerprints
        )
    for change in (
        {"return_code": 1},
        {"timed_out": True},
        {"truncated": True},
        {"stdout": "prompt only"},
    ):
        assert not verify_observation(check, observed.model_copy(update=change), **fingerprints)
