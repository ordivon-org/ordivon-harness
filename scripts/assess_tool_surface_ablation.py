#!/usr/bin/env python3
from __future__ import annotations
import json
from anc_canonical import canonical_bytes, canonical_digest
from ordivon_harness.ordivon.deepseek import _provider_tool
from ordivon_harness.ordivon.sqlite_repository_repair_bridge import INDEPENDENT_REPOSITORY_REPAIR_TOOL_DEFINITIONS
from ordivon_harness.ordivon.turn_projection import project_turn_tool_working_set, select_turn_tool_working_set

# A real existing repository-repair phase that only needs observation + validation.
SELECTED=("read_workspace","run_check")

def assess():
    broad=INDEPENDENT_REPOSITORY_REPAIR_TOOL_DEFINITIONS
    lazy=select_turn_tool_working_set(broad,SELECTED)
    broad_provider=[_provider_tool(tool) for tool in broad]
    lazy_provider=[_provider_tool(tool) for tool in lazy]
    broad_bytes=len(canonical_bytes(broad_provider)); lazy_bytes=len(canonical_bytes(lazy_provider))
    broad_by={tool.name:canonical_digest(tool.to_dict()) for tool in broad}
    lazy_by={tool.name:canonical_digest(tool.to_dict()) for tool in lazy}
    return {
      "schemaVersion":1,
      "kind":"ordivon.harness-ts11-tool-surface-ablation",
      "sourceSurface":"independent-repository-repair",
      "treatment":"explicit-turn-tool-working-set",
      "broad":{
        "toolNames":[tool.name for tool in broad],
        "providerSchemaBytes":broad_bytes,
        "providerSchemaDigest":canonical_digest(broad_provider),
      },
      "lazy":{
        "toolNames":[tool.name for tool in lazy],
        "providerSchemaBytes":lazy_bytes,
        "providerSchemaDigest":canonical_digest(lazy_provider),
        "workingSet":project_turn_tool_working_set(broad,SELECTED),
      },
      "delta":{
        "omittedTools":len(broad)-len(lazy),
        "providerSchemaBytesRemoved":broad_bytes-lazy_bytes,
        "providerSchemaReductionRatio":round((broad_bytes-lazy_bytes)/broad_bytes,6),
      },
      "invariants":{
        "selectedDefinitionDigestsUnchanged":all(broad_by[name]==lazy_by[name] for name in lazy_by),
        "authorityExpanded":False,
        "unknownToolSelectionRejectedByProductCode":True,
        "providerBehaviorCompared":False,
      },
      "behaviorBoundary":"TS11 proves structural/context friction reduction and monotonic authority narrowing only. It does not claim higher model accuracy, latency, or task success without a predeclared live Provider experiment.",
    }

if __name__=='__main__': print(json.dumps(assess(),indent=2,sort_keys=True))
