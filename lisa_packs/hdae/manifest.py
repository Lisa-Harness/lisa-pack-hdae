"""Validate reviewed HDAE source data and deterministically render Lisa modes."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

REVISION = "12d1a3389e74642dddee47a6cc4cb217f55f1144"
GENERATOR_VERSION = "1"
ROOT = Path(__file__).parent
SOURCE_PATH = "content/source/method-manifest.json"
BINDING_PATH = "content/source/lisa-bindings.json"
OPERATION_IDS = frozenset(
    {
        "hdae_publish_artifact",
        "hdae_define_gate",
        "hdae_authorize",
        "hdae_prepare",
        "hdae_edit",
        "hdae_run_check",
        "hdae_verify",
        "hdae_accept",
        "hdae_status",
        "hdae_export",
    }
)
MODE_IDS = frozenset(
    {
        "hdae_architect",
        "hdae_use_cases",
        "hdae_plan",
        "hdae_decide",
        "hdae_evaluate",
        "hdae_execute",
    }
)


class StrictModel(BaseModel):
    """Reject unknown fields and implicit type coercion in reviewed inputs."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class SourceFile(StrictModel):
    """Identify one exact upstream file and its local read-only snapshot."""

    source_id: str = Field(min_length=1)
    upstream_path: str = Field(min_length=1)
    snapshot_path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    normative: bool


class SourceReference(StrictModel):
    """Locate a reviewed rule in a hashed canonical source heading."""

    source_id: str = Field(min_length=1)
    heading: str = Field(min_length=1)
    quote: str = Field(min_length=1)


class MethodRule(StrictModel):
    """Portable interpretation, distinct from claims about a Lisa backend."""

    rule_id: str = Field(pattern=r"^[a-z][a-z0-9_]+$")
    requirement: str = Field(min_length=1)
    category: Literal[
        "deterministic",
        "artifact",
        "human_judgment",
        "model_instruction",
        "unsupported",
    ]
    references: list[SourceReference] = Field(min_length=1)


class RuleBinding(StrictModel):
    """Declare implemented content or a candidly unsupported runtime boundary."""

    rule_id: str = Field(min_length=1)
    classification: Literal["enforced", "human/model judgment", "unsupported"]
    scope: Literal["authoring", "advisory", "unavailable"]
    capabilities: list[str]
    content_paths: list[str]
    tests: list[str]
    rationale: str = Field(min_length=1)


class ArtifactRole(StrictModel):
    """Describe authoritative project roles without duplicating project facts."""

    role: str = Field(min_length=1)
    path: str = Field(min_length=1)
    responsibility: str = Field(min_length=1)
    template_path: str = Field(min_length=1)


class GatePolicy(StrictModel):
    """Portable gate structure and lifecycle, not a runtime verifier."""

    sections: list[str] = Field(min_length=1)
    directories: list[str] = Field(min_length=3, max_length=3)
    filename: str = Field(min_length=1)
    ordering: Literal["exact_decimal"]
    states: list[str] = Field(min_length=1)
    closure: str = Field(min_length=1)
    history: str = Field(min_length=1)


class MethodManifest(StrictModel):
    """Versioned, reviewed portable interpretation of pinned upstream text."""

    schema_version: int = Field(ge=1, le=1)
    generator_version: Literal["1"]
    repository: Literal["https://github.com/gmkurtzer/hdae"]
    revision: Literal["12d1a3389e74642dddee47a6cc4cb217f55f1144"]
    version: Literal["0.1.1"]
    license: Literal["Apache-2.0"]
    interpretation: str = Field(min_length=1)
    coverage_limit: str = Field(min_length=1)
    sources: list[SourceFile] = Field(min_length=4, max_length=4)
    artifacts: list[ArtifactRole] = Field(min_length=1)
    gate_policy: GatePolicy
    rules: list[MethodRule] = Field(min_length=1)


class Capability(StrictModel):
    """Expected main-agent runtime entry, never an assertion of availability."""

    capability_id: str = Field(min_length=1)
    module_path: str = Field(min_length=1)
    status: Literal["experimental_runtime"]


class ModeBinding(StrictModel):
    """Reviewed mode input and its narrowly scoped capability surface."""

    mode_id: str = Field(min_length=1)
    mode_kind: Literal["chat", "action"]
    description: str = Field(min_length=1)
    template_path: str = Field(min_length=1)
    activation: Literal["catalog", "source_only"]
    allowed_operation_ids: list[str]
    allowed_tool_ids: list[str]
    pre_turn_operation_ids: list[str] = Field(default_factory=list)
    pre_turn_failure_policy: Literal["skip", "abort"] = "skip"
    task_completion: Literal["none", "checked_commit"] = "none"
    task_artifact_tool_id: str = ""
    accept_default_capabilities: bool = False
    fork_allowed: bool = False
    approval_continuation: Literal["report", "resume"] = "report"
    rule_ids: list[str] = Field(min_length=1)


