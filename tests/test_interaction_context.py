from __future__ import annotations

import json
import unittest

from ordivon_harness.interaction_context import (
    InteractionActionSlice,
    InteractionAffordance,
    InteractionContextInput,
    InteractionSourceRef,
    compile_interaction_context,
)
from ordivon_harness.ordivon.model import AgentToolDefinition
from ordivon_harness.working_view import (
    HarnessWorkingSetPin,
    HarnessWorkingSetSpec,
    HarnessWorkingViewSource,
    compile_working_view,
)


def tool(name: str, description: str = "fixture") -> AgentToolDefinition:
    return AgentToolDefinition(
        name=name,
        description=description,
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
    )


class InteractionContextTests(unittest.TestCase):
    def test_finance_unknown_currentness_selects_observe_not_decide(self) -> None:
        admitted = (tool("finance_observe"), tool("finance_decide"), tool("runtime_inspect"))
        materialized = compile_interaction_context(
            InteractionContextInput(
                intent="finance.current-state-and-next-action",
                sources=(
                    InteractionSourceRef(
                        owner="ordivon-finance",
                        authority_ref="finance://state/control",
                        authority_version="state:1259",
                        currentness="OBSERVATION_STALE",
                    ),
                ),
                affordances=(
                    InteractionAffordance(
                        "finance_observe",
                        "ordivon-finance",
                        "AVAILABLE",
                        "EXTERNAL_READ_NO_FINANCIAL_WRITE",
                        requires=("current external state required",),
                    ),
                    InteractionAffordance(
                        "finance_decide",
                        "ordivon-finance",
                        "BLOCKED",
                        "CANONICAL_STATE_WRITE_NO_FINANCIAL_WRITE",
                        requires=("current observation", "complete Agent-authored DecisionRecord"),
                    ),
                    InteractionAffordance(
                        "runtime_inspect",
                        "ordivon-runtime",
                        "BLOCKED",
                        "READ_ONLY",
                    ),
                ),
                blockers=("FINANCE_OBSERVATION_NOT_CURRENT",),
                raw_escape_available=True,
            ),
            admitted,
            logical_ref="interaction://finance/r1",
            logical_generation="finance-state:1259",
        )
        self.assertEqual(materialized.selected_tool_names, ("finance_observe",))
        self.assertEqual(materialized.tool_working_set["availableCount"], 3)
        self.assertEqual(materialized.tool_working_set["selectedCount"], 1)
        self.assertFalse(materialized.tool_working_set["canExpandAuthority"])
        self.assertIsInstance(materialized.source, HarnessWorkingViewSource)
        text = str(materialized.source.messages[0]["content"])
        self.assertIn("FINANCE_OBSERVATION_NOT_CURRENT", text)
        self.assertIn("finance_decide", text)

    def test_broad_current_work_preserves_unknown_and_selects_nothing(self) -> None:
        materialized = compile_interaction_context(
            InteractionContextInput(
                intent="continuity.select-current-work",
                sources=(
                    InteractionSourceRef(
                        owner="ordivon-host",
                        authority_ref="task://continuity-inventory",
                        authority_version="host:rev:9",
                        currentness="CONTINUITY_CURRENT_ONLY",
                    ),
                ),
                affordances=(),
                action_slice=InteractionActionSlice(
                    owner="consumer:unknown",
                    constraints=("Host READY is not global priority",),
                    rejected=("infer priority from task.list order",),
                ),
                blockers=("ALLOCATION_OR_PRIORITY_UNKNOWN",),
                unknowns=("global current-work allocator",),
            ),
            (tool("host_resume"), tool("runtime_inspect")),
            logical_ref="interaction://current-work/r1",
            logical_generation="host:rev:9",
        )
        self.assertEqual(materialized.selected_tool_names, ())
        self.assertEqual(materialized.tool_working_set["selectedCount"], 0)
        text = str(materialized.source.messages[0]["content"])
        self.assertIn("ALLOCATION_OR_PRIORITY_UNKNOWN", text)
        self.assertIn("global current-work allocator", text)

    def test_security_preserves_exact_raw_runtime_affordance(self) -> None:
        admitted = (
            tool("runtime_workspace_open"),
            tool("runtime_workspace_exec"),
            tool("runtime_task_observe"),
        )
        materialized = compile_interaction_context(
            InteractionContextInput(
                intent="security.authorized-physical-experiment",
                sources=(
                    InteractionSourceRef(
                        owner="ordivon-security",
                        authority_ref="security://range/accepted",
                        authority_version="range:7",
                        currentness="CURRENT",
                    ),
                ),
                affordances=(
                    InteractionAffordance(
                        "runtime_workspace_open",
                        "ordivon-runtime",
                        "AVAILABLE",
                        "PHYSICAL_SOURCE_BINDING",
                        responds_to=("NO_RUNTIME_WORKSPACE_BOUND",),
                    ),
                    InteractionAffordance(
                        "runtime_workspace_exec",
                        "ordivon-runtime",
                        "BLOCKED",
                        "PHYSICAL_EXECUTION",
                        requires=("exact Runtime Workspace binding",),
                    ),
                    InteractionAffordance(
                        "runtime_task_observe",
                        "ordivon-runtime",
                        "BLOCKED",
                        "PHYSICAL_RECOVERY",
                        requires=("existing Runtime Job identity",),
                    ),
                ),
                blockers=("NO_RUNTIME_WORKSPACE_BOUND",),
                raw_escape_available=True,
            ),
            admitted,
            logical_ref="interaction://security/r1",
            logical_generation="range:7",
        )
        self.assertEqual(materialized.selected_tool_names, ("runtime_workspace_open",))
        self.assertTrue(materialized.tool_working_set["canExpandAuthority"] is False)
        self.assertIn("caller-may-expand", str(materialized.source.messages[0]["content"]))

    def test_cross_owner_blocker_can_surface_owner_native_read_affordance(self) -> None:
        admitted = (
            tool("finance_observe"),
            tool("workstation_egress_observe"),
            tool("workstation_egress_pool_ensure"),
        )
        materialized = compile_interaction_context(
            InteractionContextInput(
                intent="finance.recover-current-observation-precondition",
                sources=(
                    InteractionSourceRef(
                        owner="ordivon-finance",
                        authority_ref="finance://observe/error",
                        authority_version="error:EGRESS_NOT_CURRENT",
                        currentness="CURRENT_FAILURE_EVIDENCE",
                    ),
                    InteractionSourceRef(
                        owner="ordivon-workstation",
                        authority_ref="workstation://egress/finance-okx",
                        authority_version="profile:digest:1",
                        currentness="UNKNOWN",
                    ),
                ),
                affordances=(
                    InteractionAffordance(
                        "workstation_egress_observe",
                        "ordivon-workstation",
                        "AVAILABLE",
                        "READ_ONLY",
                        responds_to=("EGRESS_NOT_CURRENT",),
                    ),
                    InteractionAffordance(
                        "workstation_egress_pool_ensure",
                        "ordivon-workstation",
                        "BLOCKED",
                        "RECONCILABLE_ENVIRONMENT_MUTATION",
                        requires=(
                            "healthy current member evidence",
                            "environment mutation authority",
                        ),
                        responds_to=("EGRESS_NOT_CURRENT",),
                    ),
                    InteractionAffordance(
                        "finance_observe",
                        "ordivon-finance",
                        "BLOCKED",
                        "EXTERNAL_READ_NO_FINANCIAL_WRITE",
                        requires=("current scoped egress",),
                    ),
                ),
                blockers=("EGRESS_NOT_CURRENT",),
            ),
            admitted,
            logical_ref="interaction://finance/egress-recovery/r1",
            logical_generation="finance-error+workstation-profile:r1",
        )
        self.assertEqual(
            materialized.selected_tool_names, ("workstation_egress_observe",)
        )
        text = str(materialized.source.messages[0]["content"])
        self.assertIn("ordivon-workstation", text)
        self.assertIn("workstation_egress_pool_ensure", text)
        self.assertIn("environment mutation authority", text)

    def test_cross_owner_repair_progresses_only_after_authority_is_supplied(self) -> None:
        admitted = (
            tool("workstation_egress_observe"),
            tool("workstation_egress_pool_ensure"),
            tool("finance_observe"),
        )
        materialized = compile_interaction_context(
            InteractionContextInput(
                intent="finance.recover-current-observation-precondition",
                sources=(
                    InteractionSourceRef(
                        "ordivon-workstation",
                        "workstation://egress/member/finance-okx-b",
                        "member:healthy-current",
                        "CURRENT_AVAILABLE",
                    ),
                ),
                affordances=(
                    InteractionAffordance(
                        "workstation_egress_observe",
                        "ordivon-workstation",
                        "BLOCKED",
                        "READ_ONLY",
                        requires=("pool ensure attempt not yet reconciled",),
                    ),
                    InteractionAffordance(
                        "workstation_egress_pool_ensure",
                        "ordivon-workstation",
                        "AVAILABLE",
                        "RECONCILABLE_ENVIRONMENT_MUTATION",
                        requires=(
                            "healthy current member evidence satisfied",
                            "environment mutation authority supplied",
                        ),
                        responds_to=("EGRESS_NOT_CURRENT",),
                    ),
                    InteractionAffordance(
                        "finance_observe",
                        "ordivon-finance",
                        "BLOCKED",
                        "EXTERNAL_READ_NO_FINANCIAL_WRITE",
                        requires=("current scoped egress",),
                    ),
                ),
                blockers=("EGRESS_NOT_CURRENT",),
            ),
            admitted,
            logical_ref="interaction://finance/egress-recovery/r2",
            logical_generation="member-b-current+operator-authority",
        )
        self.assertEqual(
            materialized.selected_tool_names, ("workstation_egress_pool_ensure",)
        )

    def test_compiled_source_uses_existing_working_view_carrier(self) -> None:
        admitted = (tool("owner_observe"),)
        materialized = compile_interaction_context(
            InteractionContextInput(
                intent="owner.observe",
                sources=(
                    InteractionSourceRef("owner", "owner://state", "v1", "CURRENT"),
                ),
                affordances=(
                    InteractionAffordance(
                        "owner_observe", "owner", "AVAILABLE", "READ_ONLY"
                    ),
                ),
            ),
            admitted,
            logical_ref="interaction://owner/r1",
            logical_generation="v1",
        )

        class Objects:
            def get_object(self, digest, *, expected_kind=None):
                self.assert_digest = digest
                self.assert_kind = expected_kind
                return materialized.source.to_dict()

        pin = HarnessWorkingSetPin(
            slot="interaction",
            logical_ref=materialized.source.logical_ref,
            logical_generation=materialized.source.logical_generation,
            resolved_digest=materialized.source.digest,
        )
        spec = HarnessWorkingSetSpec.initial("working-attempt:interaction-r1", pins=(pin,))
        committed = spec.commit("compiled interaction context selected for this attempt")
        view = compile_working_view(committed, Objects())
        self.assertEqual(view.messages, materialized.source.messages)
        self.assertEqual(view.working_set_digest, committed.digest)

    def test_unknown_affordance_outside_admitted_surface_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "outside the admitted surface"):
            compile_interaction_context(
                InteractionContextInput(
                    intent="fixture",
                    sources=(
                        InteractionSourceRef("owner", "ref", "v1", "CURRENT"),
                    ),
                    affordances=(
                        InteractionAffordance(
                            "invented_tool", "owner", "AVAILABLE", "READ_ONLY"
                        ),
                    ),
                ),
                (tool("real_tool"),),
                logical_ref="interaction://fixture/r1",
                logical_generation="v1",
            )

    def test_representative_compact_context_is_bounded(self) -> None:
        admitted = tuple(tool(f"tool_{index}") for index in range(6))
        materialized = compile_interaction_context(
            InteractionContextInput(
                intent="representative",
                sources=(InteractionSourceRef("owner", "owner://state", "v7", "CURRENT"),),
                affordances=tuple(
                    InteractionAffordance(
                        f"tool_{index}",
                        "owner",
                        "AVAILABLE" if index < 2 else "BLOCKED",
                        "READ_ONLY",
                        requires=(("precondition",) if index >= 2 else ()),
                    )
                    for index in range(6)
                ),
                blockers=("bounded blocker",),
                unknowns=("bounded unknown",),
            ),
            admitted,
            logical_ref="interaction://representative/r1",
            logical_generation="v7",
        )
        encoded = json.dumps(materialized.source.to_dict(), separators=(",", ":"))
        self.assertLess(len(encoded.encode("utf-8")), 2400)
        self.assertEqual(materialized.selected_tool_names, ("tool_0", "tool_1"))


if __name__ == "__main__":
    unittest.main()
