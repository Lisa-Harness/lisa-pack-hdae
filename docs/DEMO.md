# Small-Repository HDAE Demo

## Current Result

The live-created artifact is independently verified as **passed_awaiting_review**.
The live pytest runner itself **failed at its cumulative 12-request limit** after
commit approval; this is not a certified passing live pytest run. No further paid
requests were made after that limit.

The literal host-manifest model `~z-ai/glm-flash-latest` is tool-capable and uses
OpenRouter. It was sent unchanged; all 12 provider responses identified the actual
model as `z-ai/glm-5.3-flash`. Aggregate usage was 39,707 input and 3,935 output
tokens. OpenRouter reported USD 0.00149485 in total, independently of the
conservative admission estimate of USD 0.359874. Cumulative wall time, including
the repair interval, was 128.737 seconds. Provider timestamps are UTC 2026-11-02.

The first request exposed a test-only telemetry bug: SDK tool calls have flat
`name` fields, not nested `function` fields. An offline regression test covers the
repair. The continuation retained that request's usage, cost and original start
time; it did not reset the shared budget. There were two pytest live invocations,
one evidence-based telemetry repair, and no scripted model fallback.

The model chose `hdae_edit`, `hdae_run_check` and `hdae_verify`, but also repeatedly
chose prepare/status/export. Real exact edit, check and commit approvals executed.
After the runner stopped, an independent offline verifier reopened the retained
fixture and checked the actual source, committed HEAD, clean worktree, host
completion contract, evaluator and export. The criterion `counter` passed check
`behavior`. The gate remains in `gates-todo`, never `gates-done`.
`hdae_accept` was not invoked and human acceptance remains false.

See [the safe receipt](live-demo-receipt.json) for the commit, evidence fingerprint,
accounting and retained fixture locations. Pack dogfooding is **not implemented**.

An explicitly authorized rerun also failed at its 12-request limit, without a
verified commit. It made 12 requests, used 39,189 input and 3,793 output tokens,
and reported USD 0.0015334254 over 124.772 seconds. Total reported cost across
attempts is USD 0.0030282754. The retained receipt identifies this separately;
it does not replace the first attempt's independently verified artifact.

The driver now checks persisted verified state after approved commit
reconciliation and stops without requesting unnecessary model narration. That
change and richer runtime check feedback pass offline tests. No later paid run
has certified the current implementation.

## Offline Reproduction

The driver is [the live scenario test](../lisa_packs/hdae/tests/test_live_scenario.py).
From the lisa-packs checkout, use the existing framework environment and sibling
coding pack. Git commands execute only inside disposable fixture repositories.

```sh
export PYTHONPATH="$PWD/hdae:$PWD/../lisa-packs-wip/coding:$PWD/bwrap"
export HDAE_TEST_CODING_ROOT="$PWD/../lisa-packs-wip/coding/lisa_packs/coding"
export HDAE_TEST_BWRAP_ROOT="$PWD/bwrap/lisa_packs/bwrap"
../lisa/.venv/bin/python -m pytest -c hdae/pyproject.toml \
   hdae/lisa_packs/hdae/tests/test_live_scenario.py \
   -p no:cacheprovider -q --tb=short
```

Result: two passed, one live test skipped. Ordinary execution makes no paid calls.
The deterministic scenario uses scripted decisions with real operations,
approvals, worktrees, subprocess checks and commits. The second offline test
covers SDK-normalized tool accounting without any network requests.

## Opt-In Live Command

The following is the recording command pattern, not authorization to exceed this
recording's exhausted request allowance. The test reads existing host OpenRouter
credentials privately using host dotenv candidate locations and credential names.
Do not put credentials in the command, public receipt or provider error output.

```sh
live_base="/tmp/lisa-hdae-live-demo-$(date -u +%Y%m%dT%H%M%SZ)-$RANDOM"
test ! -e "$live_base" || exit 1
HDAE_RUN_LIVE=1 ../lisa/.venv/bin/python -m pytest -c hdae/pyproject.toml \
   hdae/lisa_packs/hdae/tests/test_live_scenario.py::test_live_openrouter_demo \
   --basetemp "$live_base" -p no:cacheprovider -q --tb=no --show-capture=no
```

Use the exports from the offline command first. Never reuse an existing
`--basetemp`: pytest may delete it. The resulting fixture and sanitized
`live-receipt.json` are retained, not cleaned up by this recording.

An explicitly approved repair can set `HDAE_LIVE_PREVIOUS_RECEIPT` to the prior
sanitized receipt path. The continuation carries cumulative calls, tokens, cost,
estimates and the original start time. This recording's latest receipt already
contains 12 calls, so it admits no more paid requests.

Admission counts every HTTP attempt, including SDK compatibility fallbacks.
Retries are disabled. Each request allows at most 4,096 output tokens and
262,144 encoded input bytes. Reservations charge every input byte as a token at
the greater of manifest pricing or USD 1/M input and USD 4/M output, reserving the
full output allowance before sending. The separate ceilings are USD 5 and 1,200
cumulative wall seconds. Missing provider cost is reported as unknown, never
inferred from the reservation. These are client-side admission limits, not an
OpenRouter account spending control.

## Recording Stages

1. Publish the architecture and define a gate for the counter to report one.
2. Record an explicit operator authorization of the exact gate document.
3. Prepare the isolated coding worktree and observe the failing behavior check.
4. Give the worker its initial source, exact source hash, authorized gate and
   instruction to choose bounded edits and checks through HDAE function calls.
5. Pause at each exact coding edit, check and commit invocation. Approve only
   that invocation and execute it through `execute_approved_invocation`.
6. Reconcile the enclosing operation and enter a fresh real `run_turn`.
7. Independently verify the committed source, HEAD, clean worktree, host checked
   commit contract and evaluator evidence before reporting success.
8. Leave the gate in `gates-todo`. Never call `hdae_accept` in this demo.

Planning and approvals are scripted operator decisions. Execution choices in
the live phase are real model responses. The initial source and hash are supplied
by the harness; no model-chosen source-read operation is demonstrated.

The driver-local adapter reconciles the already executed child result into its
suspended enclosing operation, checking tool ID, parameters and one consumption.
It is **not production host recovery**. It does not fabricate successful tool
results. No runtime, engine, scenario or generated metadata was edited here.

The remaining blocker is live runner convergence within the approved request cap,
not credentials, the actual code fix, criterion verification or export. A new paid
attempt requires a new explicit request allowance. Raw prompts, provider responses
and credentials are excluded from the public receipt.
