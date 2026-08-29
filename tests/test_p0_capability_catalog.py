from __future__ import annotations

from dataclasses import fields
import tempfile
import unittest
from pathlib import Path

from ordivon_harness.api import HarnessAgentRun, HarnessCognitionProfile
from ordivon_harness.capability_catalog import (
    effective_capability_catalog,
    effective_capability_catalog_digest,
    project_turn_capabilities,
)
from ordivon_harness.ordivon.model import AgentTurnCapabilities, ScriptedTurnAdapter
from ordivon_harness.ordivon.sqlite_agent_bridge import (
    NO_TOOL_AGENT_GRANT_DIGEST,
    NO_TOOL_AGENT_SURFACE_DIGEST,
)
from ordivon_harness.ordivon.sqlite_repository_repair_bridge import (
    INDEPENDENT_REPOSITORY_REPAIR_EDIT_TOOL_GRANT_DIGEST,
    INDEPENDENT_REPOSITORY_REPAIR_EDIT_TOOL_SURFACE_DIGEST,
    INDEPENDENT_REPOSITORY_REPAIR_TOOL_GRANT_DIGEST,
    INDEPENDENT_REPOSITORY_REPAIR_TOOL_SURFACE_DIGEST,
)
from ordivon_harness.ordivon.sqlite_runtime_bridge import (
    INDEPENDENT_SEARCH_TOOL_GRANT_DIGEST,
    INDEPENDENT_SEARCH_TOOL_SURFACE_DIGEST,
)

from tests.test_r1_single_capability_truth import request
from tests.test_r3_supported_agent_run import (
    FakeRuntime,
    FixedClock,
    contract,
    execution_binding,
    needs_input,
)


class CapabilityCatalogTests(unittest.TestCase):
    def test_catalog_is_source_derived_and_separates_supported_from_specialized(self) -> None:
        catalog = effective_capability_catalog()
        self.assertTrue(effective_capability_catalog_digest().startswith("sha256:"))
        surfaces = {item["surfaceId"]: item for item in catalog["executionSurfaces"]}
        expected = {
            "harness.execution.no-tool.v1": (
                NO_TOOL_AGENT_SURFACE_DIGEST,
                NO_TOOL_AGENT_GRANT_DIGEST,
                True,
            ),
            "harness.execution.runtime-search.v1": (
                INDEPENDENT_SEARCH_TOOL_SURFACE_DIGEST,
                INDEPENDENT_SEARCH_TOOL_GRANT_DIGEST,
                True,
            ),
            "harness.execution.repository-repair.v1": (
                INDEPENDENT_REPOSITORY_REPAIR_TOOL_SURFACE_DIGEST,
                INDEPENDENT_REPOSITORY_REPAIR_TOOL_GRANT_DIGEST,
                False,
            ),
            "harness.execution.repository-repair-edit.v2": (
                INDEPENDENT_REPOSITORY_REPAIR_EDIT_TOOL_SURFACE_DIGEST,
                INDEPENDENT_REPOSITORY_REPAIR_EDIT_TOOL_GRANT_DIGEST,
                False,
            ),
        }
        self.assertEqual(set(surfaces), set(expected))
        for surface_id, (catalog_digest, grant_digest, supported) in expected.items():
            with self.subTest(surface_id=surface_id):
                surface = surfaces[surface_id]
                self.assertEqual(surface["toolCatalogDigest"], catalog_digest)
                self.assertEqual(surface["toolGrantDigest"], grant_digest)
                self.assertEqual(surface["supportedByHarnessAgentRun"], supported)
                self.assertEqual(surface["stage"], "installed")
                self.assertIn("source", surface)
                self.assertNotEqual(surface["authorityRole"], "authority-granted")
        self.assertEqual(
            surfaces["harness.execution.runtime-search.v1"]["requirements"]["runtimeExecutables"],
            {
                "bash": "/bin/bash",
                "awk": "/usr/bin/awk",
                "ripgrep": "/usr/bin/rg",
            },
        )

    def test_cognition_catalog_tracks_current_structural_fields(self) -> None:
        catalog = effective_capability_catalog()
        mechanisms = catalog["cognitionMechanisms"]
        request_fields = {item["requestField"] for item in mechanisms}
        self.assertEqual(
            request_fields,
            {item.name for item in fields(AgentTurnCapabilities)} - {"tool_program"},
        )
        self.assertEqual(
            catalog["programmaticToolComposition"]["modelAction"],
            "compose_tool_program",
        )
        self.assertFalse(catalog["programmaticToolComposition"]["runtimeTool"])
        observation = catalog["sourceFencedObservationComposition"]
        self.assertEqual(observation["stage"], "installed")
        self.assertEqual(observation["visibility"], "advanced-opt-in")
        self.assertEqual(observation["grantIdentity"], "caller-bound-dynamic-source-fence")
        self.assertFalse(observation["workspaceMutationAllowed"])
        self.assertFalse(observation["harnessMintsOwnerTruth"])
        profile_fields = {
            item["profileField"]
            for item in mechanisms
            if item["profileField"] is not None
        }
        self.assertEqual(profile_fields, {item.name for item in fields(HarnessCognitionProfile)})

    def test_installed_mechanism_does_not_expand_exact_turn_authority(self) -> None:
        projection = project_turn_capabilities(request())
        self.assertEqual(projection["stage"], "turn-admitted")
        self.assertEqual(projection["nativeActions"], ["conclusion"])
        self.assertFalse(projection["callerIngressAddressable"])
        self.assertNotIn("same exact cognition", repr(projection))

        expanded = project_turn_capabilities(
            request(
                capabilities=AgentTurnCapabilities(
                    conclusion=True,
                    working_set_transition=True,
                    caller_ingress_promotion=False,
                    working_set_history=True,
                )
            )
        )
        self.assertEqual(
            expanded["nativeActions"],
            ["conclusion", "working-set-transition", "working-set-history"],
        )

    def test_in_process_explain_reports_supplied_objects_without_liveness_claims(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clock = FixedClock()
            value = contract("p0-explain")
            run = HarnessAgentRun.create(
                Path(directory) / "state",
                value,
                lambda _contract: ScriptedTurnAdapter((needs_input("model-call:p0-explain"),)),
                clock_ms=clock,
                monotonic_ms=clock,
            )
            explanation = run.explain()
            process = explanation["processLocal"]
            self.assertFalse(process["runtimeClient"]["supplied"])
            self.assertEqual(process["runtimeClient"]["liveness"], "not-probed")
            self.assertEqual(process["adapter"]["liveness"], "not-probed")
            self.assertEqual(
                explanation["run"]["toolSurface"]["surfaceId"],
                "harness.execution.no-tool.v1",
            )

        with tempfile.TemporaryDirectory() as directory:
            value = contract("p0-runtime-explain", tools=True)
            run = HarnessAgentRun.create(
                Path(directory) / "state",
                value,
                lambda _contract: ScriptedTurnAdapter((needs_input("model-call:p0-runtime"),)),
                execution_binding=execution_binding(value),
                runtime=FakeRuntime(),
            )
            explanation = run.explain()
            process = explanation["processLocal"]
            self.assertTrue(process["runtimeClient"]["supplied"])
            self.assertEqual(process["runtimeClient"]["liveness"], "not-probed")
            self.assertTrue(process["executionBinding"]["supplied"])
            self.assertEqual(
                explanation["run"]["toolSurface"]["surfaceId"],
                "harness.execution.runtime-search.v1",
            )


if __name__ == "__main__":
    unittest.main()
