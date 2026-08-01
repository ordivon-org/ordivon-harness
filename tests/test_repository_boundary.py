from __future__ import annotations

from pathlib import Path
import unittest

import ordivon_host
import ordivon_harness
from ordivon_host.domain import EventKind

from ordivon_harness.event_kinds import HARNESS_ASSIGNMENT_COMMITTED


class RepositoryBoundaryTests(unittest.TestCase):
    def test_dependency_direction_is_harness_to_host_only(self) -> None:
        self.assertFalse(hasattr(ordivon_host, "HarnessHost"))
        self.assertTrue(hasattr(ordivon_harness, "HarnessHost"))
        host_root = Path(ordivon_host.__file__).resolve().parent
        self.assertFalse((host_root / "harness").exists())

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
