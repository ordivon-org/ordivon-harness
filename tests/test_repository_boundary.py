from __future__ import annotations

from pathlib import Path
import tomllib
import unittest

import ordivon_host
import ordivon_harness
from ordivon_host.domain import EventKind
from ordivon_host.journal import HostJournal

from ordivon_harness.event_kinds import HARNESS_ASSIGNMENT_COMMITTED


class RepositoryBoundaryTests(unittest.TestCase):
    def test_dependency_direction_is_harness_to_host_only(self) -> None:
        self.assertFalse(hasattr(ordivon_host, "HarnessHost"))
        self.assertTrue(hasattr(ordivon_harness, "HarnessHost"))
        host_root = Path(ordivon_host.__file__).resolve().parent
        self.assertFalse((host_root / "harness").exists())

    def test_host_dependency_is_pinned_to_exact_event_admission_api(self) -> None:
        project = tomllib.loads(
            (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text()
        )["project"]
        host_dependencies = [
            value
            for value in project["dependencies"]
            if value.startswith("ordivon-host @ ")
        ]
        self.assertEqual(
            host_dependencies,
            [
                "ordivon-host @ "
                "git+https://github.com/zycxfyh/ordivon-host.git@"
                "ba5c56411edc4a4d222b66d5372c85fe9dcd261a"
            ],
        )
        self.assertTrue(hasattr(HostJournal, "event_object_references"))
        self.assertTrue(hasattr(HostJournal, "event_object_refs_start_sequence"))
        self.assertTrue(hasattr(HostJournal, "legacy_object_refs"))

    def test_harness_event_vocabulary_uses_host_extension_values(self) -> None:
        self.assertIs(
            HARNESS_ASSIGNMENT_COMMITTED,
            EventKind("harness.assignment-committed"),
        )
        self.assertEqual(
            HARNESS_ASSIGNMENT_COMMITTED.value,
            "harness.assignment-committed",
        )


if __name__ == "__main__":
    unittest.main()
