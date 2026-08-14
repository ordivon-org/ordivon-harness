# AM — DeepSeek Harness Evolution Challenger

Verified against the primary public repository `deepseek-ai/deepseek-harness` on 2026-08-15. This document separates repository-visible evidence from external/social statistics that still require reproducible history analysis.

## Verified current facts

- The public repository reports 12,293 commits on `master`.
- The visible Aug. 13, 2026 history includes merged pull requests through `#2521`, including release `dsh-0.1.0-rc.3`.
- The README describes DeepSeek Harness as an open-source harness developed by DeepSeek AI, in developer preview, with compatibility-breaking changes expected during rapid iteration.
- The architecture is explicitly “everything is a plugin”, powered by Cordis. Model adapters, Tool registry, session log, and the agent loop itself are plugins and can be replaced from configuration.
- A running DSH is a plugin tree composed from ordered profile/bundle layers. Patches can replace or insert configuration rows.
- DSH still distinguishes durable from live semantics: `SessionEvent` records are durable facts; `agent/*` events carry a live Agent for in-flight work. The architecture requires model-visible content to be reconstructable from the session log.
- DSH defines capability seams in terms of Service Definition, Service Provider, and Consumer. Subagent providers may vary behind one interface.
- Visible history contains branches/merges named `codex/2503-english-onboarding-copy` and `codex/docs-publish-source-build`, showing Codex-named workflows in the repository. This does not by itself quantify how much of the codebase was agent-authored.

Primary references:

- https://github.com/deepseek-ai/deepseek-harness
- https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/architecture.md
- https://github.com/deepseek-ai/deepseek-harness/commits/master/
- https://github.com/cordiverse/cordis

## What DSH positively challenges in Ordivon

DSH demonstrates that a highly replaceable loop/model/tool/session composition is not merely theoretical. Loop implementation is a legitimate morphology coordinate, profiles are a legitimate composition/selection plane, and a plugin substrate can make experimental variation extremely cheap.

The architecture also validates an important AM distinction rather than refuting it: replaceability does not erase durable semantics. DSH keeps durable session events distinct from live Agent events and requires model-visible state to be replayable. Ordivon's owner-native receipts, UNKNOWN/reconciliation, WorkingSet provenance, Runtime Job/Attempt truth, and Host Task continuity play a stricter version of the same conservation role across more external-effect owners.

## Where Ordivon should not copy DSH mechanically

Cordis registrations can unwind when a plugin unloads, but an external Resource transfer, Message delivery, Entity migration, Runtime physical effect, or Provider dispatch cannot be reversed by unloading a plugin. Ordivon therefore cannot treat plugin disposer semantics as consequence rollback.

DSH's “no privileged core” architecture is optimized for in-process composability. AM2/AM5 showed that giving an arbitrary Python Loop implementation direct Provider/Tool access would make Ordivon's effect/recovery laws bypassable. Until those kernels are physically outside the candidate's authority, importing a global plugin runtime would expand the trusted computing base rather than merely improve composition.

## Evolution lesson

The useful lesson is not “copy Cordis”. It is:

```text
make variation cheap
while keeping conserved truth explicit
```

For Ordivon today this means:

```text
Attempt-bound morphology identity
+ Agent-owned profile selection
+ checkpoint/fresh-process replacement
+ owner-native relation continuity
+ independent candidate evaluation/promotion
```

DSH remains the strongest challenger for eventually reopening AM8 if a real workload demonstrates that restart/new-Attempt replacement is materially worse than live replacement.

## Not yet verified from primary reproducible history

The following externally circulated statistics are intentionally **not** treated as established facts here: exact 64-day zero-to-open-source span, contributor share such as 42.6%, median daily working span such as 15.6 hours, weekend/commit-silence distributions, and aggregate deleted-line/churn figures. GitHub's unauthenticated contributors page currently exposes only a loading shell, not the raw contributor series needed to reproduce those numbers.

If exact raw Git history becomes locally materializable, these should be recalculated from commit objects rather than copied from screenshots or social posts.
