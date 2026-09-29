# Study Assistant — user guide

Study Assistant is a local-first, AI-powered study workbench. It ingests your
course material — PDFs, slides, images, notes, links — turns it into searchable,
structured content, and helps you learn it with quizzes, flashcards,
multi-step exercises and a tutor that answers from *your* material. It runs
entirely on your machine: one local process, one SQLite database, no account.
The only traffic that leaves is the AI calls you configure yourself.

New here? Read **[Getting started](getting-started.md)** first, then follow the
tour below. For the exhaustive list of everything the app does, see the
**[feature catalog](features.md)**. Developers and self-hosters should read the
[developer guide](../dev/README.md) instead.

## Guides

| Guide | What you will learn |
|---|---|
| [Getting started](getting-started.md) | Launch modes, the first-run wizard, connecting an AI provider, the study loop |
| [Feature catalog](features.md) | Everything, as built — the reference tour |
| [Courses and outlines](courses.md) | Course trees, AI outlines, the node workspace |
| [Exploring topics — the Scratchpad](exploring.md) | A private playground for ideas before they become a course |
| [Library: materials, folders, search](library.md) | Uploads, folders, OCR editing, search |
| [Linked folders and profiles](sources-and-profiles.md) | Watch a folder that keeps changing; multiple profiles |
| [Notes and handwriting](notes.md) | Markdown notes, LaTeX math, drawings, AI help |
| [Flashcards](flashcards.md) | FSRS spaced repetition fed by your material |
| [Quizzes](quiz.md) | Generate, take and import/export quizzes |
| [Exercises and the tutor](exercises.md) | Multi-step problems with a hint ladder |
| [Tutor chat](chat.md) | Grounded answers, citations, reviewable edit proposals |
| [Skills & prompt library](skills.md) | How the app's AI behaviors are defined and customized |
| [Local AI — fully offline setup](local-ai.md) | Run with local models, no cloud calls |
| [Today screen and progress](progress.md) | Streaks, goals, scores and diagnostics |
| [Task activity and retries](activity.md) | Background jobs, failures and retries |
| [Settings reference](settings.md) | Every settings page explained |
| [Language](language.md) | English, Ελληνικά, Deutsch |
| [Printing & PDF export](printing.md) | Print any view, math included |
| [Backups, trash & restore](backup.md) | Automatic backups, the trash, restoring |
| [Desktop app](desktop-app.md) | The native window and how it differs from the browser |
| [Privacy and security](privacy-and-security.md) | Where your data lives and how it is protected |
| [Troubleshooting](troubleshooting.md) | Common problems and fixes |
| [Visual tour](../SCREENSHOTS.md) | The screenshot gallery — every main screen, generated from the demo instance |

## The five-minute version

1. **Install** from the [Releases](https://github.com/neuronection/study-assistant/releases)
   page (Linux and Windows installers), or run from source (`pnpm webapp`).
2. **Connect an AI provider** in **Settings → AI → Providers** — pick a preset,
   paste the key (stored in your OS keyring), and let it set up models
   automatically. Any OpenAI-compatible endpoint works, including a local
   Ollama or LM Studio.
3. **Create a course** and drop in your material; extraction, OCR and indexing
   run in the background.
4. **Learn**: review due flashcards, take a generated quiz, work an exercise,
   or ask the tutor. **Study now** on Home chains whatever is due.
5. **Keep it safe**: backups are automatic, and deleted materials and topics
   sit in the trash before they are gone.

## Where to get help

- Bugs and feature requests:
  [GitHub Issues](https://github.com/neuronection/study-assistant/issues)
- Project status and known limitations:
  [STATUS.md](../STATUS.md)
- Developers and self-hosters: [developer guide](../dev/README.md)
