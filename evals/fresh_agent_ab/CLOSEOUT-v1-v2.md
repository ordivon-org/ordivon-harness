# Harness Fresh-Agent Capability Environment — V1/V2 Closeout

## Disposition

Two preregistered live DeepSeek tranches now separate **semantic capability selection** from **current-affordance selection**.

### V1 — large static Tool ecology

V1 used 64 opaque-named Tools per case but left target semantics distinctive. All 36 Provider calls completed; A/B/C each selected the frozen target 12/12. The preregistered `C-A >= 15pp` criterion failed at `0pp`.

This is a negative result for the claim that bounded retrieval/current-affordance projection automatically improves fresh-Agent selection in a merely large static Tool space. It also exposed a Provider representation debt: verbose candidate + full inspection + affordance JSON made B/C larger than A.

### V2 — static semantics intentionally underdetermine current carrier

V2 introduced an AVAILABLE target and a BLOCKED/UNKNOWN semantic twin with **byte-identical Tool descriptions**. Target-vs-twin opaque-ID ordering was balanced 6/6. A/B retained all 64 Tools; C consumed the same Top-8 candidates plus frozen current standing, then exposed only current-invokable candidates. C still exposed exactly three Tools per case, so it was not a one-Tool giveaway.

35/36 calls completed. The sole failure was an A-arm transport closure (`Remote end closed connection without response`) and was not retried.

| Treatment | Completed | Current target | Stale twin | Other wrong | Mean prompt tokens | Mean request bytes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A static-full | 11/12 | 5/11 = 45.5% | 5/11 = 45.5% | 1/11 | 3,677.0 | 15,941.0 |
| B compact retrieval | 12/12 | 3/12 = 25.0% | 8/12 = 66.7% | 1/12 | 3,781.4 | 16,428.3 |
| C compact current affordance | 12/12 | 11/12 = 91.7% | 0/12 = 0% | 1/12 | 1,115.5 | 4,235.7 |

C exceeds A by +46.2pp, clears the preregistered +25pp threshold, completes 12/12, exceeds 10/12 target accuracy, and eliminates stale-twin selection. The V2 preregistered classification is therefore `positive_currentness_dependent_gain`.

The opaque-ID split is especially diagnostic:

- A, target lower opaque ID: 5/6 target; target higher: 0/5 target, 5/5 stale twin.
- B, target lower: 3/6 target; target higher: 0/6 target, 6/6 stale twin.
- C, target lower: 5/6 target; target higher: 6/6 target; stale twin: 0/12.

When static semantics were deliberately insufficient, A/B fell back strongly toward arbitrary opaque ordering. Current standing + admission compilation removed that dependence. C's one error selected a different AVAILABLE hard candidate rather than the stale semantic twin, confirming that the treatment did not simply expose one answer.

A post-hoc paired exact McNemar/binomial check over the 11 cases with both A and C completed has 6 C-only wins, 1 A-only win, 4 both correct (`p=0.125`, two-sided). This small-sample statistic is descriptive only; the admitted result is based on the preregistered effect threshold, not a post-hoc significance threshold.

## Architecture consequence

The evidence does **not** support the simplistic architecture:

```text
large tool list -> better semantic retrieval -> better Agent
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

Retrieval is an information-economy/navigation mechanism. In V2, retrieval-only B did not improve behavior and actually selected the stale twin more often. The behaviorally load-bearing new information was **current standing compiled into current affordance**.

## Representation consequence

V1 showed that mechanically smaller discovery results can still produce a larger Provider request if the same semantics are repeated across candidate, inspection and affordance objects. V2's compact current-affordance representation removed that duplication:

- C mean prompt tokens were ~30.3% of A (`~69.7%` reduction).
- C mean request bytes were ~26.6% of A (`~73.4%` reduction).
- B remained slightly larger than A because candidate IDs were additive while all 64 Tool schemas remained visible.

This earns an engineering experiment for a **compact model-facing current-affordance projection**, while retaining exact/full inspection as an on-demand audit/recovery surface rather than replaying it into every Provider turn.

## What is now established

1. `Capability != Current Affordance` has a demonstrated fresh-Agent behavioral consequence under a controlled currentness-dependent pressure.
2. `Retrieval != Currentness`: retrieval-only did not resolve semantic-twin carrier ambiguity.
3. `Current standing + existing admission` can eliminate stale-carrier selection without granting new authority.
4. Progressive disclosure must be measured at the actual Provider request, not only at catalog API output.
5. Compact current-affordance projection can simultaneously improve selection and reduce Provider context in the V2 controlled ecology.

## What remains unproven

- cross-model generalization;
- multi-turn/end-to-end task success;
- live owner publication quality at hundreds/thousands of capabilities;
- semantic/vector/LLM retrieval advantage over deterministic retrieval;
- latency superiority;
- a universal current-affordance schema across all domains.

## Next engineering pressure

Do **not** launch V3 or a semantic retriever tournament from these results. V2's stop rule is satisfied with a discriminating positive result, and the next pressure is engineering consumption:

1. derive a compact Provider-facing projection from existing `CapabilityAffordanceSet`;
2. keep full descriptor/inspection/currentness evidence available through exact on-demand inspection;
3. prove compact projection is information-preserving for Agent actionability but does not become owner truth;
4. dogfood it through the existing First Interface/turn projection;
5. rerun focused V2-style deterministic and regression tests, not another significance-seeking live benchmark.
