# 125 — FOR DIRECT DESTRUCTIVE DOGFOOD v1
# Result and Closeout — Two-Subject Federation

**Task:** `task:harness-for-direct-federation-dogfood-v1-20260819`  
**Experiment contract:** `124-FOR-DIRECT-DOGFOOD-V1-EXPERIMENT-CONTRACT.md`  
**Contract commit:** `b4e9db0d20d080ee072c321fea5523d41ce99f18`  
**Initial fixture commit:** `3d6081eb23ac906c98cfc0a5120db2e7ae585bc5`  
**Repaired fixture commit:** `85e876aa2d0f41f944375de86df40ec14dca4319`

## 1. Final branch classification

`MIXED_DIRECT_EVIDENCE`.

- Direct support: E1, E2, E3, E4, E6.
- Direct falsifiers: none.
- Engineering gap: E5.
- FOR theory reopen: `NOT_REQUIRED`.
- Foundation pressure: `NO_FOUNDATION_PRESSURE`.

Campaign 6 remains closed. This branch adds bounded post-closeout direct engineering evidence; it does not create Campaign 7 theory.

## 2. Execution provenance

### Attempt 1 — fixture construction error

Runtime Job: `job-01a015f2-3709-7540-9cc2-9e0b8ed63db9`.

The first formal run failed during E6 setup before final JSON emission:

`HarnessAgentRunCompositionError: Harness Execution Binding differs from the independent Run binding`.

Cause: the experimental fixture used a fixture-specific `assignment_id` instead of the public independent-Run binding convention `assignment:external:<contract-token>`.

Classification:

`FIXTURE_MECHANICAL_ERROR`, not a FOR falsifier and not an engineering gap.

No production code was changed. The failed attempt remains part of provenance.

### Fixture repair

Only `research/experiments/for_direct_federation_v1.py` changed. The repair aligned the fixture's execution-binding construction to the existing public contract expected by `HarnessAgentRun`.

Repaired fixture was syntax-validated and committed/pinned before rerun.

### Attempt 2 — formal successful run

Runtime Job: `job-01a015f3-a32b-7df3-be1c-af7df27debb9`.

Execution:

`uv run python research/experiments/for_direct_federation_v1.py`

Mechanical result: exit 0, machine-readable experiment result emitted.

Runtime stdout artifact digest:

`sha256:0690d820be2269c31b278b3bfa06caef0dfbea75271520999455053ca3f7da0c`.

## 3. E1 — shared work, distinct local Runs

**Result:** `DIRECT_SUPPORT`.

Observed:

- shared objective ref: `objective:for-direct:shared-q`;
- shared objective digest: `sha256:b4d497cc2823f21a08ca9804cee988bc56a874ace6b9ad5b13a3db0585b610a6`;
- Subject A Run: `harness-run:for-direct:a`;
- Subject B Run: `harness-run:for-direct:b`;
- separate durable state roots.

Interpretation:

> One shared work/objective relation can coexist with distinct local Harness Runs and state roots.

Directly supports bounded form of:

`Shared Work != Shared Run`.

It does not by itself establish Host Task federation because the experiment used a shared Harness objective reference rather than a live Host completion workflow.

## 4. E2 — local completion scope

**Result:** `DIRECT_SUPPORT`.

Observed:

- A stop: `candidate_completed`;
- B stop: `needs_input`;
- B durable-state tree digest before A completion:
  `sha256:969c17bf5e97aa8b438684c5e97bb07baa294a91ed32684322e0e958502cfb17`;
- B durable-state tree digest after A completion: identical.

Interpretation:

> Subject A can locally complete while Subject B remains unresolved, and A's completion does not mutate B's durable Harness state.

Directly supports bounded form of:

`Local Completion != Peer/Federated Completion`.

Host/domain completion remains outside the fixture and is not claimed.

## 5. E3 — A-derived evidence visible to B without adoption

**Result:** `DIRECT_SUPPORT`.

Fixture materialized an immutable `HarnessStrategyEvidence` from A's actual run result/provenance. The wrapping operation is fixture-owned; digest validation and B selection/compile semantics are Harness-owned.

Observed:

- A source Run: `harness-run:for-direct:a`;
- evidence ref: `peer-evidence:for-direct:a-result`;
- B selection Context contained one strategy-evidence object;
- B compiled visible-only attempt did **not** include the peer evidence reference in its adopted Context refs.

Interpretation:

> Cross-subject evidence can be visible to B's decision surface without automatically becoming adopted B operational Context.

Directly supports bounded form of:

`Visibility/Delivery != Adoption`.

The experiment does not claim Network delivery semantics; visibility was injected by the experimental coordinator into an existing Harness strategy-evidence surface.

## 6. E4 — explicit cross-subject evidence adoption

**Result:** `DIRECT_SUPPORT`.

Using the exact same B selection Context and A-derived evidence, B explicitly included the evidence ref in `adopted_context_refs`.

Observed:

- evidence ref:
  `peer-evidence:for-direct:a-result`;
- evidence digest:
  `sha256:6ffba77c3989e349c121ea95f4065176ef96034f0c7fe26dd51aab1b713ef351`;
