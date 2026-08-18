# 50 — ENGINEERING CONSUMPTION MAP

Current repository engineering contracts are downstream consumers of the research core. They are **not** HaF ontology and must not be used to retroactively redefine Foundation identity.

## Current product surfaces

Current `README.md` / `ARCHITECTURE.md` expose, among other contracts:

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

## Research-approved consumption boundary — not yet a product surface

Operational Claim Standing v0 admits a technology-neutral future consumption boundary:

- `OperationalClaimRef` responsibility — exact owner-grounded bounded claim identity/scope/currentness reference;
- `OperationalClaimStandingView` responsibility — subject/use/evidence-relative immutable standing projection;
- optional `OperationalClaimUseDisposition` responsibility — use-relative settlement/continuation projection distinct from truth/completion.

Standing values are evidence-relative roles such as `SUPPORTED`, `CONTRADICTED`, `CONFLICTED`, `UNDERDETERMINED`.

This admission explicitly requires:

- claim meaning/truth ownership remains external;
- standing is not a mutable global property on Q;
- receipts remain evidence inputs, not standing objects;
- history/currentness is preserved across later projections;
- no semantic-authority global Harness Claim registry is required;
- no second evidence/history/authority plane is created.

Production implementation is **not admitted yet**. Exact classes, schema, storage and APIs require a separate implementation/admission task and should initially target E5-v2 direct dogfood rather than a universal claim platform.

## Non-inference rule

The existence of a Python class, CLI flag, SQLite table, schema field, provider protocol, test fixture or current architecture paragraph proves only current Engineering Consumption. A research-approved future consumption boundary likewise does not prove production implementation. Neither creates HaF62, alters HaF0–61, promotes the Operational Spine into a higher tier, or transfers another owner's truth into Harness.
