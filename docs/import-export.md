# Quiz interchange format — `caq/v1`

`caq` is the single-file JSON format for sharing quizzes and for authoring them with
external AI assistants. Import runs through the **same validators as generated
quizzes** — external output is never trusted, validators decide.

(Companion formats: `qpkg` quiz packages, Anki `.apkg` decks, full-app
`ca-backup/v1` archives, and **course bundles `ca-course/v1`** — see the bottom
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

# Course bundles — `ca-course/v1` (plan 22 F, ADR-050)

Whole-course sharing without personal data — a classmate (or next-semester you)
receives the *content*: materials with their extractions, notes, tree, concepts,
quizzes, exercises. Everything practice-related and personal (attempts, answers,
mistakes, analytics, chats, scheduling state, read-status) **never travels** —
that is what `ca-backup/v1` (Settings → Data) is for.

## Archive layout (zip)

| Entry | Contents |
|---|---|
| `manifest.json` | format, app version, created_at, course title, per-entity counts, `warnings` (see below) |
| `course.json` | course meta (title/subject/level/description/goals/tags/color) |
| `tree.json` | nodes (parent/title/summary/objectives/ai_hint/order) — exactly one root |
| `concepts.json` | concepts + links + per-node coverage |
| `materials.json` | materials incl. latest extraction, index card, node links, provenance, `folder_path` (virtual-library location), **`drawings`** (plan 29/ADR-064 — strokes + OCR + `id` per material drawing; absent in pre-29 bundles, imports cleanly; `view` export-region metadata per 0046/ADR-098 — absent in pre-46 bundles, imports cleanly) |
| `folders.json` | library folders (path/name hierarchy) + folder-to-node assignments (`folder_links`, plan 25 — absent in pre-25 bundles, imports cleanly) |
| `notes.json` | notes incl. blocks (drawing refs) + drawings (strokes + OCR + optional `view`) |
| `quizzes.json` | activities + questions (full metadata taxonomy) |
| `exercises.json` | exercises (all kinds incl. `card_*`) + steps |
| `skills-overrides.json` | course-scope skill forks |
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
FTS rebuild (**no re-OCR, no jobs**). **Material drawings** are recreated as new
rows and their `ca-drawing://{old}` refs are remapped to the fresh ids in both
the extraction markdown and blocks (their OCR joins the imported FTS). Title
collision → "… (imported)".

```
GET  /api/v1/courses/{id}/export              → ca-course/v1 zip download
POST /api/v1/courses/import?dry_run=true|false  body: zip
```

UI: Courses page — **Export** link on each course card, **Import course** with
dry-run preview → confirm → opens the imported workspace.
