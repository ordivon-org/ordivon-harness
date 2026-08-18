# 102 — CAMPAIGN 3 ROUND 2
# Engineering Dogfood Contract

**Research authority:** Campaign 3 Charter v1 + Round 1 P3' revision.  
**Code-change rule:** no production or test code changes during selected dogfood.  
**Interpretation rule:** current status names/receipts are implementation evidence only.

## 1. Information-positive target

Round 2 attacks these P3' distinctions using only existing engineering:

- intent/preparation/fence standing is distinct from actual dispatch;
- dispatch/terminal/reconciliation evidence is lineage-bound;
- no result content does not erase terminal/evidence standing;
- response loss does not authorize redispatch of a durably completed operation;
- current-process loss does not erase settled Tool evidence;
- missing cognitive/content authority can block continuation without creating permission for a new external effect;
- generic Provider failure can preserve dispatch ambiguity rather than being flattened to pre-dispatch failure;
- once a Provider failure is durably admitted, a local recovery signal must not rewrite it as a different unknown standing.

Round 2 does not test partial/delayed/compensating/interfering world effects because no mature current fixture establishes those semantics.

## 2. Prebound existing fixtures

### D1 — prepared Tool intent/fence exists before any receipt

`tests.test_p0_sqlite_tool_store.SQLiteHarnessRunContinuityToolTests.test_prepare_persists_v2_fence_and_runtime_authority_claim`

Pressure: prepared/authorized dispatch lineage is not itself evidence that external realization occurred.

### D2 — terminal receipt is idempotent and supersedes old dispatch fence

`tests.test_p0_sqlite_tool_store.SQLiteHarnessRunContinuityToolTests.test_terminal_receipt_is_idempotent_and_fences_old_dispatch`

Pressure: terminal evidence can settle bounded Harness standing and prohibit redispatch without implying universal domain success.

### D3 — nonterminal receipt chains to reconciled terminal receipt

`tests.test_p0_sqlite_tool_store.SQLiteHarnessRunContinuityToolTests.test_nonterminal_receipt_chains_to_reconciled_terminal_receipt`

Pressure: reconciliation advances current standing by lineage rather than rewriting the prior nonterminal record.

### D4 — metadata-only terminal receipt preserves digest/standing without content

`tests.test_p0_sqlite_tool_store.SQLiteHarnessRunContinuityToolTests.test_metadata_only_receipt_retains_observation_digest_not_content`

Pressure: evidence/terminal standing can remain while exact observation cognition is unavailable.

### D5 — Provider completion survives response loss and fences redispatch without result content

`tests.test_p0_sqlite_agent_loop.SQLiteHarnessAgentLoopTests.test_metadata_only_response_loss_fences_redispatch_without_result_content`

Pressure: durable terminal Provider standing is not erased by delivery loss; missing result content blocks recovery rather than authorizing a second Provider operation.

### D6 — fresh process reuses settled Tool evidence and executes only pending Tool

`tests.test_pc16_cross_process_tool_exchange.CrossProcessToolExchangeTests.test_fresh_process_rebuilds_complete_current_attempt_tool_exchange`

Pressure: process lifetime is not realization standing; settled vs pending Invocation evidence controls what external realization is attempted after recovery.

### D7 — missing Tool content authority blocks resume with zero new Runtime execution

`tests.test_pc16_cross_process_tool_exchange.CrossProcessToolExchangeTests.test_cross_process_tool_exchange_recovery_fails_without_tool_content_authority`

Pressure: terminal Tool standing can survive while result-content cognition/resumability fails; evidence insufficiency does not create redispatch permission.

### D8 — generic Provider adapter error defaults to dispatch ambiguity

`tests.test_provider_call_protocol.AgentTurnPersistenceModelTests.test_adapter_error_defaults_to_ambiguous_dispatch`

Pressure: one generic failure field cannot safely imply non-dispatch; dispatch safety/standing must remain typed.

### D9 — durable Provider failure is not rewritten as a new Provider-unknown state

`tests.test_provider_recovery_signal_fence_p1.ProviderRecoverySignalFenceP1Tests.test_recovery_signal_after_durable_failure_is_not_reclassified_as_provider_unknown`

Pressure: later local recovery signaling must preserve the already-admitted failure standing rather than rewriting history/currentness into a different uncertainty class.

## 3. Explicit non-fixtures

No engineering claim is made in this campaign for:

- T5 cancellation-before/after-effect race as physical causal truth;
- T6 arbitrary partial world realization;
- T7/T16 delayed world effect after local timeout;
- T8 actual duplicate physical side effect under blind retry;
- T10 external idempotency semantics;
- T11 compensation semantics;
- T12 contradictory independent external effect authorities;
- T14 interacting world effects;
- T15 domain semantic success/failure after physical effect.

These remain conceptual pressure and future owner/external evidence opportunities.

## 4. Prebound evaluator

For D1–D9 record:

- mechanical outcome;
- technology-neutral fact exposed;
- P3' pressure: `SUPPORT / FALSIFIER / NEUTRAL / INSUFFICIENT`;
- primary relation: dispatch / claim evidence / reconciliation / content availability / continuation obligation;
- owner-boundary check.

Round-level class:

- `ENGINEERING_SUPPORT_IN_SCOPE`
- `ENGINEERING_FALSIFIER_FOUND`
- `ENGINEERING_EVIDENCE_INSUFFICIENT`

## 5. Interpretation constraints

- Passing tests do not prove physical/world Effect truth or cross-implementation universality.
- A receipt may be authoritative for the exact claim its issuer owns; it is not automatically evidence for broader causal/domain claims.
- Test failure counts as a research falsifier only if the prebound semantic pressure is reached rather than failing on environment/import mechanics.
- No new tests will be written after seeing outcomes to make P3' look stronger.

## 6. Stop condition

Execute D1–D9 once under repository-canonical `uv run`. Stop Round 2 after those fixtures unless one reveals a bounded ambiguity directly relevant to P3'.
