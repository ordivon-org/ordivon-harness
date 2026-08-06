from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from anc_canonical import canonical_digest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/check_repository_repair_edit_runtime_receipt.py"
RECEIPT = REPO / "evidence/repository-repair-edit-runtime-bridge-dd50136.json"
INDEX = REPO / "evidence/index.json"

spec = importlib.util.spec_from_file_location(
    "ordivon_repository_repair_edit_runtime_receipt",
    SCRIPT,
)
assert spec and spec.loader
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def write_tampered(value: dict, root: str) -> Path:
    result = copy.deepcopy(value)
    payload = dict(result)
    payload.pop("integrity")
    result["integrity"]["payloadDigest"] = canonical_digest(payload)
    path = Path(root) / "tampered.json"
    path.write_text(json.dumps(result), encoding="utf-8")
    return path


class RepositoryRepairEditRuntimeReceiptTests(unittest.TestCase):
    def test_committed_receipt_and_index_bind_exact_v2_boundary(self) -> None:
        receipt = checker.validate_receipt(RECEIPT)
        self.assertEqual(
            receipt["implementationRevision"],
            "dd50136ef722b9df3dfb0fef195fcc1a137fd8ed",
        )
        self.assertTrue(receipt["harnessClean"])
        self.assertEqual(receipt["runtimeJobCount"], 1)
        self.assertEqual(receipt["toolCalls"], 6)
        self.assertTrue(all(receipt["checks"].values()))
        self.assertFalse(receipt["productionActivated"])
        self.assertFalse(receipt["b6Implemented"])
        index = json.loads(INDEX.read_text(encoding="utf-8"))
        entry = next(
            item
            for item in index["entries"]
            if item["claimId"]
            == "harness.repository-repair-edit-runtime-bridge.v2"
        )
        old_entry = next(
            item
            for item in index["entries"]
            if item["claimId"]
            == "harness.repository-repair-runtime-bridge.b4-b5"
        )
        self.assertEqual(old_entry["status"], "historical")
        self.assertEqual(
            old_entry["implementationRevision"],
            "b23d5fa6c820c10f937f48cc16c2d8e03d3e18ae",
        )
        self.assertIn("Historical frozen B4/B5", old_entry["scope"])
        self.assertEqual(
            entry,
            {
                "claimId": "harness.repository-repair-edit-runtime-bridge.v2",
                "file": "repository-repair-edit-runtime-bridge-dd50136.json",
                "status": "verified",
                "implementationRevision": (
                    "dd50136ef722b9df3dfb0fef195fcc1a137fd8ed"
                ),
                "scope": (
                    "Separate Agent-friendly exact-replace and completion-file "
                    "creation surface over durable Runtime Patch identity, "
                    "reconciliation, visible Check, diff, reread and closed "
                    "Workspace; does not resume frozen B5"
                ),
            },
        )

    def test_failed_check_is_rejected_after_integrity_recomputation(self) -> None:
        value = json.loads(RECEIPT.read_text(encoding="utf-8"))
        value["checks"]["visibleCheckSucceeded"] = False
        with tempfile.TemporaryDirectory() as temporary:
            path = write_tampered(value, temporary)
            with self.assertRaisesRegex(ValueError, "acceptance checks failed"):
                checker.validate_receipt(path)

    def test_revision_and_tool_contract_drift_are_rejected(self) -> None:
        receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        cases = (
            ("implementationRevision", "a" * 40, "implementation revision"),
            ("toolSurfaceDigest", "sha256:" + "b" * 64, "surface digest"),
            ("toolGrantDigest", "sha256:" + "c" * 64, "grant digest"),
        )
        for field, value, message in cases:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                tampered = copy.deepcopy(receipt)
                tampered[field] = value
                path = write_tampered(tampered, temporary)
                with self.assertRaisesRegex(ValueError, message):
                    checker.validate_receipt(path)

    def test_production_b6_or_workspace_drift_is_rejected(self) -> None:
        receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        cases = (
            ("productionActivated", True, "must not activate production"),
            ("b6Implemented", True, "must not claim B6"),
            ("workspaceClosed", False, "Workspace was not closed"),
        )
        for field, value, message in cases:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                tampered = copy.deepcopy(receipt)
                tampered[field] = value
                path = write_tampered(tampered, temporary)
                with self.assertRaisesRegex(ValueError, message):
                    checker.validate_receipt(path)

    def test_frozen_b5_limit_cannot_be_removed(self) -> None:
        receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        receipt["knownLimits"].remove(
            "This V2 receipt does not resume or alter the frozen B5 comparison campaign"
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = write_tampered(receipt, temporary)
            with self.assertRaisesRegex(ValueError, "known limits differ"):
                checker.validate_receipt(path)


if __name__ == "__main__":
    unittest.main()
