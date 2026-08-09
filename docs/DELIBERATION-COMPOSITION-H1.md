---
schema_version: 1
id: harness.research.deliberation-composition-h1
title: Deliberation Composition H1
type: experiment
profile: research
lifecycle: active
source_role: canonical
visibility: public
owners:
  - ordivon-harness
updated: 2026-08-09
summary: H1 validates a narrow Harness-owned composition that runs one no-Tool cognition turn, binds an exact non-authoritative cognition record to the same Context, and then exposes the caller-owned domain Tool loop without taking ownership of strategy, admission or effects.
evidence_status: verified
readiness: ADVANCED_RESEARCH
related:
  - harness.research.deliberation-before-tools-h0
  - harness.status
  - harness.architecture
---
# Deliberation Composition H1

## Pressure inherited from H0

H0 independently reproduced the ordering failure that had first appeared in Security:

```text
immediate Tool surface
→ model emits Tool choice
→ only afterward emits correct considered reasoning
```

In H0 baseline replicate 2 the Tool records `atlas`, while the following conclusion correctly proves `atlas` infeasible and `cobalt` uniquely optimal. Both predeclared no-Tool-deliberation-first replicates later choose `cobalt`.

H1 does **not** rerun that baseline. H0 remains immutable evidence. H1 asks a smaller engineering question:

> Can Harness replace the hand-written two-phase glue with one narrow generic composition while preserving the same Context, same caller-owned Tool bridge and correct H0 treatment behavior?

## Primitive

H1 adds an advanced/internal module:

```text
src/ordivon_harness/deliberation.py
```

Core composition:

```text
AgentTurnRequest(tools=())
        ↓
DeliberationThenToolRunner
        ↓
NonAuthoritativeDeliberationRecord
        ↓
standard user-role cognition envelope
        ↓
caller DomainToolLoopPlan
        ↓
caller DomainToolBridge
```

The helper owns only:

- phase ordering;
- exact cognition-record identity;
- same-Context binding;
- same adapter object across both phases;
- standardized transition from no-domain-Tool cognition to caller Tool exposure.

It does **not** own:

- domain scoring;
- domain strategy;
- semantic correctness;
- domain admission;
- external effect execution;
- persistence;
- a new cross-phase aggregate budget policy.

## Mechanical invariants

The primitive fails closed before Provider dispatch when:

```text
deliberation_request.tools != ()
```

or:

```text
deliberation_request.context_digest
!=
tool_plan.context_digest
```

The deliberation request must also use default non-mutating Harness capabilities.

After the no-Tool Provider turn, H1 requires:

```text
no Tool calls
candidate_completed conclusion
requested model identity == runner adapter model
```

The resulting cognition record binds:

```text
context digest
request dispatch digest
Provider result digest
adapter ID
requested model ID
effective model ID
summary
unresolved unknowns
```

and declares:

```text
domainToolIntent = false
domainAdmission  = false
externalEffect   = false
```

The model-visible projection is always appended as a `role=user` message with the explicit marker:

```text
PRIOR_NON_AUTHORITATIVE_SELF_DELIBERATION_RECORD
```

and text stating that the record is not world truth, Tool intent, admission or proof of external effect.

This intentionally avoids pretending the cognition record is ordinary assistant transcript history.

## Why existing `projected_no_tool` was not reused

Before H1, Harness already had `WorkingViewNoToolTurnRunner` in `projected_no_tool.py`. Its own contract is intentionally P-C1.1-specific and explicitly excludes Tool use, multi-turn reasoning and domain admission. It proves WorkingView/History separation; it is not a generic cognition→Tool composition.

H1 instead composes lower-level existing primitives:

```text
AgentTurnRequest(tools=())
DeepSeek/other AgentTurnAdapter
DomainToolLoopRunner
caller DomainToolBridge
```

without changing P-C1.1 semantics.

## Mechanical validation

At the H1 candidate revision, targeted tests prove:

1. a no-Tool cognition turn and later Tool loop use the same adapter instance;
2. the caller bridge receives and records the domain Tool call unchanged;
3. Tool-bearing deliberation fails before Provider dispatch;
4. Context mismatch fails before Provider dispatch;
5. non-`candidate_completed` cognition cannot open the Tool phase;
6. injected cognition is user-role and explicitly non-authoritative.

The Harness full test suite also passes before the physical run.

## Physical acceptance

Physical apparatus revision:

```text
89a7fa125bb8b1facc51bd89cb7eb1cdae3f0b4e
```

Primitive source identity:

```text
sha256:a526c581ec2f5f0af5afc4f8684fcce073d7eb9dc422100ee3f24bfb3d45ceb0
```

Acceptance script identity:

