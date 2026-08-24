from __future__ import annotations

import asyncio
import hashlib
import http.client
import os
import stat
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import httpx

from anc_canonical import (
    JsonValue,
    canonical_bytes,
    canonical_digest,
    loads_strict,
    validate_json_value,
)

from ..completion import (
    structured_completion_contract_digest,
    structured_completion_result_schema,
)
from ..tool_program import (
    HarnessToolProgram,
    HarnessToolProgramAction,
    HarnessToolProgramStep,
)
from ..working_view import (
    WORKING_SET_HISTORY_CONTROL_NAME,
    AgentCallerIngressPromotionProposal,
    AgentWorkingSetTransitionProposal,
    HarnessWorkingSetPin,
    parse_working_set_history_query,
)
from .control import ExecutionControl
from .model import (
    AgentRunConclusion,
    AgentStructuredResult,
    AgentToolCall,
    AgentToolDefinition,
    AgentTurnAdapterError,
    AgentTurnCallHandle,
    AgentTurnCapabilities,
    AgentTurnDispatchSafety,
    AgentTurnFailureCode,
    AgentTurnRequest,
    AgentTurnResult,
)

DEFAULT_DEEPSEEK_SECRET_PATH = (
    Path.home() / ".config" / "ordivon" / "secrets" / "deepseek.json"
)
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
SUPPORTED_DEEPSEEK_MODELS = ("deepseek-v4-flash", "deepseek-v4-pro")
DEFAULT_DEEPSEEK_CREDENTIAL_SCOPE_ID = "deepseek:default"
_CONCLUSION_TOOL_NAME = "submit_run_conclusion"
_WORKING_SET_TRANSITION_TOOL_NAME = "propose_working_set_transition"
_CALLER_INGRESS_PROMOTION_TOOL_NAME = "promote_caller_ingress"
_TOOL_PROGRAM_ACTION_NAME = "compose_tool_program"


def _text(value: str, label: str, *, max_bytes: int = 2_048) -> str:
    if not value or value != value.strip():
        raise ValueError(f"{label} must be non-empty and trimmed")
    if len(value.encode("utf-8")) > max_bytes:
        raise ValueError(f"{label} exceeds {max_bytes} UTF-8 bytes")
    return value


@dataclass(frozen=True, slots=True)
class DeepSeekSettings:
    api_key: str = field(repr=False)
    base_url: str = DEFAULT_DEEPSEEK_BASE_URL
    model: str = "deepseek-v4-flash"
    credential_scope_id: str = DEFAULT_DEEPSEEK_CREDENTIAL_SCOPE_ID
    timeout_seconds: float = 90.0
    max_response_bytes: int = 4_194_304
    max_output_tokens: int = 8_192

    def __post_init__(self) -> None:
        _text(self.api_key, "DeepSeek API key", max_bytes=16_384)
        if any(character.isspace() for character in self.api_key):
            raise ValueError("DeepSeek API key must not contain whitespace")
        if self.base_url != DEFAULT_DEEPSEEK_BASE_URL:
            raise ValueError("DeepSeek base URL must use the official stable endpoint")
        if self.model not in SUPPORTED_DEEPSEEK_MODELS:
            raise ValueError(f"unsupported DeepSeek model: {self.model}")
        _text(
            self.credential_scope_id,
            "DeepSeek credential scope identity",
            max_bytes=300,
        )
        if (
            self.timeout_seconds <= 0
            or self.max_response_bytes < 1
            or self.max_output_tokens < 1
        ):
            raise ValueError("DeepSeek request bounds must be positive")

    @classmethod
    def from_secret_file(
        cls,
        path: str | Path = DEFAULT_DEEPSEEK_SECRET_PATH,
        *,
        timeout_seconds: float = 90.0,
        max_response_bytes: int = 4_194_304,
        max_output_tokens: int = 8_192,
    ) -> DeepSeekSettings:
        secret_path = Path(path).expanduser()
        if secret_path.is_symlink():
            raise PermissionError("DeepSeek secret file must not be a symbolic link")
        if not secret_path.is_file():
            raise FileNotFoundError(secret_path)
        mode = stat.S_IMODE(secret_path.stat().st_mode)
        if mode & 0o077:
            raise PermissionError(
                f"DeepSeek secret permissions are too broad: {oct(mode)}; expected 0o600"
            )
        value = loads_strict(secret_path.read_bytes())
        required_fields = {
            "schemaVersion",
            "provider",
            "apiKey",
            "baseUrl",
            "model",
        }
        allowed_fields = required_fields | {"credentialScopeId"}
        if (
            not isinstance(value, dict)
            or not required_fields.issubset(value)
            or not set(value).issubset(allowed_fields)
        ):
            raise ValueError("DeepSeek secret file fields differ")
        if value["schemaVersion"] != 1 or value["provider"] != "deepseek":
            raise ValueError("DeepSeek secret schema is unsupported")
        api_key = value["apiKey"]
        base_url = value["baseUrl"]
        model = value["model"]
        credential_scope_id = value.get(
            "credentialScopeId",
            DEFAULT_DEEPSEEK_CREDENTIAL_SCOPE_ID,
        )
        if not all(
            isinstance(item, str)
            for item in (
                api_key,
                base_url,
                model,
                credential_scope_id,
            )
        ):
            raise ValueError("DeepSeek secret values must be strings")
        assert isinstance(api_key, str)
        assert isinstance(base_url, str)
        assert isinstance(model, str)
        assert isinstance(credential_scope_id, str)
        return cls(
            api_key=api_key,
            base_url=base_url,
            model=model,
            credential_scope_id=credential_scope_id,
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
            max_output_tokens=max_output_tokens,
        )


class DeepSeekTransport(Protocol):
    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        body: bytes,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> bytes: ...


