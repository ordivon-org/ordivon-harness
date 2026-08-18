# 142 — CAMPAIGN-5 PROVIDER-ROUTE PRESERVATION DIRECT DOGFOOD v1
# Result and Closeout

**Task:** `task:harness-campaign5-provider-route-preservation-direct-dogfood-v1-20260819`  
**Prebound contract + experiment:** committed before execution at `a1a61430047dfa0c43fb2f32d1d2529d57c19018`.  
**Historical Campaign-5 closeout:** 116 remains authoritative for its original revision.  
**Production source modification:** none.

## 1. Classification

`CAMPAIGN5_PROVIDER_ROUTE_PRESERVATION_DIRECT_SUPPORT_IN_SCOPE`.

All prebound provider-route/use-policy cases passed using the existing public product surface. No generic `Preserves_U`, reconfiguration engine, mutable Provider-equivalence state, provider taxonomy, locus semantics or production `src/` change was required.

This branch upgrades one narrow Campaign-5 frontier from conceptual/adjacent engineering support to bounded direct product evidence: exact Provider/Adapter/Model route preservation under one explicit `HarnessProviderUsePolicy`.

It does not rewrite Campaign-5 closeout 116 and does not create Campaign 7 or HaF62.

## 2. Exact evidence

Result artifact:

- `evidence/harness-campaign5-provider-route-preservation-v1-result.json`;
- file digest: `sha256:0693df87e7541a5589ba865e17937b46e79fb2f25bb7175b3856cae682ff0aa1`;
- classification: `CAMPAIGN5_PROVIDER_ROUTE_PRESERVATION_DIRECT_SUPPORT_IN_SCOPE`;
- exact policy digest: `sha256:d0fc3378ac734e0d8fbf45ba27b16e7518b7bdebcda7e5e70e3478cd7023c000`;
- formal dogfood Runtime Job: `job-01a01664-dda4-7081-9fe8-8d58ab83ce14`.

Focused existing policy regression:

- Runtime Job `job-01a01665-1e2a-7cd0-8092-60ca458e8844`;
- `6` tests;
- `OK`.

Full current Harness baseline:

- Runtime Job `job-01a01665-37d2-73c2-9c8e-711ce3188d7d`;
- `437` tests;
- `OK`;
- `3` skipped.

## 3. Exact bounded use contract U

The same immutable `HarnessProviderUsePolicy` bound:

Restricted input:

- ref `dataset:c5-provider-route:restricted`;
- kind `restricted-dataset`;
- digest `sha256:4b49ace705d365f9e268ccc36f5d80ca9f0173458fd33954a7f2e14feda122f9`.

Allowed route R0:

- provider `provider:scripted-local`;
- adapter `ordivon.scripted-turn-adapter.v1`;
- model `ordivon.scripted-model.v1`.

Allowed route R1:

- provider `provider:deepseek-controlled`;
- adapter `deepseek.chat-completions.non-thinking.v1`;
- model `deepseek-v4-flash`.

Both Runs bound the exact same `U.bound_reference` and policy digest.

## 4. PR1 — allowed scripted route

R0 was admitted under U.

Observed:

- adapter factory calls = `1`;
- actual adapter class = `ScriptedTurnAdapter`;
- durable state root created after admission;
- Run stop code = `candidate_completed`.

Standing: `R0_ADMITTED_UNDER_U`.

## 5. PR2 — distinct allowed DeepSeek adapter route under the same U

R1 was admitted under the same exact U.

Observed:

- adapter factory calls = `1`;
- actual adapter class = production `DeepSeekTurnAdapter`;
- controlled DeepSeek transport requests = `1`;
- durable state root created after admission;
- Run stop code = `candidate_completed`.

The controlled transport removed external network/stochastic Provider behavior while retaining the actual production DeepSeek adapter request/response mechanics. R1 is therefore stronger than a renamed provider string over `ScriptedTurnAdapter`.

Standing: `R1_ADMITTED_UNDER_SAME_U`.

Evidence limit: this is not live DeepSeek semantic evidence and does not prove provider/model answer equivalence.

## 6. PR3 — unlisted route fails before adapter/state

An exact Contract bound the same restricted input and same U but selected an unlisted route.

Observed:

- rejection: `Harness Provider route is not admitted for the Contract's restricted inputs`;
- adapter factory calls = `0`;
- durable state root created = `false`.

This directly supports pre-adapter/pre-state fail-closed route admission.

## 7. PR4 — restricted-input digest substitution fails before adapter/state

The supplied policy named the same logical restricted input ref/kind but a different digest while the Contract still bound the original bytes.

Observed:

- rejection identified policy-restricted input not bound by the Contract;
- adapter factory calls = `0`;
- durable state root created = `false`.

Therefore route membership alone is insufficient: U preservation includes exact restricted bytes.

## 8. PR5 — policy authority cannot disappear or be injected out-of-band

### Contract binds U; policy object omitted

Observed:

- rejection: Contract requires its exact Provider Use Policy;
- adapter factory calls = `0`;
- state root = absent.

### Policy supplied; Contract does not bind U

Observed:

- rejection: Provider Use Policy supplied but not bound;
- adapter factory calls = `0`;
- state root = absent.

