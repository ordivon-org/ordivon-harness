# 144 — CURRENT NO-TOOL CONCLUSION-CONTROL REGRESSION REOPEN & REPAIR v1
# Prebound Acceptance / Falsifier Contract

**Selection authority:** `143-POST-PROVIDER-ROUTE-TYPED-FRONTIER-TOURNAMENT-V1.md`.  
**Starting canonical:** `ee413f7af20e126656fa03c40e2cde56138c7e4c`.  
**Control task:** `task:harness-no-tool-conclusion-control-current-regression-repair-v1-20260819`.  
**Historical falsifier source:** exact `tests/test_p6_no_tool_conclusion_control.py` bytes at `6b4cc7724c83061a03fdb85df0003e9b4bff8d26`.  
**Foundation effect:** none. HaF0–HaF61 remain frozen; HaF62 remains UNKNOWN / NOT SELECTED / NOT ADMITTED.

## 1. Repair question

Can the current contracted Harness restore the already-supported authority distinction

`Harness-native conclusion/control correction != Runtime Tool-history authority`

for no-Tool Runs, while preserving the later product contraction that removed generic Provider continuation machinery?

This is a current product regression repair. It is not Campaign 7, not a new Foundation programme and not permission to restore historical deleted machinery.

## 2. Why the historical seven tests are valid current falsifiers

Tournament 143 established all three required currentness facts:

1. The exact historical seven-test file still imports/runs against current source without compatibility editing.
2. Current `tests/test_conclusion_correction_separation.py` still requires independent `maxConclusionCorrections` with `maxToolCalls = 0`, so the conclusion-control authority law remains a current product contract.
3. Running the exact historical seven tests against current `cd694fc...` source produced six failures, including two strict no-Tool `ToolBridgeError` reproductions.

Therefore the historical file is reused **byte-for-byte** as a current regression falsifier set at:

`tests/test_current_no_tool_conclusion_control_regression.py`.

Its provenance is historical; its acceptance meaning is current because the tested authority contract is still present.

## 3. Explicitly not restored

The repair MUST NOT restore:

- `ProviderToolContinuation`;
- generic Provider continuation/session state;
- deleted P6/P7 experiment runners/evidence as product authority;
- a Provider-neutral opaque wire-state registry;
- any new Tool-history path for no-Tool Runs.

The later contraction decision remains in force unless independent new pressure earns one of those mechanisms.

## 4. Strict owner boundary

`SQLiteHarnessAgentBridge` remains the strict no-Tool continuity boundary.

Its invariant is not the bug:

> a no-Tool Run cannot bind Runtime Tool observations or Tool Call identities.

The regression occurs earlier when invalid Harness-native control or unavailable Provider actions are incorrectly admitted into generic Tool bookkeeping before that strict invariant is checked.

A valid repair therefore changes classification/control flow **before fake Runtime Tool history exists**. It must not relax the bridge.

## 5. F1 — invalid structured conclusion control

Input shape:

- no-Tool Run;
- Provider-normalized `submit_run_conclusion` action;
- malformed conclusion fields (`summary` not a string);
- `argument_error = invalid_conclusion: ...`;
- one remaining conclusion correction;
- zero Tool corrections and zero Tool calls.

Required:

- first turn is treated as Harness conclusion/control correction, not Runtime Tool activity;
- next Provider turn remains no-Tool;
- corrected valid conclusion reaches `candidate_completed`;
- `tool_calls = 0`;
- `toolCorrections = 0`;
- `conclusionCorrections = 1`;
- no Tool observation/history is created.

Direct falsifier:

- `NO_PROGRESS` before the correction turn;
- Runtime Tool history created;
- Tool correction budget consumed.

## 6. F2 — invalid JSON conclusion control

Same authority boundary as F1, but Provider-normalized conclusion arguments are invalid JSON.

Required:

- uses conclusion-correction authority;
- corrected second turn can complete;
- zero Tool calls and Tool corrections;
- one conclusion correction.

## 7. F3 — mixed conclusion control + another Provider action

A turn contains malformed conclusion control plus another unavailable action.

Required:

- the mixed action turn is not silently converted into a valid conclusion;
- no simultaneous completion is admitted;
- no conclusion-correction budget is silently spent as if the turn contained only malformed conclusion control;
- mixed-action conflict semantics remain explicit.

This case prevents the repair from over-generalizing “malformed conclusion” into “ignore every other action on the turn.”

Current Tool-enabled mixed-action behavior remains additionally guarded by the existing current mixed-turn tests; no historical provider continuation machinery is required.

## 8. F4 — one unavailable Provider action on a no-Tool surface

A Provider emits one action normalized with `argument_error = unavailable_tool` while `AgentTurnRequest.tools == ()`.

Required:

