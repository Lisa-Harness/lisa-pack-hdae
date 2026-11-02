"""Independent checks of source interpretation and deterministic authoring."""

import json
import shutil
from pathlib import Path

import pytest
from lisa_packs.hdae.manifest import (
    BINDING_PATH,
    ROOT,
    SOURCE_PATH,
    SourceFile,
    _sections,
    check_generated,
    generate,
    load_manifests,
    main,
    render_modes,
)
from pydantic import ValidationError

_EXPECTED_RULE_COUNT = 27
_EXPECTED_MODE_COUNT = 6
_EXPECTED_CAPABILITY_COUNT = 10


def test_source_schema_rejects_unknown_fields() -> None:
    """Source inventories cannot silently carry uninterpreted metadata."""
    payload = {
        "source_id": "skill",
        "upstream_path": "skills/hdae-development/SKILL.md",
        "snapshot_path": "content/source/upstream/SKILL.md",
        "sha256": "a" * 64,
        "normative": True,
        "execute": "downloaded command",
    }
    with pytest.raises(ValidationError, match="Extra inputs"):
        SourceFile.model_validate(payload)


def test_headings_inside_fences_are_not_normative() -> None:
    """Example gate headings must not be extracted as method headings."""
    assert _sections("## Rule\ntext\n```markdown\n## Example\n```\n") == {"Rule": "text\n"}


@pytest.fixture
def source_root(tmp_path: Path) -> Path:
    """Use an isolated content tree for adversarial mutation checks."""
    shutil.copytree(ROOT / "content", tmp_path / "content")
    shutil.copytree(ROOT / "tests", tmp_path / "tests")
    return tmp_path


def mutate_json(root: Path, filename: str, field: str, value: object) -> None:
    """Change one reviewed input without touching the actual pack."""
    path = root / "content/source" / filename
    payload = json.loads(path.read_text())
    payload[field] = value
    path.write_text(json.dumps(payload))


def test_pinned_provenance_and_coverage() -> None:
    """All canonical source bytes and every registered rule binding validate."""
    method, lisa = load_manifests()
    assert method.version == "0.1.1"
    assert len(method.rules) == _EXPECTED_RULE_COUNT
    assert {rule.rule_id for rule in method.rules} == {binding.rule_id for binding in lisa.bindings}
    assert {binding.classification for binding in lisa.bindings} == {
        "enforced",
        "human/model judgment",
        "unsupported",
    }
    assert all(
        binding.scope == "authoring"
        for binding in lisa.bindings
        if binding.classification == "enforced"
    )


def test_gate_template_sections() -> None:
    """The shipped template has the independently expected upstream sections."""
    method, _ = load_manifests()
    expected = [
        "Source",
        "Goal",
        "Approved scope",
        "Non-goals",
        "Completed work",
        "Remaining work",
        "Acceptance criteria",
        "Verification plan",
        "Evidence",
        "Decisions and limitations",
        "Delivery strategy",
        "Review policy and outcome",
    ]
    assert method.gate_policy.sections == expected
    template = (ROOT / "content/templates/gate.md").read_text()
    assert list(_sections(template)) == expected
    assert not template.startswith("---")


@pytest.mark.parametrize("source", ["SKILL.md", "hdae-method.md", "VERSION", "LICENSE"])
def test_stale_sources_fail(source_root: Path, source: str) -> None:
    """Each upstream snapshot is an exact-byte input, including license/version."""
    with (source_root / "content/source/upstream" / source).open("ab") as stream:
        stream.write(b"\nchanged\n")
    with pytest.raises(ValueError, match="stale source hash"):
        load_manifests(source_root)


@pytest.mark.parametrize("filename", ["method-manifest.json", "lisa-bindings.json"])
def test_unknown_manifest_fields_fail(source_root: Path, filename: str) -> None:
    """Unparsed source or backend fields are rejected, never silently ignored."""
    mutate_json(source_root, filename, "unparsed_policy", "ignored")
    with pytest.raises(ValidationError, match="Extra inputs"):
        load_manifests(source_root)


@pytest.mark.parametrize("version", [2, True, "1"])
def test_incompatible_schema_fails(source_root: Path, version: object) -> None:
    """Only the explicitly supported integer schema version is accepted."""
    mutate_json(source_root, "method-manifest.json", "schema_version", version)
    with pytest.raises(ValidationError):
        load_manifests(source_root)


