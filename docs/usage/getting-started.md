# Getting started

Study Assistant runs fully on your machine. Materials, extractions and study data live
in `~/.local/share/StudyAssistant/`; only AI calls (OCR, chat, quiz generation) go to
the providers you configure.

## Launch

Webapp mode (recommended) — the app opens in your default browser:

```bash
pnpm webapp
```

The backend serves the built app at `http://127.0.0.1:8000` (override the port with
`SA_PORT`). Press Ctrl+C in the terminal to stop it. Alternatively `pnpm dev` runs the
frontend with hot reload at `http://localhost:5173`, and `pnpm app` opens the desktop
window (pywebview) — currently not recommended, see the known-issues note in
`docs/STATUS.md`.

## Connect an AI provider (required for AI features)

1. Open **Settings → Providers → Add provider** (settings tabs are URL-addressable —
   e.g. `/settings?tab=models` — so you can bookmark or share deep links).
2. Pick a provider from the dropdown (Google Gemini, OpenAI, Anthropic, Ollama for a
   local setup, or Custom for any OpenAI-compatible endpoint — Custom needs a base
   URL). The choice sets the connection type; the name prefills but stays editable.
3. Paste your API key — it is stored in your **operating system's keyring**, never in
   the database or any file.
4. Press **Test** to check connectivity, then go to **Models**:
   - The list shows **your selected models** per provider. **Add model** opens a
     searchable dialog over the provider's *live* catalog — type a few letters
     (fuzzy, out-of-order matching; caps count too, so "vision" lists vision
     models); long catalogs load more as you scroll. **Add all N** bulk-adds
     everything matching the current search (with a confirmation above 20).
     If listing fails (e.g. a missing/rejected API key — the error tells you
     which), fix the key via **Edit provider** or use **Add manually** and type
     the exact model id.
   - Bulk import: in the Add-model dialog, clear the search and press **Add all N**.
   - Each model's **edit** (pencil) button renames it and corrects its capabilities
     (text / image-vision / tools / embeddings) — OCR tasks only see vision-capable
     models. Unchecking *enabled* hides it from the list (re-add via Add model); the
     trash button removes it for good.
   - Existing providers can be renamed/re-keyed via their **edit** button.
5. Go to **Tasks**. Set one **default model** per capability (text / vision /
   embeddings) in the *Default models* section at the top — every task without a custom
   model uses its capability's default. To pin a specific model to a single task, pick
   it in that task's dropdown (it becomes an override; choose *— inherit default —* to
   go back). Notes:
   - **OCR** and **notes OCR** require a *vision-capable* model — the dropdown only
     offers those.
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
