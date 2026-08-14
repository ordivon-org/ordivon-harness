from __future__ import annotations

import unittest
from dataclasses import replace

from ordivon_harness.strategy_selection import (
    HarnessAgentStrategySelection,
    build_harness_strategy_selection_context,
    compile_harness_selected_attempt,
)
from tests.test_strategy_selection_p0 import mandate, profile, strategy


D_SEQ = "sha256:" + "a" * 64
D_ALT = "sha256:" + "b" * 64


class AM7MorphologyStrategySelectionTests(unittest.TestCase):
    def _profiles(self):
        sequential = replace(
            profile("profile:cheap"),
            metadata={
                "morphologyClass": "baseline",
                "loopDriver": {
                    "driverId": "loop-driver:sequential-v1",
                    "driverDigest": D_SEQ,
                },
            },
        )
        alternate = replace(
            profile("profile:observe"),
            metadata={
                "morphologyClass": "challenger",
                "loopDriver": {
                    "driverId": "loop-driver:challenger-v1",
                    "driverDigest": D_ALT,
                },
            },
        )
        return sequential, alternate

    def test_agent_owned_strategy_can_select_attempt_bound_morphology_without_new_selector(self) -> None:
        value = mandate()
        sequential, alternate = self._profiles()
        context = build_harness_strategy_selection_context(value, (sequential, alternate))
        selection = HarnessAgentStrategySelection(
            context.digest,
            strategy(context, profile_id=alternate.profile_id),
        )
        compiled = compile_harness_selected_attempt(
            context,
            selection,
            harness_run_id="harness-run:am7-challenger",
            harness_implementation_id="ordivon-harness@test",
            created_at_ms=7_000,
        )
        self.assertEqual(compiled.system_manifest["profileId"], alternate.profile_id)
        self.assertEqual(
            compiled.system_manifest["loopDriver"],
            {
                "driverId": "loop-driver:challenger-v1",
                "driverDigest": D_ALT,
            },
        )
        # Selection identifies morphology but does not make a challenger executable.
        self.assertNotIn("loopDriver", compiled.contract.to_dict())

    def test_morphology_choice_is_fenced_to_exact_available_profile_set(self) -> None:
        value = mandate()
        sequential, alternate = self._profiles()
        first_context = build_harness_strategy_selection_context(value, (sequential, alternate))
        stale = HarnessAgentStrategySelection(
            first_context.digest,
            strategy(first_context, profile_id=alternate.profile_id),
        )
        second_context = build_harness_strategy_selection_context(value, (sequential,))
        self.assertNotEqual(first_context.digest, second_context.digest)
        with self.assertRaisesRegex(ValueError, "stale context"):
            compile_harness_selected_attempt(
                second_context,
                stale,
                harness_run_id="harness-run:am7-stale",
                harness_implementation_id="ordivon-harness@test",
                created_at_ms=8_000,
            )

    def test_harness_does_not_rank_or_auto_select_loop_morphology(self) -> None:
        value = mandate()
        sequential, alternate = self._profiles()
        context = build_harness_strategy_selection_context(value, (sequential, alternate))
        projected = context.to_dict()
        self.assertEqual(len(projected["availableProfiles"]), 2)
        self.assertNotIn("selectedProfileId", projected)
        self.assertNotIn("recommendedProfileId", projected)
        self.assertNotIn("morphologyScore", projected)


if __name__ == "__main__":
    unittest.main()