- it is model-correctable bounded action feedback;
- it does not earn Runtime Tool-history authority;
- no Tool message/observation is bound;
- `tool_calls = 0` physical Tool calls;
- one Tool correction may be consumed as the bounded invalid/unavailable action budget;
- next no-Tool Provider turn may conclude normally.

Direct falsifier:

`SQLiteHarnessAgentBridge` receives fake Tool identities/observations and raises its strict no-Tool error.

## 9. F5 — multiple unavailable Provider actions on one no-Tool turn

Required:

- the turn consumes one bounded correction opportunity, not one fake physical Tool Call per unavailable action;
- no Tool messages/history are created;
- next no-Tool turn may conclude normally.

This tests turn-level correction semantics rather than artifact/action multiplicity.

## 10. F6 — repeated unavailable no-Tool turns

With `maxToolCorrections = 1`, two consecutive unavailable-action turns must stop deterministically as invalid Tool/action output after exactly one correction.

Required:

- no physical Tool calls;
- `toolCorrections = 1`;
- no Tool messages/history;
- strict no-Tool bridge remains healthy.

The repair must not create an unbounded “keep asking the model” loop.

## 11. F7 — repeated malformed conclusion controls

With `maxConclusionCorrections = 1`, two malformed conclusion-control turns must stop deterministically with invalid model output after exactly one conclusion correction.

Required:

- zero Tool calls;
- zero Tool corrections;
- one conclusion correction;
- no Runtime Tool history.

## 12. Current-contract compatibility guards

Beyond the seven restored falsifiers, acceptance MUST include current tests that were not part of historical P6:

### G1 — current conclusion-correction separation

`tests.test_conclusion_correction_separation`

Must remain green. In particular owner/domain conclusion rejection with `maxToolCalls=0` must still consume conclusion correction rather than Tool correction.

### G2 — current mixed Provider action semantics

Current mixed-turn / Tool-enabled tests must remain green. The repair must not swallow genuine Runtime Tool intent merely because another Harness-native control is malformed.

### G3 — strict no-Tool bridge

Existing no-Tool bridge tests must remain strict. No new compatibility relaxation is admitted.

### G4 — contracted current product

No `ProviderToolContinuation` symbol/API/test is added. Active docs remain explicit that generic opaque Provider continuation is not a current contracted Harness surface.

## 13. Baseline-red requirement

Before any `src/` modification:

1. commit this contract;
2. materialize the byte-exact seven-test current regression file;
3. run the focused seven-test module against the exact pre-repair commit.

Expected classification:

`CURRENT_NO_TOOL_CONCLUSION_CONTROL_REGRESSION_REPRODUCED`

if at least the Tournament-143 observed failures remain red.

If the focused tests unexpectedly become green before source modification, STOP and revalidate current source/workspace rather than applying a repair.

## 14. Minimal repair criterion

The preferred repair location is the earliest current Loop/control boundary at which Harness can distinguish:

- malformed Harness-native conclusion control;
- unavailable Provider action that has no admitted Runtime Tool surface;
- genuine admitted Runtime Tool intent;
- mixed/conflicting action turns.

A valid repair MUST NOT depend on persistence of Provider-specific opaque continuation.

Historical P6 commits may be diffed only for causal guidance. No cherry-pick/wholesale restoration is authorized.

## 15. Source-change ceiling

Expected source change should be narrowly localized to current Loop/action classification and, only if deletion-essential, directly adjacent Provider normalization helpers.

Source changes to any of the following are presumptively out of scope and require STOP/reclassification:

- `SQLiteHarnessAgentBridge` weakening;
- new persistence schema/tables;
- Provider continuation registry/state;
- Runtime Tool authority expansion;
- Claim Standing;
- Campaign-5 route policy;
- Mandate/Strategy policy.

## 16. Acceptance classification

Classify `CURRENT_NO_TOOL_CONCLUSION_CONTROL_REPAIR_ACCEPTED` only if:

- F1–F7 green;
- G1–G4 green;
- strict no-Tool bridge unchanged in authority;
- no `ProviderToolContinuation` restoration;
- no new persistence/authority plane;
- full current Harness baseline green;
- documentation/dependency/public API contracts green;
- source diff is bounded and architecture-consistent.

Classify `CURRENT_NO_TOOL_CONCLUSION_CONTROL_REPAIR_SCOPE_EXPANSION_REQUIRED` and STOP if those falsifiers cannot be repaired without restoring deleted continuation/session machinery or weakening no-Tool authority.

## 17. Post-repair currentness

If accepted, historical P6 remains historical evidence. The new repair becomes the current product proof boundary because it is tested against the contracted post-contraction architecture.

A fresh typed frontier tournament is required after closeout. No automatic continuation to Campaign 7, HaF62, OPUR, OCSS dependency, Claim UseDisposition, delegation/federation or cross-implementation work is authorized.
