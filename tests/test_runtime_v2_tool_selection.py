"""Selectors choose documents, never execute tools or invent authority."""
import asyncio
import importlib
import importlib.util
from types import SimpleNamespace

import httpx
import pytest

from cloudra.infra.config import ToolDocumentLoadingConfig
from cloudra.runtime_v2.schemas import AgentSession, RuntimeSettings
from cloudra.runtime_v2.turn_pipeline import LLMResponse
from cloudra.tools.documentation import ToolCapabilitySummary


def module():
    assert importlib.util.find_spec('cloudra.runtime_v2.tool_selection') is not None, 'Selector is missing'
    return importlib.import_module('cloudra.runtime_v2.tool_selection')


def candidates():
    return (ToolCapabilitySummary(name='read',summary='Read exact file content.'),
        ToolCapabilitySummary(name='ts_inspect',summary='Read current TS evidence and missing inputs.'))


class Provider:
    def __init__(self, content='["read"]', tools=None):
        self.content=content
        self.tools=tools or []
        self.requests=[]
    async def select_tool_names(self, agent, messages, *, resolved_settings):
        self.requests.append(messages)
        return LLMResponse(content=self.content, tool_calls=self.tools, usage={'input_tokens':12})


async def select(provider, cfg=None, transport=None, messages=None, settings=None):
    a = AgentSession(id='selector',project_id='project',role_id='coordinator',display_name='coordinator')
    return await module().ToolDocumentSelector(provider, transport=transport).select(agent=a,
        task_messages=messages or [{'role':'user','content':'Read my evidence log.'}],
        resolved_settings=settings or RuntimeSettings(model='resolved-model'),candidates=candidates(),
        config=cfg or ToolDocumentLoadingConfig())


@pytest.mark.asyncio
@pytest.mark.parametrize(('content','status','names'), [('["read","read"]','selected',('read',)),
    ('[]','empty',()), ('["hidden"]','failed',()), ('```json\n["read"]\n```','failed',()), ('{"tools":["read"]}','failed',())])
async def test_llm_names_are_strictly_validated(content,status,names):
    result=await select(Provider(content))
    assert result.status==status
    assert result.names==names


@pytest.mark.asyncio
async def test_structured_task_keeps_text_and_image_marker():
    provider=Provider('[]')
    result=await select(provider,messages=[{'content':[{'type':'text','text':'Inspect attached reaction'},
        {'type':'image_ref','image_ref':{'path':'secret-image.png'}}]}])
    assert result.status=='empty'
    text=str(provider.requests)
    assert 'Inspect attached reaction' in text
    assert 'image' in text.lower()
    assert 'secret-image.png' not in text


@pytest.mark.asyncio
async def test_jev_batch_allows_multiple_independent_matches():
    cfg=ToolDocumentLoadingConfig(strategy='semantic',jev={'endpoint':'https://jev.example/systemone',
        'model':'jev','key':'separate-key','min_probability':0.6})
    def handle(request):
        import json
        body=json.loads(request.content)
        assert set(body['questions'])=={'read','ts_inspect'}
        assert 'Read exact file' in body['questions']['read']['instructions']
        return httpx.Response(200,json={'answers':{'read':{'noul':0.9},'ts_inspect':{'noul':0.8}}})
    result=await select(Provider(),cfg,httpx.MockTransport(handle))
    assert result.names==('read','ts_inspect')


@pytest.mark.asyncio
@pytest.mark.parametrize('results', [[{'index':1,'relevance_score':4},{'index':0,'relevance_score':1}],
    [{'index':0,'relevance_score':1},{'index':0,'relevance_score':2}],
    [{'index':2,'relevance_score':1},{'index':0,'relevance_score':2}]])
async def test_rerank_results_are_complete_unique_and_use_their_own_score(results):
    cfg=ToolDocumentLoadingConfig(strategy='semantic',semantic_backend='reranker',reranker={
        'endpoint':'http://localhost:8001/rerank','model':'local','min_score':2})
    result=await select(Provider(),cfg,httpx.MockTransport(lambda _:httpx.Response(200,json={'results':results})))
    if results[0]['index']==1:
        assert result.names==('ts_inspect',)
    else:
        assert result.status=='failed'
        assert result.names==()


@pytest.mark.asyncio
async def test_cancel_is_not_transformed_into_success_or_retried():
    class Cancel(Provider):
        async def select_tool_names(self,*args,**kwargs):
            raise asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await select(Cancel())


@pytest.mark.asyncio
async def test_default_adapter_request_has_no_tools_or_native_search(monkeypatch):
    from cloudra.runtime_v2.adapters import LegacyLLMProvider
    provider=LegacyLLMProvider()
    assert hasattr(provider,'select_tool_names'), 'No-tool selection request is missing'
    sent=[]
    class Client:
        last_usage={'input_tokens':3}
        closed=False
        async def create(self,**kwargs):
            sent.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='["read"]',tool_calls=[]))])
        async def aclose(self):
            self.closed=True
    client=Client()
    monkeypatch.setattr(provider,'_make_client',lambda settings:client)
    settings=RuntimeSettings(model='actual-model',base_url='https://model.example',api_key='private',native_search='deepseek')
    a=AgentSession(id='selection-only',project_id='p',role_id='coordinator',display_name='coordinator')
    response=await provider.select_tool_names(a,[{'role':'user','content':'Task'}],resolved_settings=settings)
    assert response.content=='["read"]'
    assert sent[0]['model']=='actual-model'
    assert 'tools' not in sent[0]
    assert client.closed


@pytest.mark.asyncio
@pytest.mark.parametrize('body', [{}, {'answers':{'read':{'noul':0.9}}},
    {'answers':{'read':{'noul':True},'ts_inspect':{'noul':0.9}}}])
async def test_jev_malformed_envelope_is_an_observable_failure(body):
    cfg=ToolDocumentLoadingConfig(strategy='semantic',jev={'endpoint':'https://jev.example/systemone',
        'model':'jev','key':'secret','min_probability':0.6})
    result=await select(Provider(),cfg,httpx.MockTransport(lambda _:httpx.Response(200,json=body)))
    assert result.status=='failed'
    assert result.names==()


@pytest.mark.asyncio
async def test_provider_failure_is_recorded_without_aborting_main_task():
    class Broken(Provider):
        async def select_tool_names(self,*args,**kwargs):
            raise RuntimeError('Upstream unavailable')
    result=await select(Broken())
    assert result.status=='failed'
    assert result.error_code=='RuntimeError'


@pytest.mark.asyncio
async def test_selection_has_a_total_deadline():
    class Slow(Provider):
        async def select_tool_names(self,*args,**kwargs):
            await asyncio.sleep(60)
    result=await asyncio.wait_for(select(Slow(),settings=RuntimeSettings(timeout=1)),timeout=3)
    assert result.status=='failed'
    assert result.error_code=='TimeoutError'
