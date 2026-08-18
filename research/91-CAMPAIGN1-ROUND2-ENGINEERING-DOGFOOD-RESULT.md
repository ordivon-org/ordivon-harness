# 91 — CAMPAIGN 1 ROUND 2
# Engineering Dogfood Result

**Prebound contract:** `90-CAMPAIGN1-ROUND2-ENGINEERING-DOGFOOD-CONTRACT.md` at commit `03e865b` before execution.  
**Successful dogfood Runtime Job:** `job-01a0151c-7f38-75d0-9cb0-87faff7295a2`.  
**Mechanical outcome:** 6 selected tests ran under repository-canonical `uv run`; all 6 passed.

A prior direct `/usr/bin/python3 -m unittest` attempt (`job-01a0151c-07c6-7c72-b348-37e45dea68a0`) failed at module import because the repository environment had not been materialized. It executed none of D1–D6 and is classified `NEUTRAL / ENVIRONMENT_SETUP_FAILURE`, not research evidence.

## 1. Round-level classification

`ENGINEERING_SUPPORT_IN_SCOPE`

No selected dogfood fixture produced an engineering falsifier of P1'. Passing tests do not prove the criterion necessary or sufficient; they show that the prebound technology-neutral distinctions correspond to independently exercised mechanisms in the current Ordivon Harness without requiring code changes.

## 2. D1 — terminal receipt fences old dispatch

Mechanical outcome: PASS.

Observed implementation fact:

- a terminal Tool receipt remains current after store reopen;
- replay of the exact terminal receipt is idempotent;
- the predecessor dispatch fence is superseded and cannot become current again merely because the process/store reopened.

Technology-neutral interpretation:

- settled Invocation/result evidence survives process reconstruction;
- recovery does not reopen an already-settled dispatch opportunity.

P1' pressure: `SUPPORT` for no-history-rewrite, Invocation-frontier accounting and continuation conservatism.

Owner boundary: the test consumes a recorded Runtime job reference/Tool observation; it does not make Harness the source of physical-effect truth.

## 3. D2 — nonterminal receipt -> reconciled terminal receipt

Mechanical outcome: PASS.

Observed implementation fact:

- a nonterminal receipt remains in the lineage;
- a later reconciled terminal receipt names the previous receipt digest rather than replacing the earlier history;
- the current standing advances while provenance remains inspectable.

Technology-neutral interpretation:

- unresolved operational standing can evolve by an explicit reconciliation edge;
- recovery/settlement need not rewrite the prior uncertain state.

P1' pressure: `SUPPORT` for P1-B/P1-D and the proposition that reconciliation is a lineage transition rather than replay.

## 4. D3 — response loss fences Provider redispatch

Mechanical outcome: PASS.

Observed implementation fact:

- Provider completion metadata and exact result digest survive response loss;
- exact result content is absent under the tested retention regime;
- fresh-process recovery refuses to invoke the Provider again and instead raises an explicit recovery-required condition.

Technology-neutral interpretation:

- an operation can remain historically identified/settled while current evidence is insufficient to resume cognition;
- missing recoverable content does not create authority to duplicate an already-completed operation.

P1' pressure: `SUPPORT` for `Identity/settled lineage != resumability` and conservative continuation.

This is a Provider-operation fixture, not physical Tool-effect evidence; its value is structural recurrence of the same distinction.

## 5. D4 — fresh process rebuilds Tool exchange without redoing completed Tool

Mechanical outcome: PASS.

Observed implementation fact:

- process loss is injected after the first Tool observation has become durable;
- after reopening in a fresh process, the completed Tool A is recovered from durable receipt/evidence;
- only still-pending Tool B performs a new Runtime execution;
- the reconstructed Provider-visible current-attempt exchange contains both Tool call identities and observations in the expected order.

Technology-neutral interpretation:

- process identity is not Run identity;
- settled and pending Invocations can be distinguished across recovery;
- recovery can reconstruct operational cognition/attribution without redispatching a settled external operation.

P1' pressure: strong `SUPPORT` for T1/T8/T9 and against R2 Process/Executor Identity.

## 6. D5 — missing Tool content authority blocks resume without new effect

Mechanical outcome: PASS.

Observed implementation fact:

- the Tool operation is terminal before process loss and its receipt survives;
- exact Tool observation content is intentionally unavailable under the tested privacy/retention authority;
- fresh-process `resume` fails closed because required continuation content cannot be reconstructed;
- the second Runtime performs **zero** new workspace executions.

Technology-neutral interpretation:

- historical Run/Invocation identity can remain known while continuation evidence is insufficient;
- continuation failure does not imply permission to redispatch the external operation;
- evidence/retention authority affects resumability without automatically rewriting identity.

P1' pressure: strong `SUPPORT` for the revised three-axis evaluator, especially `same lineage / non-resumable or insufficient evidence`.

## 7. D6 — concurrent successor writers cannot both become current

Mechanical outcome: PASS.

Observed implementation fact:

- two concurrent successors attempt to advance the same current WorkingSet revision;
- exactly one successor is admitted as current;
- the recovered head is one of the candidates and continuity integrity remains healthy.

Technology-neutral interpretation:

- one linear continuation point cannot silently admit two mutually divergent successors as equally current;
- an implementation mechanism may realize P1-G through revision/CAS/lease fencing, but P1-G does not depend on that particular mechanism.

P1' pressure: `SUPPORT` for continuation-topology exclusivity as a semantic requirement.

Limit: D6 does not test declared branch semantics; T14 remains conceptual.

## 8. Rival R6 after Round 2

R6 — “Run identity is necessarily implementation-defined and has no technology-neutral criterion” is **WEAKENED, NOT FULLY FALSIFIED**.

Why weakened:

The same research distinctions recur across several materially different implementation surfaces:

- Tool dispatch/receipt/reconciliation;
- Provider completion/recovery;
- fresh-process Tool-exchange reconstruction;
- cognition/WorkingSet successor fencing.

Across these mechanisms, process restart, persistence mechanism details and object types vary, yet the higher-level distinctions remain recognizable: settled vs pending Invocation, provenance-preserving transition, unsupported continuation, no silent redispatch, and unique linear successor.

Why not fully falsified:

All D1–D6 are still one Ordivon Harness implementation family. Round 2 does not establish cross-implementation invariance across independently designed Harnesses or non-LLM controllers.

## 9. Research interpretation

Round 2 materially supports the revised P1' architecture in scope:

1. **Recovery Projection Standing** is needed because integrity/currentness mechanisms reject invalid or unsupported successor states rather than relabeling them as legitimate new Runs.
2. **Run Identity** can survive process reconstruction and is not reducible to process lifetime.
3. **Continuation Standing** is separately evidence-sensitive: missing retained content can block resume while redispatch remains forbidden.
4. **Invocation frontier accounting** is operationally real: settled/pending/reconciled statuses determine what may safely happen next.
5. **Continuation topology** needs exclusivity/branch semantics above shared ancestry.

No result requires Harness to decide physical-effect truth. Harness consumes receipts/reconciliation/evidence and preserves the obligation not to invent what those external facts do not establish.

## 10. Foundation pressure

`NO_FOUNDATION_PRESSURE` remains the Round 2 classification.

No dogfood result requires a new Harness-native responsibility beyond HaF0–HaF61, and no frozen HaF claim is falsified. The evidence sharpens relations among existing Run identity, Invocation lineage, Context/evidence and ControlFlow distinctions.

## 11. Next step

Run Round 3 cross-owner boundary audit on P1' + Round 2 evidence, then close Campaign 1. Do not broaden execution dogfood unless the boundary audit exposes one concrete unresolved falsifier.
