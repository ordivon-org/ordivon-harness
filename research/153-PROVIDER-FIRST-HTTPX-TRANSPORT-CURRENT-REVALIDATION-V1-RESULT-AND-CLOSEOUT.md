# 153 — PROVIDER-FIRST HTTPX TRANSPORT CURRENT REVALIDATION v1
# Result and Closeout

**External pressure owner:** Ordivon Computing PF3.
**External source:** `research/provider-first-harness-transport-pf3.md`, digest `sha256:ed594e9f0dfaa3d125f320559e5fdc150d04863089a2a06be42ae8fc8fa86e4d`.
**Starting canonical:** `684333be5146d4f705a91edb396e83c6a1150e1f`.
**Scope owner:** Ordivon Harness DeepSeek physical transport only.
**Foundation effect:** none. No Campaign 7 or HaF62 is selected or admitted.

## 1. Classification

`PROVIDER_FIRST_HTTPX_TRANSPORT_OWNER_ADMISSION_ACCEPTED_IN_SCOPE`.

The external PF3 result has acquired a named current consumer: the production DeepSeek physical transport. Harness now delegates HTTP/TLS streaming mechanics to pinned `httpx==0.28.1` while retaining Provider request identity, exact request bytes, proxy admission, byte bounds, failure interpretation, retry authority, cancellation outcome and durable Provider lifecycle.

This is a bounded transport-mechanism admission. It is not a general Provider-First doctrine, a new Core foundation, a claim of live-provider equivalence, or evidence of an intelligence-level phase transition.

## 2. Why Tournament 152 could be reopened

Tournament 152 selected no speculative semantic branch. It explicitly allowed reopening for a new current production/release pressure.

The Computing PF3 claimant supplied exactly such pressure:

- a concrete current Harness consumer;
- an independently recovered source/result with explicit remaining admission gates;
- a mature external mechanism owner;
- a deletable hand-owned socket lifecycle;
- destructive localhost discriminators;
- an exact owner boundary that did not require a new semantic relation.

Therefore this work is an owner-consumption/currentness repair, not Campaign 7.

## 3. Recovered hypothesis and pre-existing falsifier

The recovered PF3 question was whether Harness could delegate low-level DeepSeek HTTP/TLS/stream/cancellation mechanics without changing its higher-level Provider and continuity semantics.

Historical PF3 had already rejected synchronous HTTPX: closing a synchronous client from another thread did not promptly interrupt a request waiting for response headers.

The surviving candidate was one `httpx.AsyncClient` request in an asyncio Task behind the existing synchronous Handle boundary.

Historical terminal evidence:

- final clean async ablation: `job-019ffc24-331c-7ad3-af43-b928abcdbe6d`;
- formatting-independent prototype complexity comparison: `job-019ffc24-e2de-7a30-b74e-8279ab4af360`;
- historical Harness workspace remained clean at `321ce5c006b6a28a9f44055688e66d0c3b6b8c09`.

Historical standing remained `QUALIFIED / NOT ADMITTED`.

## 4. Current destructive revalidation

### Exact candidate replay

Runtime Job `job-01a0344a-874f-7241-8221-c2bca6a64361` replayed the exact async candidate against current Harness source `684333b`.

It established:

- exact raw request bytes;
- forced `Accept-Encoding: identity`;
- 408/504 to TIMEOUT;
- 429/5xx to UNAVAILABLE;
- other 4xx to REJECTED;
- one physical request under error;
- response byte-bound rejection;
- pre-header cancellation in about 0.41 ms;
- body-phase cancellation in about 0.43 ms;
- timeout mapping without retry;
- clean async shutdown;
- no external network and no Provider credential.

### CONNECT and TLS boundary

Runtime Job `job-01a0344c-0996-7763-9626-47fa08a475d6` used a local synthetic CONNECT proxy and generated certificate.

It established:

- exact proxy tunnel authority;
- proxy did not observe Provider Authorization or body;
- target observed exact Authorization, body and path;
- TLS hostname verification remained end-to-end to the target;
- no external network and no Provider credential.

### External mechanism contract

The selected implementation is consistent with the official HTTPX contract:

- async raw streaming uses `aiter_raw()`;
- stream context owns response closure;
- HTTPS through an HTTP proxy uses CONNECT tunnelling before target TLS;
- `trust_env=False` disables inherited environment configuration;
- retries require explicit transport configuration;
- connect/read/write/pool timeouts are explicit.

Primary references:

- https://www.python-httpx.org/async/
- https://www.python-httpx.org/advanced/proxies/
- https://www.python-httpx.org/environment_variables/
- https://www.python-httpx.org/advanced/transports/
- https://www.python-httpx.org/advanced/timeouts/
- https://www.python-httpx.org/api/

These references constrain mechanism interpretation; they do not substitute for Harness-owned behavioral tests.

## 5. Production materialization

The public `HttpClientDeepSeekTransport` name remains stable, but its implementation now uses one `_HttpxPostHandle` per call.

The admitted boundary is:

- Harness constructs and owns exact request bytes and headers;
- validated direct or loopback-CONNECT routing is passed explicitly;
- `trust_env=False`, redirects disabled, HTTP/1.1 enabled and HTTP/2 disabled;
- response bytes are consumed through undecoded `aiter_raw()` under the existing bound;
- no retry transport is configured;
- cancellation schedules `Task.cancel()` thread-safely;
- pending tasks and async generators are drained before event-loop closure;
- Harness retains status/failure/dispatch-safety mapping.

