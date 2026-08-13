from __future__ import annotations

import unittest

from anc_canonical import canonical_digest

from ordivon_harness.agent_tool_observation import HarnessToolObservation
from ordivon_harness.ordivon.model import AgentToolCall, AgentToolDefinition
from ordivon_harness.tool_program import (
    HarnessToolProgram,
    HarnessToolProgramAction,
    HarnessToolProgramExecutor,
    HarnessToolProgramStep,
    observation_ref,
    project_tool_program_action_capability,
)


READ = AgentToolDefinition(
    "read_value",
    "Read one value.",
    {
        "type": "object",
        "additionalProperties": False,
        "properties": {"key": {"type": "string"}},
        "required": ["key"],
    },
)
LOOKUP = AgentToolDefinition(
    "lookup_value",
    "Lookup a value by an exact query.",
    {
        "type": "object",
        "additionalProperties": False,
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
)
WRITE = AgentToolDefinition(
    "write_value",
    "Mutate one value.",
    {
        "type": "object",
        "additionalProperties": False,
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
    },
)


class Bridge:
    catalog_digest = canonical_digest({"tools": ["read_value", "lookup_value", "write_value"]})

    def __init__(self, *, stop_on: str | None = None, stop_status: str = "unknown") -> None:
        self.calls: list[tuple[AgentToolCall, str]] = []
        self.stop_on = stop_on
        self.stop_status = stop_status

    def definitions(self):
        return (READ, LOOKUP, WRITE)

    def execute(self, call: AgentToolCall, *, step_id: str) -> HarnessToolObservation:
        self.calls.append((call, step_id))
        if call.name == self.stop_on:
            return HarnessToolObservation(
                tool_call_id=call.tool_call_id,
                tool_name=call.name,
                status=self.stop_status,
                structured_content={"terminal": self.stop_status},
            )
        if call.name == "read_value":
            content = {"value": "needle", "digest": "sha256:" + "a" * 64}
        elif call.name == "lookup_value":
            content = {"query": call.arguments["query"], "matches": ["m1", "m2"]}
        elif call.name == "write_value":
            content = {"written": call.arguments["value"]}
        else:
            raise AssertionError(call.name)
        return HarnessToolObservation(
            tool_call_id=call.tool_call_id,
            tool_name=call.name,
            status="observed",
            structured_content=content,
        )


def dependent_program() -> HarnessToolProgram:
    return HarnessToolProgram(
        steps=(
            HarnessToolProgramStep("read", "read_value", {"key": "source"}),
            HarnessToolProgramStep(
                "lookup",
                "lookup_value",
                {"query": observation_ref("read", "value")},
            ),
        ),
        outputs={
            "query": observation_ref("lookup", "query"),
            "matches": observation_ref("lookup", "matches"),
            "sourceDigest": observation_ref("read", "digest"),
        },
    )


class ToolProgramP2Tests(unittest.TestCase):
    def test_round_trip_digest_and_prior_observation_dataflow_are_deterministic(self) -> None:
        program = dependent_program()
        self.assertEqual(HarnessToolProgram.from_dict(program.to_dict()), program)
        self.assertEqual(program.digest, HarnessToolProgram.from_dict(program.to_dict()).digest)

        bridge = Bridge()
        result = HarnessToolProgramExecutor(bridge, (READ, LOOKUP)).execute(
            program,
            remaining_tool_calls=2,
            step_prefix="turn-p2",
        )
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.output["query"], "needle")
        self.assertEqual(result.output["matches"], ["m1", "m2"])
        self.assertEqual(bridge.calls[1][0].arguments, {"query": "needle"})
        self.assertTrue(bridge.calls[0][0].tool_call_id.startswith("tool-call:program:"))
        self.assertNotEqual(bridge.calls[0][0].tool_call_id, bridge.calls[1][0].tool_call_id)

    def test_program_cannot_reference_future_or_unknown_observation(self) -> None:
        with self.assertRaisesRegex(ValueError, "already completed prior step"):
            HarnessToolProgram(
                steps=(
                    HarnessToolProgramStep(
                        "first",
                        "lookup_value",
                        {"query": observation_ref("later", "value")},
                    ),
                    HarnessToolProgramStep("later", "read_value", {"key": "x"}),
                ),
                outputs={},
            )
        with self.assertRaisesRegex(ValueError, "unknown step"):
            HarnessToolProgram(
                steps=(HarnessToolProgramStep("read", "read_value", {"key": "x"}),),
                outputs={"x": observation_ref("missing", "value")},
            )

    def test_program_cannot_expand_exact_turn_tool_authority(self) -> None:
        bridge = Bridge()
        program = HarnessToolProgram(
            steps=(HarnessToolProgramStep("write", "write_value", {"value": "x"}),),
            outputs={},
        )
        with self.assertRaisesRegex(ValueError, "not admitted on the exact turn"):
            HarnessToolProgramExecutor(bridge, (READ, LOOKUP)).execute(
                program,
                remaining_tool_calls=1,
                step_prefix="turn-p2",
            )
        self.assertEqual(bridge.calls, [])

    def test_program_requires_budget_for_every_physical_tool_before_dispatch(self) -> None:
        bridge = Bridge()
        with self.assertRaisesRegex(ValueError, "remaining Tool Call budget"):
            HarnessToolProgramExecutor(bridge, (READ, LOOKUP)).execute(
                dependent_program(),
                remaining_tool_calls=1,
                step_prefix="turn-p2",
            )
        self.assertEqual(bridge.calls, [])

    def test_unknown_stops_program_and_never_dispatches_pending_step(self) -> None:
        bridge = Bridge(stop_on="lookup_value", stop_status="unknown")
        program = HarnessToolProgram(
            steps=(
                *dependent_program().steps,
                HarnessToolProgramStep("write", "write_value", {"value": "must-not-run"}),
            ),
            outputs={"never": observation_ref("write", "written")},
        )
        result = HarnessToolProgramExecutor(bridge, (READ, LOOKUP, WRITE)).execute(
            program,
            remaining_tool_calls=3,
            step_prefix="turn-p2",
        )
        self.assertEqual(result.status, "unknown")
        self.assertEqual([call.name for call, _ in bridge.calls], ["read_value", "lookup_value"])
        self.assertEqual(result.output, {})

    def test_model_projection_keeps_exact_step_evidence_but_not_intermediate_content(self) -> None:
        result = HarnessToolProgramExecutor(Bridge(), (READ, LOOKUP)).execute(
            dependent_program(),
            remaining_tool_calls=2,
            step_prefix="turn-p2",
        )
        projection = result.to_model_projection()
        self.assertEqual(projection["output"], result.output)
        self.assertEqual(len(projection["steps"]), 2)
        encoded = repr(projection)
        self.assertNotIn("'value': 'needle'", encoded)
        self.assertIn("observationDigest", encoded)

    def test_references_are_exact_value_substitution_not_string_code(self) -> None:
        program = HarnessToolProgram(
            steps=(
                HarnessToolProgramStep("read", "read_value", {"key": "source"}),
                HarnessToolProgramStep(
                    "lookup",
                    "lookup_value",
                    {"query": observation_ref("read", "value")},
                ),
            ),
            outputs={"digest": observation_ref("read", "digest")},
        )
        result = HarnessToolProgramExecutor(Bridge(), (READ, LOOKUP)).execute(
            program,
            remaining_tool_calls=2,
            step_prefix="turn-p2",
        )
        self.assertEqual(result.output["digest"], "sha256:" + "a" * 64)

    def test_native_action_envelope_counts_inner_physical_tools_and_is_not_runtime_tool(self) -> None:
        action = HarnessToolProgramAction(
            action_call_id="program-action:p2:1",
            program=dependent_program(),
        )
        self.assertEqual(action.physical_tool_calls, 2)
        self.assertEqual(HarnessToolProgramAction.from_dict(action.to_dict()), action)
        self.assertNotEqual(action.physical_tool_calls, 1)

        capability = project_tool_program_action_capability(
            admitted_tools=(READ, LOOKUP),
            remaining_tool_calls=1,
        )
        self.assertFalse(capability["runtimeTool"])
        self.assertEqual(capability["maxProgramSteps"], 1)
        self.assertEqual(
            capability["physicalToolAccounting"],
            "one-existing-tool-budget-unit-per-program-step",
        )
        self.assertEqual(capability["admittedToolNames"], ["lookup_value", "read_value"])

    def test_action_round_trip_rejects_forged_physical_tool_count(self) -> None:
        raw = HarnessToolProgramAction(
            action_call_id="program-action:p2:forged-count",
            program=dependent_program(),
        ).to_dict()
        raw["physicalToolCalls"] = 1
        with self.assertRaisesRegex(ValueError, "physical Tool count differs"):
            HarnessToolProgramAction.from_dict(raw)


if __name__ == "__main__":
    unittest.main()