class UrllibDeepSeekTransport:
    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        body: bytes,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> bytes:
        request = urllib.request.Request(url, data=body, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                raw = response.read(max_response_bytes + 1)
        except urllib.error.HTTPError as error:
            detail = error.read(8_192).decode("utf-8", errors="replace")
            if error.code in {408, 504}:
                failure_code = AgentTurnFailureCode.TIMEOUT
            elif error.code == 429 or error.code >= 500:
                failure_code = AgentTurnFailureCode.UNAVAILABLE
            else:
                failure_code = AgentTurnFailureCode.REJECTED
            raise AgentTurnAdapterError(
                f"DeepSeek returned HTTP {error.code}: {detail}",
                failure_code=failure_code,
                dispatch_safety=AgentTurnDispatchSafety.PROVIDER_REJECTED,
            ) from error
        except urllib.error.URLError as error:
            raise AgentTurnAdapterError(
                f"DeepSeek connection failed: {error.reason}",
                failure_code=AgentTurnFailureCode.TRANSPORT_FAILED,
            ) from error
        except TimeoutError as error:
            raise AgentTurnAdapterError(
                "DeepSeek request timed out",
                failure_code=AgentTurnFailureCode.TIMEOUT,
            ) from error
        except (OSError, http.client.HTTPException) as error:
            raise AgentTurnAdapterError(
                f"DeepSeek connection failed: {error}",
                failure_code=AgentTurnFailureCode.TRANSPORT_FAILED,
            ) from error
        if len(raw) > max_response_bytes:
            raise AgentTurnAdapterError(
                "DeepSeek response exceeds the configured byte bound"
            )
        return raw


def _validated_loopback_https_proxy(value: str | None) -> str | None:
    """Accept only the Workstation-owned loopback HTTP CONNECT surface.

    DeepSeek credentials must never be redirected by an arbitrary inherited
    proxy environment. A network transport profile may therefore project only
    a plain HTTP proxy on IPv4 loopback; TLS remains end-to-end to DeepSeek.
    """
    if value is None or value == "":
        return None
    parsed = urllib.parse.urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "DeepSeek HTTPS proxy must be an unauthenticated "
            "http://127.0.0.1:<port> loopback CONNECT endpoint"
        )
    if not 1 <= parsed.port <= 65535:
        raise ValueError("DeepSeek HTTPS proxy port is invalid")
    return f"http://127.0.0.1:{parsed.port}"


def _loopback_https_proxy_from_environment() -> str | None:
    upper = os.environ.get("HTTPS_PROXY")
    lower = os.environ.get("https_proxy")
    if upper and lower and upper != lower:
        raise ValueError("HTTPS_PROXY and https_proxy disagree")
    return _validated_loopback_https_proxy(upper or lower)


class DeepSeekPostHandle(Protocol):
    def poll(self, timeout_seconds: float) -> bytes | None: ...

    def cancel(self) -> None: ...


class CancellableDeepSeekTransport(Protocol):
    def start_post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        body: bytes,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> DeepSeekPostHandle: ...


class _HttpxPostHandle:
    def __init__(
        self,
        url: str,
        *,
        headers: dict[str, str],
        body: bytes,
        timeout_seconds: float,
        max_response_bytes: int,
        https_proxy: str | None = None,
    ) -> None:
        self._url = url
        self._headers = dict(headers)
        self._body = bytes(body)
        self._timeout_seconds = timeout_seconds
        self._max_response_bytes = max_response_bytes
        self._https_proxy = _validated_loopback_https_proxy(https_proxy)
        self._done = threading.Event()
        self._cancelled = threading.Event()
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task[bytes] | None = None
        self._result: bytes | None = None
        self._error: Exception | None = None
        self._thread = threading.Thread(
            target=self._run,
            name="ordivon-deepseek-httpx",
            daemon=True,
        )
        self._thread.start()

    def poll(self, timeout_seconds: float) -> bytes | None:
        if timeout_seconds < 0:
            raise ValueError("DeepSeek poll timeout must be non-negative")
        if not self._done.wait(timeout_seconds):
            return None
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result

    def cancel(self) -> None:
        self._cancelled.set()
        with self._lock:
            loop, task = self._loop, self._task
        if loop is None or task is None or task.done():
            return
        try:
            loop.call_soon_threadsafe(task.cancel)
        except RuntimeError:
            pass

    async def _post(self) -> bytes:
        parsed = urllib.parse.urlsplit(self._url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("DeepSeek URL must be absolute HTTP(S)")
        if self._https_proxy is not None and parsed.scheme != "https":
            raise ValueError("DeepSeek loopback CONNECT proxy requires an HTTPS target")
        if self._cancelled.is_set():
            raise AgentTurnAdapterError(
                "DeepSeek request was cancelled before connection",
                failure_code=AgentTurnFailureCode.FAILED,
            )
        headers = {**self._headers, "Accept-Encoding": "identity"}
        async with httpx.AsyncClient(
            proxy=self._https_proxy,
            timeout=httpx.Timeout(self._timeout_seconds),
            trust_env=False,
            follow_redirects=False,
            http1=True,
            http2=False,
        ) as client:
            async with client.stream(
                "POST",
                self._url,
                headers=headers,
                content=self._body,
            ) as response:
                raw = bytearray()
                async for chunk in response.aiter_raw():
                    remaining = self._max_response_bytes + 1 - len(raw)
                    raw.extend(chunk[:remaining])
                    if len(raw) > self._max_response_bytes:
                        break
                body = bytes(raw)
                if self._cancelled.is_set():
                    raise AgentTurnAdapterError(
                        "DeepSeek request was cancelled in flight",
                        failure_code=AgentTurnFailureCode.FAILED,
                    )
                if not 200 <= response.status_code < 300:
                    detail = body[:8_192].decode("utf-8", errors="replace")
                    if response.status_code in {408, 504}:
                        failure_code = AgentTurnFailureCode.TIMEOUT
                    elif response.status_code == 429 or response.status_code >= 500:
                        failure_code = AgentTurnFailureCode.UNAVAILABLE
                    else:
                        failure_code = AgentTurnFailureCode.REJECTED
                    raise AgentTurnAdapterError(
                        f"DeepSeek returned HTTP {response.status_code}: {detail}",
                        failure_code=failure_code,
                        dispatch_safety=AgentTurnDispatchSafety.PROVIDER_REJECTED,
                    )
                if len(body) > self._max_response_bytes:
                    raise AgentTurnAdapterError(
                        "DeepSeek response exceeds the configured byte bound"
                    )
                return body

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            with self._lock:
                self._loop = loop
                self._task = loop.create_task(self._post())
                task = self._task
                if self._cancelled.is_set():
                    task.cancel()
            self._result = loop.run_until_complete(task)
        except asyncio.CancelledError as error:
            self._error = AgentTurnAdapterError(
                "DeepSeek request was cancelled in flight",
                failure_code=AgentTurnFailureCode.FAILED,
            )
            self._error.__cause__ = error
        except AgentTurnAdapterError as error:
            self._error = error
        except httpx.TimeoutException as error:
            self._error = AgentTurnAdapterError(
                "DeepSeek request timed out",
                failure_code=AgentTurnFailureCode.TIMEOUT,
            )
            self._error.__cause__ = error
        except httpx.RequestError as error:
            self._error = AgentTurnAdapterError(
                f"DeepSeek connection failed: {error}",
                failure_code=AgentTurnFailureCode.TRANSPORT_FAILED,
            )
            self._error.__cause__ = error
        except Exception as error:  # noqa: BLE001 - preserve worker failure for poll().
            self._error = error
        finally:
            pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            loop.run_until_complete(loop.shutdown_asyncgens())
            with self._lock:
                self._loop = None
                self._task = None
            asyncio.set_event_loop(None)
            loop.close()
            self._done.set()


class HttpClientDeepSeekTransport:
    """One-request-per-handle HTTPX transport with active task cancellation.

    The optional proxy is deliberately restricted to a Workstation-owned IPv4
    loopback CONNECT endpoint. HTTPX establishes an HTTP tunnel and performs
    end-to-end TLS with the target; inherited proxy state is disabled.
    """

    def __init__(self, *, https_proxy: str | None = None) -> None:
        self.https_proxy = _validated_loopback_https_proxy(https_proxy)

    @classmethod
    def from_environment(cls) -> HttpClientDeepSeekTransport:
        return cls(https_proxy=_loopback_https_proxy_from_environment())

    def start_post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        body: bytes,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> DeepSeekPostHandle:
        return _HttpxPostHandle(
            url,
            headers=headers,
            body=body,
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
            https_proxy=self.https_proxy,
        )

    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        body: bytes,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> bytes:
        handle = self.start_post(
            url,
            headers=headers,
            body=body,
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
        )
        raw = handle.poll(timeout_seconds + 0.25)
        if raw is None:
            handle.cancel()
            try:
                handle.poll(0.5)
            except AgentTurnAdapterError:
                pass
            raise AgentTurnAdapterError(
                "DeepSeek request timed out",
                failure_code=AgentTurnFailureCode.TIMEOUT,
            )
        return raw



def _conclusion_tool(
    structured_result_schema: dict[str, JsonValue] | None = None,
) -> dict[str, JsonValue]:
    string_array: dict[str, JsonValue] = {
        "type": "array",
        "items": {"type": "string"},
        "maxItems": 128,
    }
    result_property: dict[str, JsonValue]
    result_name: str
    if structured_result_schema is None:
        result_name = "summary"
        result_property = {"type": "string", "minLength": 1}
    else:
        result_name = "result"
        result_property = structured_result_schema
    return {
        "type": "function",
        "function": {
            "name": _CONCLUSION_TOOL_NAME,
            "description": (
                "Stop this bounded Harness Run and submit a candidate result for independent "
                "caller or domain verification. Use candidate_completed when the available "
                "bounded evidence supports the candidate result. Use needs_input when a "
                "required fact remains unresolved after the useful available observations, "
                "including when further observation-only searches would only repeat or "
                "rephrase evidence already seen. This does not complete caller-owned work."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["candidate_completed", "needs_input"],
                        "description": (
                            "Choose needs_input rather than continuing equivalent bounded "
                            "searches when required evidence remains unavailable or unknown."
                        ),
                    },
                    result_name: result_property,
                    "artifact_refs": string_array,
                    "evidence_refs": string_array,
                    "unresolved_unknowns": string_array,
                },
                "required": [
                    "status",
                    result_name,
                    "artifact_refs",
                    "evidence_refs",
                    "unresolved_unknowns",
                ],
            },
        },
    }


