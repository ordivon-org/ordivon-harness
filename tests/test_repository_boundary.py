from __future__ import annotations

import ast
from pathlib import Path
import tomllib
import unittest

import ordivon_harness
from ordivon_harness.store import HARNESS_STORE_EVENT_KINDS

ROOT = Path(__file__).resolve().parents[1]


class RepositoryBoundaryTests(unittest.TestCase):
    def test_harness_has_no_host_dependency_or_compatibility_package(self) -> None:
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())
        requirements = project["project"]["dependencies"]
        self.assertEqual(len(requirements), 3)
        self.assertIn("httpx==0.28.1", requirements)
        self.assertIn("jsonschema>=4.26,<5", requirements)
        self.assertEqual(
            sum(requirement.startswith("ordivon-protocol @ ") for requirement in requirements),
            1,
        )
        self.assertNotIn("optional-dependencies", project["project"])
        self.assertNotIn("dependency-groups", project)
        package = ROOT / "src" / "ordivon_harness"
        self.assertFalse((package / "_host_compat").exists())
        self.assertFalse((package / "host.py").exists())
        self.assertFalse((package / "runner.py").exists())
        self.assertFalse((package / "cutover.py").exists())
        self.assertFalse(hasattr(ordivon_harness, "HarnessHost"))
        self.assertFalse(hasattr(ordivon_harness, "HarnessRunner"))

    def test_source_tree_contains_no_ordivon_host_imports(self) -> None:
        source_root = ROOT / "src" / "ordivon_harness"
        violations: list[str] = []
        for path in source_root.rglob("*.py"):
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    if node.module == "ordivon_host" or node.module.startswith("ordivon_host."):
                        violations.append(f"{path.relative_to(source_root)}:{node.lineno}")
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "ordivon_host" or alias.name.startswith("ordivon_host."):
                            violations.append(f"{path.relative_to(source_root)}:{node.lineno}")
        self.assertEqual(violations, [])

    def test_harness_store_owns_its_event_vocabulary(self) -> None:
        self.assertIn("harness.run-created", HARNESS_STORE_EVENT_KINDS)
        self.assertIn("harness.provider-call-claimed", HARNESS_STORE_EVENT_KINDS)
        self.assertIn("harness.tool-step-prepared", HARNESS_STORE_EVENT_KINDS)


if __name__ == "__main__":
    unittest.main()
