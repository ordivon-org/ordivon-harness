# 108 — CAMPAIGN 4 ROUND 2
# Engineering Dogfood Contract

**Research authority:** Campaign 4 Charter v1 + Round 1 P4'/OCSS revision.  
**Code-change rule:** no production or test code changes during dogfood.  
**Interpretation rule:** receipts/proposals/context objects are evidence surfaces, not accountability ontology.

## 1. Information-positive target

Round 2 attacks these P4' distinctions using existing engineering only:

- support/evidence must bind exact contract/manifest/receipt lineage;
- same-named changed mandate must not inherit prior support;
- malformed/incomplete evidence binding/accounting fails closed;
- evidence not present in the decision Context cannot be invented/adopted;
- CompletionProposal is an exact evidence object with unresolved unknowns, not generic completion authority;
- CompletionProposal support is receipt/trace/terminal-state bound;
- independent strategy evidence is immutable/digest-bound and cannot alias another evidence role;
- completed/candidate-completed operations preserve unresolved unknowns and exact trace/receipt bindings;
- read-only telemetry preserves unavailable fields as unavailable and explicitly avoids semantic-completion overclaim.

Round 2 does not claim engineering proof for common-cause independence, counterevidence revision, support cycles, or cross-owner support composition because current fixtures do not directly exercise those concepts.

## 2. Prebound existing fixtures

### D1 — prior-attempt evidence binds manifest, contract and receipt

`tests.test_strategy_selection_p0.HarnessStrategySelectionP0Tests.test_prior_attempt_evidence_round_trip_binds_manifest_contract_and_receipt`

Pressure: evidence identity is a compound exact binding, not a loose label/ref.

### D2 — same-named changed mandate cannot reuse old receipt

`tests.test_strategy_selection_p0.HarnessStrategySelectionP0Tests.test_same_named_changed_mandate_cannot_reuse_old_receipt`

Pressure: naming similarity does not transfer support across changed claim/use contract.

### D3 — attempt evidence binding/accounting fails closed

`tests.test_strategy_selection_p0.HarnessStrategySelectionP0Tests.test_attempt_evidence_binding_and_accounting_fail_closed`

Pressure: contract/manifest/usage inconsistencies invalidate the claimed evidence relation rather than being silently tolerated.

### D4 — Agent can adopt only receipts visible in selection Context

`tests.test_strategy_selection_p0.HarnessStrategySelectionP0Tests.test_agent_can_only_adopt_receipts_visible_in_selection_context`

Pressure: an invented-but-well-formed reference cannot become operational support without an admitted Context/evidence path.

### D5 — CompletionProposal is exact prior-attempt evidence and preserves unknowns

`tests.test_strategy_selection_p1.HarnessStrategySelectionP1Tests.test_completion_proposal_is_exact_prior_attempt_evidence`

Pressure: proposal evidence is exact/digest-bound and carries unresolved unknowns rather than presenting only positive completion evidence.

### D6 — CompletionProposal receipt binding fails closed

`tests.test_strategy_selection_p1.HarnessStrategySelectionP1Tests.test_completion_proposal_receipt_binding_fails_closed`

Pressure: proposal support cannot be detached from the exact receipt it claims.

### D7 — non-completed attempt cannot carry CompletionProposal

`tests.test_strategy_selection_p1.HarnessStrategySelectionP1Tests.test_noncompleted_attempt_cannot_carry_completion_proposal`

Pressure: evidence role is lifecycle-typed; artifact shape alone cannot manufacture completion-proposal standing.

### D8 — independent strategy evidence is immutable/digest-bound

`tests.test_strategy_selection_p1.HarnessStrategySelectionP1Tests.test_strategy_evidence_is_digest_bound_immutable_snapshot`

Pressure: external/independent evidence must retain exact content binding; later mutation cannot retroactively change what was adopted.

### D9 — strategy evidence reference cannot alias prior-attempt evidence

`tests.test_strategy_selection_p1.HarnessStrategySelectionP1Tests.test_strategy_evidence_reference_cannot_alias_prior_attempt_evidence`

Pressure: one ref cannot silently occupy two evidence roles with conflicting semantics.

### D10 — completed Run preserves unresolved unknowns for caller

`tests.test_p0_standalone_runner.StandaloneHarnessRunnerTests.test_completed_run_preserves_unresolved_unknowns_for_caller`

Pressure: candidate completion/accountability must preserve material unknowns; positive result does not erase unresolved obligations.

### D11 — candidate completion remains restart-inspectable with exact receipt/trace binding

`tests.test_p0_standalone_runner.StandaloneHarnessRunnerTests.test_candidate_completion_is_terminal_and_restart_inspectable`

Pressure: bounded reproduction/inspection can preserve exact support objects across restart without asserting domain completion.

### D12 — telemetry preserves unavailable fields and unknown continuity

`tests.test_telemetry_projection.TelemetryProjectionTests.test_missing_provider_cache_fields_remain_unavailable`

Pressure: read-only accountability projection must preserve unavailable/unknown state rather than fabricate complete evidence.

### D13 — terminal telemetry explicitly limits completion interpretation

`tests.test_telemetry_projection.TelemetryProjectionTests.test_terminal_projection_normalizes_cache_and_remaining_budget`

Pressure: derived telemetry can expose exact receipt evidence while explicitly refusing to imply domain semantic completion.

## 3. Explicit non-fixtures

No current-engineering proof is claimed here for:

- T4/T5 common-cause vs independent corroboration;
- T7 owner-authoritative supersession semantics in the general case;
- T9/T16 rebuttal/counterevidence revision;
- T13/T14 domain/cross-owner support composition;
- T15 nondeterministic reproduction across independent implementations/world states;
- T17/T18 arbitrary support transitivity/cycles;
- T20 full successor-Run accountability equivalence.

These remain conceptual pressure/future evidence opportunities.

## 4. Prebound evaluator

For D1–D13 record:

- mechanical outcome;
- technology-neutral fact exposed;
- P4' pressure: `SUPPORT / FALSIFIER / NEUTRAL / INSUFFICIENT`;
- primary relation: binding / evidence admission / proposal role / unknown preservation / reproduction-inspection / projection boundary;
- owner-boundary check.

Round-level class:

- `ENGINEERING_SUPPORT_IN_SCOPE`
- `ENGINEERING_FALSIFIER_FOUND`
- `ENGINEERING_EVIDENCE_INSUFFICIENT`

## 5. Interpretation constraints

- Test pass does not prove the supported claim true; it supports the OCSS relation/invariant.
- A receipt/proposal is authoritative only for its bounded role/claim.
- `independent strategy evidence` is an implementation role name; Campaign 4 does not infer universal statistical/causal independence from the class name.
- No new graph implementation/tests will be created after outcomes are observed.

## 6. Stop condition

Execute D1–D13 once under repository-canonical `uv run`. Stop Round 2 after those fixtures unless one directly exposes a bounded contradiction in P4'.
