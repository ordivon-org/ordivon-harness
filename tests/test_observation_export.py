from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from ordivon_harness.core_contracts import HarnessBoundReference, HarnessRunContract
from ordivon_harness.independent_result import IndependentHarnessRunReceipt
from ordivon_harness.observation_export import (
    HarnessObservationExportError,
    MAPPING_VERSION,
    export_harness_observations,
)
from ordivon_harness.ordivon.continuity_records import HarnessDispatchFenceV2
from ordivon_harness.protocol import HarnessToolStepReceipt, HarnessToolStepStatus
from ordivon_harness.sqlite_store import SQLiteHarnessStore

OBSERVATION_AVAILABLE = importlib.util.find_spec("ordivon_observation_core") is not None
if OBSERVATION_AVAILABLE:
    import ordivon_observation_core as observation  # noqa: E402

OWNER_REVISION = "1" * 40
EXPORTER_REVISION = "2" * 40
INSTANCE_ID = "harness:observation-test"
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64
DIGEST_D = "sha256:" + "d" * 64


def run_contract(run_id: str, request_id: str, created_at_ms: int) -> HarnessRunContract:
    suffix = run_id.rsplit(":", 1)[-1]
    return HarnessRunContract(
        harness_run_id=run_id,
        harness_implementation_id="ordivon-harness@observation-test",
        caller_id="caller:ordivon-host",
        caller_run_ref=request_id,
        objective_ref=HarnessBoundReference(
            f"objective:{suffix}", "objective", DIGEST_A
        ),
        context_refs=(
            HarnessBoundReference(f"context:{suffix}", "context", DIGEST_B),
        ),
        provider_id="provider:scripted",
        adapter_id="adapter:scripted-v1",
        requested_model_id="model:scripted",
        tool_catalog_digest=DIGEST_C,
        tool_grant_digest=DIGEST_D,
        budget={"private": "budget content must not be exported"},
        completion_contract={"private": "completion content must not be exported"},
        system_manifest_ref=HarnessBoundReference(
            f"system-manifest:{suffix}", "system-manifest", DIGEST_A
        ),
        created_at_ms=created_at_ms,
    )


