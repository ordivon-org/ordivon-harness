from __future__ import annotations

import itertools
import tempfile
import unittest

from anc_canonical import canonical_digest
from ordivon_host import HostStorage
from ordivon_host.ops.history import validate_history as validate_host_history
from test_harness_h1 import manifest
from test_ordivon_harness_oh5 import TASK_ID, _contract, _create_task

from ordivon_harness import HarnessHost
from ordivon_harness.event_kinds import HARNESS_ASSIGNMENT_COMMITTED


class ExternalAssignmentHistoryTests(unittest.TestCase):
    def test_task_contract_object_is_admitted_by_external_assignment_event(self) -> None:
        clock = itertools.count(10_000).__next__
        with tempfile.TemporaryDirectory() as directory, HostStorage(directory) as storage:
            _create_task(storage, clock)
            host = HarnessHost(storage, clock_ms=clock)
            attempt = host.start_attempt(TASK_ID, task_contract=_contract())
            context = storage.put_object(
                {"schemaVersion": 1, "kind": "test-compiled-context"},
                kind="compiled-context",
            )
            committed = host.assign(
                attempt,
                manifest=manifest("harness:external-security-p0c"),
                context_object_digest=context.digest,
                tool_catalog_digest=canonical_digest({"tools": []}),
                tool_grant=None,
            )
            assert committed.task_contract_object is not None
            row = storage.journal.connection.execute(
                "SELECT event_id FROM events WHERE event_kind = ?",
                (HARNESS_ASSIGNMENT_COMMITTED.value,),
            ).fetchone()
            assert row is not None
            event_references = {
                item.digest
                for item in storage.journal.event_object_references(str(row["event_id"]))
            }
            self.assertIn(committed.task_contract_object.digest, event_references)
            validation = validate_host_history(storage)
            self.assertGreater(validation.events, 0)
            self.assertGreater(validation.semantic_references, 0)


if __name__ == "__main__":
    unittest.main()
