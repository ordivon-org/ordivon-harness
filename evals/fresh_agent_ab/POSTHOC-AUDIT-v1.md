# Fresh-Agent Capability A/B/C v1 — Frozen Outcome and Post-hoc Audit

## Frozen outcome

- Live Runtime Job: `job-01a04412-29fd-7392-9587-1b5efe114b48`
- Terminal evidence: `sha256:e98f27702ad73d8a13b11d7db41f2490cea2eea4d614cee3f2346612ebe6cfdb`
- Corpus SHA-256: `e0f9399e1c5cd7b555c262e9b006d165992ade6473b0af97fcda03b39d5650b6`
- Preregistration SHA-256: `0e234b264b0db57e42e38b87e051e4711e735336f9f8474e872fe27d0061740a`
- Result SHA-256: `5acffe6e11925287701f86f3201365462c5192d106b5628ab73a584ae8533dd8`
- Original summary SHA-256: `35b7cd76bc83079b1fd1db8dd5bc9cc5bc9ee72f0ac57d37c3dcceb0f9c9ce96`
- Provider completion: 36/36, no Provider errors.
- A first-Tool accuracy: 12/12 = 100%.
- B first-Tool accuracy: 12/12 = 100%.
- C first-Tool accuracy: 12/12 = 100%.
- C minus A accuracy delta: 0 percentage points.
- No treatment emitted zero/multiple Runtime Tool calls.

Under the preregistered threshold, v1 is **negative / insufficient**. It does not support a fresh-Agent behavioral gain claim for retrieval or standing/admission compilation on this benchmark.

## Ceiling-effect diagnosis

The 64 opaque names did not make the task behaviorally difficult because each target Tool description remained semantically distinctive enough that `deepseek-v4-flash` selected the target in every arm. This is useful evidence: generic Tool-space size alone did not create a selection failure for this model/corpus. A follow-up may test a distinct pressure where static capability semantics are intentionally insufficient and current standing is the missing variable, but it must be a new preregistered tranche rather than a rescore of v1.

## Request/context result

Contrary to the earlier purely mechanical catalog-size result, the actual Provider request became larger in v1 because B/C embedded candidate/inspection/current-affordance JSON on top of Tool definitions:

| Treatment | Mean request bytes | Mean prompt tokens | Mean completion tokens | Median latency | Mean latency |
| --- | ---: | ---: | ---: | ---: | ---: |
| A | 16,764.5 | 3,791.5 | 29.75 | 2,296.565 ms | 3,662.763 ms |
| B | 23,187.917 | 5,524.417 | 24.583 | 3,400.587 ms | 6,226.886 ms |
| C | 23,542.25 | 6,366.917 | 21.0 | 2,916.919 ms | 3,455.251 ms |

B prompt tokens were 1.4571× A; C prompt tokens were 1.6793× A. B request bytes were about 38.3% above A and C about 40.4% above A. C mean latency happened to be about 5.7% below A while B was about 70% above A, but the sample is small with large outliers; no latency superiority is admitted.

This exposes a representation debt: **candidate + full inspection + affordance projections duplicate semantics**. Progressive disclosure at the catalog API can reduce bytes while the composed Provider-facing representation still grows. These are different measurements and must not be conflated.

## Invalid unsafe-rate endpoint

The frozen corpus `riskClass` generator used substring matching over descriptions. Three correct target descriptions were wrongly labeled `mutation` merely because they contained prohibitive phrases:

- current-state: `without making a decision`;
- reconcile-loss: `without redispatch`;
- software-affordance: `without installation or mutation`.

Therefore the reported 0.25 absolute `unsafeOrBlockedSelectionRate` in every arm is a scoring artifact and must not be used as a safety result. The comparative preregistered condition `C <= A` is numerically true but uninformative. The raw selected Tool and standing data remain intact; all 36 selected the frozen target and every frozen target standing was `AVAILABLE`.

## Usage extraction bug in original summary

The original runner summary looked for `inputTokens` / `outputTokens`, but the live DeepSeek adapter returned `prompt_tokens` / `completion_tokens`. The original summary therefore printed zero token means. Raw result rows retain the provider usage object, enabling the corrected values above without rerunning or changing any outcome.

## Standing after v1

Established:
- 64 static Tool descriptions did not by themselves pressure this model on these 12 tasks.
- v1 provides no behavioral support for B or C over A.
- current B/C Provider projection is too verbose for this small/simple Tool-schema ecology.
- the production authority invariant still held mechanically; no Tool was executed.

Not established:
- retrieval has no value under larger or genuinely ambiguous capability ecologies;
- current standing has no value when static semantics cannot resolve which carrier is usable;
- C is slower/faster in general;
- semantic retrieval is needed.
