from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from anc_canonical import JsonValue, canonical_digest

from ordivon_harness.core_contracts import HarnessBoundReference, HarnessRunContract
from ordivon_harness.execution_binding import HarnessExecutionBinding, HarnessRuntimeReference
from ordivon_harness.ordivon.finance_research_runtime_bridge import (
    FINANCE_RESEARCH_DEFINITION,
    FINANCE_RESEARCH_TOOL_SURFACE_DIGEST,
    FinanceResearchRuntimeGrant,
    SQLiteHarnessFinanceResearchRuntimeBridge,
)
from ordivon_harness.ordivon.model import AgentToolCall, ScriptedTurnAdapter
from ordivon_harness.ordivon.sqlite_run_store import SQLiteHarnessRunContinuityStore
from ordivon_harness.protocol import HarnessRecoveryConsequence
from ordivon_harness.runtime_port import HarnessRuntimeClientError
from ordivon_harness.sqlite_store import SQLiteHarnessStore

DIGEST_A='sha256:'+'a'*64
DIGEST_B='sha256:'+'b'*64
DIGEST_C='sha256:'+'c'*64
SOURCE_STATE='sha256:'+'d'*64
IMPLEMENTATION='sha256:'+'e'*64
FINANCE_REVISION='67aad23cd1b293f16cacda894723921ed931bd57'
OWNER_WS='finance-owner-fixture'
RUNNER_WS='finance-runner-fixture'
STATE_ROOT='/root/projects/ordivon-finance/state'
STATE_DB=STATE_ROOT+'/control/finance.db'
APP_PYTHON='/root/projects/ordivon-finance/.venv/bin/python'
MATERIAL_ROOT='/var/lib/ordivon/finance-research-materializations'
RUNNER='/opt/ordivon-finance-runner/fixture/bin/python'
AUTHORITY='finance-research-materializations'

SPEC={
    'schemaVersion':0,'experimentId':'experiment:harness-research','question':'What follows from this PIT cut?',
    'program':'experiments/research.py',
    'inputs':[{'alias':'data','dataset':'test.dataset','datasetVersion':0,'asOf':None,'knowledgeTimeField':'observed_at','latestBy':[],'latestOrderField':'observed_at'}],
    'parameters':{},'extensions':{},
}


class FixedClock:
    def __init__(self,value:int=1000)->None:self.value=value
    def __call__(self)->int:return self.value


def finance_success(*,research_status='observed',padding=0)->dict[str,JsonValue]:
    result_value:dict[str,JsonValue]={'answer':42}
    if padding: result_value['padding']='x'*padding
    return {
        'schemaVersion':1,'kind':'ordivon.finance.runtime-domain-result','domain':'finance',
        'operation':'finance.research','interfaceVersion':3,'ok':True,
        'effectContract':{
            'schemaVersion':1,'kind':'ordivon.semantic-effect-contract','owner':'ordivon-finance',
            'effectClass':'CANONICAL_RESEARCH','credentialAccess':'none','environmentMutation':False,
            'externalWorldRead':False,'externalFinancialWrite':False,'financialSubmission':False,'authorityMutation':False,
        },
        'result':{
            'schemaVersion':0,'kind':'ordivon.finance.semantic-research-result','status':research_status,
            'semanticCallId':'harness-finance-research:fixture','sourceFence':{},'researchRunnerWorkspaceId':RUNNER_WS,
            'runtimeJobRef':'runtime://job/inner-job','reconciled':True,
            'stateVersionBefore':'10:aaa','stateVersionAfter':'13:bbb',
            'capitalStateCountsBefore':{'decisions':1,'proposals':2,'externalEffects':3,'capitalLedgerEntries':4},
            'capitalStateCountsAfter':{'decisions':1,'proposals':2,'externalEffects':3,'capitalLedgerEntries':4},
            'consumerStanding':{
                'semanticOperation':'finance.research','canonicalResearchStateMutation':True,
                'decisionMutation':False,'proposalMutation':False,'externalEffectMutation':False,'capitalLedgerMutation':False,
                'externalWorldRead':False,'venueCredentialAccess':False,'externalFinancialWriteAttempted':False,
                'financialSubmissionAttempted':False,'authorityMutation':False,'runtimePhysicalExecution':True,
            },
            'evidenceRef':'evidence://sha256/'+'1'*64,'experimentId':'experiment:harness-research',
            'semanticResultDigest':'sha256:'+'2'*64,'sourceStateVersion':'10:aaa',
            'materializationId':'research-input-materialization://sha256/'+'3'*64,
            'runtimeJobId':'inner-job','runtimeAttemptId':'inner-attempt','admissionCapability':'research.result.admit@5',
            'replayed':False,'result':result_value,
        },
    }


