---
schema_version: 1
id: harness.quickstart
title: Harness Quick Start
type: guide
profile: engineering
lifecycle: active
source_role: canonical
visibility: public
owners:
  - ordivon-harness
audience:
  - builder
  - operator
  - agent
updated: 2026-08-08
summary: Minimal path from a clean checkout to deterministic verification, operator inspection and live read-only acceptance.
evidence_status: verified
readiness: READY
applies_to:
  - ordivon-harness
related:
  - harness.start
  - harness.status
  - harness.compatibility
  - harness.operations
---
# Quick start

## Set up

```bash
uv sync
uvx ruff==0.15.17 check src tests scripts
uv run python -m unittest discover -s tests -v
```

Build and verify the exact installable artifact:

```bash
rm -rf dist
uv build --wheel --out-dir dist
python scripts/check_wheel.py "$(find dist -maxdepth 1 -type f -name '*.whl' -print -quit)"
```

The wheel contains one runtime dependency: the exact Ordivon Protocol pin. It does not install Host or expose a Host extra.

## Initialize independent state

```bash
ordivon-harness --state-root /var/lib/ordivon/harness store-init
ordivon-harness capabilities
```

## Run

For one exact attempt, create a caller-authored `HarnessRunContract` JSON. When the caller wants to delegate the goal/resource envelope without prescribing every execution step, use `HarnessExecutionMandate` plus a separately selected `HarnessExecutionStrategy`, then compile one exact attempt with `compile_harness_attempt()`. The current library deliberately does not choose Strategy automatically.

```python
from ordivon_harness.api import (
    HarnessExecutionMandate,
    HarnessExecutionProfile,
    HarnessExecutionStrategy,
    RunBudget,
    compile_harness_attempt,
)

# Mandate: objective/context/completion + allowed profiles + aggregate envelope.
mandate = HarnessExecutionMandate(..., max_total_tokens=65_536, max_wall_time_ms=120_000)

# Strategy: Agent/application-selected profile and exact parameters for attempt 1.
strategy = HarnessExecutionStrategy(
    mandate_digest=mandate.digest,
    attempt_index=1,
    profile_id=profile.profile_id,
    budget=RunBudget(...).to_contract_dict(),
    provider_options={"maxOutputTokens": 2048},
    rationale="Selected from current evidence and capability needs.",
)
compiled = compile_harness_attempt(
    mandate, profile, strategy,
    harness_run_id="harness-run:example:1",
    harness_implementation_id="ordivon-harness@...",
    created_at_ms=...,
)
contract = compiled.contract
```

A later attempt must also supply `HarnessMandateConsumption` reconstructed from prior Run receipts. The compiler reserves only the remaining total-token/wall-time envelope. Prior Receipt/observation references may be adopted through `strategy.adopted_context_refs`; the compiler binds those refs into the next Run Contract. This allows evidence to survive a failed or budget-exhausted strategy attempt without turning one Run into an unlimited workflow.

For direct execution, create a caller-authored `HarnessRunContract` JSON. The CLI does not invent Objective, Context, caller identity, Tool grant, budget or completion authority. The recommended API is closed over the values required for basic Contract authoring:

```python
from anc_canonical import canonical_digest
from ordivon_harness.api import HarnessBoundReference, HarnessRunContract, RunBudget

def bound_ref(reference_id: str, kind: str, claim: object) -> HarnessBoundReference:
    return HarnessBoundReference(reference_id, kind, canonical_digest(claim))

budget = RunBudget(
    max_model_calls=2,
    max_tool_calls=0,
    max_observation_bytes=65_536,
    max_wall_time_ms=90_000,
    max_total_tokens=16_384,
)
# Supply caller/objective/context/provider/system identities, the capability digests
# reported by `ordivon-harness capabilities`, and `budget.to_contract_dict()` to
# HarnessRunContract. Persist `contract.to_dict()` as RUN_CONTRACT.json.
```

`max_tool_calls=0` is valid for a no-Tool Run. Capability comes from the Tool
catalog/grant bound by the Contract; a positive Tool budget never grants a Tool by
itself. `max_tool_corrections` bounds only model-correctable Tool-call rejection;
`max_conclusion_corrections` independently bounds caller/domain conclusion-gate
rejection. Older schema-v1 Contracts that omit `maxConclusionCorrections` remain
readable with the historical default of 3.

```bash
ordivon-harness --state-root /var/lib/ordivon/harness \
  run RUN_CONTRACT.json --message 'Start the bounded Run'

ordivon-harness --state-root /var/lib/ordivon/harness status HARNESS_RUN_ID
ordivon-harness --state-root /var/lib/ordivon/harness inspect HARNESS_RUN_ID
ordivon-harness --state-root /var/lib/ordivon/harness explain HARNESS_RUN_ID
```

`capabilities` returns the package-derived `ordivon_harness.capability_catalog.effective_capability_catalog()`. Its execution surfaces are installed mechanisms, not grants. The same advanced module exposes `project_run_capabilities()` for exact Contract-bound capability facts and `project_turn_capabilities()` for only the Tool/native actions already admitted on one `AgentTurnRequest`. Installed → Run-admitted → turn-admitted is an explicit authority boundary.

