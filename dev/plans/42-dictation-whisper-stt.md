# Plan 42 — Dictation (Whisper STT) in the rich editor + chat composer

User-requested (notes #31–33, 2026-08-27). Post-1.0 backlog item B13 (Whisper-class
STT) narrowed to **dictation**: record audio in the browser, transcribe it through a
provider speech-to-text model, insert the text where the user is writing. Audio/video
*material ingestion* stays backlog. ADR-097.

## Goal

1. **Rich text editor** (`MarkdownEditor`, shared by notes/extractions/new-file/chat-md):
   a mic toolbar button — record → transcribe → insert at cursor.
2. **Chat composer** (`ChatPanel`, sidebar + page variants share it): a mic button —
   record → transcribe → insert into the draft at the caret.
3. **New task type** `transcribe` in Settings → Tasks with a new `audio` capability
   slot (per-capability default + global/course overrides, same resolution chain as
   every other task).

## Non-goals

- Bundling a local whisper runtime — any OpenAI-compatible whisper server
  (whisper.cpp `server`, faster-whisper-server, speaches, LocalAI, Groq, OpenAI) works
  via the existing `openai_compatible` provider preset; Gemini transcribes via
  `generateContent` inline audio.
- Audio-file material ingestion, speaker diarization, TTS.

## Backend

- `app/ai/tasks.py`: `TaskDef("transcribe", "Speech-to-text dictation (Whisper-class models)", "audio")`.
  Rows self-seed at boot (no migration).
- `app/ai/providers.py`: `DEFAULT_REQUIRES` gains `"audio"`; `infer_caps` returns
  `["audio"]` for STT-looking ids (`whisper`, `transcribe`) and adds `audio` for
  `gemini` (audio input on `generateContent`).
- `app/ai/skills/__init__.py`: seed skill `transcribe.audio` (system prompt: verbatim
  transcript, dictated math as LaTeX, no commentary — ADR-054 spirit). Used as the
  instruction for the Gemini path; OpenAI-compatible endpoints are verbatim by nature.
- `app/ai/transcribe.py` (new, mirrors `embeddings.py`): provider call functions —
  `openai_compatible` → `POST {base}/audio/transcriptions` multipart
  (`file`/`model`/`response_format=json`, optional `language`); `google` →
  `generateContent` with base64 `inline_data` audio; `anthropic` → unsupported error.
  Returns `(text, Usage | None)` — usage parsed when the provider reports tokens.
- `app/ai/gateway.py`: `LLMGateway.transcribe(...)` — budget gate → resolve chain →
  per-chain fallback + transient retry (same as `generate`) → `_ledger` row
  (`context_type="gateway"`, `task="transcribe"`, prompt field carries
  `[audio N bytes mime]`). Audio bytes are **ephemeral**: no blob, no DB row.
- `app/api/ai.py`: `POST /ai/transcribe` (multipart; `file`, optional `language`
  ISO code) → `{text, model}`. `MAX_AUDIO_BYTES = 25 MiB` (OpenAI's limit), audio/*
  (+ `video/webm` — Chrome's MediaRecorder default) content types only. Errors:
  `TaskUnassigned` → 409, `BudgetExceeded` → 429, `ProviderError` → 502.

## Frontend

- `lib/api.ts`: `transcribeAudio(blob) → {text, model}`.
- `components/dictation/useDictation.ts` (new hook): `getUserMedia` + `MediaRecorder`
  (mime preference webm/opus → ogg/opus → mp4), 1 Hz timer, RMS level meter written to
  a ref (no parent re-renders; the visualizer has its own rAF), stop → transcribe →
  `onResult(text)`; `cancel` discards; structured errors
  (`unsupported` / `denied` / `unassigned` / `failed`) translated by the components;
  full cleanup of tracks/AudioContext on stop and unmount.
- `components/dictation/DictationStrip.tsx`: shared recording/transcribing strip
  (pulsing dot, timer, live 5-bar level, Cancel + Insert/Transcribing…) +
  `DictationMicButton`.
- `MarkdownEditor.tsx`: mic button in the toolbar (after the ✨ helper); strip between
  toolbar and content; result via `insertMarkdown(editor, text, 'at-cursor')`.
- `ChatPanel.tsx`: mic button left of send/stop; strip above the input row; result via
  `insertIntoDraft(text)`.
- Settings: `CAP_ORDER` + `MODEL_CAPS` gain `"audio"`, `settings.caps.audio` label.

## Tests

- Backend: gateway wire tests (openai_compatible multipart shape, google inline audio,
  anthropic unsupported, fallback on 500, ledger row), API tests (seeding of the
  `transcribe` task + `audio` default slot, scripted gateway 200, 409 unassigned,
  413 size, 422 mime/language).
- Frontend: hook unit test with mocked media APIs (full flow, cancel, unsupported,
  denied, 409 → unassigned), editor test (mic → stop → text inserted at cursor),
  composer test (mic → stop → draft text).

## Docs

STATUS.md (changelog + module status), `features.md`, `ai.md` (task/capability),
`usage/notes.md` + `usage/chat.md` (dictation how-to), model-caps hints.
