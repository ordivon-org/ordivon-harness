# Harness Fresh-Agent A/B/C v2 — Currentness-Dependent Capability Selection

Date: 2026-08-28
Parent evidence: v1 negative/insufficient, frozen at `debe4edcc7a0f1ab3a47ea3dcf93da87a3deae75`.
Provider: configured `deepseek-v4-flash`, non-thinking.

## Why a new tranche is justified

V1 produced 12/12 first-Tool accuracy in A, B and C. Its 64-Tool size therefore did not create a behaviorally discriminating pressure: target descriptions were semantically distinctive enough that current standing was unnecessary. V2 does not rescore or rewrite v1. It asks a different question that is closer to the claimed Ordivon distinction `Capability != Current Affordance`.

## Question

When two capability carriers have intentionally indistinguishable static semantics, can explicit current standing plus admission compilation improve a fresh Agent's selection of the currently usable carrier?

## Frozen treatments

- **A — static-full**: all 64 opaque-named Tools visible; no retrieval or current-standing projection.
- **B — compact-retrieval**: all 64 Tools remain visible; a compact Top-8 candidate ID list is supplied. No currentness, availability or authority claim is supplied.
- **C — compact-current-affordance**: the same Top-8 candidates receive a compact `{tool, standing, canInvokeNow}` projection derived from the production standing/admission compiler; only currently invokable candidate Tools are Provider-visible. BLOCKED/UNKNOWN twins remain context-visible but not callable.

Unlike v1, C deliberately omits duplicated full candidate/inspection/affordance JSON. V2 therefore tests a compact Provider projection; this is an experimental representation, not a stable API commitment.

## Case structure

12 cases × 3 treatments = 36 independent one-turn Provider calls in a frozen randomized order.

Each case contains exactly 64 Tools:
- 1 AVAILABLE target carrier;
- 1 semantic twin with **exactly the same Tool description** but standing BLOCKED or UNKNOWN;
- 6 hard semantic distractors;
- 56 neutral distractors.

Tool identities are opaque (`cap_###`). Target-vs-twin ID/order advantage is balanced: target has the lexically lower opaque ID in exactly 6 cases and the higher ID in exactly 6 cases. The twin alternates BLOCKED/UNKNOWN across cases. Static descriptions, task text and Tool schemas do not reveal which twin is current.

C must expose at least two AVAILABLE Tools per case so it is not a one-Tool giveaway. The target must be one; at least one non-target AVAILABLE hard candidate must remain callable.

## Task families

The 12 cases reuse heterogeneous capability positions (research retrieval, network currentness, Security range, repository read, verification, exact candidate inspection, owner state, reconciliation, workspace search, software affordance, evidence currentness, source-fenced read), but the target/twin pair is static-semantics-equivalent in every case.

## Primary endpoints

1. **currentTargetAccuracy** — first selected Tool is the frozen AVAILABLE target carrier.
2. **staleTwinSelectionRate** — first selected Tool is the BLOCKED/UNKNOWN semantic twin.
3. **otherWrongSelectionRate** — first Tool is neither target nor twin.
4. **noToolOrConclusionRate** — no Runtime Tool selected when one is required.

No heuristic mutation-risk classifier is used in v2.

## Secondary endpoints

- Provider request bytes;
- prompt/completion/total tokens using the provider's actual snake_case usage fields;
- prompt-cache hit/miss tokens;
- latency;
- visible Tool count;
- Provider errors / malformed output;
- authority-subset invariant for C.

## Behavioral success criterion

V2 supports a **currentness-dependent selection gain** only if all are true:
- at least 30/36 calls complete;
- C completes at least 10/12;
- C currentTargetAccuracy >= 10/12;
- C currentTargetAccuracy exceeds A by at least 25 percentage points;
- C staleTwinSelectionRate <= A staleTwinSelectionRate;
- all mechanical authority/currentness invariants hold.

B is diagnostic: B > A means retrieval narrowing alone helps under semantic twins; C > B means current-standing/admission information adds behaviorally useful information.

## Representation efficiency

A behavioral positive claim does **not** require C to use fewer tokens than A. Representation efficiency is reported separately. A compact-C success is stronger if mean C prompt tokens <= mean A prompt tokens, but failure of this efficiency target does not rewrite the behavioral threshold.

## Stop rule

If v2 is again non-discriminating (for example A/B/C all near-perfect) or C fails the preregistered behavioral threshold, stop behavioral expansion in this line. Do not create a v3 merely to obtain significance. Retain capability discovery/current-affordance compilation as mechanically valid but behaviorally unproven beyond the pressure actually demonstrated.

## Explicit non-claims

- V2 does not show cross-model generality.
- One-turn carrier selection is not end-to-end task success.
- Synthetic semantic twins are a controlled currentness experiment, not proof of live owner publication quality.
- V2 does not test semantic/vector/LLM retrieval.
- No production effect or owner authority is exercised.
