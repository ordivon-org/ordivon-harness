# 148 — EVIDENCE INDEX TYPED INGESTION & CURRENTNESS REPAIR v1
# Result and Closeout

**Task:** `task:harness-evidence-index-typed-ingestion-currentness-repair-v1-20260819`  
**Selection authority:** Tournament 146.  
**Prebound contract/tests:** `bda3b082db92655fe25096b4ed00cb50c684f695`.  
**Implementation/currentness repair:** `d2d2e02d78708bfcf58471adc09f67f07cd29f25`.  
**Compatibility strengthening:** `bc55c547fde9691e5f27c40f64caf3c2e20fc6c1`.  
**Starting canonical:** `d6ba39047f68762ad793d70f78240be640430ace`.

## 1. Classification

`EVIDENCE_INDEX_TYPED_INGESTION_CURRENTNESS_REPAIR_ACCEPTED`.

The existing Harness evidence/file correspondence + revision/currentness gate now supports two explicit provenance-binding modes without creating a second semantic registry and without rewriting frozen evidence bytes.

No production `src/` file changed.

## 2. Baseline-red

The branch froze `research/147-EVIDENCE-INDEX-TYPED-INGESTION-CURRENTNESS-REPAIR-V1-CONTRACT.md` and `tests/test_evidence_index_typed_ingestion.py` before checker/index modification.

Prebind commit:

`bda3b082db92655fe25096b4ed00cb50c684f695`.

Frozen baseline-red Runtime Job:

`job-01a01688-afc3-7811-b9b1-9b144175047b`.

Observed:

- 4 focused tests;
- 2 failures;
- 2 errors;
- missing projection entries;
- missing external-binding helper;
- TS11 still `verified`;
- complete evidence gate still red.

This exactly reproduced the prebound currentness/ingestion failure.

## 3. Repair shape

Only the existing evidence contract was evolved:

- `scripts/check_evidence.py`;
- `evidence/index.json`;
- `docs/VERIFICATION.md`;
- `docs/authority.md`.

The permanent focused test was already frozen by 147. After the core repair commit, compatibility coverage was strengthened in `bc55c547fde9691e5f27c40f64caf3c2e20fc6c1` by factoring the unchanged legacy embedded-revision check into a directly testable helper and adding two falsifiers that prove legacy exact binding plus verified-currentness invalidation remain intact. This did not widen the production or evidence-authority surface.

No Harness runtime/provider/loop/product source changed.

## 4. Revision binding modes

### Embedded — legacy/default

Old entries continue to omit `revisionBinding` and retain the existing behavior:

- evidence payload must itself carry `implementationSourceRevision`, `implementationRevision`, or `sourceRevision`;
- that revision must equal the index revision;
- receipt-specific integrity/acceptance checks remain unchanged;
- `verified` currentness still fails after later invalidating implementation changes.

No legacy receipt was migrated to the new mode merely for uniformity.

### Index creation lineage — explicit opt-in

An immutable research projection/result may explicitly declare:

`revisionBinding = index-creation-lineage`.

The checker now requires:

1. exactly one Git creation/add commit for the evidence file;
2. index-bound implementation revision is an ancestor of that creation commit;
3. no invalidating implementation path changed from the bound revision through evidence creation;
4. current evidence bytes equal the exact bytes at the creation commit;
5. recognized embedded tested-revision hints, when present, agree with the index;
6. `verified` entries still pass the same later-currentness invalidation from the bound revision to current HEAD.

This is repository provenance/currentness binding, not semantic truth ownership.

## 5. TS11 stale-currentness repair

The checker had correctly rejected:

`harness.tool-surface.ts11-turn-working-set`

because the entry remained `verified` at:

`a57963c476d366aea0d73d96cddd223f3bd5dbaf`

after later invalidating changes in current implementation paths.

The repair did **not** weaken the checker or re-certify TS11. It demoted the entry to:

`historical`.

Its historical receipt/provenance remains retained.

## 6. Typed ingestion of four newer immutable evidence objects