```text
sha256:1aef772a61115ced3f7f5f483e52dcdabb1579f629641b9d7490f2b0afe0aa06
```

Raw receipt is retained byte-for-byte at:

```text
evidence/harness-h1-deliberation-composition-89a7fa1.json
```

Physical receipt:

```text
bytes  = 23960
sha256 = sha256:04a6a9164945487964a03e89a512ffe20930af182469b6101269db99370a6402
```

Runtime binding:

```text
jobId                 = job-019fe695-75eb-7842-8292-a14c58b66248
executionPlanDigest   = sha256:d1ce24fba38d08c4f31ce1bea9c036f20e6e882113cf7f86cda25349683f6f08
workspaceSourceDigest = sha256:b99986a261b2977a0e25992e24f7bad49410733aa804bb37faaae8cf987ea11a
executionProfile      = trusted_local
```

The H0 neutral task remains exact:

```text
taskDigest = sha256:b402b3066ebd0fa64c4e464fd4f1640a3cd1cc08b0164426f2a39805f56e223f
oracle     = cobalt
```

H1 predeclares two composition replicates; H0 baseline is not resampled.

### Replicate 1

No-Tool cognition derives `cobalt`, then the generic Tool phase records:

```text
choiceRevisions = [cobalt]
finalChoice     = cobalt
```

Evidence:

```text
deliberation digest = sha256:b27d529cd1d9d30735e9b10f55bdf875f275f3e5f5bc3a408f7459a5564142b5
execution digest    = sha256:27d222cb58ed5900caad9becf600477424693cb160845a8354e004c9e292cd85
envelope digest     = sha256:d62073c11f1e46b9fddeba6c0ac8c0ba006096a18ce504f8fc3dd1196a9aaf8d
tool trace digest   = sha256:405c2f5f9f0cfd44916d2e15ee6335d87282fc3e9c119f862c6ef332af96c709
```

### Replicate 2

No-Tool cognition independently derives `cobalt`; the Tool phase again records:

```text
choiceRevisions = [cobalt]
finalChoice     = cobalt
```

Evidence:

```text
deliberation digest = sha256:6ea3dd372bab81ec97d2957023f07f292df763e3dc2931bef9c9ced147e479bf
execution digest    = sha256:32db2540d6da2a27a6011d01928d180eea9bfc81381255d2775ef3e1000c77c8
envelope digest     = sha256:870aa1690a21db4e566e44296c46c3f59d22bd5be7a0bd46088e67c1ddb9504b
tool trace digest   = sha256:20738eeecf23c40e045fcd76d95ad252ec057bbad08c20264e1ff13727de381c
```

Both use:

```text
requested model  = deepseek-v4-flash
credential scope = credential-scope:deepseek:flash:0
```

All 10 H1 acceptance gates pass.

Retained classification:

```text
generic-composition-accepted-in-h0-consumer
```

## What H1 establishes

H1 establishes an engineering point, not a new model-science claim:

```text
Harness can own the composition:
no-Tool cognition
→ exact non-authoritative cognition record
→ later caller Tool surface
```

without owning the domain decision.

The H0 application-specific two-phase glue is therefore no longer structurally necessary for this consumer.

## What H1 does not establish

H1 does not establish:

- a population-level causal benefit;
- a mandatory hidden planning pass for every Agent turn;
- that every Tool-bearing task needs two phases;
- semantic correctness of the cognition record;
- domain strategy authority inside Harness;
- external effect safety;
- durable persistence of deliberation records;
- a unified cross-phase budget;
- a recommended public API contract.

The module therefore remains an **advanced/internal validated composition**, not an exported recommended `ordivon_harness.api` surface yet.

## Known productization gaps

Two lifecycle semantics remain before a recommended API should be considered.

### 1. Cross-phase budget

The deliberation request and Tool plan retain caller-supplied independent budgets. H1 deliberately does not claim a new aggregate budget across both phases.

A public composition would need a clear rule for whether/how total model calls, tokens and wall time are bounded across the entire composed operation.

### 2. Cancellation

The current optional `cancellation` argument is forwarded to phase B `DomainToolLoopRunner`. Phase A uses the generic direct `AgentTurnAdapter.invoke` contract, so H1 does not yet establish one cancellation boundary spanning both phases.

Until this is resolved, the composition should remain advanced/internal.

## Next pressure — H2

H2 should be a **lifecycle semantics experiment**, not another choice-quality experiment.

The smallest questions are:

```text
Can one cancellation authority cover both phases without Provider-specific policy?
Can one caller-owned aggregate budget be consumed across deliberation + Tool loop without double-spending?
```

If the existing AgentTurnAdapter/DomainToolLoop contracts cannot support those semantics cleanly, H1 should remain internal rather than widening the API.
