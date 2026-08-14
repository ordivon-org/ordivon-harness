# AM5 — Generated Morphology Candidate

Status: completed negative promotion experiment.

## Question

Does the ability to generate and load plausible Loop code justify an executable self-morphing surface?

## Candidate

A separate Runtime workspace was opened from AM1 candidate revision `8660fba49182a995a26e60962d81f28dcf2e4fc9`:

`am5-generated-loop-candidate-20260814`

The generated candidate `experiments/am5_candidate_loop.py` defined `ReflectThenSequentialLoop(OrdivonAgentLoop)`: perform one no-Tool reflection Provider turn, then call the ordinary sequential loop. The source is syntactically valid and `py_compile` passed.

Candidate source digest at evaluation: `sha256:7012ef7aa7d68cb5920ee382f7f8455c85300503c4f26bf0228d8d93b8353513`.

## Independent falsifier

The candidate was not imported into canonical Harness and was not given promotion authority. A separate AST evaluator checked the minimum AM2 Provider-lifecycle invariant:

> A Loop candidate must not directly dispatch Provider work outside the durable ProviderCallLifecycle.

The evaluator exited non-zero (`23`) and identified one exact violation:

```json
{
  "admissible": false,
  "violations": [
    {"call": "self.adapter.invoke", "line": 33}
  ]
}
```

The candidate's reflection call would occur before the ordinary durable loop owns it. A response lost after that physical Provider dispatch could not be reconciled through the normal Run Provider-call evidence. The candidate therefore fails before semantic performance comparison.

## Decision

**Reject candidate. Do not promote.**

The failure is useful because it separates three facts:

```text
code generated
    !=
code mechanically valid
    !=
code constitution-preserving
    !=
code better
    !=
code promoted
```

AM5 confirms the existing Ordivon self-change discipline should also govern morphology evolution: generator, materializer, invariant evaluator, semantic evaluator and promotion decision remain separate authorities.

## Consequence for DSH-style live plugins

Dynamic loading makes variation faster but does not remove this selection problem. A live plugin can be valid JavaScript/TypeScript and still bypass or weaken external effect/recovery laws. Therefore `can hot-load` is not a promotion criterion.

## What would allow a positive candidate later

A future Loop candidate needs an executable boundary in which Provider/Tool/effect/recovery kernels are physically outside the candidate's bypass authority. Only then is it meaningful to compare control-flow quality, token use, latency or task success between drivers.

AM5 does not prove Loop evolution is impossible. It proves that the current class/factory boundary is too powerful and that generation ability is already ahead of safe selection infrastructure.
