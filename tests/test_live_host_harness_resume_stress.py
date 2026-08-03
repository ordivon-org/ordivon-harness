from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "live_host_harness_resume_stress.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "live_host_harness_resume_stress", _SCRIPT
)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


class LiveHostHarnessResumeStressTests(unittest.TestCase):
    @staticmethod
    def _result(model_id: str, suffix: str):
        return _MODULE._result(
            model_id,
            suffix,
            conclusion=_MODULE.AgentRunConclusion(
                status="needs_input",
                summary="Pause for scripted identity verification.",
                unresolved_unknowns=("scripted identity verification",),
            ),
        )

    def test_scripted_results_use_selected_model_identity(self) -> None:
        for model_id in ("deepseek-v4-flash", "deepseek-v4-pro"):
            with self.subTest(model_id=model_id):
                result = self._result(model_id, "identity-check")
                adapter = _MODULE._scripted_adapter(model_id, (result,))

                self.assertEqual(adapter.model_id, model_id)
                self.assertEqual(adapter.invoke(object()).model_id, model_id)

    def test_scripted_adapter_rejects_mixed_model_identity(self) -> None:
        result = self._result("deepseek-v4-pro", "identity-mismatch")

        with self.assertRaisesRegex(ValueError, "model identity"):
            _MODULE._scripted_adapter("deepseek-v4-flash", (result,))


if __name__ == "__main__":
    unittest.main()
