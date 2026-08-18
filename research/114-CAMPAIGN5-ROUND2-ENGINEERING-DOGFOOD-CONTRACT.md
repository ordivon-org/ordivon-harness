# 114 — CAMPAIGN 5 ROUND 2
# Engineering Dogfood Contract

**Research authority:** Campaign 5 Charter + Round 1 P5'/OPUR revision.  
**Code-change rule:** no production/test code changes during dogfood.

## 1. Information-positive target

Round 2 attacks P5' only where current implementation already contains meaningful reconfiguration pressure:

- attempt-bound morphology choice;
- stale Context/profile-set rejection;
- no Harness auto-ranking of morphology;
- successor attempt changing loop identity with exact prior-evidence adoption;
- explicit rejection of live mutation/factory surfaces;
- scheduling change without Tool-authority change;
- exact granted Tool surface shared across morphologies;
- unresolved external effect blocking continuation across morphologies;
- deliberation record remaining non-authoritative;
- fresh-process recovery preserving settled-vs-pending Tool standing.

No engineering proof is claimed for locus migration, provider replacement, capability internalization/externalization, authority expansion/revocation, OCSS rebuttal preservation or cross-implementation substitution.

## 2. Prebound fixtures

### D1 — Agent-owned attempt-bound morphology selection
`tests.test_am7_morphology_strategy_selection.AM7MorphologyStrategySelectionTests.test_agent_owned_strategy_can_select_attempt_bound_morphology_without_new_selector`

Pressure: structural selection can change morphology without creating a new universal selector ontology.

### D2 — morphology choice fenced to exact available-profile Context
`tests.test_am7_morphology_strategy_selection.AM7MorphologyStrategySelectionTests.test_morphology_choice_is_fenced_to_exact_available_profile_set`

Pressure: stale selection fails after the effective choice surface changes.

### D3 — Harness does not auto-rank morphology
`tests.test_am7_morphology_strategy_selection.AM7MorphologyStrategySelectionTests.test_harness_does_not_rank_or_auto_select_loop_morphology`

Pressure: reconfiguration options do not imply Harness-owned scalar ranking policy.

### D4 — successor attempt changes loop identity from exact prior receipt
`tests.test_am8_live_morphing_gate.AM8LiveMorphingGateTests.test_successor_attempt_can_change_loop_identity_from_exact_prior_receipt`

Pressure: bounded successor substitution may preserve prior evidence while changing Run/loop identity.

### D5 — no live loop install/factory/hot-reload surface
`tests.test_am8_live_morphing_gate.AM8LiveMorphingGateTests.test_no_live_loop_install_or_factory_surface_is_exposed`

Pressure: reconfiguration does not require uncontrolled live mutation; bounded successor admission is a legitimate structural mechanism.

### D6 — scheduling morphology changes without Tool-authority change
`tests.test_e3_e4_builtin_morphology.E3E4BuiltinMorphologyTests.test_deliberate_then_act_changes_scheduling_not_tool_authority`

Pressure: structural scheduling difference can preserve exact action authority.

### D7 — sequential/deliberate share exact granted Tool surface
`tests.test_e3_e4_builtin_morphology.E3E4BuiltinMorphologyTests.test_sequential_and_deliberate_share_same_exact_granted_tool_surface`

Pressure: different morphology can preserve an explicitly bound exposure/authority obligation.

### D8 — unknown external effect stops both morphologies
`tests.test_e3_e4_builtin_morphology.E3E4BuiltinMorphologyTests.test_unknown_external_effect_stops_both_morphologies_without_later_provider_turn`

Pressure: reconfiguration/morphology must not reset Campaign-3 uncertainty or create retry/continuation permission.

### D9 — deliberation record explicitly non-authoritative
`tests.test_e3_e4_builtin_morphology.E3E4BuiltinMorphologyTests.test_deliberation_record_is_explicitly_non_authoritative`

Pressure: internal scheduling/cognition structure does not silently acquire external authority through cut/morphology change.

### D10 — fresh process reuses settled Tool evidence and executes only pending Tool
`tests.test_pc16_cross_process_tool_exchange.CrossProcessToolExchangeTests.test_fresh_process_rebuilds_complete_current_attempt_tool_exchange`

Pressure: process change can preserve settled/pending realization obligations without equating process identity with operational identity.

## 3. Explicit non-fixtures

Current engineering does not directly prove:

- T1/T2 authority expansion/revocation reauthorization;
- T6 same bytes under changed external authority/currentness in the general case;
- T10/T11 arbitrary provider replacement equivalence;
- T13 capability internalization/externalization;
- T14 truth-owner change;
- T15/T16 locus/Network migration;
- T17/T18 general OCSS laundering/rebinding under reconfiguration;
- T19 one-way preservation with failed reverse transition as a first-class engine feature;
- T20 nondeterministic cross-implementation output difference.

These remain conceptual/future evidence frontiers.

## 4. Evaluator

For D1–D10 record:

- mechanical outcome;
- technology-neutral relation exposed;
- P5' pressure: `SUPPORT / FALSIFIER / NEUTRAL / INSUFFICIENT`;
- preservation dimension exercised;
- owner-boundary check.

Round-level classification:

- `ENGINEERING_SUPPORT_IN_SCOPE`;
- `ENGINEERING_FALSIFIER_FOUND`;
- `ENGINEERING_EVIDENCE_INSUFFICIENT`.

## 5. Interpretation constraints

- Passing morphology tests do not prove arbitrary boundary equivalence.
- Same Tool surface is evidence only for the bound Tool-authority/exposure obligation.
- Successor attempt is not same-Run continuation merely because prior receipt is adopted.
- Fresh process recovery does not prove arbitrary Runtime-process equivalence.
- No new tests will be written after observing outcomes to make P5' pass.

## 6. Stop condition

Execute D1–D10 once under repository-canonical `uv run`; stop Round 2 afterward unless a selected fixture reveals a direct bounded contradiction.
