from __future__ import annotations

import ast
from pathlib import Path
import tomllib
import unittest

import ordivon_host
import ordivon_harness
from ordivon_host.domain import EventKind
from ordivon_host.journal import HostJournal

from ordivon_harness._host_compat import HOST_REQUIRED_SOURCE_REVISION
from ordivon_harness.event_kinds import HARNESS_ASSIGNMENT_COMMITTED


ROOT = Path(__file__).resolve().parents[1]


class RepositoryBoundaryTests(unittest.TestCase):
    def test_dependency_direction_is_harness_to_host_only(self) -> None:
        self.assertFalse(hasattr(ordivon_host, "HarnessHost"))
        self.assertTrue(hasattr(ordivon_harness, "HarnessHost"))
        host_root = Path(ordivon_host.__file__).resolve().parent
        self.assertFalse((host_root / "harness").exists())

    def test_host_dependency_and_lock_share_one_exact_revision(self) -> None:
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
        host_dependencies = [
            value
            for value in project["dependencies"]
            if value.startswith("ordivon-host @ ")
        ]
        expected = (
            "ordivon-host @ "
            "git+https://github.com/zycxfyh/ordivon-host.git@"
            f"{HOST_REQUIRED_SOURCE_REVISION}"
        )
        self.assertEqual(host_dependencies, [expected])
        lock = (ROOT / "uv.lock").read_text()
        self.assertIn(f"rev={HOST_REQUIRED_SOURCE_REVISION}", lock)
        self.assertIn(f"#{HOST_REQUIRED_SOURCE_REVISION}", lock)
        self.assertTrue(hasattr(HostJournal, "event_object_references"))
        self.assertTrue(hasattr(HostJournal, "event_object_refs_start_sequence"))
        self.assertTrue(hasattr(HostJournal, "legacy_object_refs"))

    def test_raw_host_imports_are_centralized_in_private_compat_package(self) -> None:
        source_root = ROOT / "src" / "ordivon_harness"
        violations: list[str] = []
        for path in source_root.rglob("*.py"):
            relative = path.relative_to(source_root)
            if relative.parts and relative.parts[0] == "_host_compat":
                continue
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    if node.module == "ordivon_host" or node.module.startswith(
                        "ordivon_host."
                    ):
                        violations.append(f"{relative}:{node.lineno}:{node.module}")
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "ordivon_host" or alias.name.startswith(
                            "ordivon_host."
                        ):
                            violations.append(f"{relative}:{node.lineno}:{alias.name}")
        self.assertEqual(violations, [])

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
