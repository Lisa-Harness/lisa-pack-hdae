# Lisa HDAE Experimental Runtime

This slice binds Gregory M. Kurtzer's Human-Directed Agentic Engineering method
to reviewed Lisa content and an **experimental runtime**, not a full spec release.
Pinned source snapshots are data, not executable build instructions. A separate
Ginux checkout was built and its console gate exercised; results are recorded
in [verification](docs/VERIFICATION.md), including the failed console run.

The source pin is `gmkurtzer/hdae` commit
`12d1a3389e74642dddee47a6cc4cb217f55f1144`, version `0.1.1`, Apache-2.0.
The canonical development skill and method reference are the normative inputs;
license and version are pinned provenance data.

## Content

- [Method manifest](lisa_packs/hdae/content/source/method-manifest.json):
  portable interpretation, source hashes, heading/quotation references, artifact
  roles, gate structure, lifecycle, and 27 classified rules.
- [Lisa bindings](lisa_packs/hdae/content/source/lisa-bindings.json):
  capability IDs and explicit module paths, mode surfaces, adaptations,
  dependencies and each rule's disposition.
- [Source inventory](lisa_packs/hdae/content/source/upstream/README.md):
  exact canonical snapshots, not executable build instructions.
- [Templates](lisa_packs/hdae/content/templates/gate.md): upstream-compatible
  gate sections plus product, architecture, strategy, checkpoint, optional use
  case, decision, and six high-level mode bodies.

Six generated, explicitly invoked modes are catalog-loaded:
`hdae_architect`, `hdae_use_cases`, `hdae_plan`, `hdae_decide`, and
`hdae_evaluate` are top-level chat modes; `hdae_execute` is the action worker.
All modes reject ambient default capabilities and expose no raw coding tools.

[hdae_execute](lisa_packs/hdae/modes/hdae_execute/_mode.md) is generated with the
vetted production binding:

```yaml
mode_kind: action
pre_turn_operation_ids: [hdae_prepare]
pre_turn_failure_policy: abort
task_completion: checked_commit
task_artifact_tool_id: hdae_verify
allowed_operation_ids:
  - hdae_prepare
  - hdae_edit
  - hdae_run_check
  - hdae_verify
  - hdae_status
  - hdae_export
allowed_tool_ids: []
accept_default_capabilities: false
fork_allowed: false
approval_continuation: resume
```

This requires the current kernel/SDK parsing and enforcing aborting preparation
and checked-commit completion, installed coding/bwrap packs, a Git workspace,
durable approval/workproduct services and trusted session check configuration.
The generator rejects missing or weakened action guards and unvetted metadata.
Capabilities name flat modules `lisa_packs.hdae.operations.hdae_X`, including
`hdae_edit`; the worker cannot authorize or accept its own gate.

The deterministic E2E passes real catalogs/registries, durable approvals and
workproduct storage, coding+bwrap+Git, the generated execute mode, scripted
provider gateway, actual worker turn loop, approval pause/resume, checked-commit
verification, and separate top review. Source/catalog tests alone do not
certify this path. Execution
ends at `passed_awaiting_review`; `hdae_evaluate` performs exact-evidence approved
checkpoint acceptance separately.

The binding classifications are: one **enforced** authoring-template check,
16 **human/model judgment** rules, and ten **unsupported** rules. Enforcement
here means only validating the shipped template, never full runtime conformance.
Unsupported full-method rules can have implemented subsets; their rationales
identify those subsets without upgrading incomplete contracts. Source hashes
and capability IDs are not runtime conformance evidence.

## Runtime Configuration

Use the modified local Lisa framework with the published coding and bwrap
capabilities installed. No default Lisa environment is changed by the tests.
Both sessions must bind the same project and check definitions to HDAE, while
the coding pack receives its own configuration. Never reuse HDAE configuration
as coding configuration; registries resolve each capability's owner.

