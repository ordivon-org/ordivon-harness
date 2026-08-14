# AM0 — Agent Morphology Census

Status: research candidate; evidence-bound to Harness `6639cf575eb006e8be2864037d9427b9913dd8a3`, World `da4eb2cafc7c33d0905140bceb7e7ceaef7330da`, Runtime `761bfe8dd7ca7c5e3e514891657c986eecb204e5`, Host `507589eb1ae602f788913c7a8fdfd7bad355fe6c`.

## Question

Which parts of an Ordivon Agent define stable identity/authority/continuity, and which parts are mutable morphology that may change without inventing a new truth owner or erasing already-existing consequences?

AM0 deliberately does **not** introduce a universal `AgentMorphology` object. The census is a derived research projection over owner-native facts.

## Cross-owner result

The strongest common kernel is not a loop implementation, model, context policy, Tool set, or process. It is a set of conservation laws around identity and consequences:

1. **Identity** — durable identities must not alias distinct work/effects/continuity.
2. **Authority** — capability/credential availability is not itself permission for every consequence.
3. **Provenance** — retained bytes/evidence must remain bound to the source/operation that produced them.
4. **Currentness** — historical success/capability never silently becomes current authority.
5. **Consequence fence** — planning is recomputable until an owner admits an exact consequence; after that point the identity must be durable before delivery.
6. **Receipt** — observed physical/provider outcomes are retained independently of semantic success.
7. **UNKNOWN** — ambiguous delivery/outcome is a first-class state and never authorizes blind redispatch.
8. **Recovery** — fresh processes restore proven state or fail closed; they do not invent continuity.
9. **Continuity** — Task/Run/Entity/work identities survive replaceable cognition and process instances through exact owner-native evidence.

These are candidate **constitution-level invariants**. Everything else remains morphology until a deletion falsifier proves otherwise.

## Morphology coordinate matrix

| Coordinate | Current owner | Current status | Same Entity may change it? | What must remain conserved | Deletion / boundary falsifier |
|---|---|---|---|---|---|
| model/provider model identity | Harness Run Contract / Strategy | already selectable between attempts | yes | exact attempt contract, Provider evidence, budgets | if model change requires rewriting prior Provider/Tool evidence, boundary is wrong |
| Provider adapter/transport | Harness + external transport owner | bound per Run; transport may vary pre-dispatch | yes, under exact binding/recovery | Provider request identity and ambiguous-delivery fence | if route/adapter change can turn UNKNOWN into retry permission, boundary is wrong |
| WorkingSet / durable cognition | Harness | Agent-owned transitions | yes | canonical history/provenance; source bytes/pins exact | if cognition change requires deleting history or changing prior receipts, boundary is wrong |
| caller interaction cognition | Harness | transient current interaction | yes/ephemeral | caller provenance and privacy authority | if interaction bytes become durable merely by observation, boundary is wrong |
| Tool surface | Harness Contract + owner Tool catalog/grant | exact Run/turn admission | yes across admitted attempts; not by mutating active authority | catalog/grant identity; per-effect authority | if new Tool can be used without exact current grant, boundary is wrong |
| Tool composition | Harness ToolProgram | mutable composition over existing admitted Tools | yes | every physical inner Tool call, budget, receipt, UNKNOWN | if composition becomes a second authority plane, delete it |
| Loop implementation | Harness `OrdivonAgentLoop` | privileged implementation fact today | **candidate morphology** | Run authority, cognition/effect evidence, current action surface | AM1: if two materially different loops cannot share the same conservation laws without weakening evidence, loop identity may be kernel-specific |
| loop topology/scheduling | Harness coordinator | sequential today | candidate morphology | exact action admission, Provider/Tool lifecycle, cancellation/recovery | if topology change changes effect semantics without owner-native receipt, boundary is wrong |
| internal sub-agent roles | Harness-level cognition mechanism if ephemeral | not a World Entity by default | yes | parent Run authority/evidence | if a sub-agent needs independent durable identity/authority/world relations, it crosses Entity threshold |
| independent persistent Agent/Entity | World/domain + Harness cognition | owner-native | no simple in-place change; requires continuity relation | entity identity, source departure/continuity/destination evidence | if destination-local authority is inferred from source continuity, boundary is wrong |
| World observation strategy | Agent/Harness using owner observations | recomputable planning | yes | source provenance/currentness | if historical observation silently grants current effect authority, boundary is wrong |
| World connection/path choice | Agent + owner-native path provider | recomputable before consequence admission | yes | current owner capability revalidation | if a selected path remains authoritative after owner drift without revalidation, boundary is wrong |
| World Resource transfer | World trajectory + source/destination owners | durable after preparation/consequence fence | plan may not be replaced while unknown | source egress, payload identity, destination receipt/not-committed proof | if retry occurs after UNKNOWN without exact not-committed proof, boundary is wrong |
| World Message delivery | World trajectory + source/destination owners | durable after preparation | plan may not be replaced while unknown | issuance/provenance/payload/destination receipt | if delivery implies destination belief/truth, boundary is wrong |
| World Entity migration | World trajectory + source/destination owners | identity/continuity trajectory | morphology may move; identity requires explicit continuity | entity identity, departure, continuity payload, destination materialization | if migration automatically imports destination Presence/capability/authority, boundary is wrong |
| Runtime execution target/profile | Runtime | exact Job/Attempt operation identity | yes across Jobs/Attempts | Job/Attempt/source/provider commitments and physical evidence | if target/profile changes under same admitted physical operation identity, boundary is wrong |
| Runtime process instance | Runtime/systemd/cgroup/Windows Job | explicitly replaceable/recoverable | yes | Job/Attempt identity and terminal evidence | if process death deletes work truth or causes speculative redispatch, boundary is wrong |
| Host cognition session/client | not continuity owner | replaceable | yes | Task revision/checkpoint/owner namespaces | if conversation/session identity is needed to recover Task meaning, Host boundary regressed |
| Host Task continuity | Host | durable semantic work identity | no arbitrary mutation | Journal/CAS revision, commitment, uncertainty, outcome | if cognition/process replacement rewrites Task history, boundary is wrong |

