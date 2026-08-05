from __future__ import annotations

import contextlib
import io
import itertools
import json
from pathlib import Path
import tempfile
import unittest

from anc_canonical import canonical_digest
from ordivon_host import EventKind, HostExtensionPort, HostKernel, HostStorage

from ordivon_harness.cli import main as cli_main
from ordivon_harness.core_contracts import HarnessBoundReference, HarnessRunContract
from ordivon_harness.cutover import (
    HarnessStoreMode,
    activate_cutover,
    assert_legacy_writer_allowed,
    build_cutover_inventory,
    cutover_status,
    rollback_cutover,
)
from ordivon_harness.sqlite_store import SQLiteHarnessStore

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


class CutoverFixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.host_root = root / "host"
        self.harness_root = root / "harness"
        with HostStorage(self.host_root):
            pass
        with SQLiteHarnessStore.initialize(self.harness_root):
            pass

    def add_legacy_run(self, suffix: str, *, terminal: bool = False) -> str:
        clock = itertools.count(1_000).__next__
        with HostStorage(self.host_root) as storage:
            kernel = HostKernel(
                storage,
                clock_ms=clock,
                owner_id=f"host:cutover:{suffix}",
            )
            projection = kernel.create_task(
                event_id=f"event:cutover:create:{suffix}",
                kind=EventKind.TASK_CREATED,
                task_id=f"task:cutover:{suffix}",
                goal_id=f"goal:cutover:{suffix}",
                payload={"fixture": suffix},
                frontier=(f"node:cutover:{suffix}",),
            ).projection
            port = HostExtensionPort(storage, kernel)
            contract = port.put_object(
                {
                    "schemaVersion": 1,
                    "kind": "fixture-native-harness-run-contract",
                    "harnessRunId": f"harness-run:legacy:{suffix}",
                },
                kind="fixture-native-harness-run-contract",
            )
            assigned = port.append_preserving(
                task_id=projection.task_id,
                expected_revision=projection.revision,
                event_id=f"event:cutover:assigned:{suffix}",
                kind=EventKind("fixture.harness-assigned"),
                updates={
                    "nativeHarnessRunContractObjectDigest": contract.digest,
                    "assignmentId": f"assignment:legacy:{suffix}",
                    "assignmentGeneration": 1,
                    "harnessRunId": f"harness-run:legacy:{suffix}",
                },
                referenced_objects=(contract,),
                label="cutover legacy assignment fixture",
            )
            if terminal:
                port.append_preserving(
                    task_id=projection.task_id,
                    expected_revision=assigned.projection.revision,
                    event_id=f"event:cutover:terminal:{suffix}",
                    kind=EventKind("fixture.harness-terminal"),
                    updates={"harnessRunTerminationCode": "candidate_completed"},
                    referenced_objects=(contract,),
                    label="cutover legacy terminal fixture",
                )
            return projection.task_id

    def add_external_request(
        self, suffix: str, *, observed_status: str | None = None
    ) -> str:
        clock = itertools.count(1_200).__next__
        with HostStorage(self.host_root) as storage:
            kernel = HostKernel(
                storage,
                clock_ms=clock,
                owner_id=f"host:cutover:external:{suffix}",
            )
            projection = kernel.create_task(
                event_id=f"event:cutover:external-create:{suffix}",
                kind=EventKind.TASK_CREATED,
                task_id=f"task:cutover:external:{suffix}",
                goal_id=f"goal:cutover:external:{suffix}",
                payload={"fixture": suffix},
                frontier=(f"node:cutover:external:{suffix}",),
            ).projection
            port = HostExtensionPort(storage, kernel)
            request_id = f"external-request:cutover:{suffix}"
            request = port.put_object(
                {
                    "schemaVersion": 1,
                    "kind": "ordivon.external-execution-request",
                    "requestId": request_id,
                    "adapterId": "external-executor:ordivon-harness",
                    "taskId": projection.task_id,
                    "taskRevision": projection.revision,
                    "taskAttemptRef": f"task-attempt:cutover:{suffix}",
                    "contractDigest": DIGEST_A,
                    "correlationContext": {},
                    "createdAtMs": 1_500,
                },
                kind="external-execution-request",
            )
            updates = {"externalExecutionRequestObjectDigest": request.digest}
            references = [request]
            if observed_status is not None:
                binding = port.put_object(
                    {
                        "schemaVersion": 1,
                        "kind": "ordivon.external-run-binding",
                        "bindingId": f"external-binding:cutover:{suffix}",
                        "adapterId": "external-executor:ordivon-harness",
                        "requestId": request_id,
                        "foreignRunRef": f"harness-run:cutover:external:{suffix}",
                        "contractDigest": DIGEST_A,
                        "taskId": projection.task_id,
                        "taskAttemptRef": f"task-attempt:cutover:{suffix}",
                        "correlationContext": {},
                        "observedStatus": observed_status,
                        "evidenceRefs": [],
                        "lastReconciledRevision": 1,
                        "lastObservationDigest": DIGEST_B,
                        "cancellationRequested": False,
                        "completionProposalDigest": None,
                        "createdAtMs": 1_501,
                        "updatedAtMs": 1_501,
                    },
                    kind="external-run-binding",
                )
                updates["externalRunBindingObjectDigest"] = binding.digest
                references.append(binding)
            port.append_preserving(
                task_id=projection.task_id,
                expected_revision=projection.revision,
                event_id=f"event:cutover:external-request:{suffix}",
                kind=EventKind("fixture.external-requested"),
                updates=updates,
                referenced_objects=tuple(references),
                label="cutover external request fixture",
            )
            return request_id

    def create_independent_run(self, suffix: str, *, created_at_ms: int) -> str:
        contract = HarnessRunContract(
            harness_run_id=f"harness-run:cutover:{suffix}",
            harness_implementation_id="ordivon-harness@cutover-test",
            caller_id="caller:cutover-test",
            caller_run_ref=f"cutover-request:{suffix}",
            objective_ref=HarnessBoundReference(
                f"objective:cutover:{suffix}", "objective", DIGEST_A
            ),
            context_refs=(
                HarnessBoundReference(
                    f"context:cutover:{suffix}", "context", DIGEST_B
                ),
            ),
            provider_id="provider:scripted",
            adapter_id="ordivon.scripted",
            requested_model_id="scripted-model",
            tool_catalog_digest=canonical_digest(
                {"schemaVersion": 1, "tools": []}
            ),
            tool_grant_digest=canonical_digest(
                {"schemaVersion": 1, "grant": []}
            ),
            budget={
                "maxModelCalls": 1,
                "maxToolCalls": 1,
                "maxWallTimeMs": 1_000,
            },
            completion_contract={"mode": "record"},
            system_manifest_ref=HarnessBoundReference(
                f"system-manifest:cutover:{suffix}",
                "system-manifest",
                DIGEST_A,
            ),
            created_at_ms=created_at_ms,
        )
        with SQLiteHarnessStore(self.harness_root) as store:
            store.create_run(contract)
            self.assert_run_list(store, contract.harness_run_id)
        return contract.harness_run_id

    @staticmethod
    def assert_run_list(store: SQLiteHarnessStore, run_id: str) -> None:
        runs = store.list_runs()
        if not any(item.harness_run_id == run_id for item in runs):
            raise AssertionError("created independent Run is absent from list_runs")


