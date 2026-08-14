"""Experimental AM1 admission-time Agent Loop implementation binding.

A LoopDriver is deliberately *not* a plugin registry or live replacement API.  It
is one exact implementation selected for one immutable compiled Harness Attempt.
The binding can only build a loop when its identity is already present in the
Attempt system manifest and that manifest is the one referenced by the Run
Contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .mandate import CompiledHarnessAttempt
from .ordivon.loop import OrdivonAgentLoop


class HarnessLoopFactory(Protocol):
    def __call__(self, **kwargs: object) -> OrdivonAgentLoop: ...


def _text(value: str, label: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value.encode("utf-8")) > 300
    ):
        raise ValueError(f"{label} must be non-empty and trimmed")


def _digest(value: str, label: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ValueError(f"{label} must be sha256:<64 lowercase hex>")


@dataclass(frozen=True, slots=True)
class HarnessLoopDriverBinding:
    """One exact Attempt-bound Loop factory.

    `system_manifest_digest` prevents a caller from taking a valid driver choice
    from one Attempt and silently attaching it to another Run.  The driver itself
    owns no authority; all Tool/cognition/effect authority still comes from the
    exact Run composition supplied to the loop constructor.
    """

    driver_id: str
    driver_digest: str
    system_manifest_digest: str
    factory: HarnessLoopFactory

    def __post_init__(self) -> None:
        _text(self.driver_id, "Harness LoopDriver identity")
        _digest(self.driver_digest, "Harness LoopDriver digest")
        _digest(self.system_manifest_digest, "Harness LoopDriver System Manifest digest")
        if not callable(self.factory):
            raise TypeError("Harness LoopDriver factory must be callable")

    @classmethod
    def from_compiled_attempt(
        cls,
        attempt: CompiledHarnessAttempt,
        *,
        driver_id: str,
        driver_digest: str,
        factory: HarnessLoopFactory,
    ) -> "HarnessLoopDriverBinding":
        manifest = attempt.to_dict()["systemManifest"]
        assert isinstance(manifest, dict)
        declared = manifest.get("loopDriver")
        expected = {"driverId": driver_id, "driverDigest": driver_digest}
        if declared != expected:
            raise ValueError("Harness LoopDriver differs from the compiled Attempt manifest")
        if attempt.contract.system_manifest_ref.digest != attempt.to_dict()["contract"]["systemManifestRef"]["digest"]:
            raise ValueError("compiled Harness Attempt Contract manifest reference differs")
        return cls(
            driver_id=driver_id,
            driver_digest=driver_digest,
            system_manifest_digest=attempt.contract.system_manifest_ref.digest,
            factory=factory,
        )

    def require_contract(self, system_manifest_digest: str) -> None:
        if system_manifest_digest != self.system_manifest_digest:
            raise ValueError("Harness LoopDriver binding belongs to another Run manifest")

    def build(self, **kwargs: object) -> OrdivonAgentLoop:
        loop = self.factory(**kwargs)
        if not isinstance(loop, OrdivonAgentLoop):
            raise TypeError("Harness LoopDriver factory must return OrdivonAgentLoop")
        return loop


__all__ = ["HarnessLoopDriverBinding", "HarnessLoopFactory"]
