# 124 — FOR DIRECT DESTRUCTIVE DOGFOOD v1
# Experiment Contract — Two-Subject Federation

**Control task:** `task:harness-for-direct-federation-dogfood-v1-20260819`  
**Research role:** empirical falsification/evidence acquisition for Campaign-6 FOR.  
**Theory status:** Campaign 6 remains closed unless a direct falsifier is observed.  
**Production change rule:** forbidden during this experiment.

## 1. Purpose

Obtain the first direct engineering evidence containing at least two independently bounded Harness operational subjects and at least one inter-subject information/evidence relation.

The experiment is not a production multi-agent framework and does not attempt full federation completeness.

## 2. Subject construction

A subject is operationally instantiated by:

- separate durable state root where a Run is used;
- distinct `harness_run_id` / local Run contract;
- shared experimental objective reference where relevant;
- local Provider/adapter/Context state;
- no hidden shared Harness Run state.

Experimental coordinator objects may relate subjects but are explicitly fixture-owned unless they call an existing Harness public surface.

## 3. Evidence labels

Each case is classified separately:

- `DIRECT_SUPPORT` — two actual local subjects/operations plus a FOR-relevant relation are exercised through current Harness behavior;
- `DIRECT_FALSIFIER` — current Harness behavior directly contradicts a FOR law/criterion in bounded scope;
- `ENGINEERING_GAP` — FOR relation is conceptually defined but no current production surface can represent/test it without adding semantics;
- `FIXTURE_ONLY_PRESSURE` — only experimental scaffolding demonstrates the scenario; not counted as direct Harness evidence.

Branch-level outcomes remain:

- `FOR_DIRECT_SUPPORT_IN_SCOPE`;
- `FOR_DIRECT_FALSIFIER_FOUND`;
- `FOR_ENGINEERING_GAP_FOUND`;
- `MIXED_DIRECT_EVIDENCE`.

## 4. E1 — Shared work, distinct local Runs

### Setup

Instantiate Subject A and Subject B as two actual `HarnessAgentRun` instances:

- separate state roots;
- distinct run IDs / caller-run refs;
- same exact objective reference/digest;
- no shared run store.

### Prebound observation

Record:

- A run ID;
- B run ID;
- objective ref equality;
- independent local terminal/paused state.

### FOR pressure

Supports `Shared Work != Shared Run` if the same objective relation coexists with distinct durable Runs.

### Falsifier

If current Harness requires a shared Run identity/state in order for the two subjects to share an objective reference, record `DIRECT_FALSIFIER`.

## 5. E2 — Local completion scope

### Setup

A uses a scripted completion turn. B uses a scripted `needs_input` turn under the same objective reference.

### Prebound observation

After both execute:

- A must be `candidate_completed`;
- B must remain `needs_input` / paused;
- A completion must not mutate B's run state.

No fixture-level aggregate completion rule is created.

### FOR pressure

Supports `Local Completion != Federated/Peer Completion`.

### Limit

This does not directly test Host Task completion because no Host Task completion operation occurs inside the local fixture.

## 6. E3 — Cross-subject evidence visibility without adoption

### Setup

1. Subject A produces a bounded result/evidence payload.
2. Fixture materializes an exact immutable `HarnessStrategyEvidence` object whose content records A's source run ID/result digest. The wrapping step is fixture-owned; digest/binding validation is Harness-owned.
3. Subject B receives a `HarnessStrategySelectionContext` in which that strategy evidence is visible.
4. B selects an attempt **without** including the evidence reference in `adopted_context_refs`.
5. Compile B's attempt through current Harness public selection/compile APIs.

### Prebound observation

The peer evidence may be present in B's selection Context but its reference must not appear as an adopted Context reference in the compiled B contract/manifest.

### FOR pressure

Directly pressures `Visibility/Delivery != Adoption` using two subject-origin identities and Harness evidence-admission machinery.

### Falsifier

If visibility alone causes automatic adoption into B's compiled contract, record `DIRECT_FALSIFIER`.

## 7. E4 — Explicit cross-subject evidence adoption

### Setup