This directly supports exact Contract↔policy authority binding rather than mutable caller overlay semantics.

## 9. PR6 — admission is use-relative, not global provider equivalence

R1 was admitted under broad U containing R0 and R1.

A different exact `U_scripted_only`, with policy digest

`sha256:3cab19fff0780f194baf71c600706b65a16f0a29d2252a13ccd3279f0c9aa00e`,

allowed only R0. The exact R1 route was rejected under that policy before adapter/state creation.

Directly supported:

`admitted under U != globally admitted/equivalent under every U'`.

This is a concrete use-relative preservation fact.

## 10. What this says about Campaign-5 OPUR

The historical Campaign-5 primitive remains:

`Preserves_U(B0 --T--> B1)`.

This branch does **not** materialize or directly test a generic transition object T. Instead it proves a narrower concrete consumption result:

- one exact U already exists as a product object;
- two genuinely different provider/adapter/model endpoint configurations are both admitted under U;
- U-required input and route obligations remain exact across that endpoint change;
- drift in route, bytes or policy binding fails before execution composition proceeds.

This is bounded direct support for the Campaign-5 principle that endpoint implementation identity need not remain identical when the relevant use obligations remain satisfied.

However the current `HarnessProviderUsePolicy` is route-membership based. It does not itself encode transition lineage, directional migration semantics, adoption/revocation or general OPUR obligation families.

Therefore **full directional `Preserves_U(B0 -> B1)` proof remains open**.

## 11. Provider implementation evidence standing

The experiment exercised two genuinely distinct adapter implementations:

- deterministic `ScriptedTurnAdapter`;
- production `DeepSeekTurnAdapter` with controlled transport.

This directly refutes the weak interpretation that the branch changed only provider identity strings under one adapter implementation.

But it still does not establish live Provider replacement safety, equal model semantics/results, equal privacy properties beyond the explicitly bound route policy, cross-implementation Harness invariance, or arbitrary provider implementations.

Current classification therefore remains **provider-route policy preservation**, not general provider-implementation equivalence.

## 12. Acceptance gates

All prebound gates passed:

- same exact policy across R0/R1 = true;
- distinct adapter implementations exercised = true;
- scripted route admitted = true;
- DeepSeek adapter route admitted = true;
- controlled DeepSeek transport only = true;
- unlisted route rejected pre-adapter/pre-state = true;
- restricted digest substitution rejected pre-adapter/pre-state = true;
- missing bound policy rejected pre-adapter/pre-state = true;
- unbound policy injection rejected pre-adapter/pre-state = true;
- route admission use-relative/not-global = true;
- generic `Preserves_U` required = false;
- production source modification required = false;
- provider semantic equivalence claimed = false;
- locus preservation claimed = false;
- cross-implementation invariance claimed = false.

No direct falsifier fired. No `CAMPAIGN5_PROVIDER_ROUTE_MATERIALIZATION_GAP` was found.

## 13. Campaign-5 currentness update

Historical closeout 116 correctly stated that general provider/locus/internalization proof was not established at that revision.

Current standing is now split:

- exact ProviderUsePolicy route preservation under one bounded U: **BOUNDED DIRECT SUPPORT**;
- pre-provider fail-closed unlisted-route enforcement: **BOUNDED DIRECT SUPPORT**;
- exact restricted-byte preservation under U: **BOUNDED DIRECT SUPPORT**;
- exact Contract↔policy binding preservation: **BOUNDED DIRECT SUPPORT**;
- provider-route admission is use-relative/non-global: **BOUNDED DIRECT SUPPORT**;
- full directional `Preserves_U(B0 -> B1)` transition semantics: **OPEN**;
- live provider implementation replacement equivalence: **OPEN / narrower evidence only**;
- locus migration: **OPEN / no before→after pair**;
- internalization/externalization: **OPEN / relation-blocked**;
- cross-implementation invariance: **OPEN**.

## 14. Owner-boundary audit

**PASS.** Harness owns exact Run Contract/policy/route admission and adapter composition order. The branch made no claim about Provider semantic quality, external legal/privacy truth, Network reachability or locus health.

The controlled DeepSeek response is experiment control evidence only; it does not become a Provider-world truth claim.

## 15. Foundation / theory pressure

`NO_FOUNDATION_PRESSURE`.

No Campaign-5 law required revision. No generic reconfiguration engine was deletion-essential. No new owner-native Foundation responsibility appeared.

HaF0–HaF61 remain frozen. HaF62 remains UNKNOWN / NOT SELECTED / NOT ADMITTED. Campaign 7 remains unselected.

## 16. Closeout

**CAMPAIGN-5 PROVIDER-ROUTE PRESERVATION DIRECT DOGFOOD v1 COMPLETE.**

- historical Campaign-5 closeout: preserved;
- exact provider-route/use-policy preservation: bounded direct support;
- distinct production adapter route evidence: bounded and controlled;
- unlisted-route/input/policy drift: fails closed before adapter/state;
- generic `Preserves_U`: not implemented and not required;
- full directional transition proof: still open;
- locus/internalization: still open;
- production source change: none;
- new Foundation: none;
- next Harness frontier: intentionally UNKNOWN pending a fresh typed tournament.
