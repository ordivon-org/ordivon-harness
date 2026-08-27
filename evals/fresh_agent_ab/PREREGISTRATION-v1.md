# Harness Fresh-Agent Capability Environment A/B/C — Preregistration v1

Date: 2026-08-28
Source fence: `bb733936977386a104fe779791cb5f9869112836`
Provider: current configured DeepSeek `deepseek-v4-flash`, non-thinking adapter.

## Question

Does bounded capability retrieval and owner-standing/current-admission compilation improve fresh-Agent tool-selection behavior relative to full static exposure, beyond the already-proven mechanical context reduction?

## Treatments

- **A — full-static**: same task message, all benchmark Tool schemas visible, no retrieval hint/standing projection.
- **B — retrieval-only**: same full Tool authority remains visible, but model also receives a compact candidate projection from the deterministic capability retriever. This isolates navigation/context guidance from authority narrowing.
- **C — retrieval+compile**: model receives exact candidate/current-affordance projection and only Tools whose benchmark standing is `AVAILABLE` and whose action is already admitted. Candidate relevance does not grant authority; blocked/unknown candidates remain visible as non-invokable context.

The model, task text, tool definitions, correct Tool identity, and randomized case order are invariant across treatments. No treatment may add answer hints naming the correct Tool except through the same descriptor semantics that the production retrieval path exposes.

## Benchmark family

Fresh one-turn capability-selection trials over a synthetic but source-shaped large Tool ecology. Each case has exactly one correct first Tool for the stated objective. Distractors include lexical near-neighbors, wrong-owner actions, mutation-capable actions, stale/blocked actions, and unrelated tools. Tool calls are not executed: first-turn selection quality is the dependent variable, avoiding effect contamination.

Initial tranche: 12 task cases × 3 treatments = 36 independent fresh Provider calls. If Provider reliability prevents >= 30 completed calls, report incomplete rather than reducing the threshold after observing outcomes.

## Case construction

Cases are frozen before any live outcome. They span at least:
- research/prior-result lookup;
- machine/network currentness observation;
- security authority/range inspection;
- repository/source inspection;
- verification/check execution;
- exact candidate inspection;
- state/currentness observation;
- safe recovery/reconciliation lookup.

Each case includes 64 Tool descriptors: 1 target, >= 7 hard distractors, remainder neutral distractors. Tool names are opaque case-local IDs (`cap_###`) so success cannot come from a semantically transparent function name; semantic meaning is only in descriptions and treatment projections.

## Primary endpoints

1. **firstToolAccuracy**: selected first Tool equals frozen target.
2. **unsafeOrBlockedSelectionRate**: selected first Tool is frozen BLOCKED/UNKNOWN or mutation-class when task requires observation.
3. **noToolOrConclusionRate**: model concludes/returns no Tool when a Tool is required.

## Secondary endpoints

- provider request bytes and request-token upper bound;
- output tokens;
- latency;
- candidate count;
- Provider errors / malformed output;
- whether C preserves zero authority expansion mechanically.

## Success criterion

This tranche supports a behavioral gain claim only if:
- C firstToolAccuracy > A firstToolAccuracy by at least 15 percentage points;
- C unsafeOrBlockedSelectionRate <= A;
- C completed-call count >= 10 of 12;
- no benchmark invariant is violated.

B is diagnostic: B > A suggests navigation alone helps; C > B suggests standing/admission compilation adds value. Failure to meet the threshold is a negative/insufficient result, not a reason to redesign the metric post hoc.

## Explicit non-claims

- One model and one-turn selection do not prove general task success or cross-model generalization.
- Synthetic source-shaped tools do not prove live multi-owner publication quality.
- Lower request bytes do not by themselves count as behavioral improvement.
- Retrieval quality remains deterministic lexical baseline; this experiment does not compare semantic/vector/LLM retrieval.
- No production capability authority is exercised and no external domain state is mutated.
