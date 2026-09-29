# Getting started

Study Assistant runs fully on your machine. Materials, extractions and study data live
in `~/.local/share/StudyAssistant/`; only AI calls (OCR, chat, quiz generation) go to
the providers you configure.

## Launch

Webapp mode (recommended) — the app opens in your default browser:

```bash
pnpm webapp
```

The backend serves the built app at `http://127.0.0.1:8200` (override the port with
`SA_PORT`). Press Ctrl+C in the terminal to stop it. Alternatively `pnpm dev` runs the
frontend with hot reload at `http://localhost:3200`, and `pnpm app` opens the desktop
window (pywebview) — currently not recommended, see the known-issues note in
`docs/STATUS.md`.

## First-run wizard

On a fresh install (no AI provider and no course yet) a setup wizard opens
automatically. It walks you through the same steps described below, in order:

1. **Working directory** — where your database, files and backups live. The default
   is fine for most people; change it only if you want your data elsewhere (e.g. a
   synced folder). A change applies the next time you start the app.
2. **AI provider** — pick a preset, name it, paste the API key (straight into your
   OS keyring). A successful create moves on by itself.
3. **Models** — enable the models the provider discovered; *Enable all* takes one
   click.
4. **Default models** — one default per capability (text / vision / embeddings /
   audio); optional, editable later in Settings → AI → Tasks.
5. **First course** — create your own, or load the ready-made *Calculus I (sample)*
   course.
6. **First materials** — drop PDFs/slides/Markdown onto the course; extraction and
   indexing continue in the background.

Every step can be skipped, and the wizard is never forced on you again — but you
can re-run it any time via **Run setup wizard** on the Home onboarding card or in
the empty state of Settings → AI → Providers.

## The sample course

*Calculus I (sample)* is a one-click demo of the full loop, loaded with real
content: three short Markdown chapters (derivatives, limits, integration — all
rendered with KaTeX), a **3-question sample quiz** (single choice, numeric with
deterministic grading, true/false), **6 flashcards in the FSRS queue — 2 already
due** so the Home review tile and the Practice tab light up honestly, a
**Derivatives concept** linked to the questions and the course root for the
diagnostics, and an **exam date two weeks out** so the countdown on Home has
something to count. Everything is editable or deletable like any other course.

## Connect an AI provider (required for AI features)

**Quick way — one-click setup tiles.** Open **Settings → AI → Providers** and press
**Add provider**: a dialog opens with a provider grid (OpenAI, Google Gemini,
OpenRouter, Anthropic, Groq, Mistral, DeepSeek, Ollama for a local setup, or
Custom for any OpenAI-compatible endpoint). Picking a tile shows that
provider's own key steps (each with a copy button) and, where one exists, the
free-tier note and a "get an API key" link. Paste the key and press **Set up
automatically** — the key is validated against the provider's real catalog
first (a rejected key stores nothing), a curated set of current models is
saved, and default chat/vision models plus a speech-to-text model (where the
provider offers one, e.g. OpenAI's whisper) are assigned automatically —
without overwriting any model you already assigned to a task. If none of the
curated ids match the provider's current catalog, the full catalog is saved
instead and the result tells you so (then pick defaults manually under
**Tasks**). If the key is mis-typed or belongs to a different vendor (e.g. an
OpenRouter key pasted for OpenAI), the error says so with a hint. **Advanced**
discloses the API base URL (fixed for providers that have one true endpoint),
the hosting option and the country — changing any of them saves through the
manual form, exactly like the **Custom** tile does (name, base URL, key,
hosting, country).

**Manual / advanced way.** Use **Add provider → Custom** for anything else
(e.g. LM Studio, llama.cpp, or a self-hosted OpenAI-compatible endpoint):1. Open **Settings → AI → Providers → Add provider** (settings tabs are URL-addressable —
   e.g. `/settings?tab=models` — so you can bookmark or share deep links).
2. Pick a provider from the dropdown (OpenAI, Google Gemini, OpenRouter,
   Anthropic, Groq, Mistral, DeepSeek, Ollama for a local setup, or Custom for
   any OpenAI-compatible endpoint — Custom needs a base
   URL). The choice sets the connection type; the name prefills but stays editable.
3. Paste your API key — it is stored in your **operating system's keyring**, never in
   the database or any file.
4. Press **Test** to check connectivity (the row shows Connected/Failed and the
   model count), then go to **Models**:
   - The list shows **your selected models** per provider. **Add model** opens the
     provider's *live* catalog inline: a searchable list (substring match, e.g.
     "vision" lists vision models), **capability filters** (text / image-vision /
     tools / embeddings / audio, plus *Unclassified*), **Add all N** for everything
     currently filtered, and **Add manually** for ids the catalog can't list. Every
     catalog row shows the *guessed* capabilities — click its chevron to open the
     draft panel and correct them (plus display name and reasoning effort) before
     adding.
   - Each model's **edit** (pencil) opens the same draft panel inline — rename it,
     correct its capabilities (OCR tasks only see vision-capable models), or set
     reasoning effort. The trash button removes it for good (with confirmation).
   - Existing providers can be renamed/re-keyed via their **edit** button.
   - Providers connected from a preset tile also show **Set up automatically**:
     re-run their setup anytime with the stored key — pick which curated models
     to save and which empty defaults (chat / vision / transcription) to fill.
     Whatever you already assigned is never touched.
