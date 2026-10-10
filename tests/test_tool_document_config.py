"""Tool selection configuration is atomic, explicit and secret-safe."""
import pytest
import yaml
from pydantic import ValidationError

import cloudra.infra.config as config


def cls():
    assert hasattr(config, 'ToolDocumentLoadingConfig'), 'Selection configuration is missing'
    return config.ToolDocumentLoadingConfig


def test_default_selector_has_no_new_credentials():
    cfg = cls()()
    assert cfg.strategy == 'llm'
    assert not cfg.jev.key
    assert not cfg.reranker.key


def test_semantic_activation_requires_its_own_boundary():
    with pytest.raises(ValidationError):
        cls()(strategy='semantic', semantic_backend='jev', jev={'endpoint':'https://api.example/v1/systemone','model':'jev','key':'secret'})
    cfg = cls()(strategy='semantic', semantic_backend='reranker', reranker={
        'endpoint':'http://localhost:8001/v1/rerank','model':'local','min_score':-0.2})
    assert cfg.reranker.min_score == -0.2
    assert cfg.jev.min_probability is None


def test_display_omits_actual_keys():
    cfg = cls()(jev={'key':'do-not-return'}, reranker={'key':'another-secret'})
    shown = cfg.to_display_dict()
    assert shown['jev']['key_set']
    assert 'key' not in shown['jev']
    assert 'do-not-return' not in str(shown)
    assert 'another-secret' not in str(shown)


def test_merge_preserves_keys_and_rejects_invalid_clear():
    cfg = cls()(strategy='semantic', semantic_backend='jev', jev={
        'endpoint':'https://api.example/v1/systemone','model':'jev','key':'secret','min_probability':0.7})
    changed = cfg.with_patch({'jev':{'max_tools':3}})
    assert changed.jev.key == 'secret'
    with pytest.raises(ValidationError):
        cfg.with_patch({'jev':{'key':''}})
    cleared = cfg.with_patch({'strategy':'llm','jev':{'key':''}})
    assert cleared.jev.key == ''


def test_yaml_round_trip_keeps_policy_and_invalid_yaml_fails_loud(tmp_path, monkeypatch):
    assert hasattr(config.CloudraConfig, 'model_fields')
    cls()
    path = tmp_path/'selection-config.yaml'
    cfg = config.CloudraConfig(data_dir=tmp_path/'data',config_file=path)
    cfg.tool_document_loading = cls()(strategy='semantic', semantic_backend='reranker', reranker={
        'endpoint':'http://localhost:8001/v1/rerank','model':'local','min_score':0.3})
    path.write_text(yaml.safe_dump(config._model_to_yaml_data(cfg)))
    restored = config.CloudraConfig(data_dir=tmp_path/'data', config_file=path)
    assert restored.tool_document_loading.strategy == 'semantic'
    assert restored.tool_document_loading.reranker.min_score == 0.3
    path.write_text('tool_document_loading:\n  strategy: semantic\n')
    with pytest.raises(ValueError):
        config.CloudraConfig(data_dir=tmp_path/'data',config_file=path)
