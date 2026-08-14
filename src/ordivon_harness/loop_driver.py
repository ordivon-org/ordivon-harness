"""Experimental AM1/AM2 Agent Loop implementation identity binding.

A LoopDriver identity is deliberately *not* an executable plugin, registry, or
live-replacement API.  AM1 proved that loop implementation identity can be frozen
into one immutable compiled Attempt without expanding Run authority.  AM2 then
rejected the first factory seam: a Python callable/subclass has no mechanical
proof that it preserves Provider/Tool lifecycle, recovery, or that a claimed
driver digest identifies the executed code.

This module therefore retains only the exact identity/addressing result.  A future
executable LoopDriver interface must be earned by extracting non-bypassable loop
kernels and binding implementation bytes/contract evidence; it must not grow back
from an arbitrary callable.
"""

from __future__ import annotations

from dataclasses import dataclass

from anc_canonical import canonical_digest

from .mandate import CompiledHarnessAttempt, HarnessLoopDriverRef



def _builtin_ref(driver_id: str, scheduling_mode: str) -> HarnessLoopDriverRef:
    descriptor = {
        "schemaVersion": 1,
        "kind": "ordivon.builtin-loop-driver-semantics",
        "driverId": driver_id,
        "schedulingMode": scheduling_mode,
        "constitutionKernel": "ordivon-agent-loop-v1",
    }
    return HarnessLoopDriverRef(
        driver_id=driver_id,
        driver_digest=canonical_digest(descriptor),
    )


SEQUENTIAL_LOOP_DRIVER = _builtin_ref(
    "loop-driver:sequential-v1", "sequential"
)
DELIBERATE_THEN_ACT_LOOP_DRIVER = _builtin_ref(
    "loop-driver:deliberate-then-act-v1", "deliberate_then_act"
)
_BUILTIN_SCHEDULING_MODES = {
    (SEQUENTIAL_LOOP_DRIVER.driver_id, SEQUENTIAL_LOOP_DRIVER.driver_digest): "sequential",
    (
        DELIBERATE_THEN_ACT_LOOP_DRIVER.driver_id,
        DELIBERATE_THEN_ACT_LOOP_DRIVER.driver_digest,
    ): "deliberate_then_act",
}


def builtin_scheduling_mode(identity: "HarnessLoopDriverIdentity | HarnessLoopDriverRef | None") -> str:
    if identity is None:
        return "sequential"
    key = (identity.driver_id, identity.driver_digest)
    try:
        return _BUILTIN_SCHEDULING_MODES[key]
    except KeyError as error:
        raise ValueError(
            "Harness LoopDriver is identified but has no admitted built-in executable implementation"
        ) from error

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
class HarnessLoopDriverIdentity:
    """One exact Attempt-bound Loop implementation identity, without execution.

    The object proves only that an immutable compiled Attempt declared this
    `(driverId, driverDigest)` pair.  It grants no right to load, execute, replace,
    discover, or promote code.
    """

    driver_id: str
    driver_digest: str
    system_manifest_digest: str

    def __post_init__(self) -> None:
        _text(self.driver_id, "Harness LoopDriver identity")
        _digest(self.driver_digest, "Harness LoopDriver digest")
        _digest(self.system_manifest_digest, "Harness LoopDriver System Manifest digest")

    @classmethod
    def from_compiled_attempt(
        cls,
        attempt: CompiledHarnessAttempt,
        *,
        driver_id: str,
        driver_digest: str,
    ) -> "HarnessLoopDriverIdentity":
        manifest_value = attempt.to_dict()["systemManifest"]
        assert isinstance(manifest_value, dict)
        declared = manifest_value.get("loopDriver")
        expected = {"driverId": driver_id, "driverDigest": driver_digest}
        if declared != expected:
            raise ValueError("Harness LoopDriver differs from the compiled Attempt manifest")
        contract_value = attempt.to_dict()["contract"]
        assert isinstance(contract_value, dict)
        manifest_ref = contract_value["systemManifestRef"]
        assert isinstance(manifest_ref, dict)
        if attempt.contract.system_manifest_ref.digest != manifest_ref["digest"]:
            raise ValueError("compiled Harness Attempt Contract manifest reference differs")
        return cls(
            driver_id=driver_id,
            driver_digest=driver_digest,
            system_manifest_digest=attempt.contract.system_manifest_ref.digest,
        )

    def require_contract(self, system_manifest_digest: str) -> None:
        if system_manifest_digest != self.system_manifest_digest:
            raise ValueError("Harness LoopDriver identity belongs to another Run manifest")


__all__ = [
    "DELIBERATE_THEN_ACT_LOOP_DRIVER",
    "HarnessLoopDriverIdentity",
    "SEQUENTIAL_LOOP_DRIVER",
    "builtin_scheduling_mode",
]