## Three change classes

### C1 — Cognition state change

Examples: WorkingSet transition, caller-ingress promotion, historical recall.

Same Entity and same execution constitution. No new World continuity event is required.

### C2 — Cognitive morphology change

Examples: model swap between attempts, future LoopDriver change, context strategy, internal ephemeral multi-agent coordination.

The Agent may remain the same Entity **iff** identity, authority, consequence and continuity invariants remain exact and the change does not create an independently acting persistent entity.

### C3 — Entity/relational topology change

Examples: persistent independently-authorized sub-agent, Entity migration between Worlds, creation/removal of an independently acting Entity with its own durable cognition and World relations.

This is not merely a Harness plugin change. It requires World/domain continuity semantics and destination-native authority/currentness.

## World-derived consequence fence

World current architecture supplies the strongest cross-owner cut:

```text
Observe → Query → Select        recomputable morphology/planning
                 │
                 ▼
        owner admits exact consequence
                 │
          DURABILITY FENCE
                 │
                 ▼
       Prepared / Dispatched / Bound
                 │
          Receipt | UNKNOWN
                 │
              Reconcile
```

This yields an AM law:

> Morphology may change aggressively before an admitted consequence. After an admitted consequence, replacement is allowed only if it preserves and reconciles the exact outstanding consequence identity; replacement never erases or reinterprets UNKNOWN.

## Runtime-derived physical law

Runtime confirms that process/execution machinery is not Agent identity. Jobs/Attempts/process trees are physical truth owners; ambiguous dispatch is not repeated; a process can vanish while durable work remains recoverable. Therefore same-process liveness is not a constitution-level requirement.

## Host-derived continuity law

Host explicitly treats cognition sessions and physical Runtime processes as replaceable dependencies. External-continuity checkpoints are semantic working claims, not copied Runtime/Git/domain truth. Therefore conversation/process/session identity cannot be promoted into Agent identity merely for convenience.

## Harness-derived cognition law

Harness already makes cognition, Tool composition, Provider Strategy and source-change candidates variable while retaining canonical history/effect evidence. The remaining privileged morphology candidate is `OrdivonAgentLoop` itself. AM1 should test the smallest admission-time LoopDriver identity seam before any live plugin runtime.

## Multi-Agent entity threshold candidate

A sub-agent remains internal morphology when all are true:

- no independent durable identity beyond the parent Run;
- no independent persistent WorkingSet/continuity requirement;
- no separately granted external consequence authority;
- no independently retained World relationships or migration/presence;
- its outputs are evidence/cognition consumed and admitted by the parent Agent/owner.

It crosses the World Entity threshold when independent identity + durable continuity + independently addressable World relation/authority become necessary. Merely prompting multiple personas or running multiple model calls is insufficient.

## AM0 retention decision

**Retain as research laws:** the nine constitution candidates, three change classes, consequence fence, and multi-Agent Entity threshold candidate.

**Do not create:** `AgentMorphology` database/object, global plugin registry, universal WorldInteraction, universal Agent/Entity ontology, or live loop mutation API.

**Advance to AM1:** make loop implementation identity explicit at immutable Run/Attempt composition and test whether it can vary while all retained owner-native invariants stay unchanged.
