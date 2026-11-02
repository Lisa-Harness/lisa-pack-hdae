# Verification and Remaining Gates

## Deterministic Evidence

The whole scenario uses a scripted provider gateway with real operations,
catalog loading, approval consumption, protected state, coding worktree, bwrap,
subprocess tests, Git commits, the generated worker action mode, and actual
kernel turn completion. It includes a real failing check before the fix and
separate top-loop checkpoint acceptance.

The recording driver additionally lets the gateway choose the edit/check/verify
sequence and stops before acceptance. Its operator approval choices are scripted
and explicitly labeled. That adapter is test-only nested-operation reconciliation.

Run offline from the parent lisa-packs checkout:

```sh
export PYTHONPATH="$PWD/hdae:$PWD/../lisa-packs-wip/coding:$PWD/bwrap"
export HDAE_TEST_CODING_ROOT="$PWD/../lisa-packs-wip/coding/lisa_packs/coding"
export HDAE_TEST_BWRAP_ROOT="$PWD/bwrap/lisa_packs/bwrap"
../lisa/.venv/bin/python -m pytest -c hdae/pyproject.toml \
  hdae/lisa_packs/hdae/tests -m 'not live' -q -p no:cacheprovider
```

These integration tests require the real coding and bwrap providers, working
Linux bubblewrap, and the modified framework. They do not substitute host
execution if containment fails. All fixture Git commits are confined to
temporary test repositories and have signing disabled there only.

The framework's full configured offline suite passed 4,395 tests with three
skips and one expected failure before the final bounded binary-fingerprint
addition. Its focused persistence/proof tests passed afterward. Source-wide
framework mypy and strict pack mypy passed. Consult current command output for
the final totals rather than treating these historical counts as release proof.

An initial wheel was installed into a separate temporary directory, and source
provenance plus generated content were validated from outside the checkout.
Final packaging must be rerun after remaining edits.

## Ginux Exercise

Fresh checkout: `gmkurtzer/ginux` at
`759cf2e221b459b0195c3fa7ed909688b755e74e`.

The machine had QEMU and openSUSE OVMF firmware. Rust 1.99.0, rustfmt, clippy,
and the UEFI and freestanding targets were installed into a checkout-local
toolchain; the user's default toolchain was not changed.

The environment explicitly selected TCG, OVMF code, and OVMF variables. `make
check` passed. `make test-c1` reached the ring-3 controller and exercised its
commands but failed when starting the embedded minimal system:

```plaintext
ginux> domain start demo
ginux: minimal system init execution failed
GINUX_KERNEL_PANIC
Controller console test failed: QEMU did not shut down within 75 seconds.
```

The test harness terminated QEMU. This is a failed real exercise, not a passed
Ginux gate, not evidence of full OS compatibility, and not execution through the
HDAE pack's configured bwrap runner. No existing VM disk was reset.

## Live Model Evidence

See [demo instructions](DEMO.md) and [the receipt](live-demo-receipt.json).
The selected OpenRouter alias returned `z-ai/glm-5.3-flash` in provider metadata.
One live-created commit passed independent offline verification, but the live
pytest run reached its request cap after doing the work. A separately authorized
rerun also reached its cap without verified delivery. Aggregate reported cost
was USD 0.0030282754. Neither attempt is a certified passing live pytest run.

No human acceptance was recorded for either live fixture. No further paid retry
is implicitly authorized. The deterministic stop-condition repair and richer
worker feedback have been tested without network calls, not certified by a new
live run.

## Remaining Release Gates

- Successful live-model E2E suitable for a repeatable demonstration.
- Pack dogfood through the pack after the disclosed external bootstrap.
- A passing real Ginux/QEMU gate through the approved execution profile.
- Production nested-operation continuation, not a test-only replay adapter.
- Approved batches/delegated closure and deferred/reopened gate lifecycle.
- Explicit recovery and revocation without weakening exclusive claims.
- Human-evaluated criteria and complete traceability audits.
- Full redacted reproducible export and independent rerun.
- Final framework coverage, dead-code, and architecture gates.

The pack is an experimental implementation slice, not completion of every
requirement in the parent specification. Unsupported rules remain classified in
the binding manifest; do not convert them to enforcement claims based on this
document.
