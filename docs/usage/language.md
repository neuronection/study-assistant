# Language

The app ships in three languages: **English**, **Ελληνικά** (Greek) and
**Deutsch** (German).

## Changing the language

1. Open **Settings → General** (the first tab).
2. Pick a language from the searchable dropdown — type to filter (e.g. "ελλ"
   finds Ελληνικά). It applies **instantly** — the whole interface switches
   without a reload.
3. Your choice is stored on this device (browser/app window), not in your
   course data. On a shared machine, each user can run their own language.

The **first-run wizard's** welcome step offers the same language dropdown,
so a fresh install can start in your language before anything is set up.

Dates, times and numbers follow the chosen language: plan items show
"Σήμερα" for today in Greek, due cards format per locale, and percentages
and costs use the local separators (e.g. `85 %` in German).

## What stays English

- Brand and product names (Study Assistant, Neuronection, …).
- Technical protocol tokens you interact with directly: tool names in chat
  (`CALC`, `SYMPY`, `FIND`), `OCR`, `FSRS`, LaTeX and Mermaid syntax hints.
- Error detail messages are English machine codes; the UI text around them
  is translated.
- AI-generated content (lessons, quizzes, flashcards) follows the language
  of the AI model you configured — switching the UI language does not
  change what the model writes.

## Missing translations

If a string is missing in your language, it falls back to English. The
language picker only lists languages that are (nearly) fully translated, so
you should never see a mixed interface.
