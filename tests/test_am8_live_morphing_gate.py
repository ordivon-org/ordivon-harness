from __future__ import annotations

import inspect
import unittest
from dataclasses import replace

from ordivon_harness.loop_driver import HarnessLoopDriverIdentity
from ordivon_harness.standalone import StandaloneHarnessRunner
from ordivon_harness.strategy_selection import (
    HarnessAgentStrategySelection,
    build_harness_strategy_selection_context,
    compile_harness_selected_attempt,
)
from tests.test_strategy_selection_p0 import evidence, mandate, profile, strategy


D_SEQ = "sha256:" + "1" * 64
D_NEXT = "sha256:" + "2" * 64


class AM8LiveMorphingGateTests(unittest.TestCase):
    def _profiles(self):
        first = replace(
            profile("profile:cheap"),
            metadata={
                "loopDriver": {
                    "driverId": "loop-driver:sequential-v1",
                    "driverDigest": D_SEQ,
                }
            },
        )
        successor = replace(
            profile("profile:observe"),
            metadata={
                "loopDriver": {
                    "driverId": "loop-driver:successor-v1",
                    "driverDigest": D_NEXT,
                }
            },
        )
        return first, successor

    def test_successor_attempt_can_change_loop_identity_from_exact_prior_receipt(self) -> None:
        value = mandate()
        first_profile, successor_profile = self._profiles()
        first_context = build_harness_strategy_selection_context(
            value, (first_profile, successor_profile)
        )
        first_selection = HarnessAgentStrategySelection(
            first_context.digest,
            strategy(first_context, profile_id=first_profile.profile_id),
        )
        first = compile_harness_selected_attempt(
            first_context,
            first_selection,
            harness_run_id="harness-run:am8-first",
            harness_implementation_id="ordivon-harness@test",
            created_at_ms=10_000,
        )
        prior = evidence(first, total_tokens=400, wall_time_ms=500)
        successor_context = build_harness_strategy_selection_context(
            value,
            (first_profile, successor_profile),
            (prior,),
        )
        successor_selection = HarnessAgentStrategySelection(
            successor_context.digest,
            strategy(
                successor_context,
                profile_id=successor_profile.profile_id,
                adopted_context_refs=(successor_context.consumption.receipt_refs[-1],),
            ),
        )
        successor = compile_harness_selected_attempt(
            successor_context,
            successor_selection,
            harness_run_id="harness-run:am8-successor",
            harness_implementation_id="ordivon-harness@test",
            created_at_ms=11_000,
        )
        self.assertNotEqual(first.system_manifest["loopDriver"], successor.system_manifest["loopDriver"])
        self.assertEqual(
            successor.contract.context_refs[-1].digest,
            prior.receipt.digest,
        )
        identity = HarnessLoopDriverIdentity.from_compiled_attempt(
            successor,
            driver_id="loop-driver:successor-v1",
            driver_digest=D_NEXT,
        )
        identity.require_contract(successor.contract.system_manifest_ref.digest)

    def test_no_live_loop_install_or_factory_surface_is_exposed(self) -> None:
        params = inspect.signature(StandaloneHarnessRunner.__init__).parameters
        for forbidden in (
            "loop_driver_binding",
            "loop_factory",
            "plugin_registry",
            "hot_reload",
        ):
            self.assertNotIn(forbidden, params)
        for forbidden in ("factory", "build", "install", "unload", "reload"):
            self.assertFalse(hasattr(HarnessLoopDriverIdentity, forbidden))


if __name__ == "__main__":
    unittest.main()
