from __future__ import annotations

import unittest
from dataclasses import replace

from ordivon_harness.loop_driver import HarnessLoopDriverBinding
from tests.test_execution_mandate import mandate, profile, strategy
from ordivon_harness.mandate import compile_harness_attempt


D = "sha256:" + "e" * 64


class AM1LoopDriverTests(unittest.TestCase):
    def _compiled(self):
        value = mandate()
        selected_profile = replace(
            profile(),
            metadata={
                "loopDriver": {
                    "driverId": "loop-driver:experimental-a",
                    "driverDigest": D,
                }
            },
        )
        return compile_harness_attempt(
            value,
            selected_profile,
            strategy(value),
            harness_run_id="harness-run:am1-binding",
            harness_implementation_id="ordivon-harness@test",
            created_at_ms=2_000,
        )

    def test_binding_requires_exact_compiled_driver(self) -> None:
        compiled = self._compiled()
        binding = HarnessLoopDriverBinding.from_compiled_attempt(
            compiled,
            driver_id="loop-driver:experimental-a",
            driver_digest=D,
            factory=lambda **_: None,  # build is intentionally not invoked in this identity test
        )
        self.assertEqual(binding.system_manifest_digest, compiled.contract.system_manifest_ref.digest)
        binding.require_contract(compiled.contract.system_manifest_ref.digest)

        with self.assertRaisesRegex(ValueError, "differs from the compiled Attempt manifest"):
            HarnessLoopDriverBinding.from_compiled_attempt(
                compiled,
                driver_id="loop-driver:experimental-b",
                driver_digest=D,
                factory=lambda **_: None,
            )

    def test_binding_cannot_attach_to_another_manifest(self) -> None:
        compiled = self._compiled()
        binding = HarnessLoopDriverBinding.from_compiled_attempt(
            compiled,
            driver_id="loop-driver:experimental-a",
            driver_digest=D,
            factory=lambda **_: None,
        )
        with self.assertRaisesRegex(ValueError, "belongs to another Run manifest"):
            binding.require_contract("sha256:" + "f" * 64)


if __name__ == "__main__":
    unittest.main()