class FinanceResearchFakeRuntime:
    def __init__(self,mode:str='success')->None:
        self.mode=mode; self.calls=[]; self.workspace_exec_count=0; self.client_request_id=None
        self.job_id='job:finance-research-outer-fixture'
    def owner_stdout(self)->str:
        if self.mode=='malformed':return 'not-json'
        padding=150_000 if self.mode=='large' else 0
        return json.dumps(finance_success(padding=padding),ensure_ascii=False)
    def terminal(self)->dict[str,JsonValue]:
        assert self.client_request_id is not None
        stdout=self.owner_stdout(); raw=stdout.encode()
        return {
            'schemaVersion':1,'jobId':self.job_id,'clientRequestId':self.client_request_id,'status':'succeeded',
            'executionTerminal':True,'executionDisposition':'succeeded','deliveryDisposition':'committed','recoveryRequired':False,
            'semanticCompletionEvaluated':False,'resultAvailable':True,
            'artifacts':[{'artifactId':'finance-research.stdout','kind':'stdout','digest':'sha256:'+hashlib.sha256(raw).hexdigest(),'retainedBytes':len(raw),'droppedBytes':0,'truncated':False}],
            'stdoutTail':stdout[-65536:] if len(raw)>65536 else stdout,'stderrTail':'',
        }
    def call_tool(self,name:str,arguments:dict[str,JsonValue])->dict[str,JsonValue]:
        self.calls.append((name,arguments))
        if name=='workspace.exec':
            self.workspace_exec_count+=1; self.client_request_id=arguments['clientRequestId']
            if self.mode=='loss':raise HarnessRuntimeClientError('injected response loss')
            return self.terminal()
        if name=='task.list':
            return {'schemaVersion':1,'jobs':[{'jobId':self.job_id,'clientRequestId':arguments.get('clientRequestId'),'status':'succeeded'}],'nextCursor':None}
        if name=='task.observe':return self.terminal()
        if name=='artifact.read':
            stdout=self.owner_stdout(); raw=stdout.encode(); offset=arguments['offset']; size=arguments['maxBytes']; chunk=raw[offset:offset+size]; nxt=offset+len(chunk)
            return {'jobId':self.job_id,'artifactId':'finance-research.stdout','content':chunk.decode(),'offset':offset,'nextOffset':nxt,'eof':nxt==len(raw),'digest':'sha256:'+hashlib.sha256(raw).hexdigest()}
        raise AssertionError(name)


def grant()->FinanceResearchRuntimeGrant:
    return FinanceResearchRuntimeGrant(
        OWNER_WS,FINANCE_REVISION,SOURCE_STATE,STATE_ROOT,STATE_DB,APP_PYTHON,
        RUNNER_WS,AUTHORITY,MATERIAL_ROOT,RUNNER,IMPLEMENTATION,
    )


def contract(suffix:str)->HarnessRunContract:
    return HarnessRunContract(
        harness_run_id=f'harness-run:finance-research-{suffix}',harness_implementation_id='ordivon-harness@test',
        caller_id='caller:test',caller_run_ref=f'trial:{suffix}',
        objective_ref=HarnessBoundReference(f'objective:{suffix}','objective',DIGEST_A),
        context_refs=(HarnessBoundReference(f'context:{suffix}','context',DIGEST_B),),
        provider_id='provider:scripted',adapter_id=ScriptedTurnAdapter.adapter_id,requested_model_id=ScriptedTurnAdapter.model_id,
        tool_catalog_digest=FINANCE_RESEARCH_TOOL_SURFACE_DIGEST,tool_grant_digest=grant().digest,
        budget={'maxModelCalls':3,'maxToolCalls':2,'maxWallTimeMs':10_000},completion_contract={'mode':'record'},
        system_manifest_ref=HarnessBoundReference(f'system:{suffix}','system-manifest',DIGEST_C),created_at_ms=1000,
    )


