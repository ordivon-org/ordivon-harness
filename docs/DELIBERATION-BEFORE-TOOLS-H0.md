---
schema_version: 1
id: harness.research.deliberation-before-tools-h0
title: Deliberation Before Tools H0
type: experiment
profile: research
lifecycle: active
source_role: canonical
visibility: public
owners:
  - ordivon-harness
updated: 2026-08-09
summary: Harness-native neutral experiment independently reproducing a Tool-first/later-correct-reasoning mismatch and observing 2/2 correct choices when the same task receives one no-domain-Tool deliberation turn before Tool exposure.
evidence_status: verified
readiness: RESEARCH
related:
  - harness.status
  - harness.architecture
---
# Deliberation Before Tools H0

## Why H0 exists

Security IF0–IF3 exposed a repeated ordering problem: a model could emit a consequential Tool intent and only afterward produce a conclusion that correctly rejected its own Tool choice. That evidence was strong inside Security but still domain-specific.

H0 asks whether the same phenomenon exists in Harness without Security authority, truth, message or payoff semantics:

> On a neutral mechanically scored task, does immediate Tool availability sometimes produce a Tool choice that conflicts with the model's later considered conclusion, and does a no-Tool deliberation turn before Tool exposure change the observed result?

H0 is deliberately research-only. The Tool records a candidate string, reveals no evaluator score and performs no external effect.

## Neutral task

A candidate is feasible only when:

```text
memory <= 16
dependencies <= 2
```

For feasible candidates:

```text
score = throughput - 3*latency - 2*retries
```

Fixed candidates:

| Candidate | Throughput | Latency | Retries | Memory | Dependencies | Feasible | Score |
|---|---:|---:|---:|---:|---:|---|---:|
| atlas | 98 | 4 | 3 | 24 | 1 | no | 80 if ignored |
| birch | 76 | 5 | 2 | 12 | 3 | no | 57 if ignored |
| cobalt | 68 | 2 | 2 | 14 | 2 | yes | **58** |
| delta | 74 | 5 | 1 | 15 | 2 | yes | 57 |

The unique evaluator oracle is therefore:

```text
cobalt
```

Task digest:

```text
sha256:b402b3066ebd0fa64c4e464fd4f1640a3cd1cc08b0164426f2a39805f56e223f
```

## Predeclared comparison

Before the physical run, H0 fixes exactly two replicates per treatment. Samples are not increased after seeing results.

### Immediate-Tool baseline

```text
same task facts
+ submit_choice Tool immediately visible
→ Tool choice
→ conclusion
```

### Deliberation-first treatment

```text
same task facts
+ tools=()
→ non-authoritative self-deliberation record
→ same task facts + exact prior cognition record
+ same submit_choice Tool
→ Tool choice
→ conclusion
```

The deliberation record is model cognition evidence only. It is not evaluator truth, not choice authority, and not an external effect.

The outcome classifier is intentionally not success-biased:

```text
baseline 2/2 correct + treatment 2/2 correct
→ ordering-pressure-not-reproduced

baseline has error + treatment 2/2 correct
→ ordering-pressure-reproduced-in-sample

treatment has error
→ deliberation-first-not-sufficient-in-sample
```

## Apparatus

Initial apparatus commit:

```text
bcf8bd24e6845f1b46b1eb7253d252fdaa147c9f
```

An initial physical batch stopped with `provider_state_unknown` before a complete predeclared comparison and wrote no structured partial receipt. That batch is equipment-only and excluded from behavior claims.

This exposed an apparatus evidence defect, so only failure retention changed: completed replicates and failed stage are now retained if a later Provider/protocol interruption occurs. The neutral task, prompts, Tool semantics, oracle and `2 + 2` sample plan did not change.

Accepted apparatus revision:

```text
95760397caea9785b5374cd7f0a134e618c2cad5
```

Full local validation at this revision:

```text
301 tests passed
3 skipped
compileall passed
```

## Physical evidence

Raw receipt is retained byte-for-byte at:

```text
evidence/harness-h0-deliberation-authority-9576039.json
```

Physical identity:

```text
bytes  = 46669
sha256 = sha256:2398be1ddba7b9433557fed8bb30ce7920fcacb24fd48e269dec7f5511ee0425
```

Runtime binding:

```text
jobId                 = job-019fe67f-e914-7311-91ac-1b405e27f3f5
executionPlanDigest   = sha256:675da8122d3c4f621a31cd30226cded5652a4020383ef6c45f723f2485507865
workspaceSourceDigest = sha256:096495fc845b28218dbd9862e167e8fa64121cd6b1a1f0b91cb2f86787d820f6
executionProfile      = trusted_local
```

All completed samples use:

```text
requested model  = deepseek-v4-flash
credential scope = credential-scope:deepseek:flash:0
provider mode    = non-thinking
```

All mechanical experiment gates pass.

## Baseline result

### Baseline replicate 1

```text
Tool choice = cobalt
later conclusion = cobalt
correct = true
```

Trace digest:

