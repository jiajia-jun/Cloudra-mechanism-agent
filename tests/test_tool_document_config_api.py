"""Selection config uses the real protected runtime API and atomic writer."""
import pytest
from httpx import ASGITransport, AsyncClient

from cloudra.services.api_v2 import create_v2_app


@pytest.mark.asyncio
async def test_tool_document_loading_api_preserves_secrets_and_rejects_invalid_activation(tmp_path, monkeypatch):
    from cloudra.infra.config import get_config
    cfg = get_config()
    monkeypatch.setattr(cfg, 'config_file', tmp_path/'config.yaml')
    async with AsyncClient(transport=ASGITransport(app=create_v2_app()), base_url='http://testserver') as client:
        response = await client.patch('/api/v2/runtime/config/tool-document-loading', json={
            'strategy':'semantic','semantic_backend':'jev','jev':{
                'endpoint':'https://api.example/v1/systemone','model':'jev','key':'secret-to-hide','min_probability':0.7}})
        assert response.status_code == 200
        assert response.json()['tool_document_loading']['jev']['key_set']
        assert 'secret-to-hide' not in response.text
        saved = cfg.config_file.read_text()
        invalid = await client.patch('/api/v2/runtime/config/tool-document-loading',json={'jev':{'key':''}})
        assert invalid.status_code == 422
        assert isinstance(invalid.json()['detail']['message'], str)
        assert 'secret-to-hide' not in invalid.text
        assert cfg.config_file.read_text() == saved
        cleared = await client.patch('/api/v2/runtime/config/tool-document-loading',json={'strategy':'llm','jev':{'key':''}})
        assert cleared.status_code == 200
        assert not cleared.json()['tool_document_loading']['jev']['key_set']
