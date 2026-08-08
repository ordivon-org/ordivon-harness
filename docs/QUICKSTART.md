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

Create a caller-authored `HarnessRunContract` JSON. The CLI does not invent Objective, Context, caller identity, Tool grant, budget or completion authority. The recommended API is closed over the values required for basic Contract authoring:

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

`max_tool_calls=0` is valid for a no-Tool Run. Capability comes from the Tool catalog/grant bound by the Contract; a positive Tool budget never grants a Tool by itself.

```bash
ordivon-harness --state-root /var/lib/ordivon/harness \
  run RUN_CONTRACT.json --message 'Start the bounded Run'

ordivon-harness --state-root /var/lib/ordivon/harness status HARNESS_RUN_ID
ordivon-harness --state-root /var/lib/ordivon/harness inspect HARNESS_RUN_ID
```

For the built-in DeepSeek profile, the Contract must bind the canonical no-Tool catalog/grant and the configured DeepSeek Adapter/model. The current adapter reserves a conservative request-token upper bound equal to the serialized Provider request bytes plus its 8,192-token completion ceiling. A small Contract such as `max_total_tokens=4_096` can therefore be rejected safely before the first Provider dispatch; `16_384` is a practical starting bound for a small no-Tool Run, not a universal required value.

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