5. Go to **Tasks**. Set one **default model** per capability (text / vision /
   embeddings / speech-to-text / text-to-speech) in the *Default models* section at the
   top — every task without a custom model uses its capability's default. To pin a
   specific model to a single task, pick
   it in that task's dropdown (it becomes an override; choose *— inherit default —* to
   go back). Notes:
   - **OCR** and **notes OCR** require a *vision-capable* model — the dropdown only
     offers those.
   - **Transcribe** (dictation) requires a speech-to-text model.
   - All other tasks (chat, quizgen, outline, description, tutor…) accept any model.
   - **Embeddings** enables semantic search; without it, search falls back to
     keyword-only (still fully functional).

Nothing is hardcoded to a specific vendor — Gemini is just one example provider.

## The study loop

1. **Library** — upload PDFs (text or scanned), photos, notes. Scanned pages and
   images are OCR'd into searchable markdown with proper math and diagrams. Organize
   into folders; fix OCR mistakes in the side-by-side editor — the search index
   updates immediately.
2. **Courses** — create a course, upload/assign materials to it, then press **AI
   outline** to draft a chapter/section structure from your material. Review the
   draft, delete what you don't want, commit. Allocate materials to sections manually
   or accept the AI's suggestions (shown with confidence).
3. **Quiz** — generate quizzes from your material (choose count). Answers are graded
   instantly and deterministically — typed math like `2x` vs `x*2` counts as correct.
4. **Exercises** — multi-step problems with a hint ladder that never reveals the
   answer (guaranteed by code, not promises).
5. **Tutor chat** — the sidebar chat answers questions grounded in *your* material,
   with citations back to the source documents.

## Where data lives

Everything is stored locally under `~/.local/share/StudyAssistant/` (or your
platform's equivalent): `app.db` (SQLite), `blobs/` (original files, content-addressed),
`cache/`, `backups/` (automatic backups land here — see [backup.md](backup.md)).
Delete the folder to reset the app — or use the built-in flag:

### Changing the working directory

The working directory is visible and changeable in **Settings → Data → Working
directory** (and in the setup wizard). Rules:

- The new folder must be **empty** or an **existing Study Assistant data folder**
  (contains `app.db`). To move existing data: download a backup first, switch,
  restart, then restore the backup into the new location.
- The change is stored in a small pointer file in your platform config dir
  (`~/.config/StudyAssistant/working-dir.txt` on Linux) and **applies on the next
  app start** — Settings shows a banner while a change is pending, with Undo.
- The `SA_DATA_DIR` environment variable (or `backend/.env`) always wins over the
  UI setting — it stays the power-user escape hatch.

```bash
pnpm dev --reset                # prompt before wiping db + blobs + cache + thumbnails + inbox
pnpm dev --reset --yes          # skip the confirmation
pnpm dev --reset --all --yes    # also delete backups/
```

`--reset` works the same on `pnpm webapp` and `pnpm app`. It resolves the exact
location from the `SA_DATA_DIR` environment variable, else `XDG_DATA_HOME`, else
`~/.local/share/StudyAssistant`. If an old `~/.local/share/CourseAssistant`
folder exists (pre-rename), it is renamed automatically on the next launch.
**API keys are not here** — they live in your
operating system's keyring, referenced by the provider rows in `app.db`.

> **Gotcha (VS Code snap / sandboxed terminals).** Some launchers rewrite
> `XDG_DATA_HOME` to a version-specific path — the VS Code snap, for example, uses
> `~/snap/code/<rev>/.local/share`. A snap update then points the app at a *new*
> folder, so your database (and with it every provider and its keyring link) appears
> to vanish; the API key itself is still safe in the keyring, but the provider no
> longer references it. If you run the app from such a terminal, pin a stable data
> dir by creating `backend/.env` with:
>
> ```ini
> SA_DATA_DIR=/home/<you>/.local/share/StudyAssistant
> ```
>
> The backend loads `backend/.env` automatically in both `pnpm dev` and `pnpm app`.
