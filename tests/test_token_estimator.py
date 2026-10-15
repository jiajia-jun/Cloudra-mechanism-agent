def test_empty_cache_still_counts_numeric_tool_output_without_network(tmp_path, monkeypatch):
    import tiktoken.load

    from cloudra.infra import token_estimator

    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("DATA_GYM_CACHE_DIR", raising=False)
    token_estimator._encoding_for.cache_clear()

    def unexpected_download(*_args, **_kwargs):
        raise AssertionError("token counting must not download an encoding asset")

    monkeypatch.setattr(tiktoken.load, "read_file", unexpected_download)

    # Digits and commas are separate tokenizer pieces. The old chars/4
    # fallback counted this 2,000-token tool output as only 500 tokens.
    assert token_estimator.TokenEstimator.count_text("0," * 1000) == 2000


def test_truncation_uses_real_tokens_with_an_empty_cache(tmp_path, monkeypatch):
    from cloudra.infra import token_estimator

    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("DATA_GYM_CACHE_DIR", raising=False)
    token_estimator._encoding_for.cache_clear()

    assert token_estimator.TokenEstimator.truncate_to_tokens("0," * 1000, 10) == "0," * 5