class LisaBindings(StrictModel):
    """Lisa adaptation and explicit exclusions separate from method semantics."""

    schema_version: int = Field(ge=1, le=1)
    generator_version: Literal["1"]
    source_revision: Literal["12d1a3389e74642dddee47a6cc4cb217f55f1144"]
    backend_status: Literal["experimental_runtime"]
    dependencies: list[str] = Field(min_length=1)
    adaptations: list[str] = Field(min_length=1)
    capabilities: list[Capability] = Field(min_length=10, max_length=10)
    optional_exported_tool_ids: list[str]
    modes: list[ModeBinding] = Field(min_length=6, max_length=6)
    bindings: list[RuleBinding] = Field(min_length=1)


def _pairs_without_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs_without_duplicates)


def _path(root: Path, relative: str) -> Path:
    parsed = PurePosixPath(relative)
    if (
        not relative
        or "\\" in relative
        or parsed.is_absolute()
        or any(part in {".", "..", ".git"} for part in relative.split("/"))
        or str(parsed) != relative
    ):
        raise ValueError(f"unsafe content path: {relative}")
    candidate = root.joinpath(*parsed.parts)
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"content escapes root: {relative}")
    for parent in (candidate, *candidate.parents):
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError(f"symlink content path: {relative}")
    return candidate


