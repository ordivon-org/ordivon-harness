from __future__ import annotations

import unittest

from anc_canonical import canonical_digest

from ordivon_harness.ordivon.cognition_admission import (
    CognitionAdmissionKernel,
    CognitionSurfaceUnavailable,
)
from ordivon_harness.working_view import (
    AgentCallerIngressPromotionProposal,
    AgentWorkingSetTransitionProposal,
    HarnessWorkingSetPin,
    HarnessWorkingSetSpec,
)


def pin(slot: str, suffix: str) -> HarnessWorkingSetPin:
    return HarnessWorkingSetPin(
        slot=slot,
        logical_ref=f"source://r2/{suffix}",
        logical_generation=f"generation:{suffix}",
        resolved_digest=canonical_digest({"r2": suffix}),
    )


def committed(attempt: str, *pins: HarnessWorkingSetPin) -> HarnessWorkingSetSpec:
    return HarnessWorkingSetSpec.initial(attempt, pins=tuple(pins)).commit("fixture")


class TransitionHandler:
    def __init__(self, current: HarnessWorkingSetSpec, successor: HarnessWorkingSetSpec) -> None:
        self.current = current
        self.successor = successor
        self.calls = 0

    def load_current_working_set(self):
        return self.current

    def apply_working_set_transition(self, proposal, *, source_working_set_digest, source_model_view_digest):
        self.calls += 1
        return self.successor


class PromotionHandler:
    def __init__(self, current: HarnessWorkingSetSpec, successor: HarnessWorkingSetSpec) -> None:
        self.current = current
        self.successor = successor
        self.calls = 0

    def load_current_working_set(self):
        return self.current

    def apply_caller_ingress_promotion(self, proposal, *, source_working_set_digest, source_model_view_digest):
        self.calls += 1
        return self.successor

    def project_current_caller_ingress(self, messages):
        return ()


class R2CognitionAdmissionKernelTests(unittest.TestCase):
    def test_transition_preserves_same_selection_as_attempt_reset(self) -> None:
        task = pin("task", "task")
        source = committed("working-attempt:r2-a", task)
        successor = committed("working-attempt:r2-b", task)
        handler = TransitionHandler(source, successor)
        proposal = AgentWorkingSetTransitionProposal(
            next_attempt_id="working-attempt:r2-b",
            pins=(task,),
            basis="reset attempt only",
        )
        result = CognitionAdmissionKernel(
            working_set_transition_handler=handler
        ).apply_working_set_transition(
            proposal,
            source_working_set_digest=source.digest,
            source_model_view_digest=canonical_digest({"view": "a"}),
        )
        self.assertFalse(result.selection_changed)
        self.assertEqual(result.committed_working_set, successor)
        self.assertEqual(handler.calls, 1)

    def test_promotion_reports_actual_committed_selection_change(self) -> None:
        task = pin("task", "task2")
        caller = pin("caller", "caller")
        source = committed("working-attempt:r2-p-a", task)
        successor = committed("working-attempt:r2-p-b", task, caller)
        handler = PromotionHandler(source, successor)
        proposal = AgentCallerIngressPromotionProposal(
            next_attempt_id="working-attempt:r2-p-b",
            promotion_slot="caller",
            caller_message_indexes=(0,),
            basis="retain exact caller",
        )
        result = CognitionAdmissionKernel(
            caller_ingress_promotion_handler=handler
        ).apply_caller_ingress_promotion(
            proposal,
            source_working_set_digest=source.digest,
            source_model_view_digest=canonical_digest({"view": "p"}),
        )
        self.assertTrue(result.selection_changed)
        self.assertEqual(result.source_working_set, source)
        self.assertEqual(result.committed_working_set, successor)

    def test_stale_source_fails_before_durable_handler_apply(self) -> None:
        source = committed("working-attempt:r2-stale", pin("task", "stale"))
        successor = committed("working-attempt:r2-next", pin("task", "next"))
        handler = TransitionHandler(source, successor)
        proposal = AgentWorkingSetTransitionProposal(
            next_attempt_id="working-attempt:r2-next",
            pins=successor.pins,
            basis="must fail stale source",
        )
        with self.assertRaisesRegex(ValueError, "no longer the current selected cognition"):
            CognitionAdmissionKernel(
                working_set_transition_handler=handler
            ).apply_working_set_transition(
                proposal,
                source_working_set_digest=canonical_digest({"wrong": True}),
                source_model_view_digest=canonical_digest({"view": "wrong"}),
            )
        self.assertEqual(handler.calls, 0)

    def test_missing_surface_is_explicit_not_generic_handler_failure(self) -> None:
        proposal = AgentWorkingSetTransitionProposal(
            next_attempt_id="working-attempt:r2-none",
            pins=(),
            basis="unavailable",
        )
        with self.assertRaises(CognitionSurfaceUnavailable):
            CognitionAdmissionKernel().apply_working_set_transition(
                proposal,
                source_working_set_digest=canonical_digest({"source": "none"}),
                source_model_view_digest=canonical_digest({"view": "none"}),
            )


if __name__ == "__main__":
    unittest.main()
