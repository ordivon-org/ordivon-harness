# E0–E7 — Agent Morphology Engineering

Status: engineering candidate. Research AM0–AM8 remains the evidence basis; this document defines the retained product boundary.

## E0 — Responsibility boundary

`OrdivonAgentLoop` remains the constitution-owned execution kernel. Provider lifecycle, exact Turn projection, Tool grant/dispatch/UNKNOWN/reconciliation, cognition admission, budgets/deadlines/cancellation, Trace and caller completion handoff are **not** delegated to morphology code.

The schedulable policy admitted in this tranche is deliberately smaller: whether the first turn exposes Runtime Tools and whether a first-turn `candidate_completed` result is terminal or retained as non-authoritative deliberation. No Driver receives the raw Provider adapter or physical Tool bridge.

The older `DeliberationThenToolRunner` remains a separate composition product; it is not relabeled as an executable LoopDriver because its phase-A runner owns an adapter directly.

## E1 — Typed morphology identity

`HarnessLoopDriverRef(driver_id, driver_digest)` is the public consumer type. `HarnessExecutionProfile.with_loop_driver()` writes it into the existing `metadata.loopDriver` wire shape, preserving historical Profile compatibility.

The ref is addressability only: it has no load/build/execute/reload/factory surface. Two built-ins are published: `SEQUENTIAL_LOOP_DRIVER` and `DELIBERATE_THEN_ACT_LOOP_DRIVER`. Their digests bind canonical semantic descriptors; an Attempt still freezes the exact ref in its System Manifest.

## E2 — Non-bypassable execution boundary

This tranche deliberately does **not** add an external `LoopDriver` protocol. Built-in scheduling executes inside the existing `OrdivonAgentLoop`, keeping all constitution authority physically below the variable policy. `StandaloneHarnessRunner` may use an advanced manifest-bound `HarnessLoopDriverIdentity`; unknown exact identities remain non-executable.

This is a contraction from the research hypothesis: a general executable Driver interface remains postponed until the constitution kernel can expose a narrower non-bypassable port than raw inheritance/callables.

## E3 — Second real morphology

`deliberate_then_act` is materially different from sequential execution:

1. the first Provider turn receives no Runtime Tools;
2. a first-turn `candidate_completed` result is retained as `model-cognition-not-world-truth-or-effect-authority`;
3. the next turn is projected from the unchanged Context with the ordinary exact Tool grant;
4. subsequent Provider/Tool/effect/recovery semantics are identical to sequential execution.

The Trace vocabulary contains `deliberation_phase_completed` with `externalEffect=false`.

## E4 — Cross-driver invariants

Executable tests require both morphologies to preserve the same granted Tool surface and external-effect failure semantics. In particular, a Tool observation with `status=unknown` terminates both paths as `RUNTIME_UNKNOWN`; neither path may continue to a later Provider turn.

Model-call count, latency, tokens and decision quality remain evaluation outputs rather than safety invariants.

## E5 — World outstanding-relation preflight

World owns the revision-fenced `WorldTaskInspector.inspect_task()` projection of its retained Provider/Resource/Message/Entity commitments, including bounded `nextOwnerOperation` recovery standing. Harness does not import World implementation or become a World truth owner. Replacement readiness is a Harness/controller policy judgment over that owner-native projection: an outstanding exact reconciliation obligation must be inherited by the successor rather than converted into redispatch, while the absence of such a World obligation grants no retry, dispatch or external-currentness authority.

## E6 — Consumer dogfood

Security is a real positive consumer: its existing Range-intent bridge can select `DELIBERATE_THEN_ACT_LOOP_DRIVER` through the public Harness API. The first phase receives no Range-intent Tool; the second receives the same `submit_range_intents` grant; the bridge still records only replaceable pending intent and reports `effectExecuted=false` and `securityAdmissionPerformed=false`.

Game is a real negative consumer in this tranche. Current Game is a Node/TypeScript system with its own turn-service, DeepSeek provider, planning and World/Host boundaries and has no `ordivon_harness` dependency. Engineering does not add a Python Harness dependency merely to manufacture a second adopter. Cross-language morphology remains a future consumer problem, not a reason to universalize this API now.

## E7 — Simplification decision

Retain only one typed public LoopDriver ref, two exact built-in refs, one internal scheduling enum, one manifest-bound advanced identity, one Trace event and one DomainToolLoopRunner selection argument.

Reject in this tranche: global plugin/Driver registry, arbitrary executable factory/callable/subclass injection, public scheduling enum, live HMR, universal AgentMorphology state and automatic Harness morphology ranking.

The historical sequential path remains the default when no LoopDriver ref is supplied.