```yaml
resources:
  packs:
    include: [lisa-pack-hdae, lisa-pack-coding, lisa-pack-bwrap]
    configuration:
      lisa-pack-hdae:
        workspace_root: /absolute/path/to/project
        checks:
          - check_id: behavior
            argv: [.venv/bin/python, -B, tests/probe.py]
      lisa-pack-coding:
        workspace_root: /absolute/path/to/project
        worktree_dir: /absolute/path/to/worktrees
        preparation_recipes:
          - id: project
            prepare_argv: [uv, sync, --frozen]
        checks:
          - id: behavior
            argv: [.venv/bin/python, -B, tests/probe.py]
        required_check_ids: [behavior]
      lisa-pack-bwrap:
        sandbox:
          floor:
            execution: sandbox
            persistence: direct-write
            network: deny
            paths:
              /absolute/path/to/worktrees: rw
```

This is the pack-configuration block, not a complete session plan. Supply model,
surface, routing vocabulary, and existing session requirements separately. Grant
preparation network access explicitly if dependencies need downloading. The
current execution backend requires coding's bwrap floor; alternate QEMU/host
providers are not yet integrated.

The gate ledger stays under the configured project's `hdae/`; protected authority
is stored under the host data directory, keyed by project. Top and worker can
share that data root using distinct surfaces. A separate data root currently
needs an explicit authority-sharing design. Wake the worker explicitly; no
watcher or resident launch service is installed.

`hdae_authorize` and `hdae_accept` require exact-action approval. Inner coding
actions also retain their existing approvals. The demo supplies explicitly
labeled test-operator decisions; this is not a production unattended policy.

## Offline Commands

From the pack directory, with the configured Lisa framework environment:

```sh
PYTHONPATH=. /home/adam/Code/lisa/.venv/bin/python -m lisa_packs.hdae.manifest validate
PYTHONPATH=. /home/adam/Code/lisa/.venv/bin/python -m lisa_packs.hdae.manifest generate
PYTHONPATH=. /home/adam/Code/lisa/.venv/bin/python -m lisa_packs.hdae.manifest check
/home/adam/Code/lisa/.venv/bin/python -m pytest \
  lisa_packs/hdae/tests/test_manifest.py \
  lisa_packs/hdae/tests/test_catalog.py -q -p no:cacheprovider
```

`validate` rejects unknown fields, duplicate JSON keys/IDs, incompatible source
pins, stale hashes or quotations, uncovered headings/rules, fabricated
capabilities, missing content and unsupported enforcement claims. `generate`
writes only the six catalog mode files from reviewed templates and manifests.
`check` compares exact generated bytes without writing. All commands are
offline: no upstream fetch, model call, subprocess policy execution or arbitrary
Python generation. Same approved inputs produce the same mode bytes, not a
claimed byte-identical wheel.

Raw coding tools are not permitted in the execute binding. `hdae_edit` delegates
bounded approved-path changes to the coding owner; `hdae_run_check` uses trusted
configured checks, and `hdae_verify` reconciles evidence before checked delivery.

## Limits And Maintenance

Semantic completeness, adequate tests, usability and risk remain judgment.
The runtime implements exact-action authorization, protected evidence,
exclusive claims, isolated worktrees, automated check freshness and checkpoint
acceptance. Batch delegation, deferral, reopening, explicit recovery and human
criteria are **unsupported**. Export withholds raw stdout/stderr and the execution
root and marks accounting incomplete; a complete redacted reproducible export
and full rerun are **not implemented**. Current-branch execution, automatic PR
creation, historical import, Ginux/QEMU profiles and cost accounting remain
unsupported or unverified. This bootstrap did not enforce its own creation.

The recording driver's exact-child-result adapter is test infrastructure, not
production nested-operation recovery. A live model produced one independently
verified artifact, but neither recorded live pytest attempt passed within its
request cap. Do not present this as a ready-to-record successful live demo.

See [maintenance](docs/MAINTENANCE.md) for separate check, adaptation and release
procedures. Nothing silently follows upstream `main` or changes running project
contracts. Heading coverage does not prove all semantic rules were extracted.
Source integrity hashes do not authenticate an author or human approval.

See [LICENSE](LICENSE) and [NOTICE](NOTICE) for attribution. This adaptation
does not claim upstream endorsement. Installed-wheel and full backend release
gates remain separate obligations owned by the main implementation.
