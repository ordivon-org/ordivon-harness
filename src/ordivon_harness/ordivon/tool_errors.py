"""Shared Tool bridge failure taxonomy.

Request lowering, Runtime execution, recovery, and the Agent loop use one bounded
failure vocabulary without importing each other's implementation modules.
"""

from enum import StrEnum


class ToolBridgeErrorKind(StrEnum):
    MODEL_CORRECTABLE = "model_correctable"
    AUTHORITY_DENIED = "authority_denied"
    PROTOCOL_INVALID = "protocol_invalid"
    CONTROL_STOPPED = "control_stopped"
    INTERNAL = "internal"


class ToolBridgeError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        kind: ToolBridgeErrorKind = ToolBridgeErrorKind.INTERNAL,
    ) -> None:
        super().__init__(message)
        self.kind = kind

    @property
    def recoverable_by_model(self) -> bool:
        return self.kind in {
            ToolBridgeErrorKind.MODEL_CORRECTABLE,
            ToolBridgeErrorKind.AUTHORITY_DENIED,
        }


__all__ = ["ToolBridgeError", "ToolBridgeErrorKind"]