def test_missing_bindings_fail(source_root: Path) -> None:
    """Adding or removing rules cannot quietly omit a Lisa disposition."""
    payload = json.loads((source_root / BINDING_PATH).read_text())
    mutate_json(source_root, "lisa-bindings.json", "bindings", payload["bindings"][1:])
    with pytest.raises(ValueError, match="coverage mismatch"):
        load_manifests(source_root)


def test_unclassified_headings_fail(source_root: Path) -> None:
    """Known source headings remain classified even if an interpreter omits a rule."""
    payload = json.loads((source_root / SOURCE_PATH).read_text())
    payload["rules"] = [rule for rule in payload["rules"] if rule["rule_id"] != "retrospective"]
    mutate_json(source_root, "method-manifest.json", "rules", payload["rules"])
    with pytest.raises(ValueError, match="unclassified source headings"):
        load_manifests(source_root)


@pytest.mark.parametrize("field", ["heading", "quote"])
def test_stale_locators_fail(source_root: Path, field: str) -> None:
    """A valid file hash is insufficient when the registered locator is wrong."""
    payload = json.loads((source_root / SOURCE_PATH).read_text())
    payload["rules"][0]["references"][0][field] = "not a canonical fragment"
    mutate_json(source_root, "method-manifest.json", "rules", payload["rules"])
    with pytest.raises(ValueError, match=r"source heading|source fragment"):
        load_manifests(source_root)


def test_unknown_capabilities_fail(source_root: Path) -> None:
    """A fabricated runtime ID cannot be introduced through a mode surface."""
    payload = json.loads((source_root / BINDING_PATH).read_text())
    payload["modes"][0]["allowed_operation_ids"].append("hdae_magic")
    mutate_json(source_root, "lisa-bindings.json", "modes", payload["modes"])
    with pytest.raises(ValueError, match="unknown mode capability"):
        load_manifests(source_root)


def test_runtime_enforcement_claims_fail(source_root: Path) -> None:
    """Expected operations cannot be relabeled implemented enforcement."""
    payload = json.loads((source_root / BINDING_PATH).read_text())
    binding = payload["bindings"][0]
    binding["classification"] = "enforced"
    binding["scope"] = "authoring"
    binding["tests"] = ["tests/test_manifest.py::test_pinned_provenance_and_coverage"]
    mutate_json(source_root, "lisa-bindings.json", "bindings", payload["bindings"])
    with pytest.raises(ValueError, match="unverified runtime enforcement"):
        load_manifests(source_root)


def test_unimplemented_rule_cannot_be_enforced(source_root: Path) -> None:
    """Unrelated passing tests cannot promote unsupported semantics to enforcement."""
    payload = json.loads((source_root / BINDING_PATH).read_text())
    binding = next(item for item in payload["bindings"] if item["rule_id"] == "ledger_history")
    binding["classification"] = "enforced"
    binding["scope"] = "authoring"
    binding["capabilities"] = []
    binding["tests"] = ["tests/test_manifest.py::test_gate_template_sections"]
    mutate_json(source_root, "lisa-bindings.json", "bindings", payload["bindings"])
    with pytest.raises(ValueError, match="unimplemented authoring enforcement"):
        load_manifests(source_root)


def test_missing_content_fails(source_root: Path) -> None:
    """Missing authored content fails instead of falling back to Python prose."""
    (source_root / "content/templates/hdae_architect.md").unlink()
    with pytest.raises(ValueError, match="missing bound content"):
        load_manifests(source_root)


def test_missing_gate_section_fails(source_root: Path) -> None:
    """A template edit cannot erase a substantive upstream obligation."""
    path = source_root / "content/templates/gate.md"
    path.write_text(path.read_text().replace("## Evidence", "## Commentary"))
    with pytest.raises(ValueError, match="gate template sections"):
        load_manifests(source_root)


@pytest.mark.parametrize("path", ["../escape.md", "/tmp/escape.md", "content//source.md"])
def test_unsafe_source_paths_fail(source_root: Path, path: str) -> None:
    """Reviewed JSON cannot redirect the builder outside the content tree."""
    payload = json.loads((source_root / SOURCE_PATH).read_text())
    payload["sources"][0]["snapshot_path"] = path
    mutate_json(source_root, "method-manifest.json", "sources", payload["sources"])
    with pytest.raises(ValueError, match="unsafe content path"):
        load_manifests(source_root)


