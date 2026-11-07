# Bundled tokenizer assets (plan 52 T5a)

These files are **data**, never code. The tokenizer service loads them from
this directory (which the packaging spec ships as `app/data`) and never
fetches an encoding at request or boot time.

| File | Source | Canonical sha256 |
|---|---|---|
| `cl100k_base.tiktoken.gz` | gzip of OpenAI's `cl100k_base.tiktoken` (`https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken`) | `223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7` (uncompressed BPE file, the checksum `tiktoken_ext` pins) |
| `reference_corpus.json` | deterministic synthetic English/Greek/German/CJK/code samples | — |

The gzip container's own checksum is pinned in
`app/ai/tokenizers/service.py`; the service verifies the **uncompressed**
sha256 above after decompression, so a swapped container or payload is a
structured `tokenizer_missing` state, never a silent wrong count.

`cl100k_base` is the encoding OpenAI's `text-embedding-3-*` models use.
Licence: the tiktoken library and its encoding data are MIT-licensed
(OpenAI).

Hugging Face `tokenizer.json` assets do **not** live here. Study has no
concrete HF model mapping in plan 52 T5a, so the service exposes only the
spec interface and degrades that kind visibly; a later wave may pre-seed
verified assets under `<data_dir>/tokenizers/<sha256>/tokenizer.json`.
`sentencepiece` remains reserved and unsupported until a concrete model
requires it.
