"""Real SDK catalog checks for the authored HDAE mode slice."""

import json

import yaml
from lisa_packs.hdae import get_content_root
from lisa_packs.hdae.manifest import ROOT, check_generated, load_manifests
from sdk.content import build_mode_catalog_json, resolve_mode_roots


def test_catalog_discovers_authored_top_modes() -> None:
    """The actual SDK loader discovers exact reviewed top-loop surfaces."""
    check_generated()
    catalog = json.loads(build_mode_catalog_json(resolve_mode_roots([get_content_root()])))
    _, lisa = load_manifests()
    expected = {mode.mode_id for mode in lisa.modes if mode.activation == "catalog"}
    assert expected == {
        "hdae_architect",
        "hdae_use_cases",
        "hdae_plan",
        "hdae_decide",
        "hdae_evaluate",
        "hdae_execute",
    }
    assert expected == set(catalog)
    for mode in lisa.modes:
        if mode.activation != "catalog":
            continue
        actual = catalog[mode.mode_id]
        assert actual["mode_provider_id"] == "lisa-pack-hdae"
        assert actual["mode_kind"] == mode.mode_kind
        assert actual["allowed_operation_ids"] == mode.allowed_operation_ids
        assert actual["allowed_tool_ids"] == []
        assert actual["routable"] is False
        assert actual["accept_default_capabilities"] is False
        assert actual["tools_authoritative"] is True
        assert actual["entry_operation_ids"] == []
        assert actual["pre_turn_operation_ids"] == mode.pre_turn_operation_ids
        assert actual["pre_turn_failure_policy"] == mode.pre_turn_failure_policy
        assert actual["post_turn_operation_ids"] == []
        assert actual["task_completion"] == mode.task_completion
        assert actual["task_artifact_tool_id"] == mode.task_artifact_tool_id
        assert actual["approval_continuation"] == mode.approval_continuation
        front_matter = yaml.safe_load(
            (ROOT / "modes" / mode.mode_id / "_mode.md").read_text().split("---", 2)[1]
        )
        assert front_matter["fork_allowed"] is False
        assert actual["instruction_body"].endswith((ROOT / mode.template_path).read_text().strip())