The old `_response_socket`, `_shutdown_socket` and `_HttpClientPostHandle` implementation is deleted. There is no compatibility twin.

Direct runtime dependency authority now contains exactly:

- the exact Ordivon Protocol revision;
- `httpx==0.28.1`;
- bounded `jsonschema`.

The complete transitive graph is pinned by `uv.lock` and mirrored in `requirements-audit.txt`. Host remains absent.

## 6. Permanent discriminators

New current wire tests cover:

- exact request and raw-response representation;
- identity encoding even when a caller supplies another value;
- status mapping and one-request behavior;
- response bounds;
- redirects not followed;
- prompt pre-header and body-phase cancellation;
- timeout mapping without retry;
- inherited environment proxies ignored;
- malformed URL and non-HTTPS proxied target rejected before dispatch.

The existing loopback-proxy suite now checks the HTTPX configuration/request boundary rather than monkeypatching `http.client` internals.

Integrated focused acceptance:

- Runtime Job `job-01a03453-8571-7e83-81c2-27c93a91d20e`;
- dependency contract passed;
- 24 transport/provider/loop tests passed;
- `git diff --check` passed.

Ruff:

- Runtime Job `job-01a03453-d40c-7ba1-9bef-9ce81a8875d7`;
- source, tests and scripts passed.

The first full run, `job-01a0345a-e6eb-7860-875c-c72f1dc6b08c`, exposed an old two-dependency assertion. After repairing that duplicate projection, `job-01a0345d-6ad4-7f80-916d-572dba1e8d4f` passed all 538 unit tests with 3 skips, then exposed the same stale assumption in the isolated wheel checker. The repaired isolated wheel gate passed in `job-01a0345f-f823-72d2-8877-1d4ea2e6ea99`, including installation, Host absence, public API and 14 CLI commands.

Final exact-tree local acceptance is recorded outside this self-referential closeout in the publishing Task receipt.

## 7. Complexity correction

Integrated production complexity was recomputed against exact starting revision `684333b` in Runtime Job `job-01a03458-c340-7822-bf70-a05333d95c79`.

| Metric | old socket block | integrated HTTPX block | ratio |
|---|---:|---:|---:|
| normalized LOC | 163 | 139 | 0.8528 |
| AST nodes | 1311 | 1157 | 0.8825 |
| normalized chars | 8266 | 7260 | 0.8783 |
| physical LOC | 245 | 218 | 0.8898 |

The integrated mechanism deletes roughly 11–15% of the measured production transport block, not the 32–44% suggested by the minimal current replay and not the 39–54% suggested by the historical prototype.

This difference is substantive. Production integration must retain richer Harness error detail, dispatch-safety semantics, proxy validation, synchronous compatibility and cleanup boundaries that the prototype did not fully represent. Tests and the dependency graph also expand.

Therefore:

`prototype compression != integrated system compression`.

The admission is earned by ownership transfer plus preserved behavior and modest production deletion. A large complexity or phase-transition claim is rejected.

## 8. Research-to-capability conversion

The conversion chain is now concrete:

`external PF3 result -> named DeepSeek transport consumer -> production implementation -> permanent wire/cancellation tests -> isolated wheel -> current owner admission`.

Observed capability change:

- Harness no longer owns socket extraction/shutdown mechanics;
- cancellation is expressed through the async task abstraction;
- HTTP/TLS behavior is delegated to a mature library under explicit configuration;
- exact Harness Provider authority remains unchanged.

Observed cost:

- one new pinned direct dependency and its transitive graph;
- more supply-chain and update currentness;
- new wire-level and packaging guards;
- two stale duplicate dependency projections had to be repaired.

This is capability conversion because a named behavior and engineering surface changed. It is not yet evidence of improved live-provider outcomes or user-visible model quality.

## 9. Explicit non-results

This closeout does not establish:

- a general rule that mature libraries always reduce total system complexity;
- OpenAI SDK admission;
- live DeepSeek correctness or performance improvement;
- universal proxy compatibility;
- HTTP/2 equivalence;
- automatic retries;
- a new Provider identity or durable lifecycle;
- a new Agent affordance;
- a finite-intelligence phase transition;
- Campaign 7, HaF62 or a Core revision.

A separately authorized live-provider test is needed only if a provider-specific unknown later appears. Current localhost, CONNECT/TLS and repository acceptance leave no known transport-mechanism blocker.

## 10. PPD lesson

The useful result is not merely “replace `http.client` with HTTPX.”

The pressure sequence was:

1. recover an external claimant without treating it as current standing;
2. preserve its synchronous falsifier;
3. replay the exact async mechanism against current source;
4. close the previously missing CONNECT/TLS discriminator;
5. materialize it in the named owner;
6. let full acceptance reveal duplicate currentness authorities;
7. recompute complexity after integration;
8. lower the claim when production evidence contradicted prototype leverage.

The decisive correction is:

`high-leverage hypothesis -> current destructive test -> bounded owner admission or rejection`.

PF3 earns bounded owner admission. Its large phase-transition interpretation does not.

## 11. Closeout

**PROVIDER-FIRST HTTPX TRANSPORT CURRENT REVALIDATION v1 COMPLETE.**

- external result: consumed;
- named consumer: production DeepSeek transport;
- old socket lifecycle: deleted;
- transport semantics: preserved in current tests;
- loopback CONNECT/TLS boundary: directly tested;
- dependency/wheel projections: current;
- complexity claim: corrected downward;
- live-provider consequence: not claimed;
- next Harness branch: UNKNOWN / NONE SELECTED.