class HarnessCutoverTests(unittest.TestCase):
    def test_active_legacy_run_blocks_activation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = CutoverFixture(Path(directory))
            task_id = fixture.add_legacy_run("active")
            inventory = build_cutover_inventory(
                fixture.host_root,
                fixture.harness_root,
                generated_at_ms=2_000,
            )
            self.assertFalse(inventory.can_activate)
            self.assertEqual(len(inventory.legacy_runs), 1)
            self.assertTrue(inventory.legacy_runs[0].blocking)
            self.assertIn(task_id, inventory.blockers[0])
            with self.assertRaisesRegex(RuntimeError, "legacy"):
                activate_cutover(
                    fixture.host_root,
                    fixture.harness_root,
                    created_at_ms=2_000,
                )
            self.assertEqual(
                cutover_status(fixture.host_root).selected_mode,
                HarnessStoreMode.LEGACY_HOST,
            )

    def test_terminal_legacy_run_allows_activation_and_disables_legacy_writer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = CutoverFixture(Path(directory))
            fixture.add_legacy_run("terminal", terminal=True)
            receipt, inventory = activate_cutover(
                fixture.host_root,
                fixture.harness_root,
                created_at_ms=2_000,
            )
            self.assertTrue(inventory.can_activate)
            self.assertEqual(receipt.sequence, 1)
            self.assertEqual(receipt.action, "activate")
            self.assertEqual(receipt.selected_mode, HarnessStoreMode.INDEPENDENT)
            status = cutover_status(fixture.host_root)
            self.assertEqual(status.selected_mode, HarnessStoreMode.INDEPENDENT)
            self.assertEqual(status.latest_receipt, receipt)
            with self.assertRaisesRegex(RuntimeError, "legacy Host-backed"):
                assert_legacy_writer_allowed(fixture.host_root)
            receipt_files = tuple(
                (fixture.host_root / "harness-cutover" / "receipts").glob("*.json")
            )
            inventory_files = tuple(
                (fixture.host_root / "harness-cutover" / "inventories").glob("*.json")
            )
            self.assertEqual(len(receipt_files), 1)
            self.assertEqual(len(inventory_files), 1)
            self.assertEqual(receipt_files[0].stat().st_mode & 0o777, 0o600)

    def test_rollback_allowed_before_independent_work_and_receipts_chain(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = CutoverFixture(Path(directory))
            activated, _ = activate_cutover(
                fixture.host_root,
                fixture.harness_root,
                created_at_ms=2_000,
            )
            rolled_back, _ = rollback_cutover(
                fixture.host_root,
                fixture.harness_root,
                created_at_ms=3_000,
            )
            self.assertEqual(rolled_back.sequence, 2)
            self.assertEqual(rolled_back.previous_receipt_digest, activated.digest)
            self.assertEqual(rolled_back.selected_mode, HarnessStoreMode.LEGACY_HOST)
            status = cutover_status(fixture.host_root)
            self.assertEqual(status.selected_mode, HarnessStoreMode.LEGACY_HOST)
            self.assertEqual(len(status.receipts), 2)
            assert_legacy_writer_allowed(fixture.host_root)

    def test_rollback_refuses_any_post_activation_independent_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = CutoverFixture(Path(directory))
            activate_cutover(
                fixture.host_root,
                fixture.harness_root,
                created_at_ms=2_000,
            )
            run_id = fixture.create_independent_run("post-activation", created_at_ms=2_001)
            with self.assertRaisesRegex(RuntimeError, run_id):
                rollback_cutover(
                    fixture.host_root,
                    fixture.harness_root,
                    created_at_ms=3_000,
                )
            self.assertEqual(
                cutover_status(fixture.host_root).selected_mode,
                HarnessStoreMode.INDEPENDENT,
            )

    def test_request_only_external_harness_work_blocks_activation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = CutoverFixture(Path(directory))
            request_id = fixture.add_external_request("request-only")
            inventory = build_cutover_inventory(
                fixture.host_root,
                fixture.harness_root,
                generated_at_ms=2_000,
            )
            self.assertFalse(inventory.can_activate)
            self.assertEqual(inventory.external_requests[0].status, "request_only")
            self.assertTrue(inventory.external_requests[0].blocking)
            self.assertIn(request_id, inventory.blockers[0])

    def test_terminal_external_harness_request_does_not_block_activation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = CutoverFixture(Path(directory))
            fixture.add_external_request("completed", observed_status="completed")
            inventory = build_cutover_inventory(
                fixture.host_root,
                fixture.harness_root,
                generated_at_ms=2_000,
            )
            self.assertTrue(inventory.can_activate)
            self.assertFalse(inventory.external_requests[0].blocking)

    def test_nonterminal_independent_run_blocks_initial_activation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = CutoverFixture(Path(directory))
            run_id = fixture.create_independent_run("preexisting", created_at_ms=1_500)
            inventory = build_cutover_inventory(
                fixture.host_root,
                fixture.harness_root,
                generated_at_ms=2_000,
            )
            self.assertFalse(inventory.can_activate)
            self.assertIn(run_id, inventory.blockers[0])

    def test_cli_cutover_commands_and_legacy_writer_guard(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = CutoverFixture(Path(directory))

            def invoke(command: str, *, include_harness: bool = True):
                argv = ["--state-root", str(fixture.host_root)]
                if include_harness:
                    argv.extend(
                        ["--harness-state-root", str(fixture.harness_root)]
                    )
                argv.append(command)
                stdout = io.StringIO()
                stderr = io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    code = cli_main(argv)
                return code, stdout.getvalue(), stderr.getvalue()

            code, output, error = invoke("cutover-inventory")
            self.assertEqual(code, 0, error)
            self.assertTrue(json.loads(output)["inventory"]["canActivate"])

            code, output, error = invoke("cutover-activate")
            self.assertEqual(code, 0, error)
            self.assertEqual(
                json.loads(output)["receipt"]["selectedMode"],
                HarnessStoreMode.INDEPENDENT.value,
            )

            code, output, error = invoke("cutover-status", include_harness=False)
            self.assertEqual(code, 0, error)
            self.assertEqual(
                json.loads(output)["cutover"]["selectedMode"],
                HarnessStoreMode.INDEPENDENT.value,
            )

            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = cli_main(
                    [
                        "--state-root",
                        str(fixture.host_root),
                        "cancel",
                        "task:cutover:missing",
                    ]
                )
            self.assertEqual(code, 1)
            self.assertIn("legacy Host-backed Harness writes are disabled", stderr.getvalue())

            code, output, error = invoke("cutover-rollback")
            self.assertEqual(code, 0, error)
            self.assertEqual(
                json.loads(output)["receipt"]["selectedMode"],
                HarnessStoreMode.LEGACY_HOST.value,
            )

    def test_inventory_tampering_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = CutoverFixture(Path(directory))
            activate_cutover(
                fixture.host_root,
                fixture.harness_root,
                created_at_ms=2_000,
            )
            inventory_path = next(
                (fixture.host_root / "harness-cutover" / "inventories").glob("*.json")
            )
            inventory_path.write_text(
                inventory_path.read_text().replace('"canActivate": true', '"canActivate": false')
            )
            with self.assertRaises(ValueError):
                cutover_status(fixture.host_root)

    def test_receipt_tampering_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = CutoverFixture(Path(directory))
            activate_cutover(
                fixture.host_root,
                fixture.harness_root,
                created_at_ms=2_000,
            )
            receipt_path = next(
                (fixture.host_root / "harness-cutover" / "receipts").glob("*.json")
            )
            receipt_path.write_text(receipt_path.read_text().replace("independent", "legacy_host"))
            with self.assertRaises(ValueError):
                cutover_status(fixture.host_root)


if __name__ == "__main__":
    unittest.main()
