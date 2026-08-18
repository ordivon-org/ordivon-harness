# 141 — CAMPAIGN-5 PROVIDER-ROUTE PRESERVATION DIRECT DOGFOOD v1

**Branch role:** post-closeout bounded direct empirical evidence for Campaign 5 / OPUR.  
**Starting authority:** Post-Rich-Effect Typed Frontier Tournament v1 at `207ff45f1ac7ce938ec9acef1a7256c68097c541`.  
**Historical Campaign-5 authority:** closeout 116 remains closed and is not rewritten.  
**Control task:** `task:harness-campaign5-provider-route-preservation-direct-dogfood-v1-20260819`.  
**Foundation effect:** none. HaF0–HaF61 remain frozen; HaF62 remains UNKNOWN / NOT SELECTED / NOT ADMITTED.

## 1. Question

Can current public Harness provider-use admission preserve one exact bounded use contract across a real provider-route change, while failing closed on route/input/policy drift, **without** adding generic `Preserves_U`, a reconfiguration engine, provider taxonomy, locus semantics or mutable policy state?

The concrete use contract is already product-authored:

`U_provider = exact restricted HarnessBoundReference values + exact allowed HarnessProviderRoute set`.

This branch tests preservation of those exact obligations only.

## 2. Scope boundary

Harness owns the product facts exercised here:

- immutable `HarnessProviderUsePolicy`;
- exact restricted-input binding;
- exact `(providerId, adapterId, requestedModelId)` route membership;
- exact policy digest binding in `HarnessRunContract`;
- pre-adapter/pre-state composition rejection;
- normal adapter identity validation after policy admission.

This branch does **not** ask Harness to own or infer:

- Provider semantic quality/correctness;
- privacy-law or competition-rule truth;
- model-output equivalence;
- Provider availability;
- Network/locus reachability;
- implementation interchangeability in general;
- universal or bidirectional OPUR equivalence.

## 3. Existing implementation ordering under test

Current `HarnessAgentRun.create` performs:

1. `_validate_structure(...)`;
2. `validate_provider_use_policy(...)` inside that structural validation;
3. `_resolve_adapter(...)` / adapter factory;
4. SQLite state-root initialization and durable Run creation.

Therefore an invalid provider-use composition promises fail-closed behavior before adapter construction and before durable Run state creation.

The dogfood must verify this promise rather than merely call `validate_provider_use_policy` directly.

## 4. One exact U and two genuinely distinct allowed routes

Construct one exact immutable policy `U` over one exact restricted input `D` and two allowed routes:

### R0 — scripted route

- `providerId = provider:scripted-local`;
- `adapterId = ScriptedTurnAdapter.adapter_id`;
- `requestedModelId = ScriptedTurnAdapter.model_id`.

### R1 — DeepSeek adapter route

- `providerId = provider:deepseek-controlled`;
- `adapterId = DeepSeekTurnAdapter.adapter_id`;
- `requestedModelId = deepseek-v4-flash`.

R1 must instantiate the production `DeepSeekTurnAdapter` implementation with a deterministic in-process transport response. The controlled transport removes network availability/model stochasticity from the experiment but must not replace the adapter implementation being exercised.

This is stronger than changing provider identity strings under one adapter. It still does **not** constitute live-provider semantic evidence or independently designed Harness implementation evidence.

## 5. PR1 — exact U + allowed R0

### Construction

Create one no-Tool `HarnessRunContract` that binds:

- exact restricted input D;
- exact `U.bound_reference`;
- exact R0 provider/adapter/model identities.

Supply the exact U to `HarnessAgentRun.create` and a real `ScriptedTurnAdapter` factory.

### Required observations

- adapter factory called exactly once;
- durable state root created only after admission;
- Run reaches `candidate_completed`;
- contract binds the same exact U digest used by PR2.

### Expected standing

`R0_ADMITTED_UNDER_U`.

## 6. PR2 — same exact U + genuinely distinct allowed R1

### Construction

Create a distinct no-Tool `HarnessRunContract` with the **same exact restricted input D and same exact U reference**, but route R1.

Adapter factory constructs production `DeepSeekTurnAdapter` with deterministic controlled transport returning one valid conclusion Tool response.

### Required observations

- exact policy object/digest equals PR1 U;
- R1 is a distinct route in provider, adapter and model identity from R0 where the concrete implementations define them;
- adapter implementation is actually `DeepSeekTurnAdapter`, not a renamed scripted fixture;
- adapter factory called exactly once;
- controlled transport receives one Provider request;
- durable state root is created only after policy admission;
- Run reaches `candidate_completed`.

### Expected standing

`R1_ADMITTED_UNDER_SAME_U`.

### Destructive point

A provider-route change does not fail merely because route identity changed when the exact product-authored U explicitly admits both endpoints.

The result is **provider-route policy preservation**, not provider semantic equivalence.

## 7. PR3 — unlisted route must fail before adapter/state

Construct R2 using the exact D and exact U binding but a route not listed in U.

Required:

