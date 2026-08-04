from __future__ import annotations

from dataclasses import dataclass

from anc_canonical import JsonValue
from ._host_compat.runtime import (
    RuntimeClient,
    RuntimeClientError,
    ensure_workspace_closed,
)

from .host import (
    HarnessHost,
    HarnessLifecycleError,
    RecordedNativeRunAbandonment,
    RecordedNativeRunRecovery,
)
from .ordivon.run_store import HostHarnessRunStore
from .ordivon.tools import RuntimeToolBridge, discover_harness_runtime_catalog
from .protocol import HarnessProviderCallStatus
from .recovery import validate_native_run_recovery_trigger


@dataclass(frozen=True, slots=True)
class NativeRunRecoveryResult:
    recovery: RecordedNativeRunRecovery
    abandonment: RecordedNativeRunAbandonment | None

    @property
    def safe_to_replace(self) -> bool:
        return self.abandonment is not None


class NativeRunRecoveryController:
    """Recover an Assignment whose native process disappeared before record_run()."""

    def __init__(self, host: HarnessHost, runtime: RuntimeClient) -> None:
        self.host = host
        self.runtime = runtime

    def recover(
        self,
        task_id: str,
        *,
        trigger: str = "host_restart",
        auto_abandon: bool = True,
    ) -> NativeRunRecoveryResult:
        validate_native_run_recovery_trigger(trigger)
        try:
            abandonment = self.host.load_current_native_run_abandonment(task_id)
        except HarnessLifecycleError:
            abandonment = None
        if abandonment is not None:
            return NativeRunRecoveryResult(
                recovery=abandonment.recovery,
                abandonment=abandonment,
            )
        try:
            self.host.load_current_run(task_id)
        except HarnessLifecycleError:
            pass
        else:
            raise HarnessLifecycleError(
                "recorded native Harness Run must use its durable receipt, not abandonment recovery"
            )
        committed = self.host.load_current_assignment(task_id)
        if committed.native_run_contract is None or committed.tool_grant is None:
            raise HarnessLifecycleError(
                "current Harness Assignment is not a native Run"
            )

        run_store = HostHarnessRunStore(self.host, committed)
        provider_unknowns: list[str] = []
        provider_dispatch_pending = False
        provider_evidence: dict[str, JsonValue] = {"status": "not-present"}
        try:
            retained_provider_call = run_store.load_current_provider_call()
        except KeyError:
            retained_provider_call = None
        except Exception as error:  # noqa: BLE001 - corrupt extension state becomes recovery evidence.
            retained_provider_call = None
            provider_evidence = {
                "status": "unreadable",
                "errorType": type(error).__name__,
                "message": str(error)[:2_048],
            }
            provider_unknowns.append("active Provider Call state is unreadable")
        if retained_provider_call is not None:
            record = retained_provider_call.record
            failure = retained_provider_call.failure
            now_ms = self.host.kernel.clock_ms()
            structured_outcome = (
                retained_provider_call.result is not None
                and retained_provider_call.result_object is not None
            ) or (
                failure is not None
                and retained_provider_call.failure_object is not None
            )
            provider_evidence = {
                "status": record.status.value,
                "providerCallId": record.provider_call_id,
                "recordDigest": record.digest,
                "recordObjectDigest": retained_provider_call.record_object.digest,
                "sourceKind": record.source_kind.value,
                "sourceDigest": record.source_digest,
                "sourceObjectDigest": record.source_object_digest,
                "stateObjectDigest": record.state_object_digest,
                "turnId": record.turn_id,
                "turnSequence": record.turn_sequence,
                "requestDigest": record.request_digest,
                "adapterId": record.adapter_id,
                "requestedModelId": record.requested_model_id,
                "holderId": record.holder_id,
                "claimGeneration": record.claim_generation,
                "issuedAtMs": record.issued_at_ms,
                "expiresAtMs": record.expires_at_ms,
                "recordedAtMs": record.recorded_at_ms,
                "expired": now_ms > record.expires_at_ms,
                "resultDigest": record.result_digest,
                "resultObjectDigest": record.result_object_digest,
                "failureDigest": record.failure_digest,
                "failureObjectDigest": record.failure_object_digest,
                "failureReceipt": (
                    None if failure is None else failure.to_dict()
                ),
                "structuredFailure": failure is not None,
                "structuredOutcome": structured_outcome,
            }
            if record.status is HarnessProviderCallStatus.COMPLETED:
                raise HarnessLifecycleError(
                    "durable completed Provider Call result requires resume; "
                    "abandonment recovery is not admissible"
                )
            if (
                record.status
                in {
                    HarnessProviderCallStatus.FAILED,
                    HarnessProviderCallStatus.UNKNOWN,
                }
                and structured_outcome
            ):
                raise HarnessLifecycleError(
                    f"durable structured {record.status.value.upper()} Provider "
                    "outcome requires resume; abandonment recovery is not admissible"
                )
            if record.status is HarnessProviderCallStatus.CLAIMED:
                if now_ms <= record.expires_at_ms:
                    detail = (
                        "has a live claim; wait for its holder or resume after expiry"
                    )
                else:
                    detail = "claim expired before dispatch and resume must reclaim it"
                raise HarnessLifecycleError(
                    f"Provider Call {record.provider_call_id} {detail}; "
                    "abandonment recovery is not admissible"
                )
            if record.status is HarnessProviderCallStatus.DISPATCHING:
                provider_dispatch_pending = True
                provider_unknowns.append(
                    "Provider Call DISPATCHING outcome remains UNKNOWN: "
                    f"{record.provider_call_id}"
                )
            elif record.status is HarnessProviderCallStatus.UNKNOWN:
                provider_unknowns.append(
                    "Provider Call UNKNOWN outcome requires explicit reconciliation: "
                    f"{record.provider_call_id}"
                )
            elif record.status is HarnessProviderCallStatus.FAILED:
                detail = (
                    "has a durable structured outcome that is not yet consumed"
                    if structured_outcome
                    else "has no durable structured outcome"
                )
                provider_unknowns.append(
                    f"Provider Call FAILED {detail}: {record.provider_call_id}"
                )

        try:
            catalog = discover_harness_runtime_catalog(self.runtime)
        except RuntimeClientError:
            catalog_status = "unavailable"
        else:
            catalog_status = (
                "matched"
                if catalog.digest == committed.assignment.tool_catalog_digest
                else "drifted"
            )

        tool_step_unknowns: list[str] = []
        tool_step_evidence: dict[str, JsonValue] = {"status": "not-present"}
        try:
            retained_step = run_store.load_current_tool_step()
        except KeyError:
            retained_step = None
        except Exception as error:  # noqa: BLE001 - corrupt extension state becomes recovery evidence.
            retained_step = None
            tool_step_evidence = {
                "status": "unreadable",
                "errorType": type(error).__name__,
                "message": str(error)[:2_048],
            }
            tool_step_unknowns.append("active Tool Step state is unreadable")
        if retained_step is not None:
            receipt = retained_step.receipt
            tool_step_evidence = {
                "status": ("prepared" if receipt is None else receipt.status.value),
                "toolCallId": retained_step.intent.tool_call_id,
                "clientRequestId": retained_step.intent.client_request_id,
                "runtimeJobRef": (None if receipt is None else receipt.runtime_job_ref),
            }
            if receipt is None or not receipt.terminal:
                if catalog_status != "matched":
                    tool_step_unknowns.append(
                        "active Tool Step cannot reconcile without the committed Runtime catalog"
                    )
                else:
                    bridge = RuntimeToolBridge(
                        committed,
                        harness_run_id=run_store.harness_run_id,
                        runtime=self.runtime,
                        run_store=run_store,
                    )
                    try:
                        observation = bridge.reconcile_current_tool_step()
                    except Exception as error:  # noqa: BLE001 - reconciliation failure must remain UNKNOWN evidence.
                        tool_step_evidence = {
                            **tool_step_evidence,
                            "reconciliation": "failed",
                            "errorType": type(error).__name__,
                            "message": str(error)[:2_048],
                        }
                        tool_step_unknowns.append(
                            "active Tool Step reconciliation failed"
                        )
                    else:
                        committed = bridge.committed
                        run_store = bridge.run_store or run_store
                        tool_step_evidence = {
                            **tool_step_evidence,
                            "reconciliation": "recorded",
                            "resultStatus": observation.status,
                            "runtimeJobRef": observation.runtime_job_ref,
                            "observationDigest": observation.digest,
                        }
                        if observation.status in {"unknown", "cancel-requested"}:
                            tool_step_unknowns.append(
                                f"active Tool Step remains {observation.status}: "
                                f"{retained_step.intent.tool_call_id}"
                            )

        workspace_id = committed.assignment.workspace_ref
        workspace_evidence: dict[str, JsonValue]
        consequence = self.host.grant_recovery_consequence(committed)
        if workspace_id is None:
            workspace_status = "not_applicable"
            workspace_evidence = {"workspaceId": None, "notApplicable": True}
        elif consequence.value == "observation-only" and not provider_dispatch_pending:
            try:
                workspace_evidence = ensure_workspace_closed(
                    self.runtime,
                    workspace_id,
                    force=True,
                )
            except RuntimeClientError as error:
                workspace_status = "unknown"
                workspace_evidence = {
                    "workspaceId": workspace_id,
                    "errorType": type(error).__name__,
                    "message": str(error)[:2_048],
                }
            else:
                workspace_status = (
                    "already_absent"
                    if workspace_evidence.get("alreadyAbsent") is True
                    else "closed"
                )
        else:
            try:
                workspace_snapshot = self.runtime.call_tool(
                    "workspace.get",
                    {"schemaVersion": 1, "workspaceId": workspace_id},
                )
            except RuntimeClientError as error:
                workspace_status = "unknown"
                workspace_evidence = {
                    "workspaceId": workspace_id,
                    "retained": True,
                    "errorType": type(error).__name__,
                    "message": str(error)[:2_048],
                }
            else:
                try:
                    diff_evidence = self.runtime.call_tool(
                        "workspace.diff",
                        {
                            "schemaVersion": 1,
                            "workspaceId": workspace_id,
                            "maxBytes": 1_048_576,
                        },
                    )
                except RuntimeClientError as error:
                    diff_evidence = {
                        "available": False,
                        "errorType": type(error).__name__,
                        "message": str(error)[:2_048],
                    }
                workspace_status = "retained"
                workspace_evidence = {
                    "workspaceId": workspace_id,
                    "retained": True,
                    "workspace": workspace_snapshot,
                    "diff": diff_evidence,
                }

        workspace_evidence = {
            **workspace_evidence,
            "toolStepReconciliation": tool_step_evidence,
            "toolStepUnresolvedUnknowns": list(tool_step_unknowns),
            "providerCallReconciliation": provider_evidence,
            "providerCallUnresolvedUnknowns": list(provider_unknowns),
        }
        additional_unknowns = tuple(
            dict.fromkeys((*tool_step_unknowns, *provider_unknowns))
        )
        recovery = self.host.record_native_run_recovery(
            committed,
            trigger=trigger,
            catalog_status=catalog_status,
            workspace_status=workspace_status,
            workspace_evidence=workspace_evidence,
            additional_unknowns=additional_unknowns,
        )
        if recovery.assessment.safe_to_abandon and auto_abandon:
            abandonment = self.host.abandon_native_run(
                recovery,
                reason_code=trigger,
            )
        else:
            abandonment = None
        return NativeRunRecoveryResult(
            recovery=recovery,
            abandonment=abandonment,
        )