def _tool_program_action_tool(
    allowed_tool_names: tuple[str, ...],
    *,
    max_steps: int,
) -> dict[str, JsonValue]:
    return {
        "type": "function",
        "function": {
            "name": _TOOL_PROGRAM_ACTION_NAME,
            "description": (
                "Compose one bounded linear program over only the Runtime Tools admitted "
                "for this exact turn. Use this when later Tool arguments depend mechanically "
                "on exact JSON fields observed from earlier steps. Each step remains one "
                "physical Tool Call with normal budget, recovery, UNKNOWN, and effect semantics. "
                "References use {\"$harnessObservationRef\":{\"stepId\":...,\"path\":[...]}}. "
                "No branching, loops, shell, Python, expressions, or hidden Tools are allowed."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "steps": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": max_steps,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "step_id": {"type": "string", "minLength": 1},
                                "tool_name": {
                                    "type": "string",
                                    "enum": list(allowed_tool_names),
                                },
                                "arguments": {
                                    "type": "object",
                                    "additionalProperties": True,
                                },
                            },
                            "required": ["step_id", "tool_name", "arguments"],
                        },
                    },
                    "outputs": {
                        "type": "object",
                        "additionalProperties": True,
                    },
                },
                "required": ["steps", "outputs"],
            },
        },
    }


def _parse_tool_program_action(
    action_call_id: str,
    arguments: dict[str, JsonValue],
) -> HarnessToolProgramAction:
    if set(arguments) != {"steps", "outputs"}:
        raise ValueError("DeepSeek ToolProgram fields differ")
    raw_steps = arguments["steps"]
    raw_outputs = arguments["outputs"]
    if not isinstance(raw_steps, list) or any(not isinstance(item, dict) for item in raw_steps):
        raise TypeError("DeepSeek ToolProgram steps must be objects")
    if not isinstance(raw_outputs, dict):
        raise TypeError("DeepSeek ToolProgram outputs must be an object")
    steps: list[HarnessToolProgramStep] = []
    for raw_step in raw_steps:
        if set(raw_step) != {"step_id", "tool_name", "arguments"}:
            raise ValueError("DeepSeek ToolProgram step fields differ")
        if not isinstance(raw_step["arguments"], dict):
            raise TypeError("DeepSeek ToolProgram step arguments must be an object")
        steps.append(
            HarnessToolProgramStep(
                step_id=raw_step["step_id"],
                tool_name=raw_step["tool_name"],
                arguments=dict(raw_step["arguments"]),
            )
        )
    return HarnessToolProgramAction(
        action_call_id=action_call_id,
        program=HarnessToolProgram(steps=tuple(steps), outputs=dict(raw_outputs)),
    )


def _working_set_transition_tool() -> dict[str, JsonValue]:
    pin_schema: dict[str, JsonValue] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "slot": {"type": "string", "minLength": 1},
            "logical_ref": {"type": "string", "minLength": 1},
            "logical_generation": {"type": "string", "minLength": 1},
            "resolved_digest": {
                "type": "string",
                "pattern": "^sha256:[0-9a-f]{64}$",
            },
        },
        "required": [
            "slot",
            "logical_ref",
            "logical_generation",
            "resolved_digest",
        ],
    }
    return {
        "type": "function",
        "function": {
            "name": _WORKING_SET_TRANSITION_TOOL_NAME,
            "description": (
                "Choose the exact already-known sources that should form the next "
                "committed Working Set. This changes only your model-visible cognition "
                "view; it is not an external Tool effect and does not discover sources. "
                "Use an unchanged exact pin selection only when you intentionally want "
                "a new cognition attempt with the same durable sources; that is an "
                "attempt reset, not progress and not a way to wait for caller input. "
                "When waiting for caller input, submit a needs_input conclusion instead."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "next_attempt_id": {"type": "string", "minLength": 1},
                    "pins": {
                        "type": "array",
                        "items": pin_schema,
                        "maxItems": 128,
                    },
                    "basis": {"type": "string", "minLength": 1},
                },
                "required": ["next_attempt_id", "pins", "basis"],
            },
        },
    }


