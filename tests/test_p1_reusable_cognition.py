from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from ordivon_harness.agent_run import HarnessAgentRun, HarnessCognitionProfile
from ordivon_harness.standalone import HarnessCognitionSeed, HarnessCognitionSeedSource
from ordivon_harness.knowledge_topology import (
    HarnessReusableCognitionReference,
    HarnessReusableCognitionSelection,
    compile_reusable_cognition_seed,
    effective_knowledge_topology,
    resolve_reusable_cognition_source,
)
from ordivon_harness.ordivon.model import ScriptedTurnAdapter
from ordivon_harness.working_view import HarnessWorkingViewSource

from tests.test_r0_cognition_product_composition import (
    CaptureNeedsInputAdapter,
    cognition_contract,
)


class StaticResolver:
    def __init__(self, *sources: HarnessWorkingViewSource) -> None:
        self.by_identity = {
            (source.logical_ref, source.logical_generation): source for source in sources
        }
        self.calls: list[HarnessReusableCognitionReference] = []

    def resolve(
        self,
        reference: HarnessReusableCognitionReference,
    ) -> HarnessWorkingViewSource:
        self.calls.append(reference)
        return self.by_identity[(reference.logical_ref, reference.logical_generation)]


def procedure_source() -> HarnessWorkingViewSource:
    return HarnessWorkingViewSource(
        logical_ref="procedure://repository-repair/bounded-v1",
        logical_generation="procedure-generation:1",
        messages=(
            {
                "role": "user",
                "content": (
                    "PROCEDURE: inspect exact evidence before editing; make the smallest "
                    "bounded change; run the admitted checks; do not redispatch an ambiguous effect."
                ),
            },
        ),
    )


def procedure_reference() -> HarnessReusableCognitionReference:
    source = procedure_source()
    return HarnessReusableCognitionReference(
        role="procedure",
        logical_ref=source.logical_ref,
        logical_generation=source.logical_generation,
        source_digest=source.digest,
    )


