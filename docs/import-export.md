# Quiz interchange format — `caq/v1`

`caq` is the single-file JSON format for sharing quizzes and for authoring them with
external AI assistants. Import runs through the **same validators as generated
quizzes** — external output is never trusted, validators decide.

(Companion formats: `qpkg` quiz packages, Anki `.apkg` decks, full-app
`ca-backup/v1` archives, and **course bundles `ca-course/v2`** — see the bottom
of this page.)

## Document

```jsonc
{
  "$schema": "caq/v1",
  "title": "Chain Rule — Practice Set",
  "questions": [ /* 1–50 question objects */ ]
}
```

## Question object

```jsonc
{
  "id": "q1",                          // optional, stable within file
  "type": "single",                    // single | multi | truefalse | text |
                                       // numeric | equation
  "stem_md": "Differentiate $f(x) = x^2\\sin x$",
  "options_md": ["$2x\\sin x$", "$2x\\cos x$", "$x^2\\cos x + 2x\\sin x$"],
  "answer": 2,                          // per type — see below
  "explanation_md": "Product rule: …",
  "concepts": ["chain rule", "product rule"],   // 1–3, required
  "skill": "procedural",               // conceptual | procedural | applied | notation
  "bloom": "apply",                    // remember … create
  "difficulty": 3,                     // 1–5
  "expected_time_sec": 120,
  "misconceptions": {"0": "forgot_product_rule"},  // option index → error tag
  "sympy_check": {"expected": "2*x*sin(x) + x**2*cos(x)"}
}
```

- **Markdown shorthand everywhere** (`stem_md`, `options_md`, `explanation_md`):
  GitHub-flavored markdown with `$…$`/`$$…$$` LaTeX and ```mermaid fences — what LLMs
  emit natively.
- **Answers per type** (shorthand accepted): `single` → `2` or `{"index": 2}` ·
  `multi` → `[0,2]` or `{"indices":[0,2]}` · `truefalse` → `true` · `text` →
  `"value"` (or `{"value": …, "accept": [alternatives]}`) · `numeric` → `3.14`
  (or `{"value":…, "tolerance":…, "relative":bool}`) · `equation` → LaTeX/sympy
  string.
- `options_md` required for single/multi (≥2 options). `sympy_check` optional but
  recommended for equation questions — grading uses it preferentially.

## Validation rules (dry-run shows these per question)

- Known type; non-empty stem; well-formed answer for the type (index in range, etc.)
- Explanation required; concepts required (1–3) — diagnostics depend on them
- skill ∈ 4 values; bloom ∈ 6 values; difficulty 1–5; expected_time > 0
- Equation distractors must not be equivalent to the answer (checked with the
  math equivalence chain)

Questions that fail are importable only flagged `review`; the preview marks them.

## API

```
POST /api/v1/quiz/import?dry_run=true|false   body: caq document
GET  /api/v1/quiz/activities/{id}/export      → .caq.json download
```

Planned (post-v1): `qpkg` zip tier with assets/checksums, watched inbox directory,
agent self-serve `schema.json`.

---

# Course bundles — `ca-course/v2` (plan 22 F → plan 50 A, ADR-050/ADR-109)

Whole-course sharing without personal data by default — a classmate (or
next-semester you) receives the *content*: materials with their extractions,
notes, tree, concepts, quizzes, exercises, **flashcards with their FSRS
schedules (v2)**, **exam date (v2)**, and **discovered error patterns (v2)**.
Attempts/answers and note version history stay behind explicit opt-in flags;
mistakes, analytics, chats and read-status **never travel** — that is what
`ca-backup/v1` (Settings → Data) is for. The exporter emits v2 only; the
importer accepts **v1 and v2** (v1 → v2 defaults: no card schedules, no exam
date, no history).

## Archive layout (zip)

| Entry | Contents |
|---|---|
| `manifest.json` | format, app version, created_at, course title, `options` (`include_history`/`include_note_versions`, v2), per-entity counts, `warnings` (see below) |
| `course.json` | course meta (title/subject/level/description/goals/tags/color + **`exam_date` v2**) |
| `tree.json` | nodes (parent/title/summary/objectives/ai_hint/order) — exactly one root |
| `concepts.json` | concepts + links + per-node coverage |
| `materials.json` | materials incl. latest extraction, index card, node links, provenance, `folder_path` (virtual-library location), **`drawings`** (plan 29/ADR-064 — strokes + OCR + `id` per material drawing; absent in pre-29 bundles, imports cleanly; `view` export-region metadata per 0046/ADR-098 — absent in pre-46 bundles, imports cleanly); v2 questions carry their `id` (for history remapping) |
| `folders.json` | library folders (path/name hierarchy) + folder-to-node assignments (`folder_links`, plan 25 — absent in pre-25 bundles, imports cleanly) |
| `notes.json` | notes incl. blocks (drawing refs) + drawings (strokes + OCR + optional `view`) |
| `quizzes.json` | activities + questions (full metadata taxonomy) |
| `exercises.json` | exercises (all kinds incl. `card_*`) + steps |
| `skills-overrides.json` | course-scope skill forks |
| `cards.json` (v2) | per-flashcard FSRS schedule (state/stability/difficulty/reps/lapses/due/last review) + **`reviews` (review log) only when `include_history`** — schedules travel by default, history is opt-in |
| `patterns.json` (v2) | **discovered** error patterns only (seeded/system rows are re-seeded, never exported) |
| `history.json` (v2, opt-in) | quiz attempts + answers, exercise sessions + step attempts, quiz help events — empty unless `include_history` |
| `note-versions.json` (v2, opt-in) | note version history — empty unless `include_note_versions` (current body always travels in `notes.json`) |
| `blobs/<sha256>` | every referenced original (content-addressed) |

**Degraded exports never fail**: if a referenced blob file is missing on disk
(e.g. deleted or lost after a partial restore), the export still succeeds — the
material/drawing travels without its original file (`blob_sha`/`png_sha`
nulled; extraction markdown and drawing strokes always travel) and
`manifest.warnings` records what was skipped; the import dry-run preview
surfaces those same warnings. Folder assignments of **linked-source folders**
are machine-local and never travel (a warning says so; their materials still
export, landing unfiled).

## Validation & import

`dry_run=true` returns a preview (title, counts, warnings — e.g. materials
without extraction). Commit always **imports as a new course** with full id
remapping: tree paths rebuilt natively via the tree service, concept ids
remapped into question tags, extractions written directly and re-chunked with
FTS rebuild (**no re-OCR**). **Material drawings** are recreated as new
rows and their `ca-drawing://{old}` refs are remapped to the fresh ids in both
the extraction markdown and blocks (their OCR joins the imported FTS). Title
collision → "… (imported)".