@unittest.skipUnless(OBSERVATION_AVAILABLE, "exact Observation contract is optional")
class HarnessObservationExporterTests(unittest.TestCase):
    def create_history(self, root: Path) -> None:
        with SQLiteHarnessStore.initialize(root) as store:
            run_a = run_contract(
                "harness-run:observation-a",
                "external-request:observation-a",
                1_000,
            )
            run_b = run_contract(
                "harness-run:observation-b",
                "external-request:observation-b",
                1_001,
            )
            store.create_run(run_a)
            store.create_run(run_b)
            receipt = HarnessToolStepReceipt(
                receipt_id="harness-tool-step-receipt:observation-a",
                intent_digest=DIGEST_A,
                harness_run_id=run_a.harness_run_id,
                tool_call_id="tool-call:observation-a",
                status=HarnessToolStepStatus.UNKNOWN,
                runtime_job_ref="job-019fd000-0000-7000-8000-000000000001",
                observation_digest=DIGEST_C,
                reconciled=False,
                created_at_ms=1_003,
            )
            fence = HarnessDispatchFenceV2(
                fence_id="harness-dispatch-fence:observation-a",
                harness_run_id=run_a.harness_run_id,
                run_revision=1,
                binding_digest=DIGEST_B,
                intent_digest=DIGEST_A,
                runtime_operation="workspace.exec",
                client_request_id="request:observation-a",
                issued_at_ms=1_002,
                expires_at_ms=2_002,
            )
            receipt_object = store.put_object(
                receipt.to_dict(), kind="harness-tool-step-receipt"
            )
            fence_object = store.put_object(
                fence.to_dict(), kind="harness-dispatch-fence"
            )
            lease = store.acquire_run_lease(
                run_a.harness_run_id,
                owner_id="worker:observation-test",
                ttl_ms=1_000,
                now_ms=1_002,
            )
            store.append_event(
                event_id="event:observation-a:tool-step",
                harness_run_id=run_a.harness_run_id,
                event_kind="harness.tool-step-recorded",
                data={"private": "tool event payload must not be exported"},
                expected_revision=1,
                recorded_at_ms=1_003,
                lease=lease,
                lease_checked_at_ms=1_003,
                referenced_objects=(fence_object, receipt_object),
            )
            run_receipt = IndependentHarnessRunReceipt(
                harness_run_id=run_a.harness_run_id,
                caller_id=run_a.caller_id,
                caller_run_ref=run_a.caller_run_ref,
                contract_digest=run_a.digest,
                harness_implementation_id=run_a.harness_implementation_id,
                system_manifest_digest=run_a.system_manifest_ref.digest,
                started_at_ms=1_000,
                finished_at_ms=1_004,
                stop_reason="completed",
                termination_code="candidate_completed",
                trace_digest=DIGEST_A,
                context_digests=(run_a.context_refs[0].digest,),
                tool_catalog_digest=run_a.tool_catalog_digest,
                tool_grant_digest=run_a.tool_grant_digest,
                runtime_job_refs=(
                    "job-019fd000-0000-7000-8000-000000000001",
                ),
                artifact_refs=(),
                usage={
                    "modelCalls": 2,
                    "toolCalls": 1,
                    "observationBytes": 3_682,
                    "totalTokens": 58,
                    "wallTimeMs": 821,
                    "toolCorrections": 0,
                    "providerUsage": [
                        {
                            "inputTokens": 40,
                            "outputTokens": 18,
                            "private": "provider usage detail must remain owner-native",
                        }
                    ],
                },
                conclusion_digest=DIGEST_B,
            )
            run_receipt_object = store.put_object(
                run_receipt.to_dict(), kind="independent-harness-run-receipt"
            )
            terminal_lease = store.acquire_run_lease(
                run_a.harness_run_id,
                owner_id="worker:observation-test",
                ttl_ms=1_000,
                now_ms=1_004,
            )
            store.append_event(
                event_id="event:observation-a:run-completed",
                harness_run_id=run_a.harness_run_id,
                event_kind="harness.run-completed",
                data={"private": "terminal payload must not be exported"},
                expected_revision=2,
                recorded_at_ms=1_004,
                lease=terminal_lease,
                lease_checked_at_ms=1_004,
                referenced_objects=(run_receipt_object,),
            )

    @staticmethod
    def durable_snapshot(root: Path) -> dict[str, bytes]:
        return {
            str(path.relative_to(root)): path.read_bytes()
            for path in sorted(root.rglob("*"))
            if (
                path.is_file()
                and not path.is_symlink()
                and not path.name.endswith(("-wal", "-shm"))
            )
        }

    def run_export(
        self,
        directory: str,
        *,
        limit: int = 256,
        fail_after_bundle: bool = False,
        exported_at_ms: int = 2_000,
    ) -> dict[str, object]:
        root = Path(directory)
        return export_harness_observations(
            state_root=root / "harness",
            instance_id=INSTANCE_ID,
            checkpoint_path=root / "sidecar" / "harness.json",
            outbox_root=root / "outbox",
            owner_revision=OWNER_REVISION,
            exporter_revision=EXPORTER_REVISION,
            exported_at_ms=exported_at_ms,
            limit=limit,
            fail_after_bundle=fail_after_bundle,
        )

    def test_global_sequence_typed_links_gateway_and_replay(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.create_history(root / "harness")
            before = self.durable_snapshot(root / "harness")
            result = self.run_export(directory)
            self.assertEqual(result["eventCount"], 4)
            self.assertEqual(self.durable_snapshot(root / "harness"), before)
            bundle_path = Path(str(result["bundlePath"]))
            encoded = bundle_path.read_text(encoding="utf-8")
            for private in (
                "budget content must not be exported",
                "completion content must not be exported",
                "tool event payload must not be exported",
                "terminal payload must not be exported",
                "provider usage detail must remain owner-native",
                '"inputTokens"',
                '"outputTokens"',
            ):
                self.assertNotIn(private, encoded)
            bundle = observation.ObservationExportBundle.from_dict(json.loads(encoded))
            events = tuple(event for batch in bundle.batches for event in batch.events)
            self.assertEqual([event.source.sequence for event in events], [1, 2, 3, 4])
            self.assertEqual(
                [event.source.native_revision for event in events], [1, 1, 2, 3]
            )
            terminal = events[-1]
            self.assertEqual(
                terminal.attributes["typedKeyKinds"],
                ["independent-harness-run-receipt"],
            )
            self.assertTrue(all(not event.measurements for event in events[:-1]))
            self.assertEqual(
                {
                    key: (measurement.value, measurement.unit)
                    for key, measurement in terminal.measurements.items()
                },
                {
                    "ordivon.harness.model_calls": (2, "1"),
                    "ordivon.harness.tool_calls": (1, "1"),
                    "ordivon.harness.observation_bytes": (3_682, "By"),
                    "ordivon.harness.total_tokens": (58, "token"),
                    "ordivon.harness.wall_time": (821, "ms"),
                    "ordivon.harness.tool_corrections": (0, "1"),
                },
            )
            relations = [relation.to_dict() for event in events for relation in event.relations]
            self.assertTrue(
                any(
                    item["relationType"] == "executes"
                    and item["targetId"]
                    == "job-019fd000-0000-7000-8000-000000000001"
                    for item in relations
                )
            )
            self.assertTrue(
                any(
                    item["targetKind"] == "ordivon.runtime.client-request"
                    and item["targetId"] == "request:observation-a"
                    for item in relations
                )
            )
            self.assertTrue(
                any(
                    item["targetKind"] == "ordivon.host.external-request"
                    and item["targetId"] == "external-request:observation-a"
                    for item in relations
                )
            )
            producer = observation.ObservationProducerIdentity(
                "ordivon-harness", "harness-journal", INSTANCE_ID
            )
            with observation.SQLiteObservationGateway.initialize(
                root / "gateway",
                gateway_instance_id="observation-gateway:harness-test",
                producer_allowlist=(producer,),
                mapping_versions=(
                    ("ordivon-harness", "harness-journal", MAPPING_VERSION),
                ),
                created_at_ms=100,
            ) as gateway:
                accepted = sum(
                    gateway.ingest(batch, ingested_at_ms=3_000).accepted
                    for batch in bundle.batches
                )
                self.assertEqual(accepted, 4)
                self.assertTrue(gateway.doctor(full=True)["healthy"])
            self.assertEqual(
                self.run_export(directory, exported_at_ms=2_001)["status"],
                "no_events",
            )

    def test_pagination_and_failure_after_bundle_recover(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.create_history(root / "harness")
            with self.assertRaisesRegex(HarnessObservationExportError, "injected failure"):
                self.run_export(directory, limit=2, fail_after_bundle=True)
            self.assertFalse((root / "sidecar" / "harness.json").exists())
            self.assertEqual(len(tuple((root / "outbox").glob("bundle-*.json"))), 1)
            first = self.run_export(directory, limit=2)
            self.assertEqual(first["eventCount"], 2)
            self.assertEqual(len(tuple((root / "outbox").glob("bundle-*.json"))), 1)
            second = self.run_export(directory, limit=2, exported_at_ms=2_001)
            self.assertEqual(second["eventCount"], 2)
            self.assertEqual(
                self.run_export(directory, limit=2, exported_at_ms=2_002)["status"],
                "no_events",
            )

    def test_sidecar_inside_owner_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.create_history(root / "harness")
            with self.assertRaisesRegex(HarnessObservationExportError, "outside"):
                export_harness_observations(
                    state_root=root / "harness",
                    instance_id=INSTANCE_ID,
                    checkpoint_path=root / "harness" / "checkpoint.json",
                    outbox_root=root / "outbox",
                    owner_revision=OWNER_REVISION,
                    exporter_revision=EXPORTER_REVISION,
                    exported_at_ms=2_000,
                )


if __name__ == "__main__":
    unittest.main()
