from __future__ import annotations

import hashlib
import json
import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT / "research" / "authority" / "CURRENT.json"
OWNER = "research-owner:harness"
AUTHORITY = "authority:ordivon:research-owner:harness"


class ResearchOwnerPublicationTests(unittest.TestCase):
    def _publication(self) -> tuple[dict[str, object], dict[str, object], Path]:
        current = json.loads(CURRENT.read_text(encoding="utf-8"))
        publication_path = ROOT / "research" / current["publication"]
        publication = json.loads(publication_path.read_text(encoding="utf-8"))
        return current, publication, publication_path

    def test_current_pointer_binds_exact_immutable_publication(self) -> None:
        current, _publication, publication_path = self._publication()
        self.assertEqual(current["schemaVersion"], 1)
        self.assertEqual(current["kind"], "ordivon.research-owner-current")
        self.assertEqual(current["ownerResearchRef"], OWNER)
        self.assertEqual(current["authorityRef"], AUTHORITY)
        self.assertTrue(str(current["publication"]).startswith("authority/publications/"))
        self.assertNotIn("..", Path(str(current["publication"])).parts)

        payload = publication_path.read_bytes()
        observed = "sha256:" + hashlib.sha256(payload).hexdigest()
        self.assertEqual(observed, current["currentAuthorityVersionRef"])
        self.assertEqual(
            publication_path.name,
            str(current["currentAuthorityVersionRef"]).removeprefix("sha256:") + ".json",
        )

    def test_publication_preserves_owner_native_recovery_and_boundaries(self) -> None:
        _current, publication, _path = self._publication()
        self.assertEqual(publication["kind"], "ordivon.research-owner-publication")
        self.assertEqual(publication["ownerResearchRef"], OWNER)
        self.assertEqual(publication["authorityRef"], AUTHORITY)
        self.assertEqual(
            publication["currentRecovery"],
            {"locator": "research/README.md", "targetRole": "OWNER_RESEARCH_CORPUS"},
        )
        self.assertTrue((ROOT / publication["currentRecovery"]["locator"]).is_file())

        source = publication["source"]
        self.assertEqual(source["corpusRoot"], "research")
        self.assertEqual(source["authorityBranch"], "refs/heads/main")
        self.assertRegex(source["sourceRevision"], re.compile(r"^[0-9a-f]{40}$"))
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", source["sourceRevision"], "HEAD"],
            cwd=ROOT,
            check=True,
        )

        closeout = publication["closeouts"][0]
        closure = {item["scope"]: item["status"] for item in closeout["closure"]}
        self.assertEqual(closure["HaF0-HaF61"], "FROZEN_CURRENT")
        self.assertEqual(closure["HaF62"], "NOT_ADMITTED")
        self.assertEqual(closure["CAMPAIGN_7"], "NOT_SELECTED")
        self.assertEqual(closure["POST_HTTPX_EVIDENCE_CURRENTNESS_REPAIR_155"], "ACCEPTED")
        self.assertIn("EVIDENCE_77_HISTORICAL_0_VERIFIED", closeout["residualState"])

    def test_result_standing_is_explicit_and_does_not_invent_next_foundation(self) -> None:
        _current, publication, _path = self._publication()
        statements = {
            (item.get("subjectRef"), item.get("predicate")): item.get("value")
            for item in publication["statements"]
        }
        self.assertEqual(statements[(OWNER, "CANONICAL_NAME")], "Ordivon Harness")
        self.assertEqual(
            statements[(OWNER, "CANONICAL_REFERENT")], "Agent Operational Mediation"
        )
        self.assertTrue(
            statements[("result:harness:haf62-not-admitted", "STANDING:NOT_ADMITTED")]
        )
        self.assertTrue(
            statements[("result:harness:campaign7-not-selected", "STANDING:NOT_SELECTED")]
        )
        self.assertTrue(
            statements[("result:harness:post-httpx-evidence-currentness-repair", "STANDING:CURRENT")]
        )

    def test_research_root_declares_publication_as_projection_not_second_authority(self) -> None:
        research_root = (ROOT / "research" / "README.md").read_text(encoding="utf-8")
        authority = (ROOT / "docs" / "authority.md").read_text(encoding="utf-8")
        self.assertIn("research/authority/CURRENT.json", research_root)
        self.assertIn("not a second research corpus", research_root)
        self.assertIn(OWNER, research_root)
        self.assertIn("projection only", authority)
        self.assertIn("does not make Atlas", authority)


if __name__ == "__main__":
    unittest.main()