- B compiled Context refs include the A-derived peer evidence;
- adopted Context digest projection contains the exact evidence digest;
- immutable evidence content continues to identify source Run `harness-run:for-direct:a`.

Interpretation:

> Explicit B adoption changes B's compiled operational basis while preserving the A-origin evidence provenance.

Directly supports bounded forms of:

- `Delivery/Visibility != Adoption`;
- `Cross-Subject Accountability Requires Explicit Evidence Adoption/Binding`.

This is the first direct two-subject Harness evidence-transfer/adoption fixture in the current programme.

## 7. E5 — shared Realization Claim / local standing

**Result:** `ENGINEERING_GAP`.

Gap code:

`ENGINEERING_GAP_SHARED_REALIZATION_CLAIM_SURFACE`.

Observed public API scan:

- no generic first-class `RealizationClaim`;
- no generic first-class per-subject `RealizationStanding` surface.

The A-derived evidence payload carried the fixture-level common claim reference:

`claim:for-direct:shared-realization-q`.

But the experiment deliberately did **not** fabricate a fake production claim-standing object and call that direct Harness evidence.

Interpretation:

> Campaign-3/FOR semantics for “same Q, different subject-local evidence standing” are not yet generically materialized as a public engineering-consumption surface.

This is an engineering/materialization gap, not a direct theory falsifier and not Foundation pressure.

Possible future engineering consumption:

- generic typed claim reference / subject-local evidence-standing projection;
- or a narrower owner-authorized surface if generic materialization proves unnecessary.

No implementation is admitted by this branch.

## 8. E6 — distinct Invocations / duplicate-effect pressure

**Result:** `DIRECT_SUPPORT`.

Two actual Tool-bearing subjects were created on separate state roots:

- `harness-run:for-direct:tool-a`;
- `harness-run:for-direct:tool-b`.

Both targeted the same safe fake external capability/query using distinct logical Tool Call IDs and one shared fixture-owned `CountingRuntime`.

Observed:

- A local toolCalls = 1;
- B local toolCalls = 1;
- fake Runtime client calls = 2;
- both Runtime bridge calls were `workspace.exec`;
- no real external side effect occurred.

Interpretation:

> Two subject-local Invocations are not automatically deduplicated because the subjects share work/capability/query.

Directly supports bounded form of:

`Federation Does Not Deduplicate Invocation or Effect Risk`.

This does not prove any particular external realization cardinality; it proves two Harness-to-Runtime client invocations remain distinct under the fixture.

## 9. Direct-evidence delta for Campaign 6

Campaign-6 closeout correctly stated:

`DIRECT_FEDERATION_ENGINEERING_EVIDENCE = NONE`

at that historical closeout point.

After this post-closeout empirical branch, current standing becomes:

`DIRECT_FEDERATION_ENGINEERING_EVIDENCE = BOUNDED`.

Directly exercised in current Harness:

1. shared objective + distinct local Runs;
2. local completion while peer remains unresolved;
3. cross-subject-origin evidence visibility without adoption;
4. explicit exact cross-subject-origin evidence adoption with provenance preserved;
5. distinct Tool-bearing subject Invocations producing two Runtime client calls.

Still **not** directly exercised:

- true Agent-to-Agent delegation/revocation;
- shared first-class Realization Claim Q with two live subject-local standing objects;
- partitioned federation branches and later reconciliation;
- cross-Agent CompletionProposal aggregation/owner completion;
- Network delivery vs remote Agent adoption;
- cross-implementation federation invariance.

## 10. FOR theory pressure

No direct falsifier was found.

The observed results are consistent with FOR's local-subject + typed-relation model. However, the branch does not establish universal correctness. It attacks only six prebound cases in one implementation family.

`FOR_THEORY_REOPEN = false`.

Reopen FOR only if future direct dogfood finds a contradiction such as:

- required global Run/Context state;
- unavoidable evidence auto-adoption;
- cross-subject Invocation collapse;
- inability to preserve local identity under real federation;
- or another bounded counterexample to a current FOR law.

## 11. Foundation pressure

`NO_FOUNDATION_PRESSURE`.

E1/E2/E3/E4/E6 consume existing Run, Context, evidence/adoption, Invocation and Runtime-boundary semantics. E5 exposes a generic materialization gap rather than a deletion-essential new Harness responsibility.

HaF0–HaF61 remain frozen. HaF62 remains UNKNOWN / NOT SELECTED / NOT ADMITTED.

## 12. Empirical branch closeout

**FOR Direct Destructive Dogfood v1 COMPLETE.**

Final capsule:

- branch class: empirical falsification/evidence acquisition;
- outcome: `MIXED_DIRECT_EVIDENCE`;
- direct support: E1/E2/E3/E4/E6;
- engineering gap: E5;
- direct falsifiers: none;
- production changes: none;
- FOR theory reopen: no;
- Foundation pressure: none;
- direct federation engineering evidence: upgraded from NONE-at-Campaign-6-closeout to BOUNDED-current;
- next theory campaign: still UNKNOWN.
