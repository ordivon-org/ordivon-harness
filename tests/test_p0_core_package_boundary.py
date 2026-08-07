from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class HarnessCorePackageBoundaryTests(unittest.TestCase):
    def run_probe(self, statement: str) -> dict[str, object]:
        completed = subprocess.run(
            [sys.executable, "-c", statement],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)

    def test_package_root_and_core_do_not_eagerly_load_host(self) -> None:
        observed = self.run_probe(
            "import json,sys,ordivon_harness; "
            "root_loaded=any(k=='ordivon_host' or k.startswith('ordivon_host.') for k in sys.modules); "
            "import ordivon_harness.core as core; "
            "core_loaded=any(k=='ordivon_host' or k.startswith('ordivon_host.') for k in sys.modules); "
            "print(json.dumps({'rootLoadedHost':root_loaded,'coreLoadedHost':core_loaded,"
            "'hasStandalone':'StandaloneHarnessRunner' in core.__all__}))"
        )
        self.assertFalse(observed["rootLoadedHost"])
        self.assertFalse(observed["coreLoadedHost"])
        self.assertTrue(observed["hasStandalone"])

    def test_host_compatibility_export_remains_lazy_and_available(self) -> None:
        observed = self.run_probe(
            "import json,sys,ordivon_harness; "
            "before=any(k=='ordivon_host' or k.startswith('ordivon_host.') for k in sys.modules); "
            "runner=ordivon_harness.HarnessRunner; "
            "after=any(k=='ordivon_host' or k.startswith('ordivon_host.') for k in sys.modules); "
            "print(json.dumps({'before':before,'after':after,'name':runner.__name__}))"
        )
        self.assertFalse(observed["before"])
        self.assertTrue(observed["after"])
        self.assertEqual(observed["name"], "HarnessRunner")

    def test_independent_modules_have_no_host_compatibility_imports(self) -> None:
        package = ROOT / "src" / "ordivon_harness"
        paths = (
            "core.py",
            "run_state.py",
            "standalone.py",
            "independent_result.py",
            "independent_cli.py",
            "ordivon/tool_bridge.py",
            "ordivon/loop.py",
            "ordivon/run_recovery.py",
            "ordivon/runtime_lowering.py",
            "ordivon/sqlite_agent_bridge.py",
            "ordivon/sqlite_run_store.py",
            "ordivon/sqlite_runtime_bridge.py",
        )
        for relative in paths:
            with self.subTest(relative=relative):
                source = (package / relative).read_text(encoding="utf-8")
                self.assertNotIn("ordivon_host", source)
                self.assertNotIn("_host_compat", source)


if __name__ == "__main__":
    unittest.main()