### Campaign-3 owner-fact capture

- claim: `harness.research.campaign3-rich-effect-owner-capture-v1`;
- file: `harness-campaign3-rich-effect-owner-v1-capture.json`;
- bound revision: `786d64a7cfb21d52e9e541331c3db67a9edd4f29`;
- binding: `index-creation-lineage`;
- index status: `historical`.

### Campaign-3 validated result

- claim: `harness.research.campaign3-rich-effect-owner-result-v1`;
- file: `harness-campaign3-rich-effect-owner-v1-result.json`;
- same bound revision `786d64...`;
- binding: `index-creation-lineage`;
- index status: `historical`.

### Campaign-5 provider-route result

- claim: `harness.research.campaign5-provider-route-preservation-v1`;
- file: `harness-campaign5-provider-route-preservation-v1-result.json`;
- bound revision: `a1a61430047dfa0c43fb2f32d1d2529d57c19018`;
- binding: `index-creation-lineage`;
- index status: `historical`.

### Current no-Tool conclusion/control repair summary

- claim: `harness.execution.current-no-tool-conclusion-control-repair-v1`;
- file: `harness-current-no-tool-conclusion-control-repair-v1.json`;
- bound revision: `8925fdba026cdef4f9d8969fae244ee3e5e46730`;
- binding: `index-creation-lineage`;
- index status: `verified`.

The repair summary remains `verified` because no later invalidating implementation path has changed after its bound repair revision.

## 7. Historical index status does not erase bounded research standing

C3/C5 are `historical` in `evidence/index.json` because the index's `verified` role means current whole-implementation certification against the configured implementation paths. The later no-Tool Loop repair changed current implementation after those evidence revisions.

This does **not** rewrite or revoke the bounded semantic standing owned by research closeouts 139 and 142.

Therefore:

`EvidenceIndexHistorical != ResearchResultSuperseded`.

The two systems carry different truth roles:

- evidence index: repository provenance + implementation-currentness classification;
- research closeout: bounded interpreted research standing/currentness.

This is typed redundancy rather than conflict.

## 8. Frozen evidence bytes preserved

Exact SHA-256 before and after repair remained identical:

- C3 capture: `5695253f4148536178e7e579624762d27af68f541632121e3dd507f1d2a1f698`;
- C3 result: `bd251924d98b9cd25bb76fd0496bdfd51f485d86a878767ef45533a2aedc7c4d`;
- C5 result: `0693df87e7541a5589ba865e17937b46e79fb2f25bb7175b3856cae682ff0aa1`;
- repair 145 summary: `d455cc726e6356e4463a6c7463d9573d3d2730c88b78723fa362129159b7b4ae`.

Post-repair digest audit Runtime Job:

`job-01a0168d-709e-7fe2-8993-8d79ea455c94`.

No evidence byte rewriting occurred.

## 9. Focused acceptance

Initial post-repair focused Runtime Job:

`job-01a01689-e6c9-7c82-9d66-6e9491500c6f`.

Result: 4/4 passed.

After compatibility strengthening `bc55c547...`, final focused Runtime Job:

`job-01a01692-913d-7d32-a17f-821505a193e9`.

Result:

- **6 tests**;
- **6 passed**;
- Ruff passed;
- evidence contract valid;
- documentation contract valid;
- dependency contract valid.

The final six permanent falsifiers directly prove:

- exact four projection entries/status/revisions/binding modes;
- exact four frozen SHA-256 values;
- TS11 historical demotion;
- correct external binding accepted;
- non-ancestor binding rejected;
- legacy embedded revision binding remains exact and rejects revision drift;
- verified-currentness still rejects stale TS11 while accepting the current repair revision;
- complete evidence contract green.

## 10. Legacy evidence and repository gates

Runtime Job:

`job-01a0168b-3308-7e82-9a49-3e754187e4d0`.

Passed:

- `git diff --check`;
- evidence contract;
- documentation contract;
- dependency contract;
- focused typed-ingestion tests;
- existing repository-repair evidence receipt tests;
- public API tests.

