from __future__ import annotations

from ..models import HarnessCapabilityManifest

ORDIVON_HARNESS_ID = "ordivon-harness-v0"
ORDIVON_HARNESS_PROTOCOL = "ordivon.agent-loop"
ORDIVON_HARNESS_PROTOCOL_REVISION = "p1"


def ordivon_harness_manifest() -> HarnessCapabilityManifest:
    """Return the first-party native capability declaration at P1."""

    return HarnessCapabilityManifest(
        harness_id=ORDIVON_HARNESS_ID,
        protocol=ORDIVON_HARNESS_PROTOCOL,
        protocol_revision=ORDIVON_HARNESS_PROTOCOL_REVISION,
        persistent_session=False,
        session_resume=False,
        session_fork=False,
        interrupt=True,
        tool_events=True,
        approval_events=False,
        usage=True,
        images=False,
        compaction=False,
        checkpoint=True,
        local_subagents=False,
        extensions=(
            "ordivon.runtime-aci.v1",
            "ordivon.explicit-unknown.v0",
            "ordivon.deepseek-turn-adapter.v0",
            "ordivon.run-state-resume.v1",
            "ordivon.effect-checkpoint.v1",
            "ordivon.provider-call-cancel.v1",
            "ordivon.runtime-job-cancel.v1",
            "ordivon.native-run-contract.v0",
            "ordivon.tool-grant.v0",
            "ordivon.run-provenance.v0",
            "ordivon.native-run-recovery.v0",
            "ordivon.safe-abandonment.v0",
            "ordivon.provider-fault-taxonomy.v0",
        ),
    )