For the built-in DeepSeek profile, the Contract must bind the canonical no-Tool catalog/grant and the configured DeepSeek Adapter/model. The current adapter reserves a conservative request-token upper bound equal to the serialized Provider request bytes plus its 8,192-token completion ceiling. A small Contract such as `max_total_tokens=4_096` can therefore be rejected safely before the first Provider dispatch; `16_384` is a practical starting bound for a small no-Tool Run, not a universal required value.

### Supported Python Agent Run surface

For normal Python execution, use `HarnessAgentRun` rather than composing the SQLite Store, Continuity, Provider bridge and `StandaloneHarnessRunner` yourself. The caller still owns the exact Contract and Provider choice; Harness passes the persisted Contract to the caller-supplied Adapter factory before execution. On reopen/resume, Harness mechanically reconstructs Continuity and the exact Snapshot-bound Provider source.

```python
from ordivon_harness.api import HarnessAgentRun, DeepSeekTurnAdapter

run = HarnessAgentRun.create(
    "/var/lib/ordivon/harness",
    contract,
    lambda exact_contract: DeepSeekTurnAdapter(
        settings, completion_contract=exact_contract.completion_contract
    ),
)
execution = run.run(({"role": "user", "content": "Start the bounded Run"},))

run = HarnessAgentRun.open(
    "/var/lib/ordivon/harness",
    contract.harness_run_id,
    lambda exact_contract: DeepSeekTurnAdapter(
        settings, completion_contract=exact_contract.completion_contract
    ),
)
execution = run.resume(
    additional_messages=({"role": "user", "content": "Additional caller input"},)
)
```

The Adapter factory is caller policy, not Harness policy. Static composition is admitted before durable Run creation: unsupported Tool/cognition/Runtime-binding combinations fail before the factory when the Adapter is irrelevant, and Adapter/model/structured-completion mismatches fail after the factory returns but before `harness.run-created`. This preflight does not probe Provider or Runtime liveness.

For Agent-owned durable cognition, the same surface accepts `HarnessCognitionProfile` plus an exact caller-authored `HarnessCognitionSeed`. Build seed sources with `HarnessCognitionSource`/`HarnessCognitionSeedSource`; Harness does not discover, rank or summarize them.

A Tool-bearing application supplies a `HarnessRuntimeClient` through the Python API instead of the primary CLI. `call_tool()` is only the success-shape Protocol. The caller must also translate its transport and Runtime rejection failures into `HarnessRuntimeClientError` / `HarnessRuntimeToolRejected` with a `HarnessRuntimeErrorDetail`. In particular, a Runtime rejection with `commit_state` `not_started` or `not_committed` remains model-correctable; passing an unrelated client exception through unchanged loses that recovery meaning and is treated as a Harness failure. The recommended API also exports `HarnessExecutionBinding`, `HarnessRuntimeReference`, and the independent search catalog/grant digests required by the current `SQLiteHarnessRuntimeBridge`.

When a caller needs a typed semantic result instead of free-form summary text, bind the result shape into the existing completion authority:

```python
from ordivon_harness.api import (
    DeepSeekTurnAdapter,
    HarnessRunContract,
    decode_structured_completion_result,
)

completion_contract = {
    "mode": "structured-result-v1",
    "resultKind": "my-domain-result",
    "resultSchema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {"choice": {"type": "string", "enum": ["a", "b"]}},
        "required": ["choice"],
    },
}
contract = HarnessRunContract(..., completion_contract=completion_contract, ...)
adapter = DeepSeekTurnAdapter(
    settings, completion_contract=contract.completion_contract
)
# after the Run, with a non-null conclusion:
value = decode_structured_completion_result(contract, execution.loop_result.conclusion)
```

A candidate-completed Run may still carry explicit unresolved unknowns in
`unresolved_unknowns`; that means the bounded Run produced its candidate while
honestly reporting facts that remain unknown. The caller/domain, not Harness,
decides whether those unknowns block acceptance, justify another strategy, or are
irrelevant. Harness-owned execution stops such as `no_progress` do not synthesize
an Agent conclusion; inspect the stop code/detail and resume state instead. This
keeps a caller-bound structured completion result distinct from Harness execution
disposition.

The exact completion Contract is part of `HarnessRunContract.digest`. `StandaloneHarnessRunner` fails closed if a `structured-result-v1` Contract is paired with an Adapter that was not bound to the same completion Contract. DeepSeek receives the caller schema as the `submit_run_conclusion.result` Tool schema, and Harness stores the canonical result JSON in the existing conclusion summary representation, so this adds no second durable result store or Host-specific result type. **Caller/domain verification remains mandatory**: `decode_structured_completion_result` is a codec, not semantic admission.

## Pause and resume

```bash
ordivon-harness --state-root /var/lib/ordivon/harness \
  resume HARNESS_RUN_ID --message 'Additional caller input'
```

## Recovery

```bash
ordivon-harness --state-root /var/lib/ordivon/harness recover HARNESS_RUN_ID
```

Recovery is evidence-driven. A dispatched Provider or Tool operation with an ambiguous physical outcome is not blindly repeated.

## Python API

Use `ordivon_harness.api` for normal applications and `ordivon_harness.core` for advanced persistence/continuity composition. `ordivon_harness.host_external_adapter` is an explicit, Host-free integration helper when a higher-level Host wants to call an independent Harness Run.
