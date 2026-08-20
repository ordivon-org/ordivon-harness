from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from anc_canonical import canonical_digest

from ordivon_harness.api import (
    AgentTurnResult,
    HarnessBoundReference,
    HarnessExecutionBinding,
    HarnessPrivacyPolicy,
    HarnessRunContract,
    HarnessRuntimeReference,
)
from ordivon_harness.observation_tool_surface import (
    OBSERVATION_TOOL_SURFACE_DIGEST,
    HarnessObservationAuthorityStatementProjection,
    HarnessObservationReadObject,
    HarnessObservationSourceAuthority,
    HarnessObservationToolGrant,
    build_observation_tool_surface,
)
from ordivon_harness.ordivon.model import AgentRunConclusion, AgentToolCall, ScriptedTurnAdapter


def digest(label: str) -> str:
    return canonical_digest({"observation-surface": label})


def contract(suffix: str, grant: HarnessObservationToolGrant) -> HarnessRunContract:
    return HarnessRunContract(
        harness_run_id=f"harness-run:observation-{suffix}",
        harness_implementation_id="ordivon-harness@observation-read-v1",
        caller_id="caller:observation-test",
        caller_run_ref=f"trial:observation-{suffix}",
        objective_ref=HarnessBoundReference("objective:observation", "objective", digest("objective")),
        context_refs=(HarnessBoundReference("context:observation", "context", digest("context")),),
        provider_id="provider:scripted",
        adapter_id=ScriptedTurnAdapter.adapter_id,
        requested_model_id=ScriptedTurnAdapter.model_id,
        tool_catalog_digest=OBSERVATION_TOOL_SURFACE_DIGEST,
        tool_grant_digest=grant.digest,
        budget={
            "maxModelCalls": 5,
            "maxToolCalls": 3,
            "maxObservationBytes": 65536,
            "maxWallTimeMs": 10000,
            "maxTotalTokens": 10000,
            "maxModelRetries": 1,
            "maxToolCorrections": 2,
            "maxConclusionCorrections": 2,
            "maxObservationOnlyTurns": 4,
            "maxNoProgressTurns": 3,
        },
        completion_contract={"mode": "record"},
        system_manifest_ref=HarnessBoundReference(
            "manifest:observation", "system-manifest", digest("manifest")
        ),
        created_at_ms=1000,
        privacy=HarnessPrivacyPolicy(
            content_policy="bounded-private-content",
            allow_model_content=True,
            allow_tool_content=True,
        ),
    )


def source_authority() -> HarnessObservationSourceAuthority:
    return HarnessObservationSourceAuthority(
        owner_research_ref="research-owner:human",
        authority_ref="authority:ordivon:research-owner:human",
        authority_version_ref=digest("human-authority-version"),
        source_transport_revision="transport-human-v1",
    )


def binding(
    value: HarnessRunContract,
    authority: HarnessObservationSourceAuthority | None = None,
) -> HarnessExecutionBinding:
    token = value.digest[7:31]
    references = [
        HarnessRuntimeReference(
            namespace="ordivon.harness",
            reference_type="harness_run",
            reference_id=value.harness_run_id,
            generation="1",
            digest=value.digest,
        ),
    ]
    if authority is not None:
        references.append(
            HarnessRuntimeReference(
                namespace="ordivon.harness",
                reference_type="source_authority",
                reference_id=authority.authority_ref,
                generation=authority.source_transport_revision,
                digest=authority.authority_version_ref,
            )
        )
    references.sort(key=lambda item: item.sort_key)
    return HarnessExecutionBinding(
        harness_run_id=value.harness_run_id,
        workspace_ref="workspace:observation-source",
        assignment_id=f"assignment:external:{token}",
        assignment_generation=1,
        assignment_digest=value.digest,
        runtime_binding_digest=digest("runtime-binding"),
        tool_catalog_digest=value.tool_catalog_digest,
        tool_grant_digest=value.tool_grant_digest,
        deadline_ms=value.deadline_ms,
        runtime_references=tuple(references),
    )