- `HarnessAgentRun.create` rejects with provider-route admission error;
- adapter factory invocation count remains zero;
- state root does not exist after rejection.

Any adapter construction or durable state creation before rejection is a direct falsifier of the bounded product claim.

## 8. PR4 — restricted-input digest substitution must fail before adapter/state

Construct a policy whose restricted input uses the same logical ref/kind as D but a different digest, and bind that policy exactly in the Run Contract while the Contract still binds original D bytes.

Required:

- rejection identifies unbound/mismatched restricted input;
- adapter factory invocation count remains zero;
- state root remains absent.

A route alone is insufficient: preservation is over exact U obligations including the restricted bytes.

## 9. PR5 — missing / unbound policy must fail before adapter/state

Two subcases:

### PR5-A — Contract binds U; caller omits U object

Must reject before adapter/state.

### PR5-B — caller supplies U; Contract does not bind U

Must reject before adapter/state.

These prevent a mutable out-of-band policy overlay from becoming authority.

## 10. PR6 — use-relative non-global-equivalence guard

Construct a second exact policy `U_scripted_only` over the same D but allowing only R0.

R1 was admitted under U in PR2. Under `U_scripted_only`, the exact same R1 route must now be rejected before adapter/state.

This proves only:

`Route admission is use-contract-relative; admitted under U != globally equivalent/admitted under every U'`.

The current product does not materialize a first-class directional reconfiguration transition object. Therefore this branch explicitly **does not claim** to have directly proved full directional `Preserves_U(B0 -> B1)` semantics. It proves endpoint obligation preservation under one exact U plus non-global use relativity.

## 11. Cross-case acceptance gates

Classify `CAMPAIGN5_PROVIDER_ROUTE_PRESERVATION_DIRECT_SUPPORT_IN_SCOPE` only if all hold:

1. PR1 R0 is admitted and completes under exact U;
2. PR2 genuinely exercises production `DeepSeekTurnAdapter` under the same exact U and completes using controlled transport;
3. R0/R1 policy reference/digest is exactly identical;
4. PR3 unlisted route fails before adapter factory and state creation;
5. PR4 restricted-input digest substitution fails before adapter factory and state creation;
6. PR5-A and PR5-B fail before adapter factory and state creation;
7. PR6 proves R1 admission is U-relative rather than a global Provider property;
8. no generic `Preserves_U`/reconfiguration product type is added;
9. no provider semantic quality, live-provider equivalence, locus preservation or cross-implementation invariance is claimed;
10. no production `src/` modification is required;
11. current Harness baseline remains healthy after research-only materialization.

## 12. Direct falsifiers

Classify `CAMPAIGN5_PROVIDER_ROUTE_PRESERVATION_DIRECT_FALSIFIER_FOUND` if any prebound case shows:

- an exact allowed R0 or R1 is rejected solely because route identity changed despite same exact U;
- an unlisted route reaches adapter construction or durable Run state;
- restricted input bytes can drift while U is still treated as satisfied;
- a bound policy can be omitted silently;
- an unbound policy can be injected as effective authority;
- policy admission silently widens from one U to another;
- successful route admission requires a generic reconfiguration engine or mutable Provider-equivalence state.

## 13. Materialization-gap stop rule

Classify `CAMPAIGN5_PROVIDER_ROUTE_MATERIALIZATION_GAP` and STOP before production modification if current public surfaces cannot express PR1–PR6 without adding:

- generic `Preserves_U`;
- reconfiguration graph/registry;
- mutable provider-equivalence status;
- provider taxonomy/safety classifier;
- locus/Network migration semantics.

A gap does not authorize implementation in this branch.

## 14. Evidence-limit classifications

Use narrower classifications if needed:

- `PROVIDER_ROUTE_POLICY_PRESERVATION_ONLY`;
- `DISTINCT_ADAPTER_ROUTE_NOT_ESTABLISHED`;
- `PRE_PROVIDER_FAIL_CLOSED_NOT_ESTABLISHED`;
- `USE_RELATIVITY_NOT_ESTABLISHED`;
- `PROVIDER_ROUTE_MATERIALIZATION_GAP`.

Even full acceptance remains bounded provider-route policy evidence, not general OPUR closure.

## 15. Explicit non-claims

This branch does not establish:

- provider/model semantic equivalence;
- equal answers/performance/cost/privacy behavior across providers;
- live DeepSeek availability or correctness;
- general provider implementation replacement safety;
- locus migration preservation;
- internalization/externalization preservation;
- bidirectional/global operational equivalence;
- cross-implementation Harness invariance;
- Campaign 7;
- HaF62.

## 16. Execution order

1. Commit this contract and `research/experiments/campaign5_provider_route_preservation_v1.py` before executing it.
2. Run the frozen experiment from that exact prebound commit.
3. If direct cases pass, run focused provider-use-policy tests and full Harness baseline.
4. Write result/closeout without rewriting Campaign-5 historical closeout.
5. Update dedicated Host continuity and canonical main.
6. Run a fresh typed frontier tournament before selecting any subsequent work.