def test_symlink_outputs_fail(source_root: Path, tmp_path: Path) -> None:
    """Generation refuses symlink output directories and leaves other paths alone."""
    external = tmp_path / "external"
    external.mkdir()
    (source_root / "modes").symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError, match=r"symlink content path|content escapes root"):
        generate(source_root)
    assert list(external.iterdir()) == []


def test_deterministic_generation_and_drift(source_root: Path) -> None:
    """Identical approved inputs produce identical mode bytes; tampering fails."""
    expected = render_modes(source_root)
    assert len(expected) == _EXPECTED_MODE_COUNT
    generate(source_root)
    check_generated(source_root)
    generate(source_root)
    assert expected == render_modes(source_root)
    assert all((source_root / relative).read_bytes() == raw for relative, raw in expected.items())
    path = source_root / "modes/hdae_plan/_mode.md"
    path.write_bytes(path.read_bytes() + b"\nchanged\n")
    with pytest.raises(ValueError, match="generated content drift"):
        check_generated(source_root)


def test_execute_action_contract(source_root: Path) -> None:
    """The generated action carries only the vetted guarded execution surface."""
    _, lisa = load_manifests(source_root)
    execute = next(mode for mode in lisa.modes if mode.mode_id == "hdae_execute")
    assert execute.activation == "catalog"
    assert execute.mode_kind == "action"
    assert execute.allowed_operation_ids == [
        "hdae_prepare",
        "hdae_edit",
        "hdae_run_check",
        "hdae_verify",
        "hdae_status",
        "hdae_export",
    ]
    assert execute.allowed_tool_ids == []
    assert execute.pre_turn_operation_ids == ["hdae_prepare"]
    assert execute.pre_turn_failure_policy == "abort"
    assert execute.task_completion == "checked_commit"
    assert execute.task_artifact_tool_id == "hdae_verify"
    assert execute.accept_default_capabilities is False
    assert execute.fork_allowed is False
    assert execute.approval_continuation == "resume"
    assert "modes/hdae_execute/_mode.md" in render_modes(source_root)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("activation", "source_only"),
        ("mode_kind", "chat"),
        ("pre_turn_operation_ids", []),
        ("pre_turn_failure_policy", "skip"),
        ("task_completion", "none"),
        ("task_artifact_tool_id", "coding_create_worktree"),
        ("allowed_operation_ids", ["hdae_prepare", "hdae_verify"]),
        ("allowed_tool_ids", ["coding_edit_files"]),
        ("accept_default_capabilities", True),
        ("fork_allowed", True),
        ("approval_continuation", "report"),
        ("pre_turn_failure_policy", "ignored"),
        ("fork_allowed", "false"),
        ("unvetted_metadata", True),
    ],
)
def test_weakened_execute_contract_fails(source_root: Path, field: str, value: object) -> None:
    """Missing guards, raw tools, unknown metadata and coercion fail closed."""
    payload = json.loads((source_root / BINDING_PATH).read_text())
    payload["modes"][-1][field] = value
    if field == "allowed_tool_ids":
        payload["optional_exported_tool_ids"] = value
        mutate_json(source_root, "lisa-bindings.json", "optional_exported_tool_ids", value)
    mutate_json(source_root, "lisa-bindings.json", "modes", payload["modes"])
    with pytest.raises(ValueError):
        load_manifests(source_root)


def test_flat_runtime_capabilities() -> None:
    """All ten runtime bindings name actual flat operation modules."""
    _, lisa = load_manifests()
    assert len(lisa.capabilities) == _EXPECTED_CAPABILITY_COUNT
    assert "hdae_edit" in {item.capability_id for item in lisa.capabilities}
    for capability in lisa.capabilities:
        assert capability.module_path == f"lisa_packs.hdae.operations.{capability.capability_id}"
        assert (ROOT / "operations" / f"{capability.capability_id}.py").is_file()
        assert capability.status == "experimental_runtime"


def test_duplicate_json_keys_fail(source_root: Path) -> None:
    """Ambiguous JSON cannot silently replace a reviewed field."""
    path = source_root / SOURCE_PATH
    path.write_text(
        path.read_text().replace(
            '"schema_version": 1,', '"schema_version": 1, "schema_version": 1,'
        )
    )
    with pytest.raises(ValueError, match="duplicate JSON key"):
        load_manifests(source_root)


def test_cli_reports_limits(source_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Validation reports source success without implying a working backend."""
    assert main(["validate", "--root", str(source_root)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["runtime_enforcement_verified"] is False
    assert report["backend_status"] == "experimental_runtime"
    assert report["execute_activation"] == "catalog"
