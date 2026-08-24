"""Lazy public exports.

This facade exposes only Host-free Agent-loop, Provider, continuity, and Runtime-bridge values.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS: dict[str, tuple[str, str]] = {
    'DEFAULT_DEEPSEEK_BASE_URL': ('.deepseek', 'DEFAULT_DEEPSEEK_BASE_URL'),
    'DEFAULT_DEEPSEEK_SECRET_PATH': ('.deepseek', 'DEFAULT_DEEPSEEK_SECRET_PATH'),
    'SUPPORTED_DEEPSEEK_MODELS': ('.deepseek', 'SUPPORTED_DEEPSEEK_MODELS'),
    'AgentLoopResult': ('.loop', 'AgentLoopResult'),
    'AgentRunConclusion': ('.model', 'AgentRunConclusion'),
    'AgentStructuredResult': ('.model', 'AgentStructuredResult'),
    'AgentToolCall': ('.model', 'AgentToolCall'),
    'AgentToolDefinition': ('.model', 'AgentToolDefinition'),
    'AgentTurnAdapter': ('.model', 'AgentTurnAdapter'),
    'AgentTurnAdapterError': ('.model', 'AgentTurnAdapterError'),
    'AgentTurnCallHandle': ('.model', 'AgentTurnCallHandle'),
    'AgentTurnDispatchSafety': ('.model', 'AgentTurnDispatchSafety'),
    'AgentTurnFailureCode': ('.model', 'AgentTurnFailureCode'),
    'AgentTurnRequest': ('.model', 'AgentTurnRequest'),
    'AgentTurnResult': ('.model', 'AgentTurnResult'),
    'CancellationToken': ('.loop', 'CancellationToken'),
    'DeepSeekPostHandle': ('.deepseek', 'DeepSeekPostHandle'),
    'DeepSeekSettings': ('.deepseek', 'DeepSeekSettings'),
    'DeepSeekTransport': ('.deepseek', 'DeepSeekTransport'),
    'DeepSeekTurnAdapter': ('.deepseek', 'DeepSeekTurnAdapter'),
    'ExecutionControl': ('.control', 'ExecutionControl'),
    'HarnessDispatchFenceV2': ('.continuity_records', 'HarnessDispatchFenceV2'),
    'HarnessProviderCallClaimHeld': ('.run_store_port', 'HarnessProviderCallClaimHeld'),
    'HarnessProviderCallRecoveryRequired': ('.run_store_port', 'HarnessProviderCallRecoveryRequired'),
    'HarnessProviderCallRequestMismatch': ('.run_store_port', 'HarnessProviderCallRequestMismatch'),
    'HarnessProviderCallRecordV2': ('.continuity_records', 'HarnessProviderCallRecordV2'),
    'HarnessProviderCallSourceRef': ('.run_store_port', 'HarnessProviderCallSourceRef'),
    'HarnessRunContinuityStore': ('.run_store_port', 'HarnessRunContinuityStore'),
    'HarnessRunEvent': ('.events', 'HarnessRunEvent'),
    'HarnessRunStoreBinding': ('.run_store_port', 'HarnessRunStoreBinding'),
    'HarnessRunState': ('..run_state', 'HarnessRunState'),
    'HarnessTrace': ('.events', 'HarnessTrace'),
    'INDEPENDENT_REPOSITORY_REPAIR_EDIT_TOOL_DEFINITIONS': ('.sqlite_repository_repair_bridge', 'INDEPENDENT_REPOSITORY_REPAIR_EDIT_TOOL_DEFINITIONS'),
    'INDEPENDENT_REPOSITORY_REPAIR_EDIT_TOOL_GRANT': ('.sqlite_repository_repair_bridge', 'INDEPENDENT_REPOSITORY_REPAIR_EDIT_TOOL_GRANT'),
    'INDEPENDENT_REPOSITORY_REPAIR_EDIT_TOOL_GRANT_DIGEST': ('.sqlite_repository_repair_bridge', 'INDEPENDENT_REPOSITORY_REPAIR_EDIT_TOOL_GRANT_DIGEST'),
    'INDEPENDENT_REPOSITORY_REPAIR_EDIT_TOOL_SURFACE': ('.sqlite_repository_repair_bridge', 'INDEPENDENT_REPOSITORY_REPAIR_EDIT_TOOL_SURFACE'),
    'INDEPENDENT_REPOSITORY_REPAIR_EDIT_TOOL_SURFACE_DIGEST': ('.sqlite_repository_repair_bridge', 'INDEPENDENT_REPOSITORY_REPAIR_EDIT_TOOL_SURFACE_DIGEST'),
    'INDEPENDENT_REPOSITORY_REPAIR_TOOL_DEFINITIONS': ('.sqlite_repository_repair_bridge', 'INDEPENDENT_REPOSITORY_REPAIR_TOOL_DEFINITIONS'),
    'INDEPENDENT_REPOSITORY_REPAIR_TOOL_GRANT': ('.sqlite_repository_repair_bridge', 'INDEPENDENT_REPOSITORY_REPAIR_TOOL_GRANT'),
    'INDEPENDENT_REPOSITORY_REPAIR_TOOL_GRANT_DIGEST': ('.sqlite_repository_repair_bridge', 'INDEPENDENT_REPOSITORY_REPAIR_TOOL_GRANT_DIGEST'),
    'INDEPENDENT_REPOSITORY_REPAIR_TOOL_SURFACE': ('.sqlite_repository_repair_bridge', 'INDEPENDENT_REPOSITORY_REPAIR_TOOL_SURFACE'),
    'INDEPENDENT_REPOSITORY_REPAIR_TOOL_SURFACE_DIGEST': ('.sqlite_repository_repair_bridge', 'INDEPENDENT_REPOSITORY_REPAIR_TOOL_SURFACE_DIGEST'),
    'SQLiteHarnessRepositoryRepairEditRuntimeBridge': ('.sqlite_repository_repair_bridge', 'SQLiteHarnessRepositoryRepairEditRuntimeBridge'),
    'SQLiteHarnessRepositoryRepairRuntimeBridge': ('.sqlite_repository_repair_bridge', 'SQLiteHarnessRepositoryRepairRuntimeBridge'),
    'INDEPENDENT_SEARCH_TOOL_GRANT': ('.sqlite_runtime_bridge', 'INDEPENDENT_SEARCH_TOOL_GRANT'),
    'INDEPENDENT_SEARCH_TOOL_GRANT_DIGEST': ('.sqlite_runtime_bridge', 'INDEPENDENT_SEARCH_TOOL_GRANT_DIGEST'),
    'INDEPENDENT_SEARCH_TOOL_SURFACE': ('.sqlite_runtime_bridge', 'INDEPENDENT_SEARCH_TOOL_SURFACE'),
    'INDEPENDENT_SEARCH_TOOL_SURFACE_DIGEST': ('.sqlite_runtime_bridge', 'INDEPENDENT_SEARCH_TOOL_SURFACE_DIGEST'),
    'HttpClientDeepSeekTransport': ('.deepseek', 'HttpClientDeepSeekTransport'),
    'OrdivonAgentLoop': ('.loop', 'OrdivonAgentLoop'),
    'RunBudget': ('.loop', 'RunBudget'),
    'RunDeadline': ('.control', 'RunDeadline'),
    'RunStopCode': ('.loop', 'RunStopCode'),
    'NO_TOOL_AGENT_GRANT': ('.sqlite_agent_bridge', 'NO_TOOL_AGENT_GRANT'),
    'NO_TOOL_AGENT_GRANT_DIGEST': ('.sqlite_agent_bridge', 'NO_TOOL_AGENT_GRANT_DIGEST'),
    'NO_TOOL_AGENT_SURFACE': ('.sqlite_agent_bridge', 'NO_TOOL_AGENT_SURFACE'),
    'NO_TOOL_AGENT_SURFACE_DIGEST': ('.sqlite_agent_bridge', 'NO_TOOL_AGENT_SURFACE_DIGEST'),
    'SQLiteHarnessAgentBridge': ('.sqlite_agent_bridge', 'SQLiteHarnessAgentBridge'),
    'SQLiteHarnessRunContinuityStore': ('.sqlite_run_store', 'SQLiteHarnessRunContinuityStore'),
    'SQLiteHarnessRuntimeBridge': ('.sqlite_runtime_bridge', 'SQLiteHarnessRuntimeBridge'),
    'SEARCH_WORKSPACE_DEFINITION': ('.sqlite_runtime_bridge', 'SEARCH_WORKSPACE_DEFINITION'),
    'ScriptedTurnAdapter': ('.model', 'ScriptedTurnAdapter'),
    'static_provider_request_digest': ('.model', 'static_provider_request_digest'),
    'StoredHarnessRunSnapshot': ('.run_store_port', 'StoredHarnessRunSnapshot'),
    'StoredHarnessProviderCall': ('.run_store_port', 'StoredHarnessProviderCall'),
    'StoredHarnessToolStep': ('.run_store_port', 'StoredHarnessToolStep'),
    'ToolBridge': ('.tool_bridge', 'ToolBridge'),
    'ToolObservation': ('.tool_bridge', 'ToolObservation'),
    'TraceRecorder': ('.events', 'TraceRecorder'),
    'UrllibDeepSeekTransport': ('.deepseek', 'UrllibDeepSeekTransport'),
}

__all__ = list(_EXPORTS)

def __getattr__(name: str) -> Any:
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attribute_name = target
    module = import_module(module_name, __name__)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value

def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