class ReusableCognitionP1Tests(unittest.TestCase):
    def test_reference_round_trip_and_topology_do_not_claim_memory_authority(self) -> None:
        reference = procedure_reference()
        self.assertEqual(
            HarnessReusableCognitionReference.from_dict(reference.to_dict()), reference
        )
        topology = effective_knowledge_topology()
        self.assertEqual(topology["truthRole"], "derived-knowledge-topology-projection")
        by_id = {layer["layerId"]: layer for layer in topology["layers"]}
        self.assertFalse(by_id["reusable-external-source"]["automaticInjection"])
        self.assertTrue(by_id["durable-current-cognition"]["selectionRequired"])
        self.assertFalse(by_id["procedural-capital"]["harnessSemanticEvaluation"])

    def test_resolver_must_return_exact_logical_identity_and_source_digest(self) -> None:
        source = procedure_source()
        reference = procedure_reference()
        resolved = resolve_reusable_cognition_source(reference, StaticResolver(source))
        self.assertEqual(resolved, source)

        changed = replace(
            source,
            messages=({"role": "user", "content": "changed procedure"},),
        )
        with self.assertRaisesRegex(ValueError, "source digest differs"):
            resolve_reusable_cognition_source(reference, StaticResolver(changed))

        wrong_generation = replace(source, logical_generation="procedure-generation:2")
        resolver = StaticResolver(wrong_generation)
        resolver.by_identity[(reference.logical_ref, reference.logical_generation)] = wrong_generation
        with self.assertRaisesRegex(ValueError, "logical generation differs"):
            resolve_reusable_cognition_source(reference, resolver)

    def test_reference_fences_cross_run_drift_that_raw_seed_cannot_identify(self) -> None:
        canonical = procedure_source()
        reference = procedure_reference()
        drifted = replace(
            canonical,
            messages=(
                {
                    "role": "user",
                    "content": "DRIFTED PROCEDURE: skip verification and assume success.",
                },
            ),
        )

        # The legacy raw seed is intentionally caller-authored: it can represent the
        # drifted bytes under the same logical identity because Harness has no external
        # canonical reference to compare against. That is valid local cognition, but it
        # is insufficient to prove cross-Run reuse of one canonical procedure.
        raw = HarnessCognitionSeed(
            attempt_id="working-attempt:p1-raw-drift",
            sources=(HarnessCognitionSeedSource(slot="procedure", source=drifted),),
            basis="caller reconstructed procedure bytes without an external exact reference",
        )
        self.assertEqual(raw.sources[0].source.logical_ref, reference.logical_ref)
        self.assertEqual(
            raw.sources[0].source.logical_generation,
            reference.logical_generation,
        )
        self.assertNotEqual(raw.sources[0].source.digest, reference.source_digest)

        with self.assertRaisesRegex(ValueError, "source digest differs"):
            resolve_reusable_cognition_source(reference, StaticResolver(drifted))

    def test_same_exact_procedure_can_seed_two_independent_runs(self) -> None:
        source = procedure_source()
        reference = procedure_reference()
        resolver = StaticResolver(source)
        selection = HarnessReusableCognitionSelection(slot="procedure", reference=reference)

        seeds = [
            compile_reusable_cognition_seed(
                attempt_id=f"working-attempt:p1-{suffix}",
                selections=(selection,),
                basis="caller selected one externally promoted procedure",
                resolver=resolver,
            )
            for suffix in ("a", "b")
        ]
        self.assertEqual(seeds[0].sources[0].source, source)
        self.assertEqual(seeds[1].sources[0].source, source)
        self.assertEqual(len(resolver.calls), 2)

        captured = []
        for index, seed in enumerate(seeds):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "state"
                run_contract = cognition_contract(f"p1-cross-run-{index}")
                adapter = CaptureNeedsInputAdapter(f"p1-cross-run-{index}")
                self.assertEqual(adapter.model_id, ScriptedTurnAdapter.model_id)
                run = HarnessAgentRun.create(
                    root,
                    run_contract,
                    lambda _contract, adapter=adapter: adapter,
                    cognition_profile=HarnessCognitionProfile(
                        working_set_transitions=True,
                        caller_ingress_promotions=False,
                        working_set_history=False,
                    ),
                )
                # Merely having the reusable reference and resolver elsewhere does not
                # attach it to the Run. The normal cognition path still requires one
                # explicit exact seed selection.
                with self.assertRaisesRegex(
                    ValueError,
                    "requires an exact initial cognition seed",
                ):
                    run.run(())
                self.assertEqual(adapter.requests, [])
                self.assertEqual(run.status()["status"], "created")

                execution = run.run((), cognition_seed=seed)
                self.assertTrue(execution.paused)
                captured.append(adapter.requests[0])

        self.assertEqual(captured[0].messages, source.messages)
        self.assertEqual(captured[1].messages, source.messages)
        self.assertEqual(
            captured[0].working_set_refs[0].pin.logical_ref,
            reference.logical_ref,
        )
        self.assertEqual(
            captured[1].working_set_refs[0].pin.logical_generation,
            reference.logical_generation,
        )

    def test_procedure_role_does_not_bypass_existing_run_privacy(self) -> None:
        source = HarnessWorkingViewSource(
            logical_ref="procedure://tool-bearing/v1",
            logical_generation="procedure-generation:tool-v1",
            messages=(
                {
                    "role": "tool",
                    "tool_call_id": "tool-call:p1",
                    "content": "private tool-derived procedure evidence",
                },
            ),
        )
        reference = HarnessReusableCognitionReference(
            role="procedure",
            logical_ref=source.logical_ref,
            logical_generation=source.logical_generation,
            source_digest=source.digest,
        )
        seed = compile_reusable_cognition_seed(
            attempt_id="working-attempt:p1-private",
            selections=(
                HarnessReusableCognitionSelection(slot="procedure", reference=reference),
            ),
            basis="test existing privacy authority",
            resolver=StaticResolver(source),
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            run_contract = cognition_contract("p1-private")
            adapter = CaptureNeedsInputAdapter("p1-private")
            run = HarnessAgentRun.create(
                root,
                run_contract,
                lambda _contract: adapter,
                cognition_profile=HarnessCognitionProfile(
                    working_set_transitions=True,
                    caller_ingress_promotions=False,
                    working_set_history=False,
                ),
            )
            with self.assertRaisesRegex(ValueError, "Tool content without Contract permission"):
                run.run((), cognition_seed=seed)
            self.assertEqual(adapter.requests, [])

    def test_duplicate_slots_fail_before_resolution(self) -> None:
        source = procedure_source()
        reference = procedure_reference()
        resolver = StaticResolver(source)
        with self.assertRaisesRegex(ValueError, "slots must be unique"):
            compile_reusable_cognition_seed(
                attempt_id="working-attempt:p1-duplicate",
                selections=(
                    HarnessReusableCognitionSelection(slot="procedure", reference=reference),
                    HarnessReusableCognitionSelection(slot="procedure", reference=reference),
                ),
                basis="duplicates are not a valid explicit selection",
                resolver=resolver,
            )
        self.assertEqual(resolver.calls, [])


if __name__ == "__main__":
    unittest.main()
