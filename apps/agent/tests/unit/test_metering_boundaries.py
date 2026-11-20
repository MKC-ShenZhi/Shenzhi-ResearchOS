"""Mock Transport integration: real adapter sends, no real provider traffic."""
import asyncio
from contextlib import aclosing
from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx
from pydantic import BaseModel

from agent_app.execution.compaction import summarize
from agent_app.execution.metering import current_meter, Measurement, skill_identity, tool_identity, model_identity
from agent_app.execution.provider import ModelRequest
from agent_app.execution.tools import ToolRegistry, tool
from agent_app.execution.types import ToolCall, UserMessage
from agent_app.extensions.skills import SkillStore, Skill, read_skill_tool
from agent_app.integrations.llm.agent_stream import OpenAICompatProvider
from agent_app.integrations.llm.config import ModelConfig


class RecordingMeter:
    def __init__(self):
        self.started, self.completed, self.activations = [], [], set()

    async def begin(self, identity, **metadata):
        self.started.append((identity,metadata))
        return str(len(self.started))

    async def complete(self, call_id, measurement):
        self.completed.append((call_id,measurement.observation()))

    async def activate(self, skill, invocation='model_selected'):
        identity=skill_identity(skill)
        self.activations.add(identity.resource_content_digest)


def stream(usage=None):
    import json
    frames=[{'id':'request-id','choices':[{'delta':{'content':'answer'},'finish_reason':'stop'}]}]
    if usage is not None:
        frames.append({'choices':[],'usage':usage})
    return ''.join('data: '+json.dumps(f)+'\n\n' for f in frames)+'data: [DONE]\n\n'


class MeteringBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.env=patch.dict(os.environ,{'AGENT_MODEL_ROUTE_REVISION':'test-route', 'AGENT_TOOL_CONFIGURATION_RELEASE':'test-tools'})
        self.env.start()
        self.meter=RecordingMeter()
        self.token=current_meter.set(self.meter)

    async def asyncTearDown(self):
        current_meter.reset(self.token)
        self.env.stop()

    def provider(self,handler,**kwargs):
        return OpenAICompatProvider(ModelConfig(provider='dashscope',model='qwen-plus',
            models=('qwen-plus',), base_url='https://provider.invalid/v1',key='test-only'), transport=httpx.MockTransport(handler),
            retry_delay=0,**kwargs)

    async def test_outer_retry_and_parameter_degradation_each_have_start_before_send(self):
        count=0
        async def handler(request):
            nonlocal count
            count+=1
            self.assertEqual(len(self.meter.started),count)
            if count==1:
                return httpx.Response(503,json={'error':'temporarily unavailable'})
            if count==2:
                return httpx.Response(400,text='stream_options unsupported')
            return httpx.Response(200,text=stream({'prompt_tokens':4,'completion_tokens':2}))
        events=[e async for e in self.provider(handler).stream(ModelRequest('qwen-plus',[{'role':'user','content':'hi'}]))]
        self.assertEqual(count,3)
        self.assertEqual(len(self.meter.completed),3)
        self.assertEqual(len({x[1]['logical_id'] for x in self.meter.started}),1)
        self.assertEqual(self.meter.completed[-1][1]['prompt_tokens'],4)
        self.assertIsNone(self.meter.completed[0][1]['prompt_tokens'])

    async def test_summary_has_its_own_purpose_and_usage(self):
        provider=self.provider(lambda r:httpx.Response(200,text=stream({'prompt_tokens':3,'completion_tokens':1})))
        result=await summarize(provider,'qwen-plus',[UserMessage('research context')])
        self.assertEqual(result,'answer')
        self.assertEqual(self.meter.started[0][1]['purpose'],'summary')
        self.assertEqual(self.meter.completed[0][1]['prompt_tokens'],3)

    async def test_partial_usage_and_cancel_do_not_become_zero(self):
        provider=self.provider(lambda r:httpx.Response(200,text=stream({'prompt_tokens':3})))
        _=[e async for e in provider.stream(ModelRequest('qwen-plus',[]))]
        observation=self.meter.completed[-1][1]
        self.assertEqual(observation['usage_status'],'partial')
        self.assertIsNone(observation['completion_tokens'])
        class Broken(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b'data: {"choices":[{"delta":{"content":"a"}}]}\n\n'
                raise httpx.ReadError('interrupted')
        provider=self.provider(lambda r:httpx.Response(200,stream=Broken()),max_retries=0)
        with self.assertRaises(Exception):
            _=[e async for e in provider.stream(ModelRequest('qwen-plus',[]))]
        self.assertEqual(self.meter.completed[-1][1]['usage_status'],'unknown')

    async def test_tool_prepare_failure_does_not_start_parallel_and_sequential_share_gate(self):
        class Args(BaseModel):
            value:int
        @tool(name='test_tool',description='test',params=Args)
        async def execute(args):
            return str(args.value)
        registry=ToolRegistry([execute])
        invalid=await registry.dispatch(ToolCall('bad','test_tool',{'value':'invalid'}))
        self.assertTrue(invalid.is_error)
        self.assertFalse(self.meter.started)
        await registry.dispatch(ToolCall('one','test_tool',{'value':1}))
        prepared=[await registry.prepare(ToolCall(str(i),'test_tool',{'value':i})) for i in range(2,4)]
        results=await asyncio.gather(*(registry.execute_prepared(p) for p in prepared))
        self.assertEqual(len(self.meter.started),3)
        self.assertTrue(all(not r.is_error for r in results))

    async def test_skill_reference_reads_share_exact_activation_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'SKILL.md').write_text('skill content',encoding='utf-8')
            (root/'references').mkdir()
            (root/'references'/'one.md').write_text('reference',encoding='utf-8')
            skill=Skill('test-skill','test','skill content',root/'SKILL.md',root,False)
            store=SkillStore({'test-skill':skill})
            registry=ToolRegistry([read_skill_tool(store)])
            for args in ({'name':'test-skill'},{'name':'test-skill','file':'references/one.md'}):
                result=await registry.dispatch(ToolCall('call','read_skill',args))
                self.assertFalse(result.is_error)
            self.assertEqual(len(self.meter.activations),1)
            identity=skill_identity(skill)
            os.utime(root/'SKILL.md',(1,1))
            self.assertEqual(identity,skill_identity(skill))
            (root/'references'/'one.md').write_text('changed',encoding='utf-8')
            self.assertNotEqual(identity,skill_identity(skill))

    async def test_persistence_rejection_forbids_http_send(self):
        class Reject(RecordingMeter):
            async def begin(self,*a,**kw):
                raise RuntimeError('storage failed')
        current_meter.set(Reject())
        sends=[]
        provider=self.provider(lambda r:sends.append(r))
        with self.assertRaises(RuntimeError):
            _=[e async for e in provider.stream(ModelRequest('qwen-plus',[]))]
        self.assertFalse(sends)

    def test_conflicting_cumulative_frames_require_reconciliation(self):
        observation=Measurement()
        observation.cumulative_usage({'prompt_tokens':10,'completion_tokens':4})
        observation.cumulative_usage({'prompt_tokens':8,'completion_tokens':4})
        result=observation.observation()
        self.assertEqual(result['usage_status'],'unknown')
        self.assertEqual(result['missing_reason'],'conflicting_usage_frames')

    def test_partial_final_frame_retains_evidence_without_claiming_complete_usage(self):
        value=Measurement()
        value.cumulative_usage({'prompt_tokens':10,'completion_tokens':4})
        value.cumulative_usage({'prompt_tokens':12})
        result=value.observation()
        self.assertEqual(result['usage_status'],'partial')
        self.assertEqual((result['prompt_tokens'],result['completion_tokens']),(12,4))

    async def test_control_start_timeout_is_not_a_provider_retry(self):
        from agent_app.execution.metering import WorkerMeter
        calls=[]
        class Control:
            async def post(self,path,body):
                calls.append(path)
                if path.endswith('/start'):
                    raise httpx.ReadTimeout('lost start receipt')
                return {'call_id':body['call_id'],'model_budget':dict(schema_version=1,
                    basis='risk_assessed_utf8_v1',input_tokens=10,output_tokens=10,reserved_tokens=20)}
        with tempfile.TemporaryDirectory() as root,patch.dict(os.environ,{'AGENT_USAGE_SPOOL_ROOT':root}):
            stop=asyncio.Event()
            current_meter.set(WorkerMeter(Control(),run_id='run',execution_id='execution',worker_id='worker',
                                          lease_token=1,context='authorized',stop=stop))
            sends=[]
            provider=self.provider(lambda request:sends.append(request))
            with self.assertRaises(Exception):
                _=[event async for event in provider.stream(ModelRequest('qwen-plus',[]))]
            self.assertTrue(stop.is_set())
            self.assertFalse(sends)
            self.assertEqual(len(calls),2)

    async def test_decimal_temperature_is_sent_as_number_and_metered(self):
        import json
        def send(request):
            self.assertEqual(json.loads(request.content)['temperature'],0.25)
            return httpx.Response(200,text=stream({'prompt_tokens':2,'completion_tokens':1}))
        events=[e async for e in self.provider(send).stream(ModelRequest('qwen-plus',[],temperature=0.25))]
        self.assertEqual(len(self.meter.started),1)

    async def test_dynamic_output_cap_binds_retries_degradation_summary_and_body(self):
        import json
        from agent_app.execution.metering import WorkerMeter
        from agent_app.errors import BusinessError
        calls=[]; sends=[]; approvals=[]
        class Control:
            async def post(inner,path,body):
                calls.append((path,body))
                if path.endswith('/authorize'):
                    budget=body['model_budget']
                    approval=dict(schema_version=1,basis=budget['basis'],input_tokens=budget['input_bytes']+3,
                                  output_tokens=7,reserved_tokens=budget['input_bytes']+10)
                    approvals.append(approval)
                    return {'model_budget':approval}
                if path.endswith('/start'):
                    return dict(may_send=True,model_budget=approvals[-1])
                return {}
        def send(request):
            body=json.loads(request.content);sends.append(body)
            self.assertEqual(body['max_tokens'],7)
            if len(sends)==1:return httpx.Response(503,text='unavailable')
            if len(sends)==2:return httpx.Response(400,text='stream_options unsupported')
            return httpx.Response(200,text=stream({'prompt_tokens':3,'completion_tokens':2}))
        with tempfile.TemporaryDirectory() as root,patch.dict(os.environ,{'AGENT_USAGE_SPOOL_ROOT':root}):
            meter=WorkerMeter(Control(),run_id='run',execution_id='execution',worker_id='worker',lease_token=1,
                              context='authorized',stop=asyncio.Event(),risk_profile='test-reviewed-risk')
            current_meter.set(meter)
            provider=self.provider(send)
            _=[e async for e in provider.stream(ModelRequest('qwen-plus',[{'role':'user','content':'hello'}]))]
            await summarize(provider,'qwen-plus',[UserMessage('context')])
            requests=[b for p,b in calls if p.endswith('/authorize')]
            self.assertEqual(len(requests),len(sends))
            self.assertEqual(requests[-1]['purpose'],'summary')
            self.assertTrue(all(r['input_bound_evidence_ref'] is None for r in requests))
            self.assertTrue(all(r['model_budget']['input_bytes']>0 for r in requests))
            # Tampering is rejected before a sending right is consumed.
            call_id=next(iter(meter.receipts))
            with self.assertRaises(BusinessError):meter.consume_send(call_id,{'max_tokens':8,'messages':[]})
