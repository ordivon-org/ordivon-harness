from __future__ import annotations

import unittest

from ordivon_harness.mandate import HarnessExecutionProfile, HarnessLoopDriverRef
from tests.test_execution_mandate import profile


class E1LoopDriverRefTests(unittest.TestCase):
    def test_typed_ref_preserves_existing_profile_wire_shape(self) -> None:
        base = profile()
        ref = HarnessLoopDriverRef(
            driver_id="loop-driver:sequential-v1",
            driver_digest="sha256:" + "a" * 64,
        )
        bound = base.with_loop_driver(ref)
        encoded = bound.to_dict()
        self.assertEqual(set(encoded), {
            "schemaVersion", "kind", "profileId", "providerId",
            "adapterId", "requestedModelId", "toolCatalogDigest",
            "toolGrantDigest", "metadata",
        })
        self.assertEqual(encoded["metadata"]["loopDriver"], ref.to_dict())
        self.assertEqual(bound.loop_driver_ref, ref)
        self.assertEqual(HarnessExecutionProfile.from_dict(encoded), bound)

    def test_legacy_metadata_decodes_to_typed_ref_without_digest_change(self) -> None:
        legacy = profile()
        metadata = dict(legacy.to_dict()["metadata"])
        metadata["loopDriver"] = {
            "driverId": "loop-driver:legacy",
            "driverDigest": "sha256:" + "b" * 64,
        }
        encoded = legacy.to_dict()
        encoded["metadata"] = metadata
        decoded = HarnessExecutionProfile.from_dict(encoded)
        self.assertEqual(decoded.to_dict(), encoded)
        self.assertEqual(decoded.loop_driver_ref.driver_id, "loop-driver:legacy")

    def test_typed_ref_is_identity_only(self) -> None:
        ref = HarnessLoopDriverRef(
            driver_id="loop-driver:no-exec",
            driver_digest="sha256:" + "c" * 64,
        )
        for forbidden in ("build", "load", "execute", "reload", "factory"):
            self.assertFalse(hasattr(ref, forbidden))


if __name__ == "__main__":
    unittest.main()