def _sections(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    current = ""
    fence = ""
    for line in text.splitlines():
        stripped = line.lstrip()
        marker = re.match(r"(`{3,}|~{3,})", stripped)
        if marker:
            token = marker.group(1)
            if not fence:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = ""
            continue
        if fence:
            continue
        if line.startswith(("## ", "### ")):
            current = line.lstrip("#").strip()
            if current in result:
                raise ValueError(f"ambiguous heading: {current}")
            result[current] = ""
        elif current:
            result[current] += line + "\n"
    return result


def _unique(values: list[str], label: str) -> set[str]:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {label}")
    return set(values)


def _validate_sources(root: Path, method: MethodManifest) -> dict[str, dict[str, str]]:
    sources = {source.source_id: source for source in method.sources}
    _unique([source.source_id for source in method.sources], "source IDs")
    _unique([source.snapshot_path for source in method.sources], "snapshot paths")
    expected_sources = {
        "skill": ("skills/hdae-development/SKILL.md", True),
        "method": ("skills/hdae-development/references/hdae-method.md", True),
        "version": ("VERSION", False),
        "license": ("LICENSE", False),
    }
    if {
        key: (source.upstream_path, source.normative) for key, source in sources.items()
    } != expected_sources:
        raise ValueError("canonical source inventory mismatch")
    sections: dict[str, dict[str, str]] = {}
    for source in method.sources:
        raw = _path(root, source.snapshot_path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != source.sha256:
            raise ValueError(f"stale source hash: {source.source_id}")
        if source.normative:
            sections[source.source_id] = _sections(raw.decode("utf-8"))
    if _path(root, sources["version"].snapshot_path).read_text().strip() != method.version:
        raise ValueError("source version mismatch")
    return sections


def _validate_rules(method: MethodManifest, sections: dict[str, dict[str, str]]) -> set[str]:
    rule_ids = _unique([rule.rule_id for rule in method.rules], "rule IDs")
    covered: set[tuple[str, str]] = set()
    for rule in method.rules:
        for reference in rule.references:
            section = sections.get(reference.source_id, {}).get(reference.heading)
            if section is None:
                raise ValueError(f"unknown source heading: {rule.rule_id}")
            if " ".join(reference.quote.split()) not in " ".join(section.split()):
                raise ValueError(f"stale source fragment: {rule.rule_id}")
            covered.add((reference.source_id, reference.heading))
    required = {
        (source_id, heading) for source_id, entries in sections.items() for heading in entries
    }
    if covered != required:
        raise ValueError(f"unclassified source headings: {sorted(required - covered)}")
    return rule_ids


def _validate_capabilities(lisa: LisaBindings) -> set[str]:
    capability_ids = _unique([item.capability_id for item in lisa.capabilities], "capability IDs")
    if capability_ids != OPERATION_IDS:
        raise ValueError("unknown or missing runtime capability")
    for capability in lisa.capabilities:
        expected = f"lisa_packs.hdae.operations.{capability.capability_id}"
        if capability.module_path != expected:
            raise ValueError(f"unexpected module path: {capability.capability_id}")
    return capability_ids


def _validate_optional_tools(lisa: LisaBindings) -> set[str]:
    optional_tools = _unique(lisa.optional_exported_tool_ids, "optional tools")
    if any(not re.fullmatch(r"coding_[a-z0-9_]+", tool) for tool in optional_tools):
        raise ValueError("optional tools must be explicitly exported coding_* IDs")
    return optional_tools


def _validate_binding_claim(binding: RuleBinding, capability_ids: set[str]) -> None:
    if not set(binding.capabilities) <= capability_ids:
        raise ValueError(f"unknown binding capability: {binding.rule_id}")
    if binding.classification == "enforced":
        if binding.scope != "authoring" or binding.capabilities or not binding.tests:
            raise ValueError("unverified runtime enforcement claim")
        if (
            binding.rule_id != "gate_template"
            or binding.content_paths != ["content/templates/gate.md"]
            or binding.tests != ["tests/test_manifest.py::test_gate_template_sections"]
        ):
            raise ValueError("unimplemented authoring enforcement claim")
    elif binding.classification == "unsupported":
        if binding.scope != "unavailable":
            raise ValueError("unsupported binding must declare unavailable scope")
    elif binding.scope != "advisory":
        raise ValueError("judgment binding must declare advisory scope")


def _validate_binding_content(root: Path, binding: RuleBinding) -> None:
    for relative in binding.content_paths:
        if not _path(root, relative).is_file():
            raise ValueError(f"missing bound content: {relative}")
    for test in binding.tests:
        test_path, separator, test_name = test.partition("::")
        if not separator or not re.fullmatch(r"test_[a-z0-9_]+", test_name):
            raise ValueError(f"invalid conformance test reference: {test}")
        if f"def {test_name}(" not in _path(root, test_path).read_text():
            raise ValueError(f"missing conformance test: {test}")


def _validate_bindings(root: Path, lisa: LisaBindings, capability_ids: set[str]) -> None:
    for binding in lisa.bindings:
        _validate_binding_claim(binding, capability_ids)
        _validate_binding_content(root, binding)


def _validate_mode_contract(mode: ModeBinding) -> None:
    if mode.activation != "catalog":
        raise ValueError("all six reviewed modes require catalog activation")
    if mode.mode_kind != ("action" if mode.mode_id == "hdae_execute" else "chat"):
        raise ValueError("mode kind mismatch")
    if mode.mode_id == "hdae_execute":
        if (
            mode.allowed_operation_ids
            != [
                "hdae_prepare",
                "hdae_edit",
                "hdae_run_check",
                "hdae_verify",
                "hdae_status",
                "hdae_export",
            ]
            or mode.allowed_tool_ids
            or mode.pre_turn_operation_ids != ["hdae_prepare"]
            or mode.pre_turn_failure_policy != "abort"
            or mode.task_completion != "checked_commit"
            or mode.task_artifact_tool_id != "hdae_verify"
            or mode.accept_default_capabilities
            or mode.fork_allowed
            or mode.approval_continuation != "resume"
        ):
            raise ValueError("invalid execute action contract")
    elif (
        mode.pre_turn_operation_ids
        or mode.pre_turn_failure_policy != "skip"
        or mode.task_completion != "none"
        or mode.task_artifact_tool_id
        or mode.accept_default_capabilities
        or mode.fork_allowed
        or mode.approval_continuation != "report"
    ):
        raise ValueError("invalid top review contract")


def _validate_modes(
    root: Path,
    lisa: LisaBindings,
    capability_ids: set[str],
    optional_tools: set[str],
    rule_ids: set[str],
) -> None:
    if _unique([mode.mode_id for mode in lisa.modes], "mode IDs") != MODE_IDS:
        raise ValueError("mode inventory mismatch")
    for mode in lisa.modes:
        if not set(mode.allowed_operation_ids) <= capability_ids:
            raise ValueError(f"unknown mode capability: {mode.mode_id}")
        if not set(mode.allowed_tool_ids) <= optional_tools:
            raise ValueError(f"unreviewed optional tool: {mode.mode_id}")
        if not set(mode.rule_ids) <= rule_ids:
            raise ValueError(f"unknown mode rule: {mode.mode_id}")
        if mode.template_path != f"content/templates/{mode.mode_id}.md":
            raise ValueError("unexpected mode template path")
        _validate_mode_contract(mode)
        template = _path(root, mode.template_path).read_text(encoding="utf-8")
        if not template.strip() or template.startswith("---"):
            raise ValueError("mode template must be a nonempty body without runtime metadata")


def _validate_artifact_templates(root: Path, method: MethodManifest) -> None:
    for artifact in method.artifacts:
        if not _path(root, artifact.template_path).is_file():
            raise ValueError(f"missing artifact template: {artifact.role}")
    gate_template = _path(root, "content/templates/gate.md").read_text()
    if list(_sections(gate_template)) != method.gate_policy.sections:
        raise ValueError("gate template sections disagree with source interpretation")


def load_manifests(root: Path = ROOT) -> tuple[MethodManifest, LisaBindings]:
    """Load and validate source bytes, heading coverage, templates, and bindings."""
    method = MethodManifest.model_validate(_read_json(_path(root, SOURCE_PATH)))
    lisa = LisaBindings.model_validate(_read_json(_path(root, BINDING_PATH)))
    sections = _validate_sources(root, method)
    rule_ids = _validate_rules(method, sections)
    if _unique([binding.rule_id for binding in lisa.bindings], "binding IDs") != rule_ids:
        raise ValueError("rule-to-binding coverage mismatch")
    capability_ids = _validate_capabilities(lisa)
    optional_tools = _validate_optional_tools(lisa)
    _validate_bindings(root, lisa, capability_ids)
    _validate_modes(root, lisa, capability_ids, optional_tools, rule_ids)
    _validate_artifact_templates(root, method)
    return method, lisa


def render_modes(root: Path = ROOT) -> dict[str, bytes]:
    """Render approved high-level top-loop modes without interpreting upstream code."""
    method, lisa = load_manifests(root)
    rendered: dict[str, bytes] = {}
    for mode in lisa.modes:
        if mode.activation != "catalog":
            continue
        metadata = {
            "mode_id": mode.mode_id,
            "mode_provider_id": "lisa-pack-hdae",
            "mode_kind": mode.mode_kind,
            "description": mode.description,
            "routable": False,
            "command_pattern": f"^(?:/)?{mode.mode_id}(?:[\\s,:;]+(?P<query>.+))?$",
            "allowed_operation_ids": mode.allowed_operation_ids,
            "allowed_tool_ids": mode.allowed_tool_ids,
            "pre_turn_operation_ids": mode.pre_turn_operation_ids,
            "pre_turn_failure_policy": mode.pre_turn_failure_policy,
            "task_completion": mode.task_completion,
            "task_artifact_tool_id": mode.task_artifact_tool_id,
            "accept_default_capabilities": mode.accept_default_capabilities,
            "tools_authoritative": True,
            "fork_allowed": mode.fork_allowed,
            "approval_continuation": mode.approval_continuation,
        }
        front_matter = "\n".join(
            f"{key}: {json.dumps(value, ensure_ascii=True)}" for key, value in metadata.items()
        )
        body = _path(root, mode.template_path).read_text(encoding="utf-8").strip()
        provenance = (
            "<!--\n"
            f"Generated by lisa_packs.hdae.manifest v{GENERATOR_VERSION}.\n"
            f"HDAE {method.version} at {method.revision}.\n"
            "Edit the approved template, not this file.\n"
            "-->"
        )
        rendered[f"modes/{mode.mode_id}/_mode.md"] = (
            f"---\n{front_matter}\n---\n\n{provenance}\n\n{body}\n".encode()
        )
    return rendered


def check_generated(root: Path = ROOT) -> None:
    """Fail if a generated mode is missing or differs from its reviewed inputs."""
    for relative, expected in render_modes(root).items():
        target = _path(root, relative)
        if not target.is_file() or target.read_bytes() != expected:
            raise ValueError(f"generated content drift: {relative}")


def generate(root: Path = ROOT) -> list[str]:
    """Write only deterministic catalog mode files; never fetch or execute inputs."""
    rendered = render_modes(root)
    targets = {relative: _path(root, relative) for relative in rendered}
    for relative, target in targets.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(rendered[relative])
    return sorted(targets)


def main(argv: list[str] | None = None) -> int:
    """Run offline provenance validation, mode generation, or drift checking."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "generate", "check"))
    parser.add_argument("--root", type=Path, default=ROOT)
    arguments = parser.parse_args(argv)
    try:
        method, lisa = load_manifests(arguments.root)
        if arguments.command == "generate":
            generate(arguments.root)
        elif arguments.command == "check":
            check_generated(arguments.root)
    except (ValueError, OSError) as error:
        parser.exit(1, f"{error}\n")
    print(
        json.dumps(
            {
                "revision": method.revision,
                "rules": len(method.rules),
                "runtime_enforcement_verified": False,
                "backend_status": lisa.backend_status,
                "execute_activation": next(
                    mode.activation for mode in lisa.modes if mode.mode_id == "hdae_execute"
                ),
                "classifications": {
                    category: sum(binding.classification == category for binding in lisa.bindings)
                    for category in ("enforced", "human/model judgment", "unsupported")
                },
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
