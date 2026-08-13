from __future__ import annotations

import unittest

from anc_canonical import canonical_digest

from ordivon_harness.telemetry import build_harness_telemetry_projection


class TelemetryProjectionTests(unittest.TestCase):
    def test_terminal_projection_normalizes_cache_and_remaining_budget(self) -> None:
        receipt = {
            "schemaVersion": 1,
            "kind": "ordivon.independent-harness-run-receipt",
            "startedAtMs": 100,
            "finishedAtMs": 350,
            "stopReason": "completed",
            "terminationCode": "candidate_completed",
            "traceDigest": "sha256:" + "1" * 64,
            "runtimeJobRefs": [],
            "usage": {
                "modelCalls": 2,
                "toolCalls": 1,
                "observationBytes": 120,
                "totalTokens": 1000,
                "wallTimeMs": 250,
                "modelRetries": 0,
                "toolCorrections": 0,
                "providerAttempts": 2,
                "providerResultsReplayed": 0,
                "requestedModelId": "deepseek-v4-flash",
                "effectiveModelIds": ["deepseek-v4-flash"],
                "providerUsage": [
                    {
                        "prompt_cache_hit_tokens": 300,
                        "prompt_cache_miss_tokens": 100,
                        "providerRequestMode": "non-thinking",
                        "providerModel": "deepseek-v4-flash",
                    },
                    {
                        "prompt_cache_hit_tokens": 200,
                        "prompt_cache_miss_tokens": 400,
                        "providerRequestMode": "non-thinking",
                        "providerModel": "deepseek-v4-flash",
                    },
                ],
            },
        }
        inspected = {
            "authority": "independent-harness-run",
            "run": {
                "harnessRunId": "harness-run:test",
                "status": "completed",
                "revision": 6,
                "createdAtMs": 90,
                "updatedAtMs": 350,
                "terminalEventId": "event:terminal",
                "contractDigest": "sha256:" + "2" * 64,
            },
            "contract": {
                "adapterId": "deepseek.chat-completions.non-thinking.v1",
                "providerId": "provider:deepseek",
                "requestedModelId": "deepseek-v4-flash",
                "toolCatalogDigest": "sha256:" + "3" * 64,
                "toolGrantDigest": "sha256:" + "4" * 64,
                "budget": {
                    "maxModelCalls": 4,
                    "maxToolCalls": 3,
                    "maxObservationBytes": 1000,
                    "maxTotalTokens": 5000,
                    "maxWallTimeMs": 10000,
                    "maxModelRetries": 2,
                    "maxToolCorrections": 3,
                    "maxConclusionCorrections": 1,
                    "maxObservationOnlyTurns": 6,
                    "maxNoProgressTurns": 3,
                },
            },
            "providerCall": None,
            "snapshot": None,
            "recovery": None,
            "runReceipt": receipt,
        }
        value = build_harness_telemetry_projection(inspected)
        self.assertEqual(value["truthRole"], "derived-read-only-projection")
        self.assertEqual(value["termination"]["durationMs"], 250)
        self.assertEqual(value["cache"]["hitTokens"], 500)
        self.assertEqual(value["cache"]["missTokens"], 500)
        self.assertEqual(
            value["cache"]["hitRatio"],
            {"numerator": 500, "denominator": 1000},
        )
        self.assertEqual(value["cache"]["policyRole"], "measurement-only")
        self.assertEqual(value["budget"]["remaining"]["totalTokens"], 4000)
        self.assertEqual(value["budget"]["remaining"]["modelCalls"], 2)
        self.assertEqual(value["evidence"]["runReceiptDigest"], canonical_digest(receipt))
        self.assertIn("do not imply domain semantic completion", value["interpretationBoundary"]["completion"])

    def test_missing_provider_cache_fields_remain_unavailable(self) -> None:
        inspected = {
            "run": {
                "harnessRunId": "harness-run:paused",
                "status": "paused",
                "revision": 3,
                "createdAtMs": 1,
                "updatedAtMs": 2,
                "terminalEventId": None,
                "contractDigest": "sha256:" + "5" * 64,
            },
            "contract": {
                "adapterId": "adapter:test",
                "providerId": "provider:test",
                "requestedModelId": "model:test",
                "toolCatalogDigest": "sha256:" + "6" * 64,
                "toolGrantDigest": "sha256:" + "7" * 64,
                "budget": {"maxModelCalls": 3},
            },
            "providerCall": {"status": "unknown"},
            "snapshot": {
                "pauseReason": "provider-state-unknown",
                "remainingBudget": {"modelCalls": 2},
            },
            "recovery": {
                "safeToAbandon": False,
                "unresolvedUnknowns": ["provider outcome unknown"],
            },
            "runReceipt": None,
        }
        value = build_harness_telemetry_projection(inspected)
        self.assertFalse(value["cache"]["available"])
        self.assertIsNone(value["cache"]["hitTokens"])
        self.assertEqual(value["budget"]["remainingBasis"], "durable-run-snapshot")
        self.assertEqual(value["continuity"]["providerCallStatus"], "unknown")
        self.assertTrue(value["continuity"]["unknownsRemain"])


if __name__ == "__main__":
    unittest.main()