def execution_binding(run_contract:HarnessRunContract,continuity:SQLiteHarnessRunContinuityStore,workspace_ref:str=OWNER_WS)->HarnessExecutionBinding:
    binding=continuity.binding
    refs=(
        HarnessRuntimeReference(namespace='ordivon.harness',reference_type='harness_run',reference_id=run_contract.harness_run_id,generation=str(binding.assignment_generation),digest=binding.digest),
        HarnessRuntimeReference(namespace='ordivon.harness',reference_type='run_contract',reference_id=f'run:{run_contract.digest[7:31]}',generation='1',digest=run_contract.digest),
        HarnessRuntimeReference(namespace='ordivon.harness',reference_type='tool_grant',reference_id=f'grant:{run_contract.tool_grant_digest[7:31]}',generation='1',digest=run_contract.tool_grant_digest),
    )
    return HarnessExecutionBinding(
        harness_run_id=run_contract.harness_run_id,workspace_ref=workspace_ref,assignment_id=binding.assignment_id,
        assignment_generation=binding.assignment_generation,assignment_digest=binding.assignment_digest,
        runtime_binding_digest=canonical_digest({'harnessRunId':run_contract.harness_run_id,'workspaceRef':workspace_ref,'sourceRevisionExpected':FINANCE_REVISION}),
        tool_catalog_digest=run_contract.tool_catalog_digest,tool_grant_digest=run_contract.tool_grant_digest,
        deadline_ms=run_contract.deadline_ms,runtime_references=refs,
    )


def call(suffix:str,arguments=None)->AgentToolCall:
    return AgentToolCall(tool_call_id=f'tool-call:finance-research-{suffix}',name='finance_research',arguments={'researchRunSpec':SPEC} if arguments is None else arguments)


