from __future__ import annotations

import itertools
import multiprocessing
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch

from anc_canonical import canonical_digest
from ordivon_host import HostStorage, TaskState
from ordivon_host.journal import JournalCorruption
from test_harness_h1 import (
    ACCEPTANCE,
    OBJECTIVE,
    TASK_ID,
    TOOL_CATALOG,
    artifact,
    context_object,
    create_task,
    manifest,
    run_receipt,
)

from ordivon_harness import HarnessHost
from ordivon_harness.event_kinds import COMPLETION_DECIDED
from ordivon_harness.history import validate_history


def _accept_completion_process(directory: str, queue) -> None:
    try:
        with HostStorage(directory) as storage:
            host = HarnessHost(storage, clock_ms=lambda: 20_000)
            proposed = host.load_proposed_completion(TASK_ID)
            accepted = host.adjudicate_completion(
                proposed,
                artifact_exists=lambda _: True,
                acceptance_verifier=lambda _: (
                    True,
                    None,
                    {"accepted": True, "process": "adjudicator"},
                ),
            )
            queue.put(
                (
                    "accepted",
                    accepted.outcome_digest,
                    accepted.task_state,
                )
            )
    except Exception as error:  # noqa: BLE001 - child result asserted by parent.
        queue.put(("error", type(error).__name__, str(error)))


def _validate_completion_process(directory: str, queue) -> None:
    try:
        with HostStorage(directory) as storage:
            validation = validate_history(storage)
            snapshot = storage.read_task_event(TASK_ID)
            queue.put(
                (
                    "validated",
                    validation.events,
                    validation.semantic_link_checks,
                    snapshot.data["outcomeDigest"],
                    snapshot.data["outcomeObjectDigest"],
                )
            )
    except Exception as error:  # noqa: BLE001 - child result asserted by parent.
        queue.put(("error", type(error).__name__, str(error)))


