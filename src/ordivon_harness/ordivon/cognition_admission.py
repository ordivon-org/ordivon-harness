from __future__ import annotations

from dataclasses import dataclass

from ..working_view import (
    AgentCallerIngressPromotionProposal,
    AgentWorkingSetTransitionProposal,
    CallerIngressPromotionHandler,
    HarnessWorkingSetSpec,
    WorkingSetTransitionHandler,
)


class CognitionSurfaceUnavailable(ValueError):
    """The exact turn did not install the requested cognition mutation surface."""


@dataclass(frozen=True, slots=True)
class CognitionAdmission:
    source_working_set: HarnessWorkingSetSpec
    committed_working_set: HarnessWorkingSetSpec
    selection_changed: bool


@dataclass(frozen=True, slots=True)
class CognitionAdmissionKernel:
    """Admit exact Agent-authored cognition mutations against current selection.

    This kernel owns only the common structural admission law. Caller promotion
    and ordinary WorkingSet transition remain distinct actions with distinct
    evidence/progress semantics in the Loop. Durable handlers remain the actual
    persistence authority, and Continuity independently validates their evidence.
    """

    working_set_transition_handler: WorkingSetTransitionHandler | None = None
    caller_ingress_promotion_handler: CallerIngressPromotionHandler | None = None

    def apply_caller_ingress_promotion(
        self,
        proposal: AgentCallerIngressPromotionProposal,
        *,
        source_working_set_digest: str,
        source_model_view_digest: str,
    ) -> CognitionAdmission:
        handler = self.caller_ingress_promotion_handler
        if handler is None:
            raise CognitionSurfaceUnavailable(
                "Agent proposed caller ingress promotion but this Loop did not grant that cognition surface"
            )
        source = self._require_current_source(
            handler,
            source_working_set_digest=source_working_set_digest,
            stale_message=(
                "caller ingress promotion source is no longer current selected cognition"
            ),
        )
        committed = handler.apply_caller_ingress_promotion(
            proposal,
            source_working_set_digest=source_working_set_digest,
            source_model_view_digest=source_model_view_digest,
        )
        return CognitionAdmission(
            source_working_set=source,
            committed_working_set=committed,
            selection_changed=(committed.pins != source.pins),
        )

    def apply_working_set_transition(
        self,
        proposal: AgentWorkingSetTransitionProposal,
        *,
        source_working_set_digest: str,
        source_model_view_digest: str,
    ) -> CognitionAdmission:
        handler = self.working_set_transition_handler
        if handler is None:
            raise CognitionSurfaceUnavailable(
                "Agent proposed a Working Set transition but this Loop did not grant a cognition transition surface"
            )
        source = self._require_current_source(
            handler,
            source_working_set_digest=source_working_set_digest,
            stale_message=(
                "Working Set transition source is no longer the current selected cognition"
            ),
        )
        selection_changed = source.pins != proposal.pins
        committed = handler.apply_working_set_transition(
            proposal,
            source_working_set_digest=source_working_set_digest,
            source_model_view_digest=source_model_view_digest,
        )
        return CognitionAdmission(
            source_working_set=source,
            committed_working_set=committed,
            selection_changed=selection_changed,
        )

    @staticmethod
    def _require_current_source(
        handler: WorkingSetTransitionHandler | CallerIngressPromotionHandler,
        *,
        source_working_set_digest: str,
        stale_message: str,
    ) -> HarnessWorkingSetSpec:
        source = handler.load_current_working_set()
        if source.digest != source_working_set_digest:
            raise ValueError(stale_message)
        return source


__all__ = [
    "CognitionAdmission",
    "CognitionAdmissionKernel",
    "CognitionSurfaceUnavailable",
]
