# Security Policy

## Reporting a vulnerability

Do not open a public Issue, Discussion or pull request for a suspected vulnerability.

Use GitHub private vulnerability reporting:

- `https://github.com/zycxfyh/ordivon-harness/security/advisories/new`

Include the affected Harness, Host, Protocol and Runtime revisions; Provider adapter; reproduction steps; expected and observed authority boundaries; persisted-state impact; and whether credentials, prompts, source, Tool effects, Provider Calls or Runtime Jobs may be exposed.

The maintainer aims to acknowledge a complete report within three business days. Validation, remediation, release and disclosure timing depend on severity and the need to preserve migration, recovery or forensic evidence. Coordinate disclosure through the private advisory.

## Supported version

Only current `main` and the exact package/dependency graph currently used by the operator are supported. Historical receipts remain relevant only to the revisions they name. There are no LTS or backport branches.

## Trust boundary

Harness is a trusted-local Agent Run subsystem. It does not sandbox Provider processes, Runtime commands, repositories or domain systems.

- Host owns Task authority, Journal/CAS admission, revision fencing and outcome admission.
- Harness owns Assignment, Provider Call, Tool Step, Run Snapshot and completion-proposal semantics.
- Runtime owns physical execution and Artifact truth.
- Domain verifiers own semantic completion.

A model message, Provider session, Tool output or Runtime success cannot expand ToolGrant authority or prove Task completion.

## Provider boundary

Providers may receive bounded Task Context, prior messages, Tool definitions and retained Tool observations. Provider output is untrusted input until parsed, authority-checked and durably admitted.

DeepSeek API keys are loaded from private regular files. Codex and Hermes adapters may start local child processes and inherit only the environment deliberately supplied by their driver configuration. Hidden Provider sessions are disposable and are not durable continuity.

Mid-call Provider migration is unsupported. An ambiguous Provider delivery remains UNKNOWN and is not automatically repeated.

## Tool and Runtime boundary

ToolGrant limits the logical Tool surface; it is not a hostile-code sandbox. Runtime executes physical operations under its own trusted-local authority profile. Harness must persist intent and dispatch identity before an effectful Tool call and reconcile the original identity after response loss.

## Sensitive data

Host CAS and receipts may contain prompts, Context blocks, source-derived content, Tool arguments, model output, Runtime Job and Artifact references, provider/model identities, usage and failure details. Harness does not automatically redact secrets or personal data.

Read [`docs/DATA_AND_PRIVACY.md`](docs/DATA_AND_PRIVACY.md) before sharing state or evidence.

## Security process

Security is enforced through exact dependency pins, lockfile checks, strict object decoding, immutable CAS identities, revision fencing, ToolGrant filtering, bounded budgets and observations, private secret files, no blind redispatch, semantic-history Doctor, deterministic tests, dependency audit, secret scanning and CodeQL.

Passing checks are evidence for a bounded graph, not a security guarantee. Reassess the threat model when Provider, Tool, Host, Runtime, persistence or domain authority changes.