def _caller_ingress_promotion_tool(
    allowed_caller_indexes: tuple[int, ...],
) -> dict[str, JsonValue]:
    return {
        "type": "function",
        "function": {
            "name": _CALLER_INGRESS_PROMOTION_TOOL_NAME,
            "description": (
                "Add exact messages from the current caller interaction to the current "
                "durable Working Set. Choose only message indexes you actually saw and "
                "one new successor slot. Existing selected sources are retained "
                "mechanically; do not restate or guess their pin identities. You cannot "
                "provide or rewrite promoted bytes; Harness derives them from caller-ingress "
                "authority. This is cognition state, not a Runtime effect."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "next_attempt_id": {"type": "string", "minLength": 1},
                    "promotion_slot": {"type": "string", "minLength": 1},
                    "caller_message_indexes": {
                        "type": "array",
                        "items": {
                            "type": "integer",
                            "enum": list(allowed_caller_indexes),
                        },
                        "minItems": 1,
                        "maxItems": min(32, len(allowed_caller_indexes)),
                    },
                    "basis": {"type": "string", "minLength": 1},
                },
                "required": [
                    "next_attempt_id",
                    "promotion_slot",
                    "caller_message_indexes",
                    "basis",
                ],
            },
        },
    }


def _parse_caller_ingress_promotion(
    arguments: dict[str, JsonValue],
) -> AgentCallerIngressPromotionProposal:
    expected = {
        "next_attempt_id",
        "promotion_slot",
        "caller_message_indexes",
        "basis",
    }
    if set(arguments) != expected:
        raise ValueError("DeepSeek caller ingress promotion fields differ")
    next_attempt_id = arguments["next_attempt_id"]
    promotion_slot = arguments["promotion_slot"]
    basis = arguments["basis"]
    raw_indexes = arguments["caller_message_indexes"]
    if not all(
        isinstance(value, str)
        for value in (next_attempt_id, promotion_slot, basis)
    ):
        raise TypeError("DeepSeek caller ingress promotion text fields are invalid")
    if not isinstance(raw_indexes, list):
        raise TypeError("DeepSeek caller ingress promotion indexes must be a list")
    return AgentCallerIngressPromotionProposal(
        next_attempt_id=next_attempt_id,
        promotion_slot=promotion_slot,
        caller_message_indexes=tuple(raw_indexes),
        basis=basis,
    )


def _working_set_history_tool() -> dict[str, JsonValue]:
    return {
        "type": "function",
        "function": {
            "name": WORKING_SET_HISTORY_CONTROL_NAME,
            "description": (
                "Inspect a bounded reverse-chronological catalog of exact source pins "
                "from earlier committed Working Sets. This does not read source content, "
                "rank memories, or change cognition. Use propose_working_set_transition "
                "separately if you choose to recall one of the returned pins."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 32,
                    },
                    "before_sequence": {
                        "type": "integer",
                        "minimum": 1,
                    },
                },
                "required": ["limit"],
            },
        },
    }


def _parse_working_set_transition(
    arguments: dict[str, JsonValue],
) -> AgentWorkingSetTransitionProposal:
    if set(arguments) != {"next_attempt_id", "pins", "basis"}:
        raise ValueError("DeepSeek Working Set transition fields differ")
    next_attempt_id = arguments["next_attempt_id"]
    basis = arguments["basis"]
    raw_pins = arguments["pins"]
    if not isinstance(next_attempt_id, str) or not isinstance(basis, str):
        raise TypeError("DeepSeek Working Set transition text fields are invalid")
    if not isinstance(raw_pins, list) or any(not isinstance(item, dict) for item in raw_pins):
        raise TypeError("DeepSeek Working Set transition pins must be objects")
    pins: list[HarnessWorkingSetPin] = []
    for raw_pin in raw_pins:
        if set(raw_pin) != {
            "slot",
            "logical_ref",
            "logical_generation",
            "resolved_digest",
        }:
            raise ValueError("DeepSeek Working Set transition pin fields differ")
        pins.append(
            HarnessWorkingSetPin(
                slot=raw_pin["slot"],
                logical_ref=raw_pin["logical_ref"],
                logical_generation=raw_pin["logical_generation"],
                resolved_digest=raw_pin["resolved_digest"],
            )
        )
    return AgentWorkingSetTransitionProposal(
        next_attempt_id=next_attempt_id,
        pins=tuple(sorted(pins, key=lambda pin: pin.slot)),
        basis=basis,
    )


def _provider_tool(tool: AgentToolDefinition) -> dict[str, JsonValue]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
        },
    }


def _provider_messages(
    messages: tuple[dict[str, JsonValue], ...],
) -> list[dict[str, JsonValue]]:
    translated: list[dict[str, JsonValue]] = []
    for message in messages:
        role = message.get("role")
        if role in {"system", "user"}:
            content = message.get("content")
            if not isinstance(content, str):
                raise ValueError(f"DeepSeek {role} message content must be a string")
            translated.append({"role": role, "content": content})
            continue
        if role == "assistant":
            raw_calls = message.get("toolCalls")
            conclusion = message.get("conclusion")
            tool_program_action = message.get("toolProgramAction")
            if conclusion is not None:
                if not isinstance(conclusion, dict):
                    raise ValueError(
                        "DeepSeek assistant conclusion history is invalid"
                    )
                validate_json_value(conclusion)
                content = message.get("content")
                if content is not None and not isinstance(content, str):
                    raise ValueError(
                        "DeepSeek assistant content must be a string or null"
                    )
                retained = (
                    "Retained Harness conclusion: "
                    + canonical_bytes(conclusion).decode("utf-8")
                )
                if content:
                    retained = f"{content}\n\n{retained}"
                translated.append({"role": "assistant", "content": retained})
                continue
            if tool_program_action is not None:
                if not isinstance(tool_program_action, dict):
                    raise ValueError("DeepSeek assistant ToolProgram history is invalid")
                HarnessToolProgramAction.from_dict(tool_program_action)
                content = message.get("content")
                if content is not None and not isinstance(content, str):
                    raise ValueError("DeepSeek assistant content must be a string or null")
                retained = (
                    "Retained Harness ToolProgram action: "
                    + canonical_bytes(tool_program_action).decode("utf-8")
                )
                if content:
                    retained = f"{content}\n\n{retained}"
                translated.append({"role": "assistant", "content": retained})
                continue
            if not isinstance(raw_calls, list) or not raw_calls:
                raise ValueError("DeepSeek assistant history must retain Tool Calls")
            calls: list[dict[str, JsonValue]] = []
            for raw_call in raw_calls:
                if not isinstance(raw_call, dict) or not {
                    "toolCallId",
                    "name",
                    "arguments",
                }.issubset(raw_call) or set(raw_call) - {
                    "toolCallId",
                    "name",
                    "arguments",
                    "providerArguments",
                }:
                    raise ValueError("DeepSeek assistant Tool Call history is invalid")
                call_id = raw_call["toolCallId"]
                name = raw_call["name"]
                arguments = raw_call["arguments"]
                if not isinstance(call_id, str) or not isinstance(name, str):
                    raise TypeError(
                        "DeepSeek assistant Tool Call identities are invalid"
                    )
                validate_json_value(arguments)
                calls.append(
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": canonical_bytes(arguments).decode("utf-8"),
                        },
                    }
                )
            content = message.get("content")
            if content is not None and not isinstance(content, str):
                raise ValueError("DeepSeek assistant content must be a string or null")
            translated.append(
                {"role": "assistant", "content": content, "tool_calls": calls}
            )
            continue
        if role == "tool":
            tool_call_id = message.get("toolCallId")
            observation = message.get("observation")
            if not isinstance(tool_call_id, str):
                raise ValueError("DeepSeek Tool message has no Tool Call identity")
            validate_json_value(observation)
            translated.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": canonical_bytes(observation).decode("utf-8"),
                }
            )
            continue
        raise ValueError(f"unsupported DeepSeek message role: {role}")
    return translated


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"DeepSeek conclusion {label} must be a string array")
    return tuple(value)


