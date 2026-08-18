# 50 — ENGINEERING CONSUMPTION MAP

Current repository engineering contracts are downstream consumers of the research core. They are **not** HaF ontology and must not be used to retroactively redefine Foundation identity.

## Current product surfaces

Current public/product surfaces include:

- `HarnessExecutionMandate`
- immutable `HarnessRunContract`
- Harness Journal / CAS
- Provider Call continuity
- Tool intent / dispatch fence / receipt / reconciliation boundaries
- Agent-owned `WorkingSet` / `WorkingView` selection over canonical history
- request-bound `AgentTurnRequest.tools` and Harness-native capabilities
- privacy/content authority and retention boundaries
- Runtime client/binding boundary
- Run Receipt / terminal evidence
- `CompletionProposal`
- `HarnessAgentRun` and associated caller-facing composition surfaces
- `OperationalClaimRef`
- `OperationalClaimEvidenceRole`
- `OperationalClaimStandingView`
- `project_operational_claim_standing_view(...)`

## Research-to-engineering mapping

| Engineering surface | Research consumption |
|---|---|
| HarnessRunContract / Mandate | A boundary/specification + C action/control + I Run identity |
| WorkingSet / WorkingView | B representation/retention + I Context |
| Provider/Tool effect fencing | C action/effect/time + I Invocation/Result |
| Journal/CAS | B history/persistence and provenance; never “memory ontology” by itself |
| Runtime client/binding | Runtime bridge + C/I execution mediation |
| privacy/content authority | H information boundary + E authority bridge |
| Run Receipt | D evidence + I Result attribution |
| CompletionProposal | I bounded Run conclusion proposal; explicitly not Host/caller/domain completion |
| AgentTurnRequest capability surface | A exposure + C selection/control + H protocol/security constraints |
| OperationalClaimRef | Campaign-3 bounded Q identity + owner/scope/currentness binding; no truth ownership |
| OperationalClaimStandingView | Campaign-3 evidence-relative standing + FOR subject/use-local standing |
| OperationalClaimEvidenceRole / projection | evidence-admission roles consumed without domain truth inference |

## Operational Claim Standing v1 — current product boundary

Minimal Materialization v1 implements only a value/projection layer:

- exact owner-grounded bounded claim identity/scope/currentness;
- subject/use/evidence-relative immutable StandingViews;
- typed admitted evidence roles `supporting`, `counterevidence`, `required_unknown`;
- evidence-relative standings `SUPPORTED`, `CONTRADICTED`, `CONFLICTED`, `UNDERDETERMINED`;
- pure projection and canonical round-trip/digest behavior.

The implementation explicitly preserves:

- claim meaning/truth ownership remains external;
- standing is not a mutable global property on Q;
- evidence visibility does not equal evidence admission;
- receipts/evidence refs remain inputs rather than global standing objects;
- later StandingView generations do not rewrite prior views;
- no semantic-authority global Harness Claim registry is required;
- no second evidence/history/authority plane is created.

E5-v2 direct dogfood has exercised one shared Q with A=`SUPPORTED`, B=`UNDERDETERMINED`, visibility-without-adoption, then explicit B admission producing a later `SUPPORTED` B view while Q/A/old-B remain unchanged.

## Research-approved boundary not yet implemented

`OperationalClaimUseDisposition` remains research-approved as an optional future use-relative settlement/continuation projection. It is not a current product surface because v1/E5-v2 did not require it.

No current admission exists for:

- claim registry/database;
- claim discovery/workflow service;
- automatic owner truth lookup/evaluation;
- universal claim taxonomy;
- global mutable claim status.

## Non-inference rule

The existence of a Python class, CLI flag, SQLite table, schema field, provider protocol, test fixture or current architecture paragraph proves current Engineering Consumption only. It does not create HaF62, alter HaF0–61, promote the Operational Spine into a higher tier, or transfer another owner's truth into Harness. Likewise, research-approved but unimplemented optional surfaces are not current product facts.
