# 120 — CAMPAIGN 6 ROUND 2
# Adjacent Engineering Dogfood Contract

**Research authority:** Campaign 6 Charter + Round 1 P6'/FOR revision.  
**Critical evidence rule:** these fixtures do not instantiate two true AgentOperationalSubjects. They may support component relations only.

## 1. Round target

Use existing implementation to pressure federation-adjacent semantics for:

- bounded delegated/aggregate authority;
- exact evidence adoption;
- evidence-role separation;
- delivered caller cognition vs admitted/promoted cognition;
- source/authenticity fencing;
- durable promotion/supersession/history;
- process-independent reconstruction.

Prebound final evidence class:

`DIRECT_FEDERATION_ENGINEERING_EVIDENCE = NONE`

unless a selected fixture unexpectedly demonstrates two independently bounded AgentOperationalSubjects. No such result is expected.

## 2. Prebound fixtures

### D1 — replanned attempt adopts exact prior receipt and switches profile
`tests.test_execution_mandate.ExecutionMandateTests.test_replan_attempt_can_adopt_prior_receipt_evidence_and_switch_profile`

Adjacent pressure: transfer/adoption can preserve exact evidence while local operational configuration changes.

### D2 — profile outside capability envelope rejected
`tests.test_execution_mandate.ExecutionMandateTests.test_profile_outside_capability_envelope_is_rejected`

Adjacent pressure: possession of a broader system surface does not grant authority outside the admitted envelope.

### D3 — strategy cannot exceed aggregate economic envelope
`tests.test_execution_mandate.ExecutionMandateTests.test_strategy_cannot_exceed_aggregate_economic_envelope`

Adjacent pressure: delegated/bounded authority is not freely amplifiable by the acting operation.

### D4 — Agent adopts exact independent strategy evidence
`tests.test_strategy_selection_p1.HarnessStrategySelectionP1Tests.test_agent_may_adopt_exact_independent_strategy_evidence`

Adjacent pressure: evidence becomes locally usable through explicit adoption/binding, not visibility alone.

### D5 — evidence ref cannot alias incompatible prior-attempt role
`tests.test_strategy_selection_p1.HarnessStrategySelectionP1Tests.test_strategy_evidence_reference_cannot_alias_prior_attempt_evidence`

Adjacent pressure: cross-subject evidence transfer would need role-preserving adoption; one reference cannot silently change semantic role.

### D6 — projected caller input becomes visible and reopens bounded gate
`tests.test_pc110_caller_cognition_ingress.CallerCognitionIngressTests.test_projected_resume_caller_input_is_visible_and_reopens_soft_gate`

Adjacent pressure: externally supplied cognition enters through an explicit projection/admission event.

### D7 — non-user cognition ingress rejected
`tests.test_pc110_caller_cognition_ingress.CallerCognitionIngressTests.test_projected_resume_rejects_non_user_cognition_ingress`

Adjacent pressure: sender/source role matters; delivered content does not have generic cognition authority.

### D8 — forged caller ingress rejected before Provider dispatch
`tests.test_pc110_caller_cognition_ingress.CallerCognitionIngressTests.test_forged_caller_ingress_is_rejected_before_provider_dispatch`

Adjacent pressure: transfer provenance/authenticity is required before local operational use.

### D9 — Agent promotes exact subset; only promoted bytes survive next interaction
`tests.test_pc111_interaction_durable_promotion.InteractionDurablePromotionTests.test_agent_promotes_exact_subset_then_only_promoted_bytes_survive_next_interaction`

Adjacent pressure: receipt/delivery of information is distinct from explicit durable adoption.

### D10 — caller ingress is not materialized/selected without Agent promotion
`tests.test_pc111_interaction_durable_promotion.InteractionDurablePromotionTests.test_caller_ingress_is_not_materialized_or_selected_without_agent_promotion`

Adjacent pressure: Delivery != Adoption != durable cognition.

### D11 — correction creates ordinary new selection while stale pin remains history
`tests.test_pc112_durable_cognition_supersession.DurableCognitionSupersessionTests.test_correction_is_promotion_plus_ordinary_selection_and_stale_pin_remains_history`

Adjacent pressure: later adoption/supersession changes current cognition without rewriting prior history.

### D12 — fresh process reconstructs settled/pending Tool exchange
`tests.test_pc16_cross_process_tool_exchange.CrossProcessToolExchangeTests.test_fresh_process_rebuilds_complete_current_attempt_tool_exchange`

Adjacent pressure: operational/evidence continuity can survive process replacement; infrastructure identity is not sufficient operational-subject identity.

## 3. Explicit non-fixtures

No current fixture directly tests:

- two independent AgentOperationalSubjects under one Host Task;
- Agent-to-Agent delegation edge and revocation;
- same Q with different per-Agent evidence standing;
- duplicate concurrent Invocations from two Agents;
- partitioned Agent branches and later federation reconciliation;
- cross-Agent CompletionProposal scope;
- true cross-Agent OCSS adoption;
- Network delivery with remote Agent adoption unknown.

Those remain `CONCEPTUAL_ONLY / FUTURE_DIRECT_FEDERATION_EVIDENCE`.

## 4. Evaluator

For D1–D12 record:

- mechanical result;
- adjacent relation exposed;
- P6' pressure;
- why it does not constitute direct federation proof.

Round-level classes:

- `ADJACENT_ENGINEERING_SUPPORT_IN_SCOPE`;
- `ADJACENT_ENGINEERING_FALSIFIER_FOUND`;
- `ADJACENT_ENGINEERING_INSUFFICIENT`.

Direct evidence is reported separately and expected to remain NONE.

## 5. Stop condition

Execute D1–D12 once under repository-canonical `uv run`. Do not create a fake second-Agent fixture after seeing results.