def tool_turn(call_id: str, name: str, arguments: dict) -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id=f"model-call:{call_id}",
        model_id=ScriptedTurnAdapter.model_id,
        content=name,
        tool_calls=(AgentToolCall(f"tool-call:{call_id}", name, arguments),),
        conclusion=None,
        usage={"inputTokens": 1, "outputTokens": 1},
        finish_reason="tool_calls",
        raw_response_digest=digest(call_id),
    )


def completed() -> AgentTurnResult:
    return AgentTurnResult(
        model_call_id="model-call:observation-done",
        model_id=ScriptedTurnAdapter.model_id,
        content="standing recovered",
        tool_calls=(),
        conclusion=AgentRunConclusion(
            status="candidate_completed",
            summary="Recovered standing from exact source-fenced object.",
        ),
        usage={"inputTokens": 1, "outputTokens": 1},
        finish_reason="stop",
        raw_response_digest=digest("done"),
    )


class FakeRuntime:
    def __init__(self, source_content: str, source_digest: str):
        self.source_content = source_content
        self.source_digest = source_digest
        self.calls: list[tuple[str, dict]] = []

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "workspace.exec":
            match = {
                "type": "match",
                "data": {
                    "path": {"text": "source/standing.json"},
                    "lines": {"text": "STANDING:HISTORICAL_PRESERVED=true\n"},
                    "line_number": 1,
                    "absolute_offset": 0,
                    "submatches": [{"match": {"text": "HISTORICAL_PRESERVED"}, "start": 9, "end": 29}],
                },
            }
            unbound = {
                "type": "match",
                "data": {
                    "path": {"text": "source/unbound.json"},
                    "lines": {"text": "STANDING:HISTORICAL_PRESERVED=true\n"},
                    "line_number": 1,
                    "absolute_offset": 0,
                    "submatches": [
                        {
                            "match": {"text": "HISTORICAL_PRESERVED"},
                            "start": 9,
                            "end": 29,
                        }
                    ],
                },
            }
            return {
                "status": "succeeded",
                "jobId": "job:observation-search",
                "attemptId": "attempt:observation-search",
                "executionTerminal": True,
                "executionDisposition": "succeeded",
                "deliveryDisposition": "committed",
                "recoveryRequired": False,
                "semanticCompletionEvaluated": False,
                "exitCode": 0,
                "stdoutTail": json.dumps(match) + "\n" + json.dumps(unbound) + "\n",
                "stderrTail": "",
                "resultAvailable": True,
                "artifactsAvailable": False,
            }
        if name == "workspace.read":
            return {
                "content": self.source_content,
                "digest": self.source_digest,
                "eof": True,
                "fileByteLength": len(self.source_content.encode("utf-8")),
            }
        raise AssertionError(name)

    def find_jobs_by_client_request_id(self, client_request_id):
        return ()


