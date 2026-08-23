#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

APPLICATION_REVISION = "finance-current-state-application-v2"
CONSUMER_CLASSES = frozenset({"ordinary", "audit", "dogfood", "test"})


def _load_composition(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "ordivon_finance_current_state_composition", path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load Finance composition from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def application_foreign_references(
    consumer_episode_ref: str, consumer_class: str
) -> list[dict[str, str]]:
    episode = consumer_episode_ref.strip() if isinstance(consumer_episode_ref, str) else ""
    if not episode or episode != consumer_episode_ref or len(episode.encode("utf-8")) > 300:
        raise ValueError("consumer episode ref must be non-empty, trimmed, and <=300 UTF-8 bytes")
    if consumer_class not in CONSUMER_CLASSES:
        raise ValueError(f"consumer class must be one of {sorted(CONSUMER_CLASSES)}")
    return [
        {
            "namespace": "ordivon.application",
            "type": "application",
            "id": "finance-current-state",
            "generation": APPLICATION_REVISION,
        },
        {
            "namespace": "ordivon.application",
            "type": "consumer_class",
            "id": consumer_class,
        },
        {
            "namespace": "ordivon.application",
            "type": "consumer_episode",
            "id": episode,
        },
    ]


class ProvenanceRuntimeClient:
    """Inject caller-owned opaque consumer provenance into physical Runtime Jobs."""

    def __init__(self, delegate: Any, references: list[dict[str, str]]):
        self.delegate = delegate
        self.references = [dict(item) for item in references]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name != "workspace.exec":
            return self.delegate.call_tool(name, arguments)
        execution = arguments.get("execution")
        if not isinstance(execution, dict):
            raise TypeError("workspace.exec provenance injection requires execution object")
        existing = execution.get("foreignReferences", [])
        if not isinstance(existing, list) or not all(isinstance(item, dict) for item in existing):
            raise TypeError("workspace.exec foreignReferences must be an array of objects")
        combined = [dict(item) for item in existing] + [dict(item) for item in self.references]
        keys = [(item.get("namespace"), item.get("type"), item.get("id")) for item in combined]
        if len(keys) != len(set(keys)):
            raise ValueError("application provenance would duplicate a Runtime foreign reference")
        if len(combined) > 16:
            raise ValueError("application provenance exceeds Runtime foreign reference bound")
        combined.sort(key=lambda item: (str(item.get("namespace")), str(item.get("type")), str(item.get("id"))))
        request = dict(arguments)
        request["execution"] = {**execution, "foreignReferences": combined}
        return self.delegate.call_tool(name, request)


def _compact_obligation(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    candidate_refs = value.get("candidateOperationRefs")
    return {
        "kind": _text(value.get("kind")),
        "need": _text(value.get("need")),
        "status": _text(value.get("status")),
        "candidateOperationRefs": [
            item for item in candidate_refs or [] if isinstance(item, str) and item
        ],
    }


def _compact_operation(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    operation_ref = _text(value.get("operationRef"))
    operation_id = _text(value.get("operationId"))
    if operation_ref is None or operation_id is None:
        return None
    return {
        "operationId": operation_id,
        "operationRef": operation_ref,
        "semanticRole": _text(value.get("semanticRole")),
        "purpose": _text(value.get("purpose")),
        "authorityModel": _text(value.get("authorityModel")),
        "effectBoundary": _text(value.get("effectBoundary")),
        "externalFinancialWritePotential": value.get("externalFinancialWritePotential")
        if isinstance(value.get("externalFinancialWritePotential"), bool)
        else None,
        "governanceBoundary": value.get("governanceBoundary")
        if isinstance(value.get("governanceBoundary"), bool)
        else None,
    }


def compact_current_finance_context(context: dict[str, Any]) -> dict[str, Any]:
    obligations = [
        compact
        for item in context.get("obligations", [])
        if (compact := _compact_obligation(item)) is not None
    ]
    operation_refs = {
        ref
        for obligation in obligations
        for ref in obligation["candidateOperationRefs"]
    }
    operations = [
        compact
        for item in context.get("agentOperations", [])
        if (compact := _compact_operation(item)) is not None
    ]
    current_affordances = [
        operation for operation in operations if operation["operationRef"] in operation_refs
    ]

    goal = context.get("goal") if isinstance(context.get("goal"), dict) else {}
    portfolio = context.get("portfolio") if isinstance(context.get("portfolio"), dict) else {}
    portfolio_state = (
        context.get("portfolioState")
        if isinstance(context.get("portfolioState"), dict)
        else {}
    )
    portfolio_status = (
        portfolio_state.get("status")
        if isinstance(portfolio_state.get("status"), dict)
        else {}
    )
    decision_state = (
        context.get("decisionState")
        if isinstance(context.get("decisionState"), dict)
        else {}
    )
    latest_decision = (
        decision_state.get("latestDecision")
        if isinstance(decision_state.get("latestDecision"), dict)
        else {}
    )
    current_evaluation = (
        decision_state.get("currentEvaluation")
        if isinstance(decision_state.get("currentEvaluation"), dict)
        else {}
    )
    rationality = (
        portfolio_state.get("currentCapitalRationalityEvaluation")
        if isinstance(portfolio_state.get("currentCapitalRationalityEvaluation"), dict)
        else {}
    )
    latest_attempt = (
        portfolio_status.get("latestAttempt")
        if isinstance(portfolio_status.get("latestAttempt"), dict)
        else {}
    )
    total_equity = None
    latest_snapshot = portfolio_state.get("latestSnapshot")
    if isinstance(latest_snapshot, dict):
        equity = latest_snapshot.get("totalEquity")
        if isinstance(equity, dict):
            total_equity = {
                "value": equity.get("value"),
                "currency": _text(equity.get("currency")),
                "basis": _text(equity.get("basis")),
                "sourceField": _text(equity.get("sourceField")),
            }

    return {
        "schemaVersion": 0,
        "kind": "ordivon.application.finance-current-state-projection",
        "truthRole": "bounded-source-preserving-projection-of-finance-context",
        "stateVersion": _text(context.get("stateVersion")),
        "contextId": _text(context.get("contextId")),
        "goalId": _text(goal.get("goalId")),
        "portfolioId": _text(portfolio.get("portfolioId")),
        "decision": {
            "decisionId": _text(latest_decision.get("decisionId")),
            "standing": _text(latest_decision.get("decision")),
            "verdict": _text(current_evaluation.get("verdict")),
            "proposalEligibility": _text(current_evaluation.get("proposalEligibility")),
            "governanceNeeds": [
                item
                for item in current_evaluation.get("governanceNeeds", [])
                if isinstance(item, str)
            ],
        },
        "capitalRationality": {
            "verdict": _text(rationality.get("verdict")),
            "hardBlockingReasons": [
                item
                for item in rationality.get("hardBlockingReasons", [])
                if isinstance(item, str)
            ],
            "attentionItems": [
                item
                for item in rationality.get("attentionItems", [])
                if isinstance(item, str)
            ],
        },
        "portfolioStanding": {
            "snapshotRef": _text(portfolio_status.get("snapshotRef")),
            "snapshotObservedAt": _text(portfolio_status.get("snapshotObservedAt")),
            "observationHealth": _text(portfolio_status.get("observationHealth")),
            "latestAttemptStatus": _text(latest_attempt.get("status")),
            "latestAttemptFailedAfterSnapshot": portfolio_status.get(
                "latestAttemptFailedAfterSnapshot"
            )
            if isinstance(portfolio_status.get("latestAttemptFailedAfterSnapshot"), bool)
            else None,
            "exposureProjectionCurrent": portfolio_status.get(
                "exposureProjectionCurrent"
            )
            if isinstance(portfolio_status.get("exposureProjectionCurrent"), bool)
            else None,
            "totalEquity": total_equity,
        },
        "obligations": obligations,
        "currentAffordances": current_affordances,
        "affordanceSelection": {
            "basis": "open-obligation-candidateOperationRefs",
            "listOrderCarriesPriority": False,
            "singleNextOperationClaimed": False,
        },
        "claims": {
            "ownerTruthMinted": False,
            "priorityInferred": False,
            "operationAuthorityExpanded": False,
            "decisionConclusionSynthesized": False,
        },
    }


def run_finance_current_state_application(
    client: Any,
    composition: ModuleType,
    *,
    finance_workspace_id: str,
    workstation_workspace_id: str,
    finance_state_root: str,
    finance_app_python: str | None,
    request_prefix: str,
    consumer_episode_ref: str,
    consumer_class: str,
) -> dict[str, Any]:
    composition_receipt = composition.run_finance_workstation_composition(
        client,
        finance_workspace_id=finance_workspace_id,
        workstation_workspace_id=workstation_workspace_id,
        finance_state_root=finance_state_root,
        finance_app_python=finance_app_python,
        request_prefix=request_prefix,
    )
    status = str(composition_receipt.get("status"))
    base = {
        "schemaVersion": 1,
        "kind": "ordivon.application.finance-current-state-receipt",
        "revision": APPLICATION_REVISION,
        "status": status,
        "composition": composition_receipt,
        "currentState": None,
        "consumerProvenance": {
            "truthRole": "caller-application-provenance-claim",
            "episodeRef": consumer_episode_ref,
            "consumerClass": consumer_class,
            "adoptionProven": False,
            "benefitProven": False,
        },
        "claims": {
            "ownerTruthMinted": False,
            "providerPlumbingExposedToAgent": False,
            "workstationMutationAuthorityGranted": False,
            "toolAuthorityExpanded": False,
        },
    }
    if not status.startswith("completed"):
        return base

    env = composition._finance_env(finance_state_root, finance_app_python)
    current = composition._domain_exec(
        client,
        owner="ordivon-finance",
        workspace_id=finance_workspace_id,
        script="scripts/finance-domain.mjs",
        operation="finance.context.compile",
        arguments={},
        client_request_id=f"{request_prefix}-finance-context-current",
        env=env,
    )
    if current.envelope.get("ok") is not True:
        base["status"] = "blocked_current_context"
        return base
    result = current.envelope.get("result")
    if not isinstance(result, dict):
        raise TypeError("current Finance context compile omitted result")
    base["status"] = "completed_current_state"
    projection = compact_current_finance_context(result)
    base["currentState"] = projection
    base["modelView"] = {
        "schemaVersion": 0,
        "kind": "ordivon.application.finance-current-state-model-view",
        "intent": "finance.current-state-and-current-affordances",
        "currentState": projection,
        "claims": {
            "diagnosticCompositionOmitted": True,
            "ownerTruthMinted": False,
            "priorityInferred": False,
            "singleNextOperationClaimed": False,
            "toolAuthorityExpanded": False,
        },
    }
    base["currentContextRuntimeJobId"] = current.runtime_job_id
    base["currentContextRuntimeAttemptId"] = current.runtime_attempt_id
    return base


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--finance-workspace", required=True)
    parser.add_argument("--workstation-workspace", required=True)
    parser.add_argument("--finance-state-root", required=True)
    parser.add_argument("--finance-app-python")
    parser.add_argument("--request-prefix", required=True)
    parser.add_argument("--consumer-episode-ref", required=True)
    parser.add_argument("--consumer-class", choices=sorted(CONSUMER_CLASSES), required=True)
    parser.add_argument("--runtime-endpoint", default="http://127.0.0.1:8897/mcp")
    parser.add_argument(
        "--runtime-environment-file", default="/etc/ordivon/ordivon-runtime.env"
    )
    parser.add_argument(
        "--runtime-scripts", default="/root/projects/ordivon-runtime/scripts"
    )
    parser.add_argument(
        "--composition-script",
        default=str(Path(__file__).with_name("first_interface_finance_workstation_composition.py")),
    )
    args = parser.parse_args()

    composition = _load_composition(Path(args.composition_script))
    raw_client = composition._runtime_client(
        Path(args.runtime_scripts), Path(args.runtime_environment_file), args.runtime_endpoint
    )
    references = application_foreign_references(
        args.consumer_episode_ref, args.consumer_class
    )
    client = ProvenanceRuntimeClient(raw_client, references)
    project_environment = None
    if args.finance_app_python is None:
        project_environment = composition._prepare_finance_project_environment(
            client,
            finance_workspace_id=args.finance_workspace,
            client_request_id=f"{args.request_prefix}-finance-project-environment",
        )
    receipt = run_finance_current_state_application(
        client,
        composition,
        finance_workspace_id=args.finance_workspace,
        workstation_workspace_id=args.workstation_workspace,
        finance_state_root=args.finance_state_root,
        finance_app_python=args.finance_app_python,
        request_prefix=args.request_prefix,
        consumer_episode_ref=args.consumer_episode_ref,
        consumer_class=args.consumer_class,
    )
    if project_environment is not None:
        receipt["projectEnvironmentPreparation"] = project_environment
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["status"] == "completed_current_state" else 2


if __name__ == "__main__":
    raise SystemExit(main())
