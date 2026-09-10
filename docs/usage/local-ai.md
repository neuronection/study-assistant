# Local AI — fully offline setup

The study assistant is **provider-first**: every AI call (chat, OCR, quiz
generation, embeddings, dictation) resolves through a provider model you
configure. That means the whole app runs **100% locally, with zero API keys and
zero cost**, whenever the provider is a local engine on your machine — no
in-process models are bundled (ADR-105); the app speaks the OpenAI-compatible
surface that local engines already expose.

## Supported engines

| Engine | Base URL preset | Notes |
|---|---|---|
| [Ollama](https://ollama.com) | `http://localhost:11434/v1` | Easiest start; `ollama pull` models |
| [llama.cpp](https://github.com/ggml-org/llama.cpp) `llama-server` | `http://localhost:8080/v1` (alt port `8081` is detected too) | Start with `-vl` multimodal variants for vision OCR |
| [LM Studio](https://lmstudio.ai) | `http://localhost:1234/v1` | Enable the local server in the Developer tab |
| whisper.cpp server / speaches | add as **Custom** provider, e.g. `http://localhost:8081/v1` | OpenAI-compatible `/v1/audio/transcriptions` for dictation |

All of them speak `/v1/chat/completions` (incl. vision `image_url` parts),
`/v1/embeddings`, and (for whisper servers) `/v1/audio/transcriptions` — exactly
the surface the app's gateway uses. **API keys are optional for local engines**:
leave the key field empty, nothing is written to the keyring.

## Quick start (wizard)

1. Start your engine, e.g. `ollama serve` (or `ollama start` on desktop installs).
2. Launch the study assistant — the first-run wizard's **Provider** step probes
   your machine once for running engines (Ollama `:11434`, llama.cpp `:8080`/`:8081`,
   LM Studio `:1234`). A hit shows the engine name and model count with a one-click
   **Add** button; you can always re-probe with **Detect local engines**.
   Detection is localhost-only, read-only, and never persisted.
3. On the **Models** step, enable the models you want and correct the guessed
   capabilities in the draft panel if needed (see *Capability guesses* below).
4. On the **Defaults** step, assign one model per capability
   (text / vision / embeddings / audio). When all your providers are local the
   wizard shows an "everything runs on this machine" hint.
5. Done — no key ever entered, nothing leaves the machine.

In Settings → Providers you get the same detection from the empty state, and
every provider card has a **Connection** row that probes the engine
(`GET /v1/models` + a tiny embedding round-trip when an embeddings model is
discovered) so a wrong port or stale engine is caught in one click.

## Recommended models per capability

Vision OCR quality drives the math workflow — prefer a dedicated vision model
over a small general one. Verified 2026-09-01 with Ollama on a single workstation
(model names as installed there):

| Capability | Example models (Ollama tags) | Verified |
|---|---|---|
| Text / chat | `qwen3.5:2b`, `qwen3:4b-instruct-2507-q4_K_M`, `gemma4:e4b-it-q4_K_M` | streaming chat turn end-to-end with `qwen3.5:2b` |
| Vision (OCR) | `qwen3-vl:4b-instruct-q4_K_M`, `deepseek-ocr`, `hf.co/sahilchachra/Unlimited-OCR-GGUF` | `image_url` part transcribed correctly with `qwen3-vl:4b` |
| Embeddings | `nomic-embed-text-v2-moe` | 768-dim vectors via `/v1/embeddings`; chunk embed + hybrid search end-to-end |
| Audio (dictation) | whisper.cpp server, speaches | needs a running STT server — see table above |

Larger models are better at tool-calling and long derivations; small models may
skip the citation/comment grammar or produce weaker structured output — the
deterministic validators and repair loops catch most of that, and the
prompt-grammar fallback handles engines without reliable native tool calls.

## Capability guesses

The app guesses each model's capabilities from its name (e.g. `vl` → vision,
`embed` → embeddings). These are **initial guesses only** — fix them in the
model draft panel (Settings → Models → expand a model). One real example:
`nomic-embed-text-v2-moe` is guessed text-only because the name contains
`embed-text`, not `embedding`; flip its capability to **embeddings** and assign
it as the embeddings default — exactly the correction flow the settings UI is
built for.

## Cost and privacy

- Local engines report no token costs; the Tasks spend view stays at zero.
- Prompts, materials and embeddings never leave your machine when every
  assigned model is local.
- Hybrid search uses your local embeddings server; without an embeddings model
  assigned the app degrades to keyword (FTS) search and tells you so.

## Limitations

- Engine lifecycle is yours: start/stop models with the engine's own tooling.
- Transcription of long audio via cloud-native STT is subject to provider size
  limits; local whisper servers set their own limits.
- Vision OCR quality depends heavily on the model — check the extraction QA
  editor for the first pages you ingest and correct as needed.