class ObservationToolSurfaceTests(unittest.TestCase):
    def test_search_then_exact_digest_read_is_supported_without_mutation_surface(self):
        source = '{"standingStatements":["STANDING:HISTORICAL_PRESERVED=true","STANDING:FALSIFIED=true"]}'
        source_digest = "sha256:" + __import__("hashlib").sha256(source.encode()).hexdigest()
        grant = HarnessObservationToolGrant(
            search_paths=(".",),
            read_objects=(HarnessObservationReadObject("source/standing.json", source_digest),),
        )
        value = contract("happy", grant)
        runtime = FakeRuntime(source, source_digest)
        adapter = ScriptedTurnAdapter(
            (
                tool_turn("search", "search_workspace", {"query": "HISTORICAL_PRESERVED"}),
                tool_turn("read", "read_workspace", {"relativePath": "./source/standing.json", "mode": "FULL", "maxBytes": 4096}),
                completed(),
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            run = build_observation_tool_surface(grant).create(
                Path(directory) / "state",
                value,
                lambda _contract: adapter,
                execution_binding=binding(value),
                runtime=runtime,
            )
            result = run.run(({"role": "user", "content": "recover exact standing"},))
        self.assertEqual(result.loop_result.stop_code.value, "candidate_completed")
        self.assertEqual(result.loop_result.usage["toolCalls"], 2)
        self.assertEqual([name for name, _ in runtime.calls], ["workspace.exec", "workspace.read"])
        self.assertEqual(
            {tool.name for tool in adapter.requests[0].tools},
            {"search_workspace", "read_workspace"},
        )
        search_messages = [
            message
            for message in adapter.requests[1].messages
            if message.get("role") == "tool" and message.get("name") == "search_workspace"
        ]
        self.assertEqual(len(search_messages), 1)
        search_content = search_messages[0]["observation"]["content"]
        self.assertEqual(
            set(search_content),
            {
                "query",
                "relativePath",
                "matchCount",
                "matches",
                "totalMatchCount",
                "readAdmittedMatchCount",
                "readAdmittedObjectCount",
                "omittedUnadmittedMatchCount",
                "readRouting",
            },
        )
        self.assertNotIn("stdoutTail", search_content)
        self.assertNotIn("artifacts", search_content)
        self.assertTrue(search_content["matches"][0]["readAdmitted"])
        self.assertEqual(
            search_content["matches"][0]["readRelativePath"],
            "source/standing.json",
        )
        self.assertFalse(search_content["matches"][0]["sourceAuthorityBound"])
        self.assertEqual(search_content["totalMatchCount"], 2)
        self.assertEqual(search_content["matchCount"], 1)
        self.assertEqual(search_content["readAdmittedMatchCount"], 1)
        self.assertEqual(search_content["readAdmittedObjectCount"], 1)
        self.assertEqual(search_content["omittedUnadmittedMatchCount"], 1)
        self.assertEqual(
            search_content["readRouting"]["arguments"]["relativePath"],
            "source/standing.json",
        )
        self.assertNotIn("source/unbound.json", json.dumps(search_content))
        self.assertNotIn("workspace.patch", grant.to_dict()["runtimeOperations"])

    def test_grant_rejects_unbound_paths_and_binds_expected_digest(self):
        read_digest = digest("exact-source")
        grant = HarnessObservationToolGrant(
            search_paths=(".", "source"),
            read_objects=(HarnessObservationReadObject("source/standing.json", read_digest),),
        )
        self.assertTrue(grant.allows_path("search_workspace", "."))
        self.assertTrue(grant.allows_path("read_workspace", "source/standing.json"))
        self.assertTrue(grant.allows_path("read_workspace", "./source/standing.json"))
        self.assertTrue(grant.allows_path("read_workspace", "source/./standing.json"))
        self.assertFalse(grant.allows_path("read_workspace", "source/other.json"))
        self.assertFalse(grant.allows_path("read_workspace", "../standing.json"))
        self.assertEqual(grant.expected_digest("read_workspace", "source/standing.json"), read_digest)
        self.assertEqual(grant.expected_digest("read_workspace", "./source/standing.json"), read_digest)
        self.assertEqual(grant.expected_digest("read_workspace", "source/./standing.json"), read_digest)
        self.assertIsNone(grant.expected_digest("search_workspace", "."))
        with self.assertRaisesRegex(ValueError, "canonical relative spelling"):
            HarnessObservationReadObject("./source/standing.json", read_digest)

    def test_exact_authority_publication_read_projects_only_bound_subject_statements(self):
        authority = source_authority()
        target = "result:human:generic-operational-core-sufficiency-falsified"
        publication = json.dumps(
            {
                "kind": "ordivon.research-owner-publication",
                "ownerResearchRef": authority.owner_research_ref,
                "authorityRef": authority.authority_ref,
                "statements": [
                    {
                        "predicate": "STANDING:HISTORICAL_PRESERVED",
                        "scope": "RESULT",
                        "subjectRef": target,
                        "value": True,
                    },
                    {
                        "predicate": "STANDING:FALSIFIED",
                        "scope": "RESULT",
                        "subjectRef": target,
                        "value": True,
                    },
                    {
                        "predicate": "STANDING:CURRENT",
                        "scope": "RESULT",
                        "subjectRef": "result:human:other",
                        "value": True,
                    },
                ],
            },
            separators=(",", ":"),
        )
        read_object = HarnessObservationReadObject(
            "source/authority.json",
            authority.authority_version_ref,
            source_authority=authority,
            authority_statement_projection=HarnessObservationAuthorityStatementProjection(
                target
            ),
        )
        grant = HarnessObservationToolGrant(
            search_paths=(".",),
            read_objects=(read_object,),
        )
        value = contract("authority-publication-projection", grant)
        runtime = FakeRuntime(publication, authority.authority_version_ref)
        adapter = ScriptedTurnAdapter(
            (
                tool_turn(
                    "read-publication",
                    "read_workspace",
                    {
                        "relativePath": "source/authority.json",
                        "mode": "FULL",
                        "maxBytes": 262144,
                    },
                ),
                completed(),
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            run = build_observation_tool_surface(grant).create(
                Path(directory) / "state",
                value,
                lambda _contract: adapter,
                execution_binding=binding(value, authority),
                runtime=runtime,
            )
            result = run.run(
                ({"role": "user", "content": "recover exact authority statements"},)
            )
        self.assertEqual(result.loop_result.stop_code.value, "candidate_completed")
        read_messages = [
            message
            for message in adapter.requests[1].messages
            if message.get("role") == "tool" and message.get("name") == "read_workspace"
        ]
        self.assertTrue(read_messages)
        read_content = read_messages[-1]["observation"]["content"]
        self.assertTrue(read_content["sourceFenceVerified"])
        self.assertTrue(read_content["sourceProjectionVerified"])
        self.assertNotIn("content", read_content)
        projected = read_content["sourceProjection"]
        self.assertEqual(projected["subjectRef"], target)
        self.assertEqual(projected["statementCount"], 2)
        self.assertEqual(
            {statement["predicate"] for statement in projected["statements"]},
            {"STANDING:HISTORICAL_PRESERVED", "STANDING:FALSIFIED"},
        )
        self.assertNotIn("result:human:other", json.dumps(projected))
        self.assertFalse(projected["harnessMintsOwnerTruth"])

    def test_authority_statement_projection_requires_authority_version_source_digest(self):
        authority = source_authority()
        with self.assertRaisesRegex(ValueError, "authorityVersionRef"):
            HarnessObservationReadObject(
                "source/authority.json",
                digest("not-authority-version"),
                source_authority=authority,
                authority_statement_projection=HarnessObservationAuthorityStatementProjection(
                    "result:human:target"
                ),
            )

    def test_authority_qualified_read_projects_caller_bound_fence(self):
        source = '{"standingStatements":["STANDING:HISTORICAL_PRESERVED=true"]}'
        source_digest = "sha256:" + __import__("hashlib").sha256(source.encode()).hexdigest()
        authority = source_authority()
        read_object = HarnessObservationReadObject(
            "source/standing.json",
            source_digest,
            source_authority=authority,
        )
        grant = HarnessObservationToolGrant(
            search_paths=(".",),
            read_objects=(read_object,),
        )
        generic_grant = HarnessObservationToolGrant(
            search_paths=(".",),
            read_objects=(HarnessObservationReadObject("source/standing.json", source_digest),),
        )
        self.assertNotEqual(grant.digest, generic_grant.digest)
        self.assertFalse(grant.to_dict()["harnessMintsOwnerTruth"])
        value = contract("authority-qualified", grant)
        runtime = FakeRuntime(source, source_digest)
        adapter = ScriptedTurnAdapter(
            (
                tool_turn("search-authority", "search_workspace", {"query": "HISTORICAL_PRESERVED"}),
                tool_turn(
                    "read-authority",
                    "read_workspace",
                    {"relativePath": "source/standing.json", "mode": "FULL", "maxBytes": 4096},
                ),
                completed(),
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            run = build_observation_tool_surface(grant).create(
                Path(directory) / "state",
                value,
                lambda _contract: adapter,
                execution_binding=binding(value, authority),
                runtime=runtime,
            )
            result = run.run(({"role": "user", "content": "recover authority-qualified standing"},))
        self.assertEqual(result.loop_result.stop_code.value, "candidate_completed")
        search_messages = [
            message
            for message in adapter.requests[1].messages
            if message.get("role") == "tool" and message.get("name") == "search_workspace"
        ]
        self.assertTrue(search_messages)
        search_match = search_messages[-1]["observation"]["content"]["matches"][0]
        self.assertTrue(search_match["readAdmitted"])
        self.assertTrue(search_match["sourceAuthorityBound"])
        read_messages = [
            message
            for message in adapter.requests[2].messages
            if message.get("role") == "tool" and message.get("name") == "read_workspace"
        ]
        self.assertTrue(read_messages)
        read_content = read_messages[-1]["observation"]["content"]
        self.assertTrue(read_content["sourceFenceVerified"])
        self.assertEqual(
            read_content["sourceFenceRole"],
            "CALLER_BOUND_SOURCE_AUTHORITY_EVIDENCE",
        )
        fence = read_content["sourceFence"]
        self.assertEqual(fence["relativePath"], "source/standing.json")
        self.assertEqual(fence["sourceDigest"], source_digest)
        self.assertFalse(fence["harnessMintsOwnerTruth"])
        projected_authority = fence["sourceAuthority"]
        self.assertEqual(projected_authority["ownerResearchRef"], authority.owner_research_ref)
        self.assertEqual(projected_authority["authorityRef"], authority.authority_ref)
        self.assertEqual(
            projected_authority["authorityVersionRef"],
            authority.authority_version_ref,
        )
        self.assertEqual(
            projected_authority["sourceTransportRevision"],
            authority.source_transport_revision,
        )
        self.assertFalse(projected_authority["harnessMintsOwnerTruth"])

    def test_authority_qualified_read_requires_matching_execution_reference(self):
        authority = source_authority()
        grant = HarnessObservationToolGrant(
            search_paths=(".",),
            read_objects=(
                HarnessObservationReadObject(
                    "source/standing.json",
                    digest("authority-source"),
                    source_authority=authority,
                ),
            ),
        )
        value = contract("authority-reference-required", grant)
        with tempfile.TemporaryDirectory() as directory:
            run = build_observation_tool_surface(grant).create(
                Path(directory) / "state",
                value,
                lambda _contract: ScriptedTurnAdapter((completed(),)),
                execution_binding=binding(value),
                runtime=FakeRuntime("{}", digest("authority-source")),
            )
            with self.assertRaisesRegex(ValueError, "source_authority execution reference"):
                run.run(({"role": "user", "content": "recover authority-qualified standing"},))

    def test_source_digest_mismatch_fails_closed_before_completion_claim(self):
        source = '{"standingStatements":["STANDING:HISTORICAL_PRESERVED=true"]}'
        expected = digest("expected-source")
        observed = digest("different-source")
        grant = HarnessObservationToolGrant(
            search_paths=(".",),
            read_objects=(HarnessObservationReadObject("source/standing.json", expected),),
        )
        value = contract("mismatch", grant)
        runtime = FakeRuntime(source, observed)
        adapter = ScriptedTurnAdapter(
            (
                tool_turn("read-mismatch", "read_workspace", {"relativePath": "source/standing.json", "maxBytes": 4096}),
                AgentTurnResult(
                    model_call_id="model-call:mismatch-stop",
                    model_id=ScriptedTurnAdapter.model_id,
                    content="cannot rely on changed source",
                    tool_calls=(),
                    conclusion=AgentRunConclusion(
                        status="needs_input",
                        summary="Exact source fence changed.",
                        unresolved_unknowns=("current source object",),
                    ),
                    usage={"inputTokens": 1, "outputTokens": 1},
                    finish_reason="stop",
                    raw_response_digest=digest("mismatch-stop"),
                ),
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            run = build_observation_tool_surface(grant).create(
                Path(directory) / "state",
                value,
                lambda _contract: adapter,
                execution_binding=binding(value),
                runtime=runtime,
            )
            result = run.run(({"role": "user", "content": "recover standing"},))
        self.assertTrue(result.paused)
        second_messages = adapter.requests[1].messages
        tool_messages = [message for message in second_messages if message.get("role") == "tool"]
        self.assertTrue(tool_messages)
        self.assertIn("SourceFenceMismatch", str(tool_messages[-1]))


if __name__ == "__main__":
    unittest.main()
