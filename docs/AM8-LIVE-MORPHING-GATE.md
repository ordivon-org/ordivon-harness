# AM8 — Live Morphing Gate

Status: gate closed; same-process live Loop replacement is not admitted.

## Question

After AM0–AM7, is there reproduced Ordivon evidence that checkpoint/fresh-process/new-Attempt morphology replacement is insufficient, such that same-process hot replacement is required?

## Evidence reviewed

The retained Ordivon path already supports replacement at stronger fault boundaries than plugin unload/reload:

- Harness restores Provider-call and Tool exchange state across process loss without speculative redispatch.
- Harness WorkingSet/caller-ingress cognition is reconstructable according to exact privacy authority.
- Strategy selection can choose a different exact execution profile for a successor Attempt from prior receipt evidence.
- AM3 demonstrated complete controller/process replacement while Resource, Message and Entity consequence identity survives and UNKNOWN remains fenced.
- AM4 demonstrated that clean replacement is blocked by unresolved reconciliation obligation, not by process identity; pre-dispatch prepared commitments and terminal receipts survive replacement.
- Host Task continuity is explicitly independent of cognition session/process identity.

AM5 also showed the principal risk of a broad live plugin boundary: a syntactically valid alternate loop can dispatch a Provider call outside durable ProviderCallLifecycle. Faster loading does not solve constitution preservation.

## DSH challenger

DeepSeek Harness deliberately chooses a different optimization point: Cordis makes model adapters, tool registry, session log and agent loop plugins; plugin registrations unwind on unload and the agent loop is replaceable from configuration. DSH also retains durable Session events separately from live Agent extension points. This validates that highly dynamic loop composition is useful in another architecture, but it does not establish that Ordivon requires same-process replacement.

The convergent part is more important than the mechanism difference:

```text
DSH durable SessionEvent log     Ordivon owner-native durable evidence
DSH live agent/* extension       Ordivon replaceable cognition/control
DSH plugin composition           Ordivon exact Attempt composition
```

Both separate durable facts from replaceable live behavior. Ordivon currently gets that separation without requiring plugin-memory continuity.

## Gate criteria

Same-process live morphology may be reconsidered only if a future experiment reproduces at least one of these failures under checkpoint/new-Attempt replacement:

1. **latency discontinuity** — restart/recompose latency makes an otherwise valid workload fail a caller-owned deadline while live replacement succeeds;
2. **non-reconstructable ephemeral state** — valuable state cannot be represented as cognition/evidence without violating ownership/privacy, yet can be safely preserved across live replacement;
3. **active interactive continuity** — a real product requires replacing control policy inside one active interaction where ending the Attempt is observably unacceptable;
4. **resource discontinuity** — process replacement necessarily destroys an owner-native external capability/session that cannot be durably rebound or reconciled;
5. **measured performance advantage** — independent evaluation shows live replacement materially improves outcome/cost/latency and all constitution invariants remain mechanically non-bypassable.

Merely being able to implement hot reload, or another harness using it, does not satisfy the gate.

## Decision

**Reject live morphing for the current canonical architecture.**

Retain:

- LoopDriver identity as an exact Attempt morphology fact;
- Agent-owned successor-Attempt morphology selection;
- checkpoint/fresh-process replacement;
- owner-native relation continuity and reconciliation fences;
- future ability to reopen this gate from evidence.

Do not add:

- Cordis-style global plugin runtime;
- arbitrary executable Loop factory;
- live install/uninstall/HMR API;
- plugin disposer semantics as a substitute for external consequence reconciliation.

This is not a permanent prohibition. It is an evidence threshold: the cheaper and already-proven replacement mechanism remains canonical until it fails a real workload.