Reuse the exact B selection Context and exact A-derived evidence from E3, but B's selected strategy explicitly includes the evidence reference in `adopted_context_refs`.

### Prebound observation

Compiled B attempt must bind the exact A-derived evidence reference/digest in:

- contract Context refs;
- adopted Context digest projection/manifest where exposed.

A's source identity/digest must remain encoded in the immutable evidence content; B adoption must not rewrite provenance.

### FOR pressure

Directly supports `Cross-Subject Accountability/Context Use Requires Explicit Evidence Adoption/Binding` in the bounded strategy-evidence surface.

### Falsifier

If explicit adoption cannot distinguish from mere visibility, or provenance is rewritten as B-origin, record `DIRECT_FALSIFIER`.

## 8. E5 — Shared Realization Claim with asymmetric evidence standing

### Pre-analysis implementation fact

Repository scan found no first-class production `RealizationClaim` / per-subject claim-standing object. Campaign-3 realization semantics are currently represented through Run/tool/runtime evidence and derived research laws rather than one public generic claim API.

### Prebound classification rule

Do **not** create a fake generic `RealizationClaim` class in the experimental fixture and call it direct Harness evidence.

The fixture may use a common experimental `claim_ref` in evidence metadata to illustrate the scenario, but:

- if no current Harness surface can represent two subject-local standings for one Q, classify E5 as `ENGINEERING_GAP_SHARED_REALIZATION_CLAIM_SURFACE`;
- any metadata-only asymmetry is `FIXTURE_ONLY_PRESSURE`, not direct proof.

This gap does not by itself falsify FOR; it indicates missing generic materialization/engineering consumption.

## 9. E6 — Distinct Invocations / duplicate-effect pressure

### Setup

Instantiate two actual Tool-bearing `HarnessAgentRun` subjects:

- separate state roots and run IDs;
- same exact objective reference;
- same fake external capability/query;
- distinct logical Tool Call / Invocation IDs;
- one shared fixture-owned `CountingRuntime` implementing the existing Runtime client surface;
- no real external side effect.

Each subject performs one Tool call and then locally completes.

### Prebound observation

Record:

- A toolCalls count;
- B toolCalls count;
- shared fake Runtime physical-call count;
- invocation/request identities where exposed.

### FOR pressure

If two distinct subject-local Invocations produce two Runtime client calls, this directly supports `Federation Does Not Deduplicate Invocation or Effect Risk`.

### Falsifier

If Harness automatically collapses two distinct subject-local Invocations solely because they share objective/capability/query, record `DIRECT_FALSIFIER`.

### Gap rule

If the current public Tool-bearing Run surfaces cannot compose this case without production changes, record `ENGINEERING_GAP`; do not add production federation/dedup APIs.

## 10. Assertions forbidden in the fixture

The experimental fixture must not assert:

- global federation correctness;
- global Agent identity;
- Host completion;
- normative legitimacy of delegation;
- Network delivery/adoption truth;
- domain truth of the experimental claim;
- universal cross-implementation validity.

## 11. Mechanical implementation rules

- New code lives only under `research/experiments/`.
- Production package files and existing tests are not modified.
- Use only public Harness APIs plus explicitly fixture-owned wrappers/counters.
- The fixture emits a machine-readable JSON result per E1–E6 and exits nonzero only for unexpected mechanical failures/direct falsifiers in executable cases.
- Prebound `ENGINEERING_GAP` cases may exit successfully while reporting the gap.

## 12. Stop rule

Run the experiment once after fixture validation. Do not modify production code or change expected semantics after observing the outcome.

If fixture code itself has a mechanical bug unrelated to the hypothesis, repair only the fixture and preserve the failed attempt in the research result/provenance.

## 13. Expected evidence standing before execution

- E1: expected executable direct support opportunity.
- E2: expected executable direct support opportunity.
- E3: expected executable direct support/falsifier opportunity.
- E4: expected executable direct support/falsifier opportunity.
- E5: expected engineering-gap discovery unless a public claim-standing surface is found before fixture freeze.
- E6: expected executable direct support/falsifier opportunity using safe fake Runtime.

No final outcome is admitted until execution.
