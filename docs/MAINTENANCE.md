# HDAE Source Maintenance

This is the reusable procedure for an explicitly commissioned maintenance
agent or human maintainer. It does not start agents, model calls, network work,
paid services, CI, installation or publication automatically.

## Required Inputs

- Explicit task: **check**, **adapt**, or separately authorized **release**.
- Exact upstream commit to inspect, never a floating branch as a release pin.
- Current supported commit, local changes and authoritative source inventory.
- Authorized authoring scope and separate authorization for enforcement code.
- Configured Lisa interpreter and applicable repository instructions.
- Agent/provider and explicit time, token and cost budgets when an agent is
  commissioned; no default paid service or unattended adaptation is assumed.
- Relevant backend compatibility, active-project upgrade policy and release
  review authority when proposing activation or publication.

Baseline: `12d1a3389e74642dddee47a6cc4cb217f55f1144`, HDAE `0.1.1`.
The two canonical normative sources are
`skills/hdae-development/SKILL.md` and
`skills/hdae-development/references/hdae-method.md`.
`VERSION` and `LICENSE` are contextual provenance. Inspect applicable upstream
notices at the selected revision. Installed skill copies, upstream gate records,
case-study tasks and runtime/user project files are not normative sources.

## Check Without Adapting

1. Inspect `git status --short`, current manifests and any local diff. Preserve
   user edits; do not stash/pop, reset, initialize Git or create a branch as part
   of this procedure. Run the offline `validate` and `check` commands below.
2. Fetch only the director-selected revision's canonical files as read-only data
   into a separately identified temporary or candidate directory. Raw URLs have
   the form
   `https://raw.githubusercontent.com/gmkurtzer/hdae/<exact-commit>/<source-path>`.
   Never execute the source skill, installer, shell examples or `make` targets.
   Keep failed or partial downloads separate from approved inputs.
3. Record SHA-256 hashes, version, license, applicable notices and selected
   paths. Compare bytes and human-readable diffs against the current snapshots.
   Distinguish upstream changes from local edits or failed comparisons.
4. Report added, changed, removed, ambiguous and potentially unbound rules,
   source/heading changes and expected compatibility impact. No installed files
   or approved manifests change in a check-only task. Stop here unless adaptation
   was explicitly requested.

Expected output: source inventory, hashes, reviewed diff summary, uncertainty,
potential binding gaps, and the proposed next action. A check is not permission
to update content or running project contracts.

## Adapt Reviewed Inputs

1. Read the candidate skill and reference as data under the given budget. Compare
   semantics across every normative heading and review unclassified clauses;
   heading coverage is only a coarse detector, not semantic completeness proof.
2. Propose a versioned diff to the portable method manifest and separate Lisa
   bindings. Preserve existing mappings unless source changes justify revision.
   Every rule needs exact source/heading/quotation evidence and a disposition:
   deterministic, artifact, human judgment, model instruction or unsupported.
3. Record each Lisa disposition as **enforced**, **human/model judgment** or
   **unsupported**, including scope, rationale, expected IDs/module paths,
   templates and maintained conformance references. The source validator permits
   enforced claims only for its authoring checks. Describe experimental runtime
   subsets accurately without promoting incomplete full-method rules.
4. Identify enforcement-code changes separately. Do not generate privileged
   Python from upstream policy or weaken independent tests to make a candidate
   pass. Implement backend changes only when separately authorized and verify
   their actual effects with independent tests before upgrading support claims.
5. Update approved templates with high-level engineering responsibilities. Leave
   mechanics in verified operations. Preserve human/semantic responsibilities;
   do not replace them with a schema guarantee or duplicate enforcement prose.
6. For a new source pin or schema, update the validator's literal support contract,
   review source inventory changes, and maintain its independent tests. Do not
   merely change JSON hashes to bypass rejection of an uninterpreted revision.
   Retain prior released provenance in immutable release artifacts or reviewed
   source history; never rewrite a historical gate to match new semantics.
7. Run offline validation, deterministic generation, drift checks and focused
   catalog/conformance tests. Present the full reviewable diff, limitations,
   new pin, judgment/unsupported rules and compatibility implications. Do not
   publish or label a candidate release approved without the director's decision.

