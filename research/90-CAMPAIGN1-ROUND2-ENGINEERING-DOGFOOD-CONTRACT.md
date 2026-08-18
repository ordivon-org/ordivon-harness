# 90 — CAMPAIGN 1 ROUND 2
# Engineering Dogfood Contract

**Research authority:** Campaign 1 Charter v1 + Round 1 P1' revision.  
**Dogfood rule:** current Ordivon Harness behaviour is evidence/falsifier only, not ontology authority.  
**Code-change rule:** no production or test code changes are admitted during this dogfood round.

## 1. Information-positive target

Round 2 attacks the surviving claims from Round 1:

- same Run identity can survive fresh-process reconstruction;
- recovery validity, identity standing and resumability are distinct;
- persisted Invocation/result evidence should prevent unsafe redispatch;
- reconciliation may restore continuation without replaying an already-realized operation;
- continuation topology must prevent two concurrent successor states from silently advancing one linear continuation;
- current implementation-specific IDs/classes are mechanisms, not the sole source of these distinctions.

Round 2 does **not** attempt to prove P1' necessary/sufficient for all Harness implementations.

## 2. Exact prebound dogfood fixtures

The following existing tests were selected by fixture-feasibility inspection before execution outcomes were observed.

### D1 — terminal receipt fences old dispatch

`tests.test_p0_sqlite_tool_store.SQLiteHarnessRunContinuityToolTests.test_terminal_receipt_is_idempotent_and_fences_old_dispatch`

Maps primarily to T8 and P1-D/P1-E.

Research pressure:

- after durable terminal evidence, reopening the continuity store must not make the old dispatch fence current again;
- if it did, P1' would suffer false-continuation/duplicate-effect pressure.

### D2 — nonterminal receipt chains to reconciled terminal receipt

`tests.test_p0_sqlite_tool_store.SQLiteHarnessRunContinuityToolTests.test_nonterminal_receipt_chains_to_reconciled_terminal_receipt`

Maps to T7 -> T8 transition.

Research pressure:

- unresolved/partial standing can evolve through explicit reconciliation without rewriting prior receipt lineage;
- if reconciliation replaced history without lineage, P1-B/P1-D would be weakened.

### D3 — response loss does not authorize provider redispatch

`tests.test_p0_sqlite_agent_loop.SQLiteHarnessAgentLoopTests.test_metadata_only_response_loss_fences_redispatch_without_result_content`

Maps to the general identity/resumability distinction, with Provider continuation rather than physical Tool effect.

Research pressure:

- exact Run continuity can remain identifiable while missing content prevents safe continuation;
- a fresh process must not infer permission to reissue the already-completed Provider operation merely because exact result content was lost.

### D4 — fresh process rebuilds current-attempt Tool exchange

`tests.test_pc16_cross_process_tool_exchange.CrossProcessToolExchangeTests.test_fresh_process_rebuilds_complete_current_attempt_tool_exchange`

Maps to T1/T8/T9.

Research pressure:

- one Tool operation completed before process loss must be recovered from durable evidence rather than executed again;
- the still-pending Tool operation may proceed;
- fresh process identity must not force a new Harness Run identity by itself.

### D5 — same Run cannot resume when required Tool content authority is absent

`tests.test_pc16_cross_process_tool_exchange.CrossProcessToolExchangeTests.test_cross_process_tool_exchange_recovery_fails_without_tool_content_authority`

Maps to T7/T9 and the revised three-axis evaluator.

Research pressure:

- physical Tool execution may already be terminal and the historical Run identity may remain known;
- nevertheless, recovery must fail closed when required continuation evidence/content is unavailable;
- if the implementation instead redispatches or silently invents missing cognition, P1' is falsified in scope.

### D6 — concurrent successor writers cannot both advance one revision

`tests.test_pc1_working_view.WorkingViewPrototypeTests.test_concurrent_working_set_writers_cannot_both_advance_one_revision`

Maps to T10 / P1-G as an implementation-level proxy for continuation exclusivity.

Research pressure:

- two concurrent successors from one current state must not both become the linear current successor;
- this is evidence for the semantic need for explicit continuation topology/fencing, not proof that SQLite/CAS is the unique mechanism.

## 3. Explicitly not executed in Round 2

### T6 — definitely not dispatched before crash

No equally direct existing end-to-end dogfood fixture was identified during feasibility scan. Round 1's conceptual result remains provisional. Round 2 will **not** write a new test merely to manufacture confirming evidence.

### Full T10 branch semantics

D6 tests single-successor exclusion, not the full semantics of declared branch identity. Full branch/replay identity remains conceptual in this round.

### Provider/model migration

No current dogfood fixture is used to decide whether provider/model change preserves Run identity. T2 remains condition-relative and outside Round 2 execution.

## 4. Prebound interpretation rules

- Test `PROCESS_EXIT_ZERO` means only that the current implementation fixture behaved as its assertions specify.
- A passing D1–D6 can **support** P1' in the tested mechanism but cannot prove necessity/sufficiency.
- A failing test is not automatically a research falsifier; first determine whether the failure is an unrelated engineering regression.
- A test outcome is research-relevant only if it changes the standing of a prebound claim/rival/falsifier.
- Current implementation names (`SQLiteHarnessRunContinuityStore`, `HarnessRunContract`, etc.) must be translated back to technology-neutral commitments before interpretation.

## 5. Round 2 evaluator

For each D1–D6 record:

- mechanical test outcome;
- technology-neutral fact demonstrated, if any;
- P1' pressure: SUPPORT / FALSIFIER / NEUTRAL / INSUFFICIENT;
- rival pressure, especially R6;
- owner-boundary check.

Round-level output:

- `ENGINEERING_SUPPORT_IN_SCOPE`
- `ENGINEERING_FALSIFIER_FOUND`
- `ENGINEERING_EVIDENCE_INSUFFICIENT`

This remains subordinate to the campaign-level final result.

## 6. Stop condition

After D1–D6, stop execution dogfood. Do not broaden to the whole Harness test suite unless one selected fixture exposes a concrete ambiguity requiring a bounded follow-up.
