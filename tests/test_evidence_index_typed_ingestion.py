from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "evidence" / "index.json"
SCRIPT = ROOT / "scripts" / "check_evidence.py"

spec = importlib.util.spec_from_file_location("harness_check_evidence", SCRIPT)
assert spec is not None and spec.loader is not None
check_evidence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_evidence)

EXPECTED = {
    "harness.research.campaign3-rich-effect-owner-capture-v1": (
        "harness-campaign3-rich-effect-owner-v1-capture.json",
        "historical",
        "786d64a7cfb21d52e9e541331c3db67a9edd4f29",
        "5695253f4148536178e7e579624762d27af68f541632121e3dd507f1d2a1f698",
    ),
    "harness.research.campaign3-rich-effect-owner-result-v1": (
        "harness-campaign3-rich-effect-owner-v1-result.json",
        "historical",
        "786d64a7cfb21d52e9e541331c3db67a9edd4f29",
        "bd251924d98b9cd25bb76fd0496bdfd51f485d86a878767ef45533a2aedc7c4d",
    ),
    "harness.research.campaign5-provider-route-preservation-v1": (
        "harness-campaign5-provider-route-preservation-v1-result.json",
        "historical",
        "a1a61430047dfa0c43fb2f32d1d2529d57c19018",
        "0693df87e7541a5589ba865e17937b46e79fb2f25bb7175b3856cae682ff0aa1",
    ),
    "harness.execution.current-no-tool-conclusion-control-repair-v1": (
        "harness-current-no-tool-conclusion-control-repair-v1.json",
        "verified",
        "8925fdba026cdef4f9d8969fae244ee3e5e46730",
        "d455cc726e6356e4463a6c7463d9573d3d2730c88b78723fa362129159b7b4ae",
    ),
}


class EvidenceIndexTypedIngestionTests(unittest.TestCase):
    def _entries(self) -> dict[str, dict[str, object]]:
        raw = json.loads(INDEX.read_text(encoding="utf-8"))
        return {entry["claimId"]: entry for entry in raw["entries"]}

    def test_expected_projection_entries_are_bound_without_rewriting_bytes(self) -> None:
        entries = self._entries()
        for claim_id, (filename, status, revision, digest) in EXPECTED.items():
            entry = entries[claim_id]
            self.assertEqual(entry["file"], filename)
            self.assertEqual(entry["status"], status)
            self.assertEqual(entry["implementationRevision"], revision)
            self.assertEqual(entry["revisionBinding"], "index-creation-lineage")
            actual = hashlib.sha256((ROOT / "evidence" / filename).read_bytes()).hexdigest()
            self.assertEqual(actual, digest)

    def test_ts11_stale_verified_receipt_is_historical(self) -> None:
        entry = self._entries()["harness.tool-surface.ts11-turn-working-set"]
        self.assertEqual(entry["status"], "historical")
        self.assertEqual(
            entry["implementationRevision"],
            "a57963c476d366aea0d73d96cddd223f3bd5dbaf",
        )

    def test_legacy_embedded_binding_stays_exact(self) -> None:
        entries = self._entries()
        entry = next(item for item in entries.values() if "revisionBinding" not in item)
        filename = str(entry["file"])
        revision = str(entry["implementationRevision"])
        receipt = json.loads((ROOT / "evidence" / filename).read_text(encoding="utf-8"))
        validator = check_evidence._validate_embedded_revision_binding
        self.assertEqual(validator(filename, receipt, revision), [])
        errors = validator(filename, receipt, "0" * 40)
        self.assertTrue(any("revision mismatch" in error for error in errors))

    def test_verified_currentness_still_rejects_stale_implementation(self) -> None:
        current, invalidating = check_evidence._verified_revision_is_current(
            "a57963c476d366aea0d73d96cddd223f3bd5dbaf"
        )
        self.assertFalse(current)
        self.assertTrue(invalidating)
        current, invalidating = check_evidence._verified_revision_is_current(
            "8925fdba026cdef4f9d8969fae244ee3e5e46730"
        )
        self.assertTrue(current)
        self.assertEqual(invalidating, [])

    def test_index_creation_lineage_binding_accepts_exact_and_rejects_nonancestor(self) -> None:
        validator = check_evidence._validate_index_creation_lineage_binding
        for _claim_id, (filename, _status, revision, _digest) in EXPECTED.items():
            self.assertEqual(validator(filename, revision), [])
        current_head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        ).stdout.strip()
        errors = validator(
            "harness-campaign3-rich-effect-owner-v1-capture.json",
            current_head,
        )
        self.assertTrue(any("ancestor" in error for error in errors))

    def test_complete_evidence_contract_is_green(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("evidence contract: valid", completed.stdout)


if __name__ == "__main__":
    unittest.main()