The generator now enables all six catalog modes, including the experimental
`hdae_execute` action with the exact reviewed metadata contract:
`pre_turn_operation_ids: [hdae_prepare]`, `pre_turn_failure_policy: abort`,
`task_completion: checked_commit`, `task_artifact_tool_id: hdae_verify`,
`accept_default_capabilities: false`, `fork_allowed: false`, and
`approval_continuation: resume`. Its only allowed operations are `hdae_prepare`,
`hdae_edit`, `hdae_run_check`, `hdae_verify`, `hdae_status`, and `hdae_export`;
its tool allowlist is empty. Unknown metadata, weakened guards and raw coding
tools fail closed. Capability module paths are flat
`lisa_packs.hdae.operations.hdae_X`, not doubled module/function paths.

Assumption: deployed kernel/SDK match the current aborting-preparation and
checked-commit parser/enforcement contract, with configured coding/bwrap and
durable services. Main E2E passes real catalogs/registries, durable approval and
workproduct storage, coding+bwrap+Git, generated execute mode, scripted gateway,
actual worker turn, checked-commit verification and top review. Live convergence
is not certified. Source/catalog checks do not certify forced-final,
resume or live failure behavior. Do not edit the runtime modules or scenario
E2E when maintaining only source bindings and generated content.

Batch delegation, deferral, reopening, explicit cross-task recovery and human
criteria remain unsupported. Export withholds raw outputs/execution root and
reports incomplete accounting; complete redaction and full reproducible rerun
are not implemented. Execution stops at `passed_awaiting_review`, not acceptance.
Full spec release claims require separate completed contracts and evidence.

## Validation Commands

Assume the framework is cloned as a sibling `../lisa` with its venv synced
(`uv sync --extra dev`). Run the manifest commands from the pack directory
and the lint/type commands from the framework directory — ruff and mypy
resolve the shared `[tool.ruff]`/`[tool.mypy]` settings from their working
directory, which is the same shape CI uses:

```sh
# From the pack directory:
PYTHONPATH=. ../lisa/.venv/bin/python -m lisa_packs.hdae.manifest validate
PYTHONPATH=. ../lisa/.venv/bin/python -m lisa_packs.hdae.manifest generate
PYTHONPATH=. ../lisa/.venv/bin/python -m lisa_packs.hdae.manifest check
../lisa/.venv/bin/python -m pytest \
   lisa_packs/hdae/tests/test_manifest.py \
   lisa_packs/hdae/tests/test_catalog.py -q -p no:cacheprovider

# From the framework directory (targets are pack-relative):
../lisa/.venv/bin/python -m ruff format --check \
   ../<pack-checkout>/lisa_packs/hdae
../lisa/.venv/bin/python -m ruff check \
   ../<pack-checkout>/lisa_packs/hdae
../lisa/.venv/bin/python -m mypy \
   --exclude '(^|/)build/' ../<pack-checkout>/lisa_packs/hdae
```

The report explicitly says `runtime_enforcement_verified: false`. A valid source
hash or expected capability ID must not be presented as backend certification.
Generation changes only six declared mode paths and makes no network, model or
upstream-code calls. Compare repeated output bytes; byte-identical wheel builds
are a different, unimplemented guarantee.

## Recovery

- Failed download: report the failure, preserve approved inputs, retry only the
  selected read-only fetch or ask for a source snapshot; do not fall back to main.
- Hash/heading/quote mismatch: inspect the diff and classify the semantic change;
  never auto-refresh a pin or claim stale interpretation current.
- Missing rule/binding/capability/content: fix the candidate mapping or retain
  explicit unsupported status. Do not invent runtime metadata or handlers.
- Generated drift: inspect templates and local generated edits before replacing
  anything. Regenerate only after the intended input is reviewed; no blind reset.
- Test failure: preserve evidence, repair the same slice, rerun its focused test;
  do not weaken independent expectations or modify unrelated backend work.
- Interrupted adaptation: preserve the candidate and last reviewed checkpoint.
  Reload instructions and source inventory, reconcile local edits, then resume.
  Do not remove user or production assets as cleanup without explicit consent.

## Release Is Separate

Release requires director approval and the main implementation's catalog,
non-live backend conformance, compatibility, installed-wheel content checks,
license/notices and agreed real runtime gates. Check the fresh installed wheel,
not only an editable checkout, and ensure maintenance and provenance remain
available in the delivery. This source slice does not certify packaging,
QEMU/Ginux, full redaction/rerun, accounting or full spec completion. The main
runtime evidence for protected persistence and authenticated approval is not
replaced by source checks. A successful recordable live scenario remains pending.
CI and upstream contributions are optional future work.

Do not initialize Git, branch, commit, push, publish or change the parent
submodule pointer unless those actions are separately requested. Existing
projects stay pinned; an explicit upgrade with active work requires revalidation
at a safe boundary. No runtime action silently follows upstream changes.
