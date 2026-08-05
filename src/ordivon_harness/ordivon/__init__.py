"""Lazy public exports.

Independent Harness modules load without the optional Host integration. Historical
exports resolve on first access and preserve the pre-1.0 compatibility surface.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_HOST_EXTRA_MESSAGE = ("Ordivon Harness Ordivon adapter Host integration is not installed; "
    "install ordivon-harness[host] for Host-backed APIs")

_EXPORTS: dict[str, tuple[str, str]] = {
    'DEFAULT_DEEPSEEK_BASE_URL': ('.deepseek', 'DEFAULT_DEEPSEEK_BASE_URL'),
    'DEFAULT_DEEPSEEK_SECRET_PATH': ('.deepseek', 'DEFAULT_DEEPSEEK_SECRET_PATH'),
    'ORDIVON_HARNESS_ID': ('.manifest', 'ORDIVON_HARNESS_ID'),
    'ORDIVON_HARNESS_PROTOCOL': ('.manifest', 'ORDIVON_HARNESS_PROTOCOL'),
    'ORDIVON_HARNESS_PROTOCOL_REVISION': ('.manifest', 'ORDIVON_HARNESS_PROTOCOL_REVISION'),
    'SUPPORTED_DEEPSEEK_MODELS': ('.deepseek', 'SUPPORTED_DEEPSEEK_MODELS'),
    'AgentLoopResult': ('.loop', 'AgentLoopResult'),
    'AgentRunConclusion': ('.model', 'AgentRunConclusion'),
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
    'CompiledHarnessInput': ('.input', 'CompiledHarnessInput'),
    'DeepSeekPostHandle': ('.deepseek', 'DeepSeekPostHandle'),
    'DeepSeekSettings': ('.deepseek', 'DeepSeekSettings'),
    'DeepSeekTransport': ('.deepseek', 'DeepSeekTransport'),
    'DeepSeekTurnAdapter': ('.deepseek', 'DeepSeekTurnAdapter'),
    'ExecutionControl': ('.control', 'ExecutionControl'),
    'HarnessContextCompiler': ('.input', 'HarnessContextCompiler'),
    'HarnessContextRequest': ('.input', 'HarnessContextRequest'),
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
    'HarnessRuntimeCatalog': ('.tools', 'HarnessRuntimeCatalog'),
    'HarnessTrace': ('.events', 'HarnessTrace'),
    'INDEPENDENT_SEARCH_TOOL_GRANT': ('.sqlite_runtime_bridge', 'INDEPENDENT_SEARCH_TOOL_GRANT'),
    'INDEPENDENT_SEARCH_TOOL_GRANT_DIGEST': ('.sqlite_runtime_bridge', 'INDEPENDENT_SEARCH_TOOL_GRANT_DIGEST'),
    'INDEPENDENT_SEARCH_TOOL_SURFACE': ('.sqlite_runtime_bridge', 'INDEPENDENT_SEARCH_TOOL_SURFACE'),
    'INDEPENDENT_SEARCH_TOOL_SURFACE_DIGEST': ('.sqlite_runtime_bridge', 'INDEPENDENT_SEARCH_TOOL_SURFACE_DIGEST'),
    'HostHarnessRunStore': ('.run_store', 'HostHarnessRunStore'),
    'HttpClientDeepSeekTransport': ('.deepseek', 'HttpClientDeepSeekTransport'),
    'NativeRunTimes': ('.result', 'NativeRunTimes'),
    'OrdivonAgentLoop': ('.loop', 'OrdivonAgentLoop'),
    'OrdivonInputCompiler': ('.input', 'OrdivonInputCompiler'),
    'RunBudget': ('.loop', 'RunBudget'),
    'RunDeadline': ('.control', 'RunDeadline'),
    'RunStopCode': ('.loop', 'RunStopCode'),
    'NO_TOOL_AGENT_SURFACE': ('.sqlite_agent_bridge', 'NO_TOOL_AGENT_SURFACE'),
    'NO_TOOL_AGENT_SURFACE_DIGEST': ('.sqlite_agent_bridge', 'NO_TOOL_AGENT_SURFACE_DIGEST'),
    'RuntimeToolBridge': ('.tools', 'RuntimeToolBridge'),
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
    'ToolBridgeError': ('.tools', 'ToolBridgeError'),
    'ToolBridgeErrorKind': ('.tools', 'ToolBridgeErrorKind'),
    'ToolObservation': ('.tool_bridge', 'ToolObservation'),
    'TraceRecorder': ('.events', 'TraceRecorder'),
    'UrllibDeepSeekTransport': ('.deepseek', 'UrllibDeepSeekTransport'),
    'build_native_run_receipt': ('.result', 'build_native_run_receipt'),
    'discover_harness_runtime_catalog': ('.tools', 'discover_harness_runtime_catalog'),
    'harness_context_object_digest': ('.input', 'harness_context_object_digest'),
    'model_tool_definitions': ('.tools', 'model_tool_definitions'),
    'ordivon_harness_manifest': ('.manifest', 'ordivon_harness_manifest'),
    'record_native_run_result': ('.result', 'record_native_run_result'),
}

__all__ = list(_EXPORTS)

def __getattr__(name: str) -> Any:
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attribute_name = target
    try:
        module = import_module(module_name, __name__)
    except ModuleNotFoundError as error:
        if error.name == "ordivon_host" or (error.name or "").startswith("ordivon_host."):
            raise ModuleNotFoundError(_HOST_EXTRA_MESSAGE) from error
        raise
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value

def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
