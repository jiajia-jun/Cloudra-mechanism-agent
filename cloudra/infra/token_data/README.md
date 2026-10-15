# Offline tokenizer data

`o200k_base.tiktoken.gz` contains the unmodified OpenAI o200k_base vocabulary,
compressed with gzip. Runtime code verifies the decompressed SHA-256 before use.

- Original source: https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken
- Downloaded from Microsoft's fixed-revision mirror:
  https://raw.githubusercontent.com/dotnet/machinelearning/efefa92f4486a43047c5b47618885a71bf7f0967/src/Microsoft.ML.Tokenizers.Data.O200kBase/Data/o200k_base.tiktoken
- SHA-256: `446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d`
- The tokenizer pattern and special tokens come from OpenAI's tiktoken:
  https://github.com/openai/tiktoken/blob/main/tiktoken_ext/openai_public.py

The vocabulary and tokenizer definition are distributed under the accompanying
MIT license. They provide a local estimate for other providers; they do not
reproduce every provider's token accounting.
