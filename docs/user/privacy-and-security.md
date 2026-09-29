# Privacy and security

Study Assistant is built local-first: your material, notes, answers and
database stay on your own machine, and there is no account, no telemetry and no
Neuronection server involved. This page explains what that means in practice
and the guardrails around the AI features. For the implementation-level model,
see the [developer security page](../dev/security.md).

## Where your data lives

Everything is stored under your data directory — `~/.local/share/StudyAssistant/`
on Linux (the platform equivalent on Windows/macOS), or wherever you point the
**working directory** in Settings → Data:

| Item | Where |
|---|---|
| Database (courses, materials, notes, answers, settings) | `app.db` (SQLite) |
| Original files | `blobs/` (content-addressed, never modified) |
| Cache and thumbnails | `cache/`, `thumbnails/` |
| Automatic backups | `backups/` |

Deleting that folder resets the app; deleted materials and topics go to the
in-app **trash** first. See [Backups, trash & restore](backup.md).

## What leaves your machine

Only the AI calls you configure. When the app runs OCR, generates a quiz, or
answers a chat message, it sends the relevant content to the provider you
connected (for example Google, OpenAI, or your own local server). Nothing else
is transmitted — no analytics, no crash reports, no sync.

If you want **zero** external traffic, run a local provider (Ollama, LM Studio,
llama.cpp) and assign local models to every task. See
[Local AI — fully offline setup](local-ai.md).

## How API keys are protected

- Keys are stored in your **operating system's keyring** (the same secure store
  your desktop uses for passwords) — never in the database, a config file or an
  environment block.
- The app shows only a masked form of a key (for example `••••1234`); the full
  value is used only for the outbound provider call.
- If your keyring is unavailable, the app refuses to save the key rather than
  falling back to an insecure store.

## The AI trust boundary

Model output is treated as a suggestion, not a fact:

- **Grading is deterministic.** Math answers are compared by the app's own
  equivalence engine, not by the model's opinion — `2x` and `x*2` both count as
  correct.
- **Hints never reveal answers** — the hint ladder is enforced by code, not by
  prompt promises.
- **Edits are proposals.** When the chat offers to change a note or material, it
  shows a review card with a diff; nothing is written until you approve it, and
  the target is re-checked at approval time.
- **Fetched content is untrusted.** Pages imported from the web are converted to
  plain markdown; scripts are never executed.

## Network exposure

The backend binds to `127.0.0.1` (loopback) only. In the Docker deployment it
sits behind nginx; use the TLS configuration for anything internet-facing (see
the [developer deployment guide](../dev/deployment.md)). There is no remote API
and no user authentication because there is no remote surface.

## Practical tips

- Keep your data directory on an encrypted disk if your material is sensitive.
- Use the **sync folder** backup option only with a location you trust.
- When using a cloud AI provider, remember that the content you send is subject
  to that provider's policy — this is why local models are a first-class option.