def _parse_conclusion(
    arguments: dict[str, JsonValue],
    *,
    completion_contract: Mapping[str, JsonValue] | None = None,
) -> AgentRunConclusion:
    structured = (
        None
        if completion_contract is None
        else structured_completion_result_schema(completion_contract)
    )
    result_name = "result" if structured is not None else "summary"
    expected = {
        "status",
        result_name,
        "artifact_refs",
        "evidence_refs",
        "unresolved_unknowns",
    }
    if set(arguments) != expected:
        raise ValueError("DeepSeek conclusion fields differ")
    status = arguments["status"]
    if not isinstance(status, str):
        raise TypeError("DeepSeek conclusion status must be a string")
    structured_result: AgentStructuredResult | None = None
    if structured is None:
        summary = arguments["summary"]
        if not isinstance(summary, str):
            raise TypeError("DeepSeek conclusion summary must be a string")
    else:
        structured_result = AgentStructuredResult(arguments["result"])
        summary = f"Structured result {structured_result.digest}"
    return AgentRunConclusion(
        status=status,
        summary=summary,
        artifact_refs=_string_tuple(arguments["artifact_refs"], "Artifact refs"),
        evidence_refs=_string_tuple(arguments["evidence_refs"], "evidence refs"),
        unresolved_unknowns=_string_tuple(
            arguments["unresolved_unknowns"], "unresolved unknowns"
        ),
        structured_result=structured_result,
    )


class _DeepSeekTurnCallHandle:
    def __init__(
        self,
        adapter: DeepSeekTurnAdapter,
        post_handle: DeepSeekPostHandle,
        *,
        allowed_tool_names: set[str],
        capabilities: AgentTurnCapabilities,
    ) -> None:
        self._adapter = adapter
        self._post_handle = post_handle
        self._allowed_tool_names = allowed_tool_names
        self._capabilities = capabilities
        self._result: AgentTurnResult | None = None

    def poll(self, timeout_seconds: float) -> AgentTurnResult | None:
        if self._result is not None:
            return self._result
        raw = self._post_handle.poll(timeout_seconds)
        if raw is None:
            return None
        self._result = self._adapter._decode_response(
            raw,
            allowed_tool_names=self._allowed_tool_names,
            capabilities=self._capabilities,
        )
        return self._result

    def cancel(self) -> None:
        self._post_handle.cancel()