```text
sha256:5a57cbdeaab82dd7d38c973ae1778805695ebb6d1202a56486f32efa1c812ef4
```

### Baseline replicate 2 — independent reproduction

The first model call emits:

```text
submit_choice({"choice":"atlas"})
```

The Tool records `atlas` as the final candidate choice.

The next model call then produces a correct conclusion:

```text
atlas memory = 24 > 16 → infeasible
birch dependencies = 3 > 2 → infeasible
cobalt = 68 - 3*2 - 2*2 = 58
delta  = 74 - 3*5 - 2*1 = 57
cobalt is the unique feasible maximum
```

Thus the same bounded run contains:

```text
Tool choice = atlas
considered conclusion = cobalt
```

Trace order:

```text
model call 1
→ submit_choice(atlas)

model call 2
→ candidate_completed with correct cobalt reasoning
```

Trace digest:

```text
sha256:f99001d2491bfc90f3551dccc009e91cb90792300405864877aabb9a25e14503
```

This reproduces the Security-observed ordering pressure without Security semantics and without a real external consequence.

## Deliberation-first result

Both predeclared treatment replicates first complete a no-domain-Tool deliberation over the same task. Both independently calculate:

```text
atlas infeasible
birch infeasible
cobalt = 58
delta = 57
candidate = cobalt
```

Then, after Tool exposure:

```text
replicate 1 → submit_choice(cobalt) → correct
replicate 2 → submit_choice(cobalt) → correct
```

Authority trace digests:

```text
r1 = sha256:ed7b0135336add0d9ca419e0fb215a62e2e065c5dafe7e775dd59985ee1157b9
r2 = sha256:931ce3ae5f64143ad1fcc8ebb70d53252832b6bde3a0b9820181b9a1aeae491c
```

Deliberation identities:

```text
r1 request = sha256:d418d51d3a19f639884eb92de06c72527d487a93ddc62da9a15032a50dbb07cc
r1 result  = sha256:f4a8c7a23cf6bf8f5ba344830893f4f649acc832bd464f2b6322914a77b83ccc
r1 summary = sha256:44f23e8e67d7bb63e91f4b9171466e137a220fd02dd914e7a2887d3c5a6ba3d7

r2 request = sha256:745f444588353a746ea4a6a508beb33ce77b3c992d6ecd005b50e1a7afed1cd2
r2 result  = sha256:74a3748bce95f88cbaf841cdaac3717bf98818ac42717c952c7d62ce5e0a9134
r2 summary = sha256:495a708124081def31336b54583cc9804c48af720b5b6e01fca78f19cf3a4f29
```

The retained research classification is:

```text
ordering-pressure-reproduced-in-sample
```

## What H0 establishes

H0 gives an independent Harness-native consumer for the candidate discovered in Security:

```text
immediate Tool availability
can precede the model's substantive considered reasoning
```

and, in this small predeclared sample:

```text
no-domain-Tool deliberation first
→ 2/2 correct later Tool choices
```

This is enough to justify a **Harness research requirement** around cognition/Tool-exposure sequencing. It is not enough to make a mandatory hidden planning pass a universal product default.

The important ownership boundary is:

```text
Harness may own when a Tool surface becomes model-visible
Harness must not own which domain choice is correct
```

The evaluator exists only in H0 research. A future product mechanism must not calculate or veto `cobalt`, `atlas`, or any domain strategy.

## Why existing `projected_no_tool` is not the answer

`WorkingViewNoToolTurnRunner` already proves a no-Tool Provider turn, but its own contract is intentionally narrower. Its source explicitly excludes:

- Context discovery;
- Tool use;
- multi-turn reasoning;
- retries;
- terminal Run recording;
- domain admission.

Its P-C1.1 purpose is WorkingSet/WorkingView versus durable History separation. H0 should not silently repurpose that historical proof runner into a new orchestration layer.

The lower-level building blocks already exist (`AgentTurnRequest(tools=())`, Provider adapter, DomainToolLoop), but there is no current general composition that says:

```text
non-authoritative deliberation
→ preserve exact cognition record
→ later expose domain Tools
```

without domain-specific glue.

## Limitations

H0 does not establish:

- population-level causal effect;
- deterministic DeepSeek unreliability;
- that every task benefits from a separate deliberation turn;
- that all Tool calls are premature;
- that deliberation output is world truth or action authority;
- that a generic sequencing mode must be enabled by default;
- that other providers/models have the same behavior.

There are only two predeclared replicates per treatment. The result is strong as an independent structural falsifier, not as a statistical estimate.

## Next pressure

H1 should test the smallest **optional Harness-owned composition primitive** for deliberation before Tool exposure.

It should mechanically own only:

```text
phase ordering
exact cognition-record identity
same-context binding
model/scope/equipment provenance
Tool-surface transition
```

It must not own:

```text
domain scoring
strategy choice
semantic correctness
external admission
physical effect execution
```

If H1 can reproduce H0 using the generic composition with less domain glue, the primitive is justified. If not, retain H0 as research evidence and leave sequencing to applications.