15 tests in that focused compatibility group passed.

Ruff Runtime Job:

`job-01a0168b-4e93-7491-8476-a1cca6e5ee8c`.

Result:

`All checks passed!`

Final evidence/docs/dependency gate Runtime Job:

`job-01a0168d-ac38-73c3-968d-e9f01a633a8c`.

All gates passed.

## 11. Full deterministic acceptance

An intermediate full acceptance before the two explicit legacy/currentness strengthening tests ran in Runtime Job:

`job-01a0168b-614d-7c33-ae06-6d4303791dc3`.

It passed 448 tests with 3 skipped and also reported `harness core without host: passed`.

The **final** full acceptance after strengthening commit `bc55c547...` ran in Runtime Job:

`job-01a0168e-ff0f-7eb3-9557-4cfc37b5755a`.

Observed:

- **450 tests**;
- **OK**;
- **3 skipped**;
- 100.223 seconds for the test suite;
- Job exited 0.

The pre-branch suite had 444 tests. The final increase to 450 is exactly the six permanent evidence-contract tests now carried by the current suite.

## 12. Why a generic semantic-retention registry was not added

Tournament 146 explicitly evaluated that option and rejected it.

Repair 145 already restored its semantic falsifiers as normal permanent tests. A new registry mapping research laws to required test names/counts would create another semantic/currentness authority and could still pass after tests were weakened or made vacuous.

The evidence-index problem was different and concrete: an existing release gate was already red because its revision-binding schema had not evolved with newer immutable evidence shapes.

Therefore this repair follows:

`repair the existing owner before creating a second owner`.

## 13. Current evidence contract standing

Current `scripts/check_evidence.py` output after repair:

- historical entries: 70;
- verified entries: 1;
- contract: valid.

The sole currently verified repository evidence entry is the post-contraction no-Tool conclusion/control repair summary. This is intentionally conservative.

## 14. Additional release-currentness pressure discovered

An extra wheel smoke was run beyond the minimum 147 acceptance contract. Runtime Job `job-01a01690-c408-70e3-b44c-0ea797d4ef69` successfully built the wheel, but `scripts/check_wheel.py` rejected the isolated installation with `installed API/version differs`.

Runtime Job `job-01a01691-219b-7850-9fad-ac6d807fcc06` isolated the exact mismatch: the actual public API has 73 entries while the wheel checker expects 69. The checker is missing four already-public Claim Standing exports and has no stale extra member:

- `OperationalClaimEvidenceRole`;
- `OperationalClaimRef`;
- `OperationalClaimStandingView`;
- `project_operational_claim_standing_view`.

This pressure predates and is independent of the Evidence Index repair. Branch 147/148 changes no production `src/`, `pyproject.toml`, or `scripts/check_wheel.py`, while these Claim Standing exports were already public before starting canonical `d6ba390...`.

Therefore this wheel failure is **not** an Evidence Index repair falsifier and was not repaired out of scope. It becomes explicit direct release-currentness pressure for the required post-closeout typed frontier tournament.

## 15. Foundation / campaign pressure

`NO_FOUNDATION_PRESSURE`.

No Harness semantic Foundation changed. No Campaign reopened. No Campaign 7 was selected. HaF0–HaF61 remain frozen; HaF62 remains UNKNOWN / NOT SELECTED / NOT ADMITTED.

## 16. Closeout

**EVIDENCE INDEX TYPED INGESTION & CURRENTNESS REPAIR v1 COMPLETE.**

- legacy embedded receipt binding: preserved;
- explicit immutable projection binding: added;
- verified-currentness invalidation: preserved;
- TS11 stale verified state: corrected to historical;
- four newer evidence files: indexed;
- frozen evidence bytes: unchanged;
- evidence/file set correspondence: exact;
- production `src/` changes: none;
- full suite: 450 OK, 3 skipped;
- separate wheel/public-API checker currentness gap: OPEN and explicitly out of scope here;
- next Harness frontier: UNKNOWN pending fresh typed tournament.
