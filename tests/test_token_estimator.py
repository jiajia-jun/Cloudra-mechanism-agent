import pytest


def test_missing_encoding_cache_never_starts_a_runtime_download(tmp_path, monkeypatch):
    import tiktoken

    from cloudra.infra import token_estimator

    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("DATA_GYM_CACHE_DIR", raising=False)
    token_estimator._encoding_for.cache_clear()
    calls = []

    def unexpected_download(name):
        calls.append(name)
        raise AssertionError("tiktoken loading may download an encoding asset")

    monkeypatch.setattr(tiktoken, "get_encoding", unexpected_download)

    with pytest.raises(FileNotFoundError, match="not cached"):
        token_estimator._encoding_for("o200k_base")
    assert calls == []