class CompletionHistoryTests(unittest.TestCase):
    def _propose(self, storage: HostStorage, *, suffix: str):
        clock = itertools.count(6_000).__next__
        create_task(storage, clock)
        host = HarnessHost(storage, clock_ms=clock)
        attempt = host.start_attempt(
            TASK_ID,
            objective_digest=OBJECTIVE,
            acceptance_criteria_digest=ACCEPTANCE,
        )
        context = context_object(storage, suffix)
        assignment = host.assign(
            attempt,
            manifest=manifest(),
            context_object_digest=context.digest,
            tool_catalog_digest=TOOL_CATALOG,
        )
        recorded = host.record_run(
            assignment,
            run_receipt(
                assignment,
                run_id=f"harness-run:completion-history:{suffix}",
            ),
        )
        output = artifact("completion-history", suffix)
        proposed = host.propose_completion(
            recorded,
            summary="Completion history semantic identity is verified.",
            acceptance_results={"tests": "passed"},
            artifact_refs=(output,),
        )
        return host, proposed, output

    def _accept(self, storage: HostStorage, *, suffix: str):
        host, proposed, output = self._propose(storage, suffix=suffix)
        accepted = host.adjudicate_completion(
            proposed,
            artifact_exists=lambda ref: ref == output,
            acceptance_verifier=lambda _: (
                True,
                None,
                {"accepted": True, "fixture": suffix},
            ),
        )
        assert accepted.outcome is not None
        return accepted

    def _decision_event(self, storage: HostStorage):
        row = storage.journal.connection.execute(
            "SELECT event_id, payload_digest FROM events "
            "WHERE event_kind = ? ORDER BY sequence DESC LIMIT 1",
            (COMPLETION_DECIDED.value,),
        ).fetchone()
        assert row is not None
        payload = storage.objects.get(
            row["payload_digest"], expected_kind="host-event-payload"
        )
        assert isinstance(payload, dict)
        return row, payload

    def test_three_process_accepted_completion_history_is_valid(self) -> None:
        context = multiprocessing.get_context("fork")
        with tempfile.TemporaryDirectory() as directory:
            with HostStorage(directory) as storage:
                self._propose(storage, suffix="three-process")

            accepted_queue = context.Queue()
            adjudicator = context.Process(
                target=_accept_completion_process,
                args=(directory, accepted_queue),
            )
            adjudicator.start()
            adjudicator.join(10)
            self.assertEqual(adjudicator.exitcode, 0)
            accepted = accepted_queue.get(timeout=2)
            self.assertEqual(accepted[0], "accepted")
            self.assertEqual(accepted[2], TaskState.COMPLETED.value)

            validation_queue = context.Queue()
            validator = context.Process(
                target=_validate_completion_process,
                args=(directory, validation_queue),
            )
            validator.start()
            validator.join(10)
            self.assertEqual(validator.exitcode, 0)
            validated = validation_queue.get(timeout=2)
            self.assertEqual(validated[0], "validated")
            semantic_digest = validated[3]
            object_digest = validated[4]
            self.assertNotEqual(semantic_digest, object_digest)

            with HostStorage(directory) as storage:
                admitted = {item.digest for item in storage.journal.object_refs()}
                self.assertNotIn(semantic_digest, admitted)
                self.assertIn(object_digest, admitted)
                row, _ = self._decision_event(storage)
                self.assertIn(
                    object_digest,
                    {
                        item.digest
                        for item in storage.journal.event_object_references(
                            str(row["event_id"])
                        )
                    },
                )

    def test_outcome_semantic_digest_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with HostStorage(directory) as storage:
                self._accept(storage, suffix="semantic-drift")
                row, payload = self._decision_event(storage)
                forged = dict(payload)
                data = dict(forged["data"])
                data["outcomeDigest"] = canonical_digest(
                    {"forged": "outcome-semantic-digest"}
                )
                forged["data"] = data
                original_get = storage.objects.get

                def forged_payload(digest, *, expected_kind=None):
                    if digest == row["payload_digest"]:
                        return forged
                    return original_get(digest, expected_kind=expected_kind)

                with (
                    patch.object(
                        storage.objects, "get", side_effect=forged_payload
                    ),
                    self.assertRaisesRegex(
                        JournalCorruption,
                        "TaskOutcome semantic digest differs",
                    ),
                ):
                    validate_history(storage)

    def test_outcome_content_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with HostStorage(directory) as storage:
                accepted = self._accept(storage, suffix="content-drift")
                assert accepted.outcome is not None
                snapshot = storage.read_task_event(TASK_ID)
                outcome_object_digest = snapshot.data["outcomeObjectDigest"]
                assert isinstance(outcome_object_digest, str)
                drifted = replace(
                    accepted.outcome,
                    verification_digest=canonical_digest(
                        {"forged": "verification"}
                    ),
                )
                original_get = storage.objects.get

                def forged_outcome(digest, *, expected_kind=None):
                    if digest == outcome_object_digest:
                        return drifted.to_dict()
                    return original_get(digest, expected_kind=expected_kind)

                with (
                    patch.object(
                        storage.objects, "get", side_effect=forged_outcome
                    ),
                    self.assertRaisesRegex(
                        JournalCorruption,
                        "TaskOutcome semantic digest differs",
                    ),
                ):
                    validate_history(storage)

    def test_verification_semantic_binding_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with HostStorage(directory) as storage:
                self._accept(storage, suffix="verification-drift")
                row, payload = self._decision_event(storage)
                forged = dict(payload)
                data = dict(forged["data"])
                data["verificationDigest"] = canonical_digest(
                    {"forged": "verification-semantic-digest"}
                )
                forged["data"] = data
                original_get = storage.objects.get

                def forged_payload(digest, *, expected_kind=None):
                    if digest == row["payload_digest"]:
                        return forged
                    return original_get(digest, expected_kind=expected_kind)

                with (
                    patch.object(
                        storage.objects, "get", side_effect=forged_payload
                    ),
                    self.assertRaisesRegex(
                        JournalCorruption,
                        "CompletionDecision identities differ",
                    ),
                ):
                    validate_history(storage)

    def test_outcome_object_must_be_referenced_by_decision_event(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with HostStorage(directory) as storage:
                self._accept(storage, suffix="outcome-edge")
                row, payload = self._decision_event(storage)
                outcome_object_digest = payload["data"]["outcomeObjectDigest"]
                assert isinstance(outcome_object_digest, str)
                self.assertEqual(
                    storage.journal.connection.execute(
                        "DELETE FROM event_object_refs "
                        "WHERE event_id = ? AND digest = ? AND role = 'reference'",
                        (row["event_id"], outcome_object_digest),
                    ).rowcount,
                    1,
                )
                self.assertIn(
                    outcome_object_digest,
                    {item.digest for item in storage.journal.object_refs()},
                )
                with self.assertRaisesRegex(
                    JournalCorruption,
                    "Task Outcome is not admitted by its Event",
                ):
                    validate_history(storage)
                storage.journal.connection.execute(
                    "INSERT INTO event_object_refs(event_id, digest, role) "
                    "VALUES (?, ?, 'reference')",
                    (row["event_id"], outcome_object_digest),
                )
                validate_history(storage)

    def test_rejected_completion_has_no_outcome_and_valid_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with HostStorage(directory) as storage:
                host, proposed, output = self._propose(
                    storage, suffix="rejected"
                )
                rejected = host.adjudicate_completion(
                    proposed,
                    artifact_exists=lambda ref: ref == output,
                    acceptance_verifier=lambda _: (
                        False,
                        "fixture rejection",
                        {"accepted": False},
                    ),
                )
                self.assertFalse(rejected.decision.accepted)
                self.assertIsNone(rejected.outcome)
                snapshot = storage.read_task_event(TASK_ID)
                self.assertIsNone(snapshot.data["outcomeDigest"])
                self.assertIsNone(snapshot.data["outcomeObjectDigest"])
                validate_history(storage)


if __name__ == "__main__":
    unittest.main()
