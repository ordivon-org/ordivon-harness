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

`ordivon-host` does not import this package. Host owns generic Task, Journal, CAS, Kernel, the public `HostExtensionPort`, and Runtime client mechanics; Harness owns its event vocabulary, semantic history validation, handoff projection, durable Run state and Agent execution behavior.

## Verified boundary

The retained evidence proves:

- durable Task Attempt and Assignment identity before Provider or Runtime activity;
- Codex and Hermes provider-faithful lifecycle adapters;
- one first-party bare-model sequential loop;
- Assignment-scoped Tool authority and Runtime correlation;
- durable Trace, Tool Observation, Run receipt and completion verification;
- conservative UNKNOWN handling, safe read-only abandonment and retained effectful recovery evidence;
- Assignment-bound native Tool semantics and one pure Run disposition derivation;
- monotonic Run deadlines, cancellable Provider call handles and requested/effective model provenance;
- active socket cancellation for the default DeepSeek HTTP transport;
- durable native `workspace.exec` Intent → DispatchFence → Receipt → Observation with restart reconciliation by `clientRequestId`;
- nonterminal `cancel-requested` Receipts that can be superseded by one final reconciled Receipt;
- active-Tool-Step-first Run recovery before Workspace assessment;
- executable `needs-input` and prepared-effect Run resume;
- append-only Run-state deltas between bounded full checkpoints.

The current DispatchFence is a Host revision/Assignment/Intent fence retained in CAS and Runtime correlation evidence, with validation immediately before and after dispatch. Runtime does not independently authenticate it with a Host-issued MAC; it is therefore a practical stale-dispatch fence, not a cryptographic cross-service capability token.

Generic effectful continuation remains deliberately narrower than the visible Tool surface: durable `workspace.exec` is accepted, while durable `workspace.mutate` remains blocked until Runtime exposes a reconciliable mutation dispatch identity. Parallel Tools, subagents, automatic routing, persistent Provider sessions, a Harness daemon and a separate Harness database remain outside the accepted boundary.

## Development

Python 3.12 is required.

```bash
python3.12 -m venv .venv
. .venv/bin/activate
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