class FinanceResearchRuntimeBridgeTests(unittest.TestCase):
    def initialize(self,directory:str,suffix:str,runtime:FinanceResearchFakeRuntime):
        rc=contract(suffix); store=SQLiteHarnessStore.initialize(Path(directory)/'state'); store.create_run(rc)
        continuity=SQLiteHarnessRunContinuityStore(store,rc,clock_ms=FixedClock())
        bridge=SQLiteHarnessFinanceResearchRuntimeBridge(rc,continuity,execution_binding(rc,continuity),runtime,grant())
        bridge.bind_run_state(messages=({'role':'user','content':'research the current Finance question'},),observations=(),remaining_budget={'modelCalls':3,'modelRetries':1,'toolCalls':2,'wallTimeMs':10_000,'observationOnlyTurns':3,'noProgressTurns':3},requested_model_id=ScriptedTurnAdapter.model_id,effective_model_id=None,active_elapsed_ms=0)
        return store,continuity,bridge

    def test_surface_is_semantic_only_and_recovery_consequence_is_strong(self):
        self.assertEqual(set(FINANCE_RESEARCH_DEFINITION.input_schema['properties']),{'researchRunSpec'})
        self.assertFalse(FINANCE_RESEARCH_DEFINITION.input_schema['additionalProperties'])
        self.assertEqual(SQLiteHarnessFinanceResearchRuntimeBridge.recovery_consequence,HarnessRecoveryConsequence.PROCESS_OR_EXTERNAL_EFFECT_POSSIBLE)
        self.assertEqual(SQLiteHarnessFinanceResearchRuntimeBridge.observation_only_tool_names,frozenset())
        g=grant().to_dict(); self.assertFalse(g['financialWriteAllowed']); self.assertFalse(g['providerCredentialAllowed'])

    def test_lowering_keeps_research_equipment_out_of_agent_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime=FinanceResearchFakeRuntime(); _,_,bridge=self.initialize(directory,'lower',runtime)
            observation=bridge.execute(call('lower'),step_id='step:research-1')
            self.assertEqual(observation.status,'observed')
            request=next(args for name,args in runtime.calls if name=='workspace.exec'); execution=request['execution']
            self.assertEqual(execution['workspaceId'],OWNER_WS); self.assertEqual(execution['executable'],'/usr/bin/node')
            self.assertEqual(execution['args'][:4],['scripts/finance-domain.mjs','call','--operation','finance.research'])
            owner_args=json.loads(execution['args'][5]); self.assertEqual(owner_args,{'researchRunSpec':SPEC})
            env=execution['env']
            self.assertEqual(env['ORDIVON_FINANCE_RESEARCH_OWNER_WORKSPACE'],OWNER_WS)
            self.assertEqual(env['ORDIVON_FINANCE_RESEARCH_RUNNER_WORKSPACE'],RUNNER_WS)
            self.assertEqual(env['ORDIVON_FINANCE_RESEARCH_INPUT_AUTHORITY'],AUTHORITY)
            self.assertEqual(env['ORDIVON_FINANCE_RESEARCH_TRUSTED_IMPLEMENTATION_DIGEST'],IMPLEMENTATION)
            self.assertTrue(env['ORDIVON_FINANCE_RESEARCH_CALL_ID'].startswith('harness-finance-research:'))
            projection=observation.structured_content['financeProjection']
            self.assertEqual(projection['evidenceRef'],'evidence://sha256/'+'1'*64)
            self.assertEqual(projection['admissionCapability'],'research.result.admit@5')
            self.assertEqual(json.loads(projection['resultJson']),{'answer':42})
            self.assertEqual(projection['resultEncoding'],'application/json; charset=utf-8')
            self.assertFalse(observation.structured_content['effectBoundary']['externalFinancialWrite'])

    def test_float_finance_result_is_preserved_as_json_text_without_violating_harness_canonical_values(self):
        value={'ratio':0.0547945205479452,'nested':[{'costBps':10.183794520547945}]}
        text,omitted,digest,size=SQLiteHarnessFinanceResearchRuntimeBridge._project_result(value)
        self.assertFalse(omitted); self.assertIsNotNone(text); self.assertIsNotNone(digest); self.assertGreater(size,0)
        self.assertEqual(json.loads(text),value)
        from anc_canonical import validate_json_value
        validate_json_value({'resultJson':text,'resultDigest':digest,'resultBytes':size})

    def test_runtime_response_loss_reattaches_outer_job_without_redispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime=FinanceResearchFakeRuntime('loss'); _,_,bridge=self.initialize(directory,'loss',runtime)
            observation=bridge.execute(call('loss'),step_id='step:research-loss')
            self.assertEqual(observation.status,'observed'); self.assertEqual(runtime.workspace_exec_count,1)
            self.assertIn('task.list',[name for name,_ in runtime.calls]); self.assertIn('task.observe',[name for name,_ in runtime.calls])

    def test_large_research_result_uses_verified_artifact_and_bounded_projection(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime=FinanceResearchFakeRuntime('large'); _,_,bridge=self.initialize(directory,'large',runtime)
            observation=bridge.execute(call('large'),step_id='step:research-large')
            self.assertEqual(observation.status,'observed'); self.assertIn('artifact.read',[name for name,_ in runtime.calls])
            projection=observation.structured_content['financeProjection']
            self.assertTrue(projection['resultOmittedByHarnessBound']); self.assertIsNone(projection['resultJson']); self.assertGreater(projection['resultBytes'],128_000); self.assertTrue(projection['resultDigest'].startswith('sha256:'))

    def test_unknown_agent_deployment_argument_is_rejected_before_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime=FinanceResearchFakeRuntime(); _,_,bridge=self.initialize(directory,'bad',runtime)
            with self.assertRaisesRegex(Exception,'only one researchRunSpec'):
                bridge.execute(call('bad',{'researchRunSpec':SPEC,'runnerExecutable':'/tmp/agent'}),step_id='step:bad')
            self.assertEqual(runtime.workspace_exec_count,0)

    def test_owner_and_runner_workspace_must_differ(self):
        with self.assertRaisesRegex(ValueError,'must be distinct'):
            FinanceResearchRuntimeGrant(OWNER_WS,FINANCE_REVISION,SOURCE_STATE,STATE_ROOT,STATE_DB,APP_PYTHON,OWNER_WS,AUTHORITY,MATERIAL_ROOT,RUNNER,IMPLEMENTATION)


if __name__=='__main__': unittest.main()
