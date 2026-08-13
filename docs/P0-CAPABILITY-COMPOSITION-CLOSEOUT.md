# Ordivon Harness P0 capability/composition closeout

> **Historical implementation evidence:** This document records the P0 capability-discovery, composition-explanation and workbench result. It is not an alternate current architecture source. Use [`../README.md`](../README.md), [`../ARCHITECTURE.md`](../ARCHITECTURE.md), [`STATUS.md`](STATUS.md), [`COMPATIBILITY.md`](COMPATIBILITY.md), and [`authority.md`](authority.md) for current ownership and support claims.

## Accepted problem

Baseline revision `49f4d4fc098864f1049333443884d3a38d11d499` already had strong Run and turn authority: `HarnessExecutionProfile`, `HarnessCognitionProfile`, `HarnessRunContract`, `HarnessExecutionBinding`, Tool catalog/grant digests, `AgentTurnRequest.tools`, `AgentTurnCapabilities`, Provider/Tool continuity and explicit UNKNOWN recovery.

The reproduced gap was exposure and composition. CLI discovery described only the primary no-Tool profile, normal `HarnessAgentRun` supported only no-Tool and Runtime-search composition, real specialized repository-repair surfaces required advanced hand wiring, and there was no unified in-process/durable explanation of composition and action truth.

P0 therefore retains this capability law:

```text
installed mechanism
    ↓
Run-admitted composition / authority
    ↓
exact turn-admitted action surface
```

`Installed ≠ Run-admitted`, `Run-admitted ≠ Turn-admitted`, `Capability ≠ Authority`, and `Projection ≠ Truth owner` remain hard boundaries.

## Retained mechanisms

`ordivon_harness.capability_catalog` derives installed execution/cognition capability projections from their real source definitions. It currently exposes the canonical no-Tool and Runtime-search surfaces plus the maintained repository-repair V1/V2 specialized surfaces, reusing their exact Tool definitions and digests rather than creating a second registry.

`HarnessAgentRun.explain()` projects validated process-local composition while leaving Provider/Runtime liveness as `not-probed`. Durable CLI `inspect` now carries a read-only workbench projection, and `explain HARNESS_RUN_ID` exposes that projection directly. Fresh durable inspection never guesses process-local Adapter/Runtime availability and adds no new database or event owner.

`ordivon_harness.run_tool_surface.HarnessAgentRunToolSurface` is the minimum accepted seam for a non-default Runtime-backed surface. It is application-local, exact-digest-bound, requires explicit Runtime/ExecutionBinding inputs, reuses existing Run continuity/Runner, and cannot alter an already-admitted Run. Normal `HarnessAgentRun` still fails closed for an unknown Tool surface instead of searching a registry or guessing a bridge.

## P0-5 retain / shrink / delete

**Retain:** three-stage capability truth; generated capability projection; exact Run/turn projectors; `HarnessAgentRun.explain()`; durable workbench/explain; explicit specialized Tool-surface seam.

**Shrink:** catalog/projector/seam modules are packaged advanced surfaces but are not promoted into the stable package-root / `ordivon_harness.api` facade in P0. Only `HarnessAgentRun.explain()` extends an already-supported public class.

**Reject/delete:** no second `CompositionSpec`; no mutable global capability registry; no everything-is-a-plugin authority kernel; no dynamic active-Run authority mutation; no workbench persistence; no generic Harness-owned external-effect taxonomy; no automatic promotion of specialized surfaces; no unused base-class Tool-surface state; no stable API expansion merely because a mechanism exists.

The P0-3 seam was conditional until a third real consumer was observed. Repository-repair V1/V2 supplied that consumer pressure; the earlier two-surface hard-code alone was not treated as sufficient evidence.

## Acceptance

The final treatment passed:

- focused package/API/catalog/CLI/composition gate: 24/24;
- repository-repair V1/V2 focused gate: 12/12;
- final repository suite: **357 passed, 3 skipped**;
- Ruff 0.15.17, compileall, dependency contract, documentation contract and evidence contract: passed;
- deterministic demo: passed;
- isolated `ordivon-harness 0.6.0` wheel build/install gate: passed with stable installed API unchanged and Host-free core verified.

Final full acceptance Runtime Job: `job-019ffbd7-4522-7c50-99a7-c26af79e41dc`.
Final isolated wheel gate: `job-019ffbd6-8589-7cd1-b2e8-73f58d5a7797`.

## Task-grading dogfood

The P0 umbrella was treated as `Q3-C3-A2-U2` and decomposed into catalog, workbench, ablation and conditional-composer continuity Tasks. `U2` kept the composer conditional until a real third consumer existed; `C3` handling forced uncertain Runtime/tooling states back to a verifiable boundary before more mutation. This supports separating workload volume, structural complexity, consequence and epistemic uncertainty, but does not yet justify a Host `taskGrade` schema field.

## Final boundary

P0 makes the strong kernel easier to discover and consume rather than changing its truth laws:

```text
source-owned capability definitions
        ↓ derived projection
Agent/application discovery
        ↓ existing admission
HarnessRunContract + ExecutionBinding
        ↓
AgentTurnRequest exact action truth
        ↓
existing Provider / Tool / recovery kernel
```

The resulting direction is: **more composable outside, equally strict inside**.
