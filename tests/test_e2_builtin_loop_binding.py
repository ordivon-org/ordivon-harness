from __future__ import annotations

import unittest

from ordivon_harness.loop_driver import (
    DELIBERATE_THEN_ACT_LOOP_DRIVER,
    HarnessLoopDriverIdentity,
    SEQUENTIAL_LOOP_DRIVER,
    builtin_scheduling_mode,
)
from tests.test_execution_mandate import mandate, profile, strategy
from ordivon_harness.mandate import HarnessLoopDriverRef, compile_harness_attempt


class E2BuiltinLoopBindingTests(unittest.TestCase):
    def _compiled(self, ref: HarnessLoopDriverRef):
        value = mandate()
        selected_profile = profile().with_loop_driver(ref)
        return compile_harness_attempt(
            value, selected_profile, strategy(value),
            harness_run_id=f"harness-run:e2:{ref.driver_id.rsplit(":", 1)[-1]}",
            harness_implementation_id="ordivon-harness@test",
            created_at_ms=5_000,
        )

    def test_builtin_modes_require_exact_manifest_bound_identity(self) -> None:
        for ref, expected in (
            (SEQUENTIAL_LOOP_DRIVER, "sequential"),
            (DELIBERATE_THEN_ACT_LOOP_DRIVER, "deliberate_then_act"),
        ):
            with self.subTest(driver=ref.driver_id):
                compiled = self._compiled(ref)
                identity = HarnessLoopDriverIdentity.from_compiled_attempt(
                    compiled, driver_id=ref.driver_id, driver_digest=ref.driver_digest
                )
                self.assertEqual(builtin_scheduling_mode(identity), expected)
                self.assertEqual(identity.system_manifest_digest, compiled.contract.system_manifest_ref.digest)

    def test_unknown_exact_driver_is_identified_but_not_executable(self) -> None:
        unknown = HarnessLoopDriverRef(
            driver_id="loop-driver:future-v1",
            driver_digest="sha256:" + "f" * 64,
        )
        compiled = self._compiled(unknown)
        identity = HarnessLoopDriverIdentity.from_compiled_attempt(
            compiled, driver_id=unknown.driver_id, driver_digest=unknown.driver_digest
        )
        with self.assertRaisesRegex(ValueError, "no admitted built-in executable implementation"):
            builtin_scheduling_mode(identity)

    def test_absent_driver_preserves_historical_sequential_default(self) -> None:
        self.assertEqual(builtin_scheduling_mode(None), "sequential")


if __name__ == "__main__":
    unittest.main()
