# Ordivon Harness P2 programmatic Tool composition closeout

> Historical implementation evidence. Current product boundaries remain owned by `README.md`, `docs/STATUS.md`, `docs/COMPATIBILITY.md`, and `docs/authority.md`.

## Accepted structure

P2 asked whether one Agent semantic decision can drive several observation-dependent Tool effects without another model turn for every mechanical dependency. It did not create a general controller runtime.

The retained advanced path is:

```text
model semantic plan
→ Harness-native ToolProgram action
→ bounded linear steps over exact current AgentTurnRequest.tools
→ each step executes as one ordinary physical Tool Call
→ existing ToolBridge intent/fence/receipt/reconciliation
→ one compact ToolProgram result
→ next Provider turn
```

Prior results are referenced only by exact JSON-value substitution such as `{"$harnessObservationRef":{"stepId":"read","path":["sourceDigest"]}}`. Programs are bounded, linear, deterministic, and may reference only already completed steps.

## Authority / recovery

ToolProgram is not a Runtime Tool. Provider schemas enumerate only Tool names admitted on the exact current turn, and Loop admission independently rechecks every step. Each inner step consumes one existing Tool-call budget unit and keeps existing cancellation, Runtime error mapping, durable effect evidence and UNKNOWN semantics. UNKNOWN stops the program before later steps.

Intermediate observations are used mechanically but are not replayed one-by-one into model context. The next model turn receives one compact projection with exact step identities/status/digests/Runtime-artifact references plus bounded declared outputs.

Restart recovery derives from the immutable outer action and existing per-step durable evidence. Complete retained Tool content can reconstruct the next exact cursor or terminal result. Metadata-only continuity can prove already-terminal effects but, when required dataflow bytes were not retained, returns `recovery-required / tool-observation-content-unavailable` instead of redispatching from step zero.

## Ablation

The maintained repository-repair workload performs the same physical sequence in both variants:

```text
read → digest-bound patch → check → diff → reread
```

Baseline: **7 model calls / 5 physical Tool calls**.

Agent-authored ToolProgram treatment: **2 model calls / the same 5 physical Tool calls**.

The first treatment turn plans the program; Harness performs the mechanical chain; the second model turn receives the compact result and concludes. Response-loss reconciliation remains single-dispatch, and unreconciled UNKNOWN stops before a second Provider turn or later program effect.

DeepSeek exposes `compose_tool_program` only when the exact turn capability is admitted. It decodes to a native `HarnessToolProgramAction`, not a synthetic Runtime Tool.
## Acceptance

Release acceptance passed **398 tests with 3 skipped**, plus Ruff, compileall, dependency/documentation/evidence contracts and deterministic demo. Full acceptance Runtime Job: `job-019ffcd7-2c43-70a2-9401-2403015ad6bc`.

The isolated wheel build/install gate also passed with the stable installed API unchanged. Wheel Job: `job-019ffcd9-27e1-7523-a4bb-f23a78bac87f`.


## Retain / shrink / reject

**Retain:** bounded linear ToolProgram IR; exact prior-observation references; opt-in native turn capability/action; per-step existing Tool accounting/evidence; compact model projection; deterministic/durable recovery; DeepSeek control action.

**Shrink:** the new modules remain advanced and are not promoted into stable package-root / `ordivon_harness.api`. No program registry, scheduler, separate ledger or second effect store was added.

**Reject:** arbitrary controller-code execution as the composition primitive; loops/branches/expressions; program-level physical authority; hidden inner Tool accounting; continuation after UNKNOWN; automatic installation on every Tool-bearing Run.

P2 therefore establishes: **semantic planning by the model, mechanical composition by Harness, physical authority/evidence per Tool effect, bounded projection back to model context.**
