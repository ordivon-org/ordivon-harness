from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

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
        "historical",
        "8925fdba026cdef4f9d8969fae244ee3e5e46730",
        "d455cc726e6356e4463a6c7463d9573d3d2730c88b78723fa362129159b7b4ae",
    ),
    "harness.execution.first-interface-owner-composition-atlas-v1": (
        "harness-first-interface-owner-composition-atlas-v1.json",
        "historical",
        "792cd48cc9fbdddb7431462876d8e57d8f003643",
        "c14b0b932ed15a0f7483a69191a8b3c6f6cd1030377c2138e92d5c227363d329",
    ),
    "harness.execution.first-interface-owner-bridges-v2": (
        "harness-first-interface-owner-bridges-v2.json",
        "historical",
        "0cfed2338a28be428c11816668651463cd9ccb8b",
        "2e5590de07107d84718c3c903f151a64fd29764dd0ad8d930d67ed761f047083",
    ),
    "harness.execution.first-interface-owner-bridges-v3": (
        "harness-first-interface-owner-bridges-v3.json",
        "historical",
        "00edab4e4f6aeac395c9de3ab6a300162e56f6c1",
        "1f2abd65f175ddfff851dbdd6d568c89f422ee77e0c16d6f7908670e8f9dd66a",
    ),
    "harness.execution.first-interface-owner-bridges-v4": (
        "harness-first-interface-owner-bridges-v4.json",
        "historical",
        "f4b05bb38ef7bff10f889df69611de6aaff3a40c",
        "3a2bd1a860714b27672fa228dd25b6660bb318a75320deb18292c4461c49404d",
    ),
    "harness.execution.first-interface-owner-bridges-v5": (
        "harness-first-interface-owner-bridges-v5.json",
        "historical",
        "233bb6354f81eff070996cef898b91726857ca8e",
        "2a2c8eaf2f38af01e129d0a24cdcb1dc406e97a659f42d8cf1cb32f32dde634e",
    ),
    "harness.execution.source-reconciliation-structured-observation-v1": (
        "harness-source-reconciliation-structured-observation-v1.json",
        "historical",
        "e983c79f5582160b37ac56c1898efa80e486880d",
        "db9d22a113a1e7b5f4f4ea882d71e6aec91da2a6e61c16f5dc0abd8e821b28ea",
    ),
    "harness.execution.capability-environment-v1": (
        "harness-capability-environment-v1.json",
        "historical",
        "830dd160b1025928521204f4713cbe0e1bbbf589",
        "aa7d2c696268b218fd32ea09edaa27699d444da2632943b9824cd828a137209e",
    ),
    "harness.execution.current-affordance-compact-v2": (
        "harness-current-affordance-compact-v2.json",
        "historical",
        "17e8943edb16c0f586d5a8d022c63590755a7d6b",
        "e3a24628400842fcb9563969101b2ab7335326c2bb90128b14c51a2bf41c3598",
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
        self.assertFalse(current)
        self.assertTrue(invalidating)
        current, invalidating = check_evidence._verified_revision_is_current(
            "792cd48cc9fbdddb7431462876d8e57d8f003643"
        )
        self.assertFalse(current)
        self.assertIn(
            "src/ordivon_harness/ordivon/finance_observe_runtime_bridge.py",
            invalidating,
        )
        current, invalidating = check_evidence._verified_revision_is_current(
            "0cfed2338a28be428c11816668651463cd9ccb8b"
        )
        self.assertFalse(current)
        self.assertIn(
            "src/ordivon_harness/ordivon/finance_research_runtime_bridge.py",
            invalidating,
        )
        current, invalidating = check_evidence._verified_revision_is_current(
            "00edab4e4f6aeac395c9de3ab6a300162e56f6c1"
        )
        self.assertFalse(current)
        self.assertIn("src/ordivon_harness/ordivon/finance_research_runtime_bridge.py", invalidating)
        current, invalidating = check_evidence._verified_revision_is_current(
            "f4b05bb38ef7bff10f889df69611de6aaff3a40c"
        )
        self.assertFalse(current)
        self.assertIn(
            "src/ordivon_harness/ordivon/finance_observe_runtime_bridge.py",
            invalidating,
        )
        current, invalidating = check_evidence._verified_revision_is_current(
            "233bb6354f81eff070996cef898b91726857ca8e"
        )
        self.assertFalse(current)
        self.assertIn("src/ordivon_harness/capability_catalog.py", invalidating)
        current, invalidating = check_evidence._verified_revision_is_current(
            "e983c79f5582160b37ac56c1898efa80e486880d"
        )
        self.assertFalse(current)
        self.assertIn("pyproject.toml", invalidating)
        self.assertIn("uv.lock", invalidating)
        self.assertTrue(
            any(path.startswith("src/") for path in invalidating),
            invalidating,
        )
        current, invalidating = check_evidence._verified_revision_is_current(
            "830dd160b1025928521204f4713cbe0e1bbbf589"
        )
        self.assertFalse(current)
        self.assertIn("src/ordivon_harness/capability_discovery.py", invalidating)
        self.assertIn("src/ordivon_harness/interaction_context.py", invalidating)
        self.assertTrue(any(path.startswith("src/") for path in invalidating), invalidating)
        current, invalidating = check_evidence._verified_revision_is_current(
            "17e8943edb16c0f586d5a8d022c63590755a7d6b"
        )
        self.assertFalse(current)
        self.assertIn("pyproject.toml", invalidating)
        self.assertIn("uv.lock", invalidating)
        self.assertIn("src/ordivon_harness/ordivon/deepseek.py", invalidating)

    def test_index_creation_lineage_binding_accepts_exact_and_rejects_nonancestor(self) -> None:
        validator = check_evidence._validate_index_creation_lineage_binding
        for filename, _status, revision, _digest in EXPECTED.values():
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
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("evidence contract: valid", completed.stdout)


if __name__ == "__main__":
    unittest.main()
