# 153 — Fresh-Agent Capability / Currentness Ablation V1–V2 — Result and Closeout

Date: 2026-08-28

## 1. Question

The capability-environment v1 implementation established a mechanical chain:

```text
published descriptor
  -> bounded candidate discovery
  -> exact inspection
  -> supplied standing
  + existing admission
  -> current affordance
  -> First Interface / Tool projection
```

It did **not** establish that this chain improves fresh-Agent behavior. The live programme therefore asked two separate questions rather than assuming that a smaller Tool/catalog representation is automatically a better Agent environment.

1. Does retrieval/current-affordance projection help merely because a Tool ecology is large?
2. Does current standing matter when static capability semantics cannot identify the currently usable carrier?

The experiments were preregistered before live Provider outcomes and used one-turn DeepSeek selection without executing the selected Tools.

---

## 2. V1 — large static Tool ecology

### 2.1 Design

- preregistration commit: `bd9e1adecc45a0e9e74a7ddd143c146612df7825`
- preregistration SHA-256: `0e234b264b0db57e42e38b87e051e4711e735336f9f8474e872fe27d0061740a`
- frozen corpus/runner commit: `4ef83268ca6507cbdc905833d782304e921036bb`
- corpus SHA-256: `e0f9399e1c5cd7b555c262e9b006d165992ade6473b0af97fcda03b39d5650b6`
- live Runtime Job: `job-01a04412-29fd-7392-9587-1b5efe114b48`
- terminal evidence: `sha256:e98f27702ad73d8a13b11d7db41f2490cea2eea4d614cee3f2346612ebe6cfdb`

Twelve cases each exposed 64 opaque-named Tools. Treatments were:

- A: full static Tool surface;
- B: full Tool surface + bounded candidate projection;
- C: candidate / exact-inspection / current-affordance projection + subtractive Tool surface.

### 2.2 Result

All 36 calls completed.

| Treatment | First-Tool accuracy |
| --- | ---: |
| A | 12/12 |
| B | 12/12 |
| C | 12/12 |

C–A = `0pp`, below the preregistered `+15pp` threshold.

**Disposition: negative / insufficient.**

A merely large 64-Tool static ecology did not pressure `deepseek-v4-flash` on these tasks. Opaque names were insufficient to make selection difficult because the target descriptions remained semantically distinctive.

### 2.3 Representation debt discovered by V1

The original C treatment repeated the same semantics across:

- Tool descriptions;
- candidate projection;
- exact inspection;
- current-affordance projection.

Consequently actual Provider context grew instead of shrinking:

| Treatment | Mean prompt tokens | Mean request bytes |
| --- | ---: | ---: |
| A | 3,791.5 | 16,764.5 |
| B | 5,524.4 | 23,187.9 |
| C | 6,366.9 | 23,542.3 |

Therefore:

```text
catalog compression != Provider-context compression
```

and:

```text
audit representation != default model representation
```

The V1 post-hoc audit also invalidated one absolute safety endpoint because a substring-based fixture classifier mislabeled prohibitive phrases such as `without redispatch` as mutation. Raw outcome bytes were retained and the primary negative classification did not depend on that endpoint.

---

## 3. V2 — currentness-dependent semantic twins

### 3.1 Why V2 was a different question, not a harder V1

V1 showed a ceiling. V2 therefore did not increase Tool count or rewrite V1 scoring. It isolated a distinct pressure:

> two capability carriers have byte-identical static Tool descriptions, but only one is currently AVAILABLE.

If static semantics are identical, retrieval relevance alone cannot establish which carrier is current.

### 3.2 Design

- V2 preregistration commit: `00587de943645ee9713d36e88755b258d3c33b1d`
- preregistration SHA-256: `c1affecfb637f017cf52de155b8a46166a3d969ffe1084242c1c1e56d94c9a93`
- frozen corpus/runner commit: `0ef8ea98fd0e5b9522409e5b95a9e1943a7ce93b`
- corpus SHA-256: `6c0d95872fe57dff5334fe04ec570ea71a0f18c1d998553d24240b485d26378d`
- live Runtime Job: `job-01a0441b-bf88-7ad1-841c-a109a0ab218d`
- terminal evidence: `sha256:b41a703770dc3a90fa2cd4e90d08a474942835c9d73a11cc10f2b94995b01457`
- raw result SHA-256: `eeadbc748c4d7ddf57f0d5a700e35d23a7973b2682b82dd7d8160548ea6b2873`

Each of 12 cases contained:

- one AVAILABLE target carrier;
- one BLOCKED/UNKNOWN semantic twin with the **same Tool description bytes**;
- six hard semantic distractors;
- 56 neutral distractors.

Target-vs-twin opaque-ID ordering was balanced 6/6.

Treatments:

- A — all 64 Tools, no current standing;
- B — all 64 Tools + compact Top-8 candidate IDs, still no current standing;
- C — Top-8 + compact current standing compiled through existing admission; only current-invokable candidates remained Provider-callable.

C exposed three AVAILABLE Tools per case, so it was not a one-Tool answer leak.

### 3.3 Result

35/36 calls completed. One A-arm request ended with a remote connection closure and was not retried.

