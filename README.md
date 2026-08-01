# Ordivon Harness

Ordivon Harness owns replaceable Agent execution lifecycles above the thin `ordivon-host` continuity kernel.

It contains three deliberately distinct concerns:

```text
Host Harness extension
  TaskAttempt / Assignment / Run / Recovery / Completion

Provider-faithful adapters
  Codex App Server / Hermes ACP

First-party bare-model execution
  bounded sequential model–Tool loop / DeepSeek adapter / Runtime Tool bridge
```

The dependency is one-way:

```text
ordivon-harness → ordivon-host → ordivon-protocol
```

`ordivon-host` does not import this package. Host owns generic Task, Journal, CAS, Kernel and Runtime client mechanics; Harness owns its event vocabulary, semantic history validation, handoff projection and Agent execution behavior.

## Verified boundary

The retained evidence proves:

- durable Task Attempt and Assignment identity before Provider or Runtime activity;
- Codex and Hermes provider-faithful lifecycle adapters;
- one first-party bare-model sequential loop;
- Assignment-scoped Tool authority and Runtime correlation;
- durable Trace, Tool Observation, Run receipt and completion verification;
- conservative UNKNOWN handling, safe read-only abandonment and retained effectful recovery evidence;
- Assignment-bound native Tool semantics and one pure Run disposition derivation;
- monotonic Run deadlines, cancellation propagation and requested/effective model provenance;
- durable native `workspace.exec` Intent → Receipt → Observation with restart reconciliation by `clientRequestId`;
- bounded pause snapshots for input, approval and prepared effect dispatch.

Generic effectful continuation remains deliberately narrower than the visible Tool surface: durable `workspace.exec` is accepted, while durable `workspace.mutate` remains blocked until Runtime exposes a reconciliable mutation dispatch identity. Parallel Tools, subagents, routing, persistent Provider sessions, a Harness daemon and a separate Harness database remain outside the accepted boundary.

## Development

```bash
python -m pip install -e .
python -m unittest discover -s tests
ruff check src tests scripts
python -m compileall -q src tests scripts
```

Harness semantic history can be checked separately from the Host core doctor:

```bash
ordivon-harness --state-root /path/to/host-state doctor
```

See `ARCHITECTURE.md`, `docs/ORDIVON_HARNESS_OH1_OH5_CLOSEOUT.md` and `docs/ORDIVON_HARNESS_P0_P1_CLOSEOUT.md`.
