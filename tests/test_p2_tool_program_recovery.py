from __future__ import annotations

import unittest

from ordivon_harness.agent_tool_observation import HarnessToolObservation
from ordivon_harness.tool_program import HarnessToolProgramAction
from ordivon_harness.tool_program_recovery import (
    derive_tool_program_inner_call,
    derive_tool_program_step_id,
    recover_tool_program_action,
)

from tests.test_p2_tool_program import dependent_program


def observed(call, content):
    return HarnessToolObservation(
        tool_call_id=call.tool_call_id,
        tool_name=call.name,
        status="observed",
        structured_content=content,
    )


class ToolProgramRecoveryP2Tests(unittest.TestCase):
    def action(self, suffix: str = "a") -> HarnessToolProgramAction:
        return HarnessToolProgramAction(
            action_call_id=f"program-action:p2:{suffix}",
            program=dependent_program(),
        )

    def test_empty_restart_projection_derives_first_exact_inner_call(self) -> None:
        action = self.action()
        progress = recover_tool_program_action(action, ())
        self.assertFalse(progress.terminal)
        assert progress.next_call is not None
        self.assertEqual(progress.next_call.name, "read_value")
        self.assertEqual(progress.next_call.arguments, {"key": "source"})
        self.assertEqual(progress.action_digest, action.digest)

    def test_observed_prefix_deterministically_derives_data_dependent_next_call(self) -> None:
        action = self.action()
        first = derive_tool_program_inner_call(action, 0, ())
        first_observation = observed(
            first,
            {"value": "needle", "digest": "sha256:" + "a" * 64},
        )
        progress = recover_tool_program_action(action, (first_observation,))
        self.assertFalse(progress.terminal)
        assert progress.next_call is not None
        self.assertEqual(progress.next_call.name, "lookup_value")
        self.assertEqual(progress.next_call.arguments, {"query": "needle"})
        self.assertEqual(
            progress.next_call,
            derive_tool_program_inner_call(action, 1, (first_observation,)),
        )

    def test_complete_observed_prefix_reconstructs_compact_terminal_output(self) -> None:
        action = self.action()
        first = derive_tool_program_inner_call(action, 0, ())
        first_observation = observed(
            first,
            {"value": "needle", "digest": "sha256:" + "a" * 64},
        )
        second = derive_tool_program_inner_call(action, 1, (first_observation,))
        second_observation = observed(
            second,
            {"query": "needle", "matches": ["m1", "m2"]},
        )
        progress = recover_tool_program_action(
            action,
            (first_observation, second_observation),
        )
        self.assertTrue(progress.terminal)
        assert progress.terminal_result is not None
        self.assertEqual(progress.terminal_result.status, "completed")
        self.assertEqual(
            progress.terminal_result.output,
            {
                "query": "needle",
                "matches": ["m1", "m2"],
                "sourceDigest": "sha256:" + "a" * 64,
            },
        )

    def test_same_program_with_different_outer_action_identity_has_distinct_inner_calls(self) -> None:
        first = derive_tool_program_inner_call(self.action("a"), 0, ())
        second = derive_tool_program_inner_call(self.action("b"), 0, ())
        self.assertNotEqual(first.tool_call_id, second.tool_call_id)
        self.assertEqual(first.name, second.name)
        self.assertEqual(first.arguments, second.arguments)

    def test_forged_reordered_or_skipped_durable_prefix_fails_closed(self) -> None:
        action = self.action()
        first = derive_tool_program_inner_call(action, 0, ())
        forged = HarnessToolObservation(
            tool_call_id=first.tool_call_id + ":forged",
            tool_name=first.name,
            status="observed",
            structured_content={"value": "needle", "digest": "sha256:" + "a" * 64},
        )
        with self.assertRaisesRegex(ValueError, "differs from derived inner Tool Call"):
            recover_tool_program_action(action, (forged,))

        with self.assertRaisesRegex(ValueError, "prior observation count differs"):
            derive_tool_program_inner_call(action, 1, ())

    def test_unknown_inner_outcome_is_terminal_and_evidence_cannot_continue_after_it(self) -> None:
        action = self.action()
        first = derive_tool_program_inner_call(action, 0, ())
        unknown = HarnessToolObservation(
            tool_call_id=first.tool_call_id,
            tool_name=first.name,
            status="unknown",
            structured_content={"reason": "ambiguous delivery"},
            reconciled=True,
        )
        progress = recover_tool_program_action(action, (unknown,))
        self.assertTrue(progress.terminal)
        assert progress.terminal_result is not None
        self.assertEqual(progress.terminal_result.status, "unknown")
        self.assertEqual(progress.terminal_result.output, {})

        fake_second = HarnessToolObservation(
            tool_call_id="tool-call:forged:after-unknown",
            tool_name="lookup_value",
            status="observed",
            structured_content={"query": "needle"},
        )
        with self.assertRaisesRegex(ValueError, "continues after terminal"):
            recover_tool_program_action(action, (unknown, fake_second))

    def test_step_identity_is_deterministic_and_outer_action_bound(self) -> None:
        a = derive_tool_program_step_id(self.action("a"), 0, step_prefix="turn:p2")
        again = derive_tool_program_step_id(self.action("a"), 0, step_prefix="turn:p2")
        b = derive_tool_program_step_id(self.action("b"), 0, step_prefix="turn:p2")
        self.assertEqual(a, again)
        self.assertNotEqual(a, b)


if __name__ == "__main__":
    unittest.main()