| Treatment | Current target | Stale twin | Other wrong | Mean prompt tokens | Mean request bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| A | 5/11 = 45.5% | 5/11 = 45.5% | 1/11 | 3,677.0 | 15,941.0 |
| B | 3/12 = 25.0% | 8/12 = 66.7% | 1/12 | 3,781.4 | 16,428.3 |
| C | 11/12 = 91.7% | 0/12 = 0% | 1/12 | 1,115.5 | 4,235.7 |

C–A = `+46.2pp`, exceeding the preregistered `+25pp` threshold. C also exceeded the preregistered 10/12 accuracy floor and eliminated stale-twin selection.

**Disposition: `positive_currentness_dependent_gain`.**

### 3.4 Opaque-order destructive control

The static A/B arms exposed a strong arbitrary tie-break when currentness was absent:

- A, target opaque ID lower: target 5/6;
- A, target opaque ID higher: target 0/5, stale twin 5/5;
- B, target lower: target 3/6;
- B, target higher: target 0/6, stale twin 6/6.

C:

- target lower: target 5/6;
- target higher: target 6/6;
- stale twin: 0/12.

Thus current standing did not merely add another semantic hint. It removed dependence on an arbitrary carrier-order tie-break in a problem where static semantics were intentionally non-discriminating.

C's sole error chose another AVAILABLE hard candidate, not the stale twin. The positive result therefore does not depend on reducing the Tool surface to one obvious answer.

A post-hoc paired exact check over 11 A/C-complete case pairs produced 6 C-only wins, 1 A-only win and 4 both-correct (`p=0.125`, two-sided). This small-sample statistic is descriptive only; the admitted disposition uses the preregistered effect-size threshold, not a post-hoc significance threshold.

---

## 4. What the experiments change

### 4.1 Retrieval is not the behaviorally load-bearing result

V1 did not show a retrieval benefit. V2 B did not resolve current-carrier ambiguity and selected the stale twin more often than A.

Therefore the supported architecture is not:

```text
large Tool list -> semantic retrieval -> better Agent
```

The stronger supported chain is:

```text
Large Capability Space
  -> bounded retrieval / progressive disclosure
  -> exact candidate identity
  -> owner-current standing
  -> existing authority + admission
  -> compact Current Affordance
  -> Agent choice
  -> existing Harness effect/recovery plane
```

Retrieval remains useful as information-economy/navigation. It is not currentness and it is not authority.

### 4.2 `Capability != Current Affordance` now has behavioral evidence

Before V2 this distinction was structurally justified and mechanically enforced. V2 provides a bounded live behavioral consequence:

> when static capability semantics underdetermine which carrier is usable, a fresh Agent can fall back to arbitrary identity/order; explicit current standing plus existing admission removes that failure mode in this controlled ecology.

This does not establish universality, but it is sufficient pressure to preserve and naturally consume the distinction.

### 4.3 Compact representation is earned

V2's compact C representation simultaneously improved current-target selection and reduced actual Provider context:

- prompt tokens: `1115.5 / 3677.0 ~= 30.3%` of A;
- request bytes: `4235.7 / 15941.0 ~= 26.6%` of A.

This reverses V1's duplication failure and earns a model-facing representation split:

```text
Exact / audit carrier
  summary + source/evidence + reasons + descriptor digest

Default model carrier
  capability identity + owner + action
  + standing + admitted + canInvokeNow
```

Full exact inspection stays available on demand. It is no longer justified as default repeated Provider context.

---

## 5. Engineering consumption

The implementation following V2 is deliberately small:

1. `CapabilityAffordanceSet.to_dict()` remains the full exact audit/debug projection.
2. `CapabilityAffordanceSet.to_model_dict()` emits only load-bearing actionability facts and explicitly states that exact evidence is elided.
3. capability-aware First Interface uses the compact model projection by default.
4. capability-aware First Interface no longer duplicates a second legacy affordance list.
5. Tool selection is driven by `CapabilityAffordanceSet.selected_action_names` and is accepted only if the affordance set's admitted-action tuple exactly equals the current admitted Tool tuple.
6. admission drift after affordance compilation therefore fails closed.
7. standing reasons/evidence remain available through exact inspection or caller-authored blockers/unknowns rather than entering every model turn automatically.

This changes representation, not truth ownership or the execution plane.

---

## 6. Bounded findings

The programme supports these bounded statements:

- Tool-space size alone is not sufficient evidence of selection pressure.
- retrieval relevance does not establish currentness.
- static capability semantics can be insufficient to identify the current usable carrier.
- current standing plus existing admission can have a material fresh-Agent selection consequence under that pressure.
- arbitrary identity/order can become an accidental policy when currentness is absent.
- Provider-context measurement must occur after all projections are composed.
- exact audit representation should not automatically be the default model representation.

It does **not** establish:

- cross-model generalization;
- multi-turn or end-to-end task-success improvement;
- semantic/vector/LLM retrieval superiority;
- universal owner publication topology;
- universal current-affordance schema;
- latency superiority.

---

## 7. Closeout / reopen rule

Do not launch a V3 to seek stronger statistics and do not start a semantic-retrieval tournament from this line.

Reopen behavioral work only under new natural pressure, for example:

- compact current-affordance projection fails on a real multi-owner task;
- a large live capability ecology produces a retrieval miss that current deterministic retrieval cannot resolve;
- another model or multi-turn successor behavior materially conflicts with V2;
- currentness changes during a Run expose a recompile/re-entry failure.

Until then, the earned work is **engineering consumption of compact current affordance**, not further benchmark escalation.