class DeepSeekTurnAdapter:
    adapter_id = "deepseek.chat-completions.non-thinking.v1"

    def __init__(
        self,
        settings: DeepSeekSettings,
        *,
        transport: DeepSeekTransport | None = None,
        completion_contract: Mapping[str, JsonValue] | None = None,
    ) -> None:
        self.settings = settings
        self.model_id = settings.model
        self.transport = transport or HttpClientDeepSeekTransport.from_environment()
        self._completion_contract = (
            {} if completion_contract is None else dict(completion_contract)
        )
        self._structured_result_schema = structured_completion_result_schema(
            self._completion_contract
        )
        self.structured_completion_contract_digest = (
            structured_completion_contract_digest(self._completion_contract)
        )

    @property
    def supports_call_handle(self) -> bool:
        return callable(getattr(self.transport, "start_post", None))

    def start_invoke(
        self, request: AgentTurnRequest, control: ExecutionControl
    ) -> AgentTurnCallHandle:
        if control.stop_requested:
            raise AgentTurnAdapterError(
                "DeepSeek invocation stopped before dispatch",
                failure_code=AgentTurnFailureCode.TIMEOUT,
                dispatch_safety=AgentTurnDispatchSafety.PRE_DISPATCH_SAFE,
            )
        start_post = getattr(self.transport, "start_post", None)
        if not callable(start_post):
            raise AgentTurnAdapterError(
                "DeepSeek transport does not expose a cancellable call handle",
                failure_code=AgentTurnFailureCode.FAILED,
            )
        allowed_tool_names, url, headers, body = self._prepare_request(request)
        post_handle = start_post(
            url,
            headers=headers,
            body=body,
            timeout_seconds=control.clamp_timeout_seconds(
                self.settings.timeout_seconds
            ),
            max_response_bytes=self.settings.max_response_bytes,
        )
        return _DeepSeekTurnCallHandle(
            self,
            post_handle,
            allowed_tool_names=allowed_tool_names,
            capabilities=request.capabilities,
        )

    def invoke(self, request: AgentTurnRequest) -> AgentTurnResult:
        return self._invoke(request, timeout_seconds=self.settings.timeout_seconds)

    def invoke_with_control(
        self, request: AgentTurnRequest, control: ExecutionControl
    ) -> AgentTurnResult:
        if not self.supports_call_handle:
            if control.stop_requested:
                raise AgentTurnAdapterError(
                    "DeepSeek invocation stopped before dispatch",
                    failure_code=AgentTurnFailureCode.TIMEOUT,
                    dispatch_safety=AgentTurnDispatchSafety.PRE_DISPATCH_SAFE,
                )
            return self._invoke(
                request,
                timeout_seconds=control.clamp_timeout_seconds(
                    self.settings.timeout_seconds
                ),
            )
        handle = self.start_invoke(request, control)
        while True:
            if control.cancellation.cancelled:
                self._cancel_and_drain(handle)
                raise AgentTurnAdapterError(
                    "DeepSeek request was cancelled in flight",
                    failure_code=AgentTurnFailureCode.FAILED,
                )
            if control.deadline.expired:
                self._cancel_and_drain(handle)
                raise AgentTurnAdapterError(
                    "DeepSeek request deadline expired in flight",
                    failure_code=AgentTurnFailureCode.TIMEOUT,
                )
            result = handle.poll(min(0.05, max(0.001, control.remaining_ms / 1_000)))
            if result is not None:
                return result

    def accepts_effective_model_id(self, model_id: str) -> bool:
        return model_id == self.settings.model

    def request_token_upper_bound(self, request: AgentTurnRequest) -> int:
        """Bound prompt bytes plus the Provider-enforced completion ceiling."""
        _, _, _, body = self._prepare_request(request)
        return len(body) + self.settings.max_output_tokens

    def provider_request_digest(self, request: AgentTurnRequest) -> str:
        """Identify the exact non-secret request semantics sent to DeepSeek."""
        _, url, headers, body = self._prepare_request(request)
        semantic_headers = {
            name: value
            for name, value in headers.items()
            if name.lower() != "authorization"
        }
        return canonical_digest(
            {
                "schemaVersion": 1,
                "kind": "ordivon.deepseek-provider-request",
                "adapterId": self.adapter_id,
                "requestedModelId": self.model_id,
                "credentialScopeId": self.settings.credential_scope_id,
                "method": "POST",
                "url": url,
                "headers": semantic_headers,
                "bodyDigest": "sha256:" + hashlib.sha256(body).hexdigest(),
            }
        )

    def _invoke(
        self, request: AgentTurnRequest, *, timeout_seconds: float
    ) -> AgentTurnResult:
        allowed_tool_names, url, headers, body = self._prepare_request(request)
        raw = self.transport.post(
            url,
            headers=headers,
            body=body,
            timeout_seconds=timeout_seconds,
            max_response_bytes=self.settings.max_response_bytes,
        )
        return self._decode_response(
            raw,
            allowed_tool_names=allowed_tool_names,
            capabilities=request.capabilities,
        )

    def _prepare_request(
        self, request: AgentTurnRequest
    ) -> tuple[set[str], str, dict[str, str], bytes]:
        capabilities = request.capabilities
        allowed_tool_names = {tool.name for tool in request.tools}
        reserved = {
            _CONCLUSION_TOOL_NAME,
            _WORKING_SET_TRANSITION_TOOL_NAME,
            _CALLER_INGRESS_PROMOTION_TOOL_NAME,
            _TOOL_PROGRAM_ACTION_NAME,
            WORKING_SET_HISTORY_CONTROL_NAME,
        }
        collisions = allowed_tool_names & reserved
        if collisions:
            raise ValueError(
                "Runtime Tool catalog collides with Harness control Tools: "
                + ", ".join(sorted(collisions))
            )
        tools = [_provider_tool(tool) for tool in request.tools]
        if capabilities.working_set_transition:
            tools.append(_working_set_transition_tool())
        promotion_indexes = tuple(
            ref.caller_message_index for ref in request.caller_ingress_refs
        )
        if capabilities.caller_ingress_promotion and promotion_indexes:
            tools.append(_caller_ingress_promotion_tool(promotion_indexes))
        if capabilities.working_set_history:
            tools.append(_working_set_history_tool())
        if capabilities.tool_program:
            remaining_tool_calls = request.remaining_budget.get("toolCalls", 0)
            if type(remaining_tool_calls) is not int or remaining_tool_calls < 1:
                raise ValueError("ToolProgram capability requires positive Tool budget")
            tools.append(
                _tool_program_action_tool(
                    tuple(sorted(allowed_tool_names)),
                    max_steps=min(32, remaining_tool_calls),
                )
            )
        if capabilities.conclusion:
            tools.append(_conclusion_tool(self._structured_result_schema))
        execution_control: dict[str, JsonValue] = {
            "schemaVersion": 1,
            "kind": "ordivon.harness-agent-turn-control",
            "remainingBudget": request.remaining_budget,
            "admittedRuntimeTools": [tool.name for tool in request.tools],
            "harnessActions": [
                name
                for name, admitted in (
                    (_CONCLUSION_TOOL_NAME, capabilities.conclusion),
                    (
                        _WORKING_SET_TRANSITION_TOOL_NAME,
                        capabilities.working_set_transition,
                    ),
                    (
                        _CALLER_INGRESS_PROMOTION_TOOL_NAME,
                        capabilities.caller_ingress_promotion,
                    ),
                    (WORKING_SET_HISTORY_CONTROL_NAME, capabilities.working_set_history),
                    (_TOOL_PROGRAM_ACTION_NAME, capabilities.tool_program),
                )
                if admitted
            ],
        }
        if capabilities.caller_ingress_promotion:
            execution_control["callerIngress"] = {
                "promotable": [
                    {
                        "callerMessageIndex": ref.caller_message_index,
                        "providerMessageIndex": ref.request_message_index + 1,
                    }
                    for ref in request.caller_ingress_refs
                ]
            }
        if capabilities.working_set_transition:
            execution_control["workingSetSelection"] = [
                {
                    "pin": ref.pin.to_dict(),
                    "providerMessageStartIndex": ref.request_message_start_index + 1,
                    "providerMessageEndExclusiveIndex": ref.request_message_end_index + 1,
                }
                for ref in request.working_set_refs
            ]
        provider_messages = [
            {
                "role": "system",
                "content": (
                    "Ordivon Harness execution control. These are authoritative execution "
                    "constraints, not task evidence. Previously seen Runtime Tools that are "
                    "not listed as admitted are unavailable for this turn. Harness cognition "
                    "and conclusion control actions offered separately remain available. "
                    + (
                        "When caller-ingress promotion is available, only messages listed under "
                        "callerIngress.promotable are current caller-ingress messages eligible "
                        "for promotion; other user-role messages are selected or otherwise "
                        "non-promotable cognition. "
                        if capabilities.caller_ingress_promotion
                        else ""
                    )
                    + (
                        "When WorkingSet transition is available, workingSetSelection lists the "
                        "exact currently selected durable pins and the half-open Provider-message "
                        "ranges [start,end) that each pin produced. Use those exact identities for retain/drop "
                        "decisions; do not infer or invent pin identities from message text. "
                        if capabilities.working_set_transition
                        else ""
                    )
                    + canonical_bytes(execution_control).decode("utf-8")
                ),
            },
            *_provider_messages(request.messages),
        ]
        body_value: dict[str, JsonValue] = {
            "model": self.settings.model,
            "messages": provider_messages,
            "tools": tools,
            "tool_choice": "required",
            "thinking": {"type": "disabled"},
            "max_tokens": self.settings.max_output_tokens,
            "stream": False,
        }
        validate_json_value(body_value)
        return (
            allowed_tool_names,
            f"{self.settings.base_url}/chat/completions",
            {
                "Authorization": f"Bearer {self.settings.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "ordivon-harness-p0/2",
            },
            canonical_bytes(body_value),
        )

    def _decode_response(
        self,
        raw: bytes,
        *,
        allowed_tool_names: set[str],
        capabilities: AgentTurnCapabilities,
    ) -> AgentTurnResult:
        try:
            value = loads_strict(raw)
        except ValueError as error:
            raise ValueError("DeepSeek returned invalid JSON") from error
        if not isinstance(value, dict):
            raise TypeError("DeepSeek response must be an object")
        validate_json_value(value)
        return self._parse_response(
            value,
            raw,
            allowed_tool_names=allowed_tool_names,
            capabilities=capabilities,
        )

    @staticmethod
    def _cancel_and_drain(handle: AgentTurnCallHandle | DeepSeekPostHandle) -> None:
        handle.cancel()
        try:
            handle.poll(0.5)
        except Exception:  # noqa: BLE001 - cancellation drain must not mask stop.
            return

    def _parse_response(
        self,
        value: dict[str, JsonValue],
        raw: bytes,
        *,
        allowed_tool_names: set[str],
        capabilities: AgentTurnCapabilities,
    ) -> AgentTurnResult:
        response_id = value.get("id")
        choices = value.get("choices")
        response_model = value.get("model")
        if not isinstance(response_id, str) or not response_id:
            raise ValueError("DeepSeek response omitted its Model Call identity")
        if (
            not isinstance(choices, list)
            or len(choices) != 1
            or not isinstance(choices[0], dict)
        ):
            raise ValueError("DeepSeek response must contain exactly one choice")
        if not isinstance(response_model, str) or not response_model:
            raise ValueError("DeepSeek response omitted its model identity")
        choice = choices[0]
        finish_reason = choice.get("finish_reason")
        message = choice.get("message")
        if finish_reason == "insufficient_system_resource":
            raise AgentTurnAdapterError(
                "DeepSeek reported insufficient system resources",
                failure_code=AgentTurnFailureCode.UNAVAILABLE,
                dispatch_safety=AgentTurnDispatchSafety.PROVIDER_REJECTED,
            )
        if not isinstance(finish_reason, str) or not isinstance(message, dict):
            raise TypeError("DeepSeek choice fields are invalid")
        if message.get("role") != "assistant":
            raise ValueError("DeepSeek response role is not assistant")
        content = message.get("content")
        if content is not None and not isinstance(content, str):
            raise ValueError("DeepSeek assistant content must be a string or null")
        raw_calls = message.get("tool_calls")
        if not isinstance(raw_calls, list) or not raw_calls:
            raise ValueError(
                "DeepSeek Turn must call a Runtime Tool or submit a conclusion"
            )

        runtime_calls: list[AgentToolCall] = []
        conclusion: AgentRunConclusion | None = None
        working_set_transition: AgentWorkingSetTransitionProposal | None = None
        caller_ingress_promotion: AgentCallerIngressPromotionProposal | None = None
        tool_program_action: HarnessToolProgramAction | None = None

        def invalid_call(
            call_id: str,
            name: str,
            raw_arguments: str,
            error: str,
            arguments: dict[str, JsonValue] | None = None,
        ) -> AgentToolCall:
            raw_bytes = raw_arguments.encode("utf-8")
            return AgentToolCall(
                call_id,
                name,
                {} if arguments is None else arguments,
                argument_error=error[:300],
                raw_arguments_digest=(
                    "sha256:" + hashlib.sha256(raw_bytes).hexdigest()
                ),
                raw_arguments_preview=raw_bytes[:2_048].decode(
                    "utf-8", errors="ignore"
                ),
            )

        for raw_call in raw_calls:
            if not isinstance(raw_call, dict) or raw_call.get("type") != "function":
                raise ValueError("DeepSeek Tool Call is not a function")
            call_id = raw_call.get("id")
            function = raw_call.get("function")
            if not isinstance(call_id, str) or not isinstance(function, dict):
                raise TypeError("DeepSeek Tool Call identity or function is invalid")
            name = function.get("name")
            raw_arguments = function.get("arguments")
            if not isinstance(name, str) or not isinstance(raw_arguments, str):
                raise TypeError("DeepSeek Tool Call name or arguments are invalid")
            cognition_call = name == _WORKING_SET_TRANSITION_TOOL_NAME
            cognition_allowed = cognition_call and capabilities.working_set_transition
            promotion_call = name == _CALLER_INGRESS_PROMOTION_TOOL_NAME
            promotion_allowed = promotion_call and capabilities.caller_ingress_promotion
            history_call = name == WORKING_SET_HISTORY_CONTROL_NAME
            history_allowed = history_call and capabilities.working_set_history
            program_call = name == _TOOL_PROGRAM_ACTION_NAME
            program_allowed = program_call and capabilities.tool_program
            try:
                arguments = loads_strict(raw_arguments.encode("utf-8"))
            except ValueError:
                if cognition_allowed:
                    raise ValueError(
                        "DeepSeek Working Set transition arguments are invalid JSON"
                    )
                if promotion_allowed:
                    raise ValueError(
                        "DeepSeek caller ingress promotion arguments are invalid JSON"
                    )
                if history_allowed:
                    raise ValueError(
                        "DeepSeek Working Set history arguments are invalid JSON"
                    )
                if program_allowed:
                    raise ValueError("DeepSeek ToolProgram arguments are invalid JSON")
                runtime_calls.append(
                    invalid_call(
                        call_id,
                        name,
                        raw_arguments,
                        (
                            "unavailable_tool"
                            if name != _CONCLUSION_TOOL_NAME
                            and name not in allowed_tool_names
                            else "invalid_json"
                        ),
                    )
                )
                continue
            if not isinstance(arguments, dict):
                if cognition_allowed:
                    raise ValueError(
                        "DeepSeek Working Set transition arguments must be an object"
                    )
                if promotion_allowed:
                    raise ValueError(
                        "DeepSeek caller ingress promotion arguments must be an object"
                    )
                if history_allowed:
                    raise ValueError(
                        "DeepSeek Working Set history arguments must be an object"
                    )
                if program_allowed:
                    raise ValueError("DeepSeek ToolProgram arguments must be an object")
                runtime_calls.append(
                    invalid_call(
                        call_id,
                        name,
                        raw_arguments,
                        (
                            "unavailable_tool"
                            if name != _CONCLUSION_TOOL_NAME
                            and name not in allowed_tool_names
                            else "arguments_not_object"
                        ),
                    )
                )
                continue
            validate_json_value(arguments)
            if name == _CONCLUSION_TOOL_NAME:
                if conclusion is not None:
                    runtime_calls.append(
                        invalid_call(
                            call_id,
                            name,
                            raw_arguments,
                            "multiple_conclusions",
                            dict(arguments),
                        )
                    )
                    continue
                try:
                    conclusion = _parse_conclusion(
                        arguments, completion_contract=self._completion_contract
                    )
                except (KeyError, TypeError, ValueError) as error:
                    runtime_calls.append(
                        invalid_call(
                            call_id,
                            name,
                            raw_arguments,
                            f"invalid_conclusion: {error}",
                            dict(arguments),
                        )
                    )
            elif cognition_call:
                if not capabilities.working_set_transition:
                    raise ValueError(
                        "DeepSeek called the unavailable Working Set transition control"
                    )
                if working_set_transition is not None:
                    raise ValueError(
                        "DeepSeek emitted multiple Working Set transitions in one turn"
                    )
                try:
                    working_set_transition = _parse_working_set_transition(
                        dict(arguments)
                    )
                except (KeyError, TypeError, ValueError) as error:
                    raise ValueError(
                        f"invalid DeepSeek Working Set transition: {error}"
                    ) from error
            elif promotion_call:
                if not capabilities.caller_ingress_promotion:
                    raise ValueError(
                        "DeepSeek called the unavailable caller ingress promotion control"
                    )
                if caller_ingress_promotion is not None:
                    raise ValueError(
                        "DeepSeek emitted multiple caller ingress promotions in one turn"
                    )
                try:
                    caller_ingress_promotion = _parse_caller_ingress_promotion(
                        dict(arguments)
                    )
                except (KeyError, TypeError, ValueError) as error:
                    raise ValueError(
                        f"invalid DeepSeek caller ingress promotion: {error}"
                    ) from error
            elif program_call:
                if not capabilities.tool_program:
                    raise ValueError("DeepSeek called the unavailable ToolProgram control")
                if tool_program_action is not None:
                    raise ValueError("DeepSeek emitted multiple ToolPrograms in one turn")
                try:
                    tool_program_action = _parse_tool_program_action(
                        call_id,
                        dict(arguments),
                    )
                except (KeyError, TypeError, ValueError) as error:
                    raise ValueError(f"invalid DeepSeek ToolProgram: {error}") from error
            elif history_call:
                if not capabilities.working_set_history:
                    raise ValueError(
                        "DeepSeek called the unavailable Working Set history control"
                    )
                try:
                    parse_working_set_history_query(dict(arguments))
                except (KeyError, TypeError, ValueError) as error:
                    raise ValueError(
                        f"invalid DeepSeek Working Set history query: {error}"
                    ) from error
                runtime_calls.append(AgentToolCall(call_id, name, dict(arguments)))
            else:
                if name not in allowed_tool_names:
                    runtime_calls.append(
                        invalid_call(
                            call_id,
                            name,
                            raw_arguments,
                            "unavailable_tool",
                            dict(arguments),
                        )
                    )
                    continue
                runtime_calls.append(AgentToolCall(call_id, name, dict(arguments)))

        if working_set_transition is not None and (
            runtime_calls
            or conclusion is not None
            or caller_ingress_promotion is not None
        ):
            raise ValueError(
                "DeepSeek Working Set transition cannot be mixed with Tools, conclusion, or caller ingress promotion"
            )
        if caller_ingress_promotion is not None and (
            runtime_calls or conclusion is not None
        ):
            raise ValueError(
                "DeepSeek caller ingress promotion cannot be mixed with Tools or conclusion"
            )
        if tool_program_action is not None and (
            runtime_calls
            or conclusion is not None
            or working_set_transition is not None
            or caller_ingress_promotion is not None
        ):
            raise ValueError(
                "DeepSeek ToolProgram cannot be mixed with Runtime Tools or other Harness actions"
            )
        history_calls = [
            call
            for call in runtime_calls
            if call.name == WORKING_SET_HISTORY_CONTROL_NAME
            and call.argument_error is None
        ]
        if history_calls and (
            len(runtime_calls) != 1
            or conclusion is not None
            or caller_ingress_promotion is not None
        ):
            raise ValueError(
                "DeepSeek Working Set history control cannot be mixed with Runtime Tools or conclusion"
            )
        invalid_calls = [
            call for call in runtime_calls if call.argument_error is not None
        ]
        if invalid_calls:
            runtime_calls = invalid_calls
            conclusion = None
        if conclusion is not None and runtime_calls:
            # A model may try to both continue acting and conclude in one Provider
            # turn.  The semantic choice is ambiguous, but no physical Tool has
            # executed yet.  Preserve that causal boundary and return a
            # model-correctable invalid Tool turn instead of converting an
            # epistemic/action conflict into a Harness failure.
            corrected_calls: list[AgentToolCall] = []
            for call in runtime_calls:
                raw_arguments = canonical_bytes(call.arguments)
                corrected_calls.append(
                    AgentToolCall(
                        call.tool_call_id,
                        call.name,
                        dict(call.arguments),
                        argument_error="mixed_with_conclusion",
                        raw_arguments_digest=(
                            "sha256:" + hashlib.sha256(raw_arguments).hexdigest()
                        ),
                        raw_arguments_preview=raw_arguments[:2_048].decode(
                            "utf-8", errors="ignore"
                        ),
                    )
                )
            runtime_calls = corrected_calls
            conclusion = None
        if finish_reason != "tool_calls":
            raise ValueError("DeepSeek Tool Turn has an inconsistent finish reason")

        usage_value = value.get("usage")
        usage: dict[str, JsonValue] = {}
        if isinstance(usage_value, dict):
            validate_json_value(usage_value)
            usage.update(usage_value)
        fingerprint = value.get("system_fingerprint")
        if isinstance(fingerprint, str):
            usage["systemFingerprint"] = fingerprint
        usage["providerModel"] = response_model
        usage["providerRequestMode"] = "non-thinking"
        raw_digest = "sha256:" + hashlib.sha256(raw).hexdigest()
        return AgentTurnResult(
            model_call_id=response_id,
            model_id=self.model_id,
            content=content,
            tool_calls=tuple(runtime_calls),
            conclusion=conclusion,
            usage=usage,
            finish_reason=finish_reason,
            raw_response_digest=raw_digest,
            effective_model_id=response_model,
            working_set_transition=working_set_transition,
            caller_ingress_promotion=caller_ingress_promotion,
            tool_program_action=tool_program_action,
        )
