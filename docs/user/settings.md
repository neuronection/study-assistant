# Settings reference

Settings has five top-level tabs — **General**, **AI**, **Search & OCR**,
**Data** and **Developer** — and every tab is URL-addressable, so you can
bookmark or share a deep link (for example `/settings?tab=ai&section=models`).
This page explains what each tab does. For the study features themselves, see
the [user guide overview](README.md).

## General

- **Language** — switch the interface between English, Ελληνικά and Deutsch;
  it applies instantly (see [Language](language.md)).
- **Reminders** — opt in to browser notifications for due reviews. The browser
  asks for permission the first time; if it is denied, the app says so and the
  in-app due badges keep working regardless.
- **Interface & features** — show or hide the optional navigation surfaces:
  the Home **Continue** card, the palette **Recent** section, the course
  **Jump back in** strip, and the resume meta on course cards. These are
  per-machine display preferences and apply immediately.

## AI

The AI tab has five sections: **Providers**, **Models**, **Tasks**, **Skills**
and **Integrations**.

### Providers

Where you connect AI providers. **Add provider** opens a guided setup:

- Pick a preset tile (OpenAI, Google Gemini, OpenRouter, Anthropic, Groq,
  Mistral, DeepSeek, Ollama) or **Custom** for any OpenAI-compatible endpoint.
- Paste the API key — it goes straight into your **operating system's
  keyring**, never the database or a file. **Set up automatically** validates
  the key against the provider's real catalog, saves a curated model set and
  assigns default chat/vision/speech-to-text models without overwriting
  anything you already set. A rejected or wrong-vendor key stores nothing and
  tells you why.
- Providers added from a preset keep a **Set up automatically** button so you
  can re-run setup later with the stored key.
- Existing providers can be renamed or re-keyed from their edit button.

Keys are shown masked (for example `••••1234`). See
[Local AI](local-ai.md) for a fully offline setup and
[Privacy and security](privacy-and-security.md) for where keys live.

### Models

Lists the models you have enabled per provider. **Add model** opens the
provider's live catalog inline: searchable, with capability filters (text,
vision, tools, embeddings, audio) and **Add all N**. Each catalog row shows
*guessed* capabilities that you can correct before adding. Use a model's edit
button to rename it, fix its capabilities or set reasoning effort; the trash
button removes it.

### Tasks

Set one **default model per capability** (text, vision, embeddings,
speech-to-text, text-to-speech) at the top; every task without a custom model
inherits its capability default. To pin a model to a single task, pick it in
that task's dropdown (it becomes an override). Notes:

- **OCR** and **notes OCR** require a vision-capable model — the dropdown only
  offers those.
- **Transcribe** requires a speech-to-text model.
- **Embeddings** enables semantic search; without it, search falls back to
  keyword-only and still works.
- A cost summary and per-task assignment info help you see what is inherited
  and what is overridden.

### Skills

The **prompt library**: every AI behavior (tutor hint ladder, quiz generation,
chat answer, flashcard authoring, …) is a skill — a prompt template plus a
behavior contract. Skills are seeded from the app and stored in the database;
the database is the live runtime source. You can edit a skill, inspect its
scope, view version history and run it in a sandbox to see the result before
saving. See [Skills & prompt library](skills.md).

### Integrations (MCP connectors)

Connect external MCP servers to bring their tools into discovery and import.
Servers are disabled until you refresh and enable individual tools; each tool
declares a contract (discovery or parse) and, for parse tools, a URL pattern.
Failures are recorded honestly on the row. See the
[feature catalog](features.md) for details.

## Search & OCR

- **Semantic search** — toggle embedding-backed search on or off. It requires
  the `embeddings` task to have a model assigned.
- **OCR image size** — the long-edge cap applied to images before a vision OCR
  call (smaller is cheaper/faster, larger keeps more detail).
- **Search provider** — configure the web search used by chat research and
  discovery (Tavily or a SearXNG instance); the key is stored in the keyring.
- **Web sources** — manage external web sources (RSS/Atom feeds, YouTube
  channels/playlists, site-filtered searches) that suggest new material.
- **Local engines** — detect and configure local AI engines such as Ollama or
  LM Studio.

## Data

- **Working directory** — where your database, blobs, cache and backups live.
  The change is stored in a pointer file and **applies on the next app start**;
  a banner shows while it is pending, with Undo. See
  [Getting started](getting-started.md#changing-the-working-directory).
- **Automatic backups** — enable/disable, set the interval, and set how many
  daily and weekly backups to keep. Optionally copy each backup to a sync
  folder for off-machine redundancy. You can also create a backup on demand,
  download one, or restore a stored backup. See [Backups, trash & restore](backup.md).
- **Export & import** — download a full archive, or restore from an uploaded
  one.
- **Trash** — deleted materials and topics sit here before they are purged;
  restore or empty as needed.

## Developer

Diagnostics and developer tools, including the WebKitGTK/rendering check used
to confirm the desktop shell's web engine works on this machine. Most people
never need this tab.
