# 96 — CAMPAIGN 2 ROUND 2
# Engineering Dogfood Contract

**Research authority:** Campaign 2 Charter v1 + Round 1 P2' revision.  
**Code-change rule:** no production or test code changes during selected dogfood.  
**Interpretation rule:** implementation behavior is evidence/falsifier only, not Context ontology.

## 1. Information-positive target

Round 2 attacks these revised claims:

- invalid/ungrounded Context projection must fail before sufficiency is considered;
- materialized/available information is not automatically current/effective Context;
- durable Context basis differs from effective decision exposure;
- transient and durable material differ across continuation horizons;
- promotion/selection changes future Context authority while exact unpromoted bytes expire with their narrower authority;
- the same durable selected basis can accompany materially different effective Context at different decision frontiers;
- history/recall mechanisms do not automatically inject historical material into current Context.

Round 2 does not attempt to prove arbitrary domain decision sufficiency or model-behavior invariance.

## 2. Prebound existing fixtures

### D1 — unbound overlay rejected before Provider dispatch

`tests.test_pc14_candidate_discovery_overlay.CandidateDiscoveryOverlayTests.test_unbound_append_overlay_is_rejected_before_provider_dispatch`

Maps to T1/T16 and P2'-A.

Pressure: apparently useful additional Context that lacks valid observation/provenance binding must not become effective Context merely because it can be rendered into messages.

### D2 — materialized but unselected source never becomes later cognition

`tests.test_pc17_durable_knowledge_promotion.DurableKnowledgePromotionTests.test_materialized_but_unselected_source_never_becomes_later_cognition`

Maps to P2'-B, T13/T14-adjacent selection standing.

Pressure: source bytes may physically exist and be addressable without acquiring current Context/cognition authority.

### D3 — transient knowledge survives pause then expires at successor

`tests.test_pc17_durable_knowledge_promotion.DurableKnowledgePromotionTests.test_transient_knowledge_survives_clean_pause_within_attempt_then_expires_at_successor`

Maps to T10/T11 and P2'-H.

Pressure: one piece of admitted information can be effective now and across a clean same-attempt pause while failing to survive a successor-attempt horizon unless promoted/selected durably.

### D4 — exact caller subset promotion controls what survives next interaction

`tests.test_pc111_interaction_durable_promotion.InteractionDurablePromotionTests.test_agent_promotes_exact_subset_then_only_promoted_bytes_survive_next_interaction`

Maps to T12 and P2'-B/P2'-H/P2'-I.

Pressure: two caller messages may both be effective current-interaction Context; only explicitly promoted selected bytes become durable next-interaction Context, while unpromoted caller bytes expire.

### D5 — same selected basis, successor attempt drops transient Tool exchange

`tests.test_pc19_cognition_transition_progress.CognitionTransitionProgressTests.test_same_selection_attempt_reset_still_discards_transient_tool_exchange`

Maps directly to T13 and P2'-B.

Pressure: unchanged durable selected pins do not imply equivalent effective decision Context across attempt boundary because transient Tool evidence lifetime changes.

### D6 — new caller ingress changes effective frontier without selected-basis change

`tests.test_pc19_cognition_transition_progress.CognitionTransitionProgressTests.test_projected_resume_input_resets_gate_once_model_visible`

Maps to effective-context and bounded-control consequences.

Pressure: new admitted caller information can change the effective Context/control frontier without requiring durable WorkingSet selection to change first.

### D7 — forged historical recall source rejected before Provider dispatch

`tests.test_pc18_historical_cognition_recall.HistoricalCognitionRecallTests.test_forged_history_reader_is_rejected_before_second_provider_dispatch`

Maps to validity/provenance and History != current Context.

Pressure: historical Context is not authorized by an arbitrary reader merely because a structurally plausible pin/catalog can be produced; recall must bind to authoritative committed cognition history.

## 3. Explicit non-fixtures

Round 2 does not attempt current engineering tests for:

- T2 arbitrary representation/order equivalence — current product request ordering has its own protocol meaning and is not a clean general-equivalence test;
- T8/T9 independent corroboration — that would drift toward full Accountability/Assurance theory;
- T18 external decision contract — conceptual owner-boundary result is decisive; engineering cannot supply missing domain relevance authority;
- identical/different model outputs — explicitly non-authoritative for P2'.

## 4. Prebound evaluator

For each D1–D7 record:

- mechanical outcome;
- technology-neutral fact exposed;
- P2' pressure: `SUPPORT / FALSIFIER / NEUTRAL / INSUFFICIENT`;
- relation primarily exercised: validity / effective exposure / lifetime / selection / history;
- owner-boundary check.

Round-level result:

- `ENGINEERING_SUPPORT_IN_SCOPE`
- `ENGINEERING_FALSIFIER_FOUND`
- `ENGINEERING_EVIDENCE_INSUFFICIENT`

## 5. Interpretation constraints

- Passing a test does not prove the P2' relation universal.
- Failure is a research falsifier only if it reaches the prebound semantic pressure rather than an unrelated engineering/import/environment defect.
- `WorkingSet`, `WorkingView`, specific message overlays and SQLite records must be translated to technology-neutral roles before research interpretation.
- Actual model outputs remain outside equivalence authority.
- Do not add or modify tests after observing outcomes to improve support.

## 6. Stop condition

Execute D1–D7 once under the repository-canonical test environment. Stop Round 2 after those fixtures unless one exposes a bounded ambiguity directly relevant to P2'.