**v2 import is self-healing (ADR-109)**: every imported material with an
extraction gets a `postprocess` job (embeddings + index card) exactly like an
upload — imported courses no longer degrade to FTS-only search. The import
response carries `postprocess_job_ids`; progress rides the usual `jobs:{id}`
WS topic / activity rail. Card schedules land on the imported flashcards,
discovered error patterns are re-created for the imported course's course type
(existing keys are skipped), and history/note versions are written when the
bundle carries them. **Round-trip pin**: exporting an imported v2 course and
re-importing it on a fresh machine produces a byte-identical bundle
(manifest `created_at` excepted).

```
GET  /api/v1/courses/{id}/export[?include_history=true][&include_note_versions=true]
                                              → ca-course/v2 zip download (v2 only)
POST /api/v1/courses/import?dry_run=true|false  body: zip (v1 + v2) → {imported:{postprocess_job_ids}}
```

UI: Courses page — **Export** link on each course card, **Import course** with
dry-run preview → confirm → opens the imported workspace (postprocess progress
in the activity rail).

# Skill packs — `ca-skills/v1` (plan 50 B, ADR-110)

Custom skill prompts travel as plain JSON: **skill definitions (task/key/name/
description) + their full system-scope version history** (templates, params,
contracts, active flags). Course-type and course-scope overrides never travel
(they reference machine-local ids); skills contain prompts only — no secrets —
by construction.

## Pack shape

```json
{
  "format": "ca-skills/v1",
  "exported_at": "<iso>",
  "skills": [
    {
      "task": "chat",
      "key": "chat.answer",
      "name": "…", "description": "…", "is_system": false,
      "versions": [
        {"version": 1, "system_template": "…", "user_template": "…",
         "params": {…}, "contract": {…}, "is_active": true}
      ]
    }
  ]
}
```

## API

```
POST /api/v1/skills/export            {keys: [key…]}            → pack JSON
POST /api/v1/skills/packs/import?dry_run=true                  → staged preview
POST /api/v1/skills/packs/import?dry_run=false&resolutions={"key":"replace"|"rename"|"skip"}
```

**Preview** parses the pack and reports, per skill: version count, the packed
active version, whether the key already exists here (collision), and template
validation errors (the same jinja checks the editor enforces). **Commit** walks
the skills with the chosen collision resolution — `replace` appends the packed
versions as new versions on the existing skill (history preserved, the packed
active version wins activation), `rename` imports under a `-2`/`-3…` suffixed
key as a fresh user skill, `skip` (the default for collisions) leaves the local
skill untouched. Skills whose templates fail validation are skipped with the
reason; unknown tasks and malformed packs are rejected with 422.

UI: Settings → Skills — a per-row **Export** action downloads
`<key>.ca-skills.json`, and **Import pack…** opens the staged
file-picker → preview → commit dialog.
