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

## Non-inference rule

The existence of a Python class, CLI flag, SQLite table, schema field, provider protocol, test fixture or current architecture paragraph proves only current Engineering Consumption. It does not create HaF62, alter HaF0–61, promote the Operational Spine into a higher tier, or transfer another owner's truth into Harness.
