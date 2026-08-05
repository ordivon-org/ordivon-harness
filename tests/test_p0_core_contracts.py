from __future__ import annotations

from pathlib import Path
import unittest

from ordivon_harness.core_contracts import (
    HarnessBoundReference,
    HarnessCorrelationContext,
    HarnessPrivacyPolicy,
    HarnessRunContract,
)

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64
DIGEST_D = "sha256:" + "d" * 64


def contract() -> HarnessRunContract:
    return HarnessRunContract(
        harness_run_id="harness-run:p0-core-001",
        harness_implementation_id="ordivon-harness@0.7.0-dev",
        caller_id="caller:standalone-test",
        caller_run_ref="trial:p0-core-001",
        objective_ref=HarnessBoundReference("objective:p0-core-001", "objective", DIGEST_A),
        context_refs=(HarnessBoundReference("context:p0-core-001", "context", DIGEST_B),),
        provider_id="provider:scripted",
        adapter_id="adapter:scripted-v1",
        requested_model_id="model:scripted",
        tool_catalog_digest=DIGEST_C,
        tool_grant_digest=DIGEST_D,
        budget={"maxModelCalls": 2, "maxToolCalls": 1},
        completion_contract={"mode": "record", "verifierRef": "verifier:test"},
        system_manifest_ref=HarnessBoundReference(
            "system-manifest:p0-core-001", "system-manifest", DIGEST_A
        ),
        created_at_ms=10_000,
        source_refs=(HarnessBoundReference("source:repository", "git", DIGEST_B),),
        correlation=HarnessCorrelationContext(
            traceparent="00-11111111111111111111111111111111-2222222222222222-01"
        ),
        privacy=HarnessPrivacyPolicy(),
        deadline_ms=20_000,
    )


class HarnessCoreContractTests(unittest.TestCase):
    def test_round_trip_and_digest_are_deterministic(self) -> None:
        value = contract()
        self.assertEqual(HarnessRunContract.from_dict(value.to_dict()), value)
        self.assertEqual(HarnessRunContract.from_dict(value.to_dict()).digest, value.digest)
        self.assertTrue(value.digest.startswith("sha256:"))

    def test_contract_is_caller_neutral(self) -> None:
        rendered = str(contract().to_dict()).lower()
        for forbidden in (
            "taskprojection",
            "streamrevision",
            "hostlease",
            "hoststorage",
            "hostextension",
            "runtimecredential",
            "providersecret",
        ):
            self.assertNotIn(forbidden, rendered)

    def test_exact_decode_rejects_host_projection_injection(self) -> None:
        value = contract().to_dict()
        value["taskProjection"] = {"revision": 9}
        with self.assertRaisesRegex(ValueError, "fields differ"):
            HarnessRunContract.from_dict(value)

    def test_metadata_only_policy_rejects_content_capture(self) -> None:
        with self.assertRaisesRegex(ValueError, "metadata-only"):
            HarnessPrivacyPolicy(
                content_policy="metadata-only",
                allow_model_content=True,
            )

    def test_trace_context_rejects_zero_identity(self) -> None:
        with self.assertRaisesRegex(ValueError, "zero"):
            HarnessCorrelationContext(
                traceparent="00-00000000000000000000000000000000-2222222222222222-01"
            )

    def test_new_core_modules_do_not_import_host(self) -> None:
        root = Path(__file__).resolve().parents[1] / "src" / "ordivon_harness"
        for name in ("core_contracts.py", "store.py", "sqlite_store.py"):
            source = (root / name).read_text(encoding="utf-8")
            self.assertNotIn("ordivon_host", source)
            self.assertNotIn("_host_compat", source)


if __name__ == "__main__":
    unittest.main()
