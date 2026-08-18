# 147 — EVIDENCE INDEX TYPED INGESTION & CURRENTNESS REPAIR v1
# Prebound Acceptance / Falsifier Contract

**Selection authority:** Tournament 146.  
**Starting canonical:** `d6ba39047f68762ad793d70f78240be640430ace`.  
**Control task:** `task:harness-evidence-index-typed-ingestion-currentness-repair-v1-20260819`.

## 1. Goal

Repair the existing `evidence/index.json` + `scripts/check_evidence.py` contract so it can classify immutable research projections without rewriting their bytes, while preserving all legacy receipt revision/currentness rules.

## 2. Baseline-red

Current evidence gate is red:

- TS11 remains marked `verified` although later invalidating implementation paths changed;
- four evidence files are absent from the index;
- the checker assumes every evidence JSON embeds a legacy revision field.

The repair must make the existing gate green by improving revision binding, not by excluding files or weakening currentness.

## 3. Two explicit revision-binding modes

### Embedded (default)

Legacy entries omit `revisionBinding` or use `embedded`.

The evidence payload must carry the same implementation/source revision as the index, exactly as today.

### Index creation lineage

An immutable projection may explicitly use:

`revisionBinding = index-creation-lineage`.

For this mode the checker must prove:

1. index `implementationRevision` is a valid commit;
2. evidence file has exactly one Git add/creation commit in repository history;
3. bound revision is an ancestor of that creation commit;
4. no invalidating implementation path changes between bound revision and evidence creation;
5. current evidence bytes equal the bytes at that creation commit;
6. if the payload carries a recognized tested-revision hint (`implementationSourceRevision`, `implementationRevision`, `sourceRevision`, `prebindingRevision`, or `repairCommit`), any present valid 40-char hint used as implementation binding must not contradict the index.

The index does not become semantic truth owner; it supplies repository provenance/currentness binding for immutable evidence.

## 4. Required index updates

Demote:

- `harness.tool-surface.ts11-turn-working-set` from `verified` to `historical` at its unchanged `a57963c...` revision.

Add exactly:

### C3 owner capture

- claimId: `harness.research.campaign3-rich-effect-owner-capture-v1`
- file: `harness-campaign3-rich-effect-owner-v1-capture.json`
- status: `historical`
- implementationRevision: `786d64a7cfb21d52e9e541331c3db67a9edd4f29`
- revisionBinding: `index-creation-lineage`

### C3 validated result

- claimId: `harness.research.campaign3-rich-effect-owner-result-v1`
- file: `harness-campaign3-rich-effect-owner-v1-result.json`
- status: `historical`
- same bound revision `786d64...`
- revisionBinding: `index-creation-lineage`

### C5 provider-route result

- claimId: `harness.research.campaign5-provider-route-preservation-v1`
- file: `harness-campaign5-provider-route-preservation-v1-result.json`
- status: `historical`
- implementationRevision: `a1a61430047dfa0c43fb2f32d1d2529d57c19018`
- revisionBinding: `index-creation-lineage`

### Current no-Tool repair summary

- claimId: `harness.execution.current-no-tool-conclusion-control-repair-v1`
- file: `harness-current-no-tool-conclusion-control-repair-v1.json`
- status: `verified`
- implementationRevision: `8925fdba026cdef4f9d8969fae244ee3e5e46730`
- revisionBinding: `index-creation-lineage`

C3/C5 are implementation-bound historical evidence after the later no-Tool source repair; their scoped research standing remains in research closeouts. Repair 145 may be verified only while no later invalidating implementation change exists.

## 5. Frozen evidence bytes

The repair MUST NOT modify these exact files/digests:

- C3 capture: `5695253f4148536178e7e579624762d27af68f541632121e3dd507f1d2a1f698`
- C3 result: `bd251924d98b9cd25bb76fd0496bdfd51f485d86a878767ef45533a2aedc7c4d`
- C5 result: `0693df87e7541a5589ba865e17937b46e79fb2f25bb7175b3856cae682ff0aa1`
- repair 145 summary: `d455cc726e6356e4463a6c7463d9573d3d2730c88b78723fa362129159b7b4ae`

## 6. Focused falsifiers

Permanent focused tests must prove:

- all four entries exist with exact binding/status/revision;
- frozen file digests remain exact;
- TS11 is historical;
- correct index-creation-lineage bindings validate;
- a non-ancestor revision fails external binding;
- the complete evidence gate returns success after repair.

## 7. Legacy compatibility

All old entries without `revisionBinding` remain embedded-binding receipts and retain existing payload-vs-index revision checks.

Existing special receipt validations (A0/A1/C3 etc.) remain unchanged.

## 8. Verified currentness

`verified` entries still run the existing currentness invalidation against current implementation paths. The new external binding mode does not bypass or weaken that rule.

## 9. Scope ceiling

Allowed change surface:

- `scripts/check_evidence.py`;
- `evidence/index.json`;
- focused evidence-contract tests;
- current verification/authority docs only if needed to describe the two binding modes;
- research 147/148.

Not allowed:

- changing the four evidence JSON bytes;
- production `src/` changes;
- new database/registry/service;
- generic semantic-law registry;
- Campaign 7 or HaF62.

## 10. Acceptance

Classify `EVIDENCE_INDEX_TYPED_INGESTION_CURRENTNESS_REPAIR_ACCEPTED` only if:

- focused falsifiers green;
- `scripts/check_evidence.py` green;
- evidence/file set exact;
- legacy embedded binding unchanged;
- verified stale detection unchanged;
- four frozen digests unchanged;
- docs/dependency/public API/full tests remain healthy;
- no production source change.

A fresh typed frontier tournament is required after closeout.
