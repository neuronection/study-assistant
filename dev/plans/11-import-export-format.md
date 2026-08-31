# 11 — Assessment Import/Export & External AI Authoring

Goals: users share quizzes/questions/assessments with each other; **external AIs**
(ChatGPT, Claude, Gemini web sessions, agents) can author quizzes as simple JSON that
drops into the app via UI upload, paste, or a watched directory.

Design leverage: import runs through the **same contract validators as quizgen** (doc 08)
and the **same metadata taxonomy** (doc 10) — an imported question is held to identical
standards as a generated one. No second quality path.

## Format: two tiers

### Tier 1 — `caq` (CourseAssistant Quiz): single JSON file, LLM-authorable

The interchange format external AIs produce directly. Human-readable, one file, no zip.

```jsonc
{
  "$schema": "caq/v1",
  "title": "Chain Rule — Practice Set",
  "description": "Procedural + applied chain rule drills",
  "course_type": "math",                  // optional; matches seeded course types
  "tags": ["calculus", "derivatives"],
  "questions": [
    {
      "id": "q1",                          // stable within file
      "type": "single",                    // any C1–C21 type
      "stem_md": "Differentiate $f(x) = x^2\\sin x$",
      "options_md": ["$2x\\sin x$", "$2x\\cos x$", "$x^2\\cos x + 2x\\sin x$"],
      "answer": 2,
      "explanation_md": "Product + chain rule: …",
      "concepts": ["chain rule", "product rule"],
      "skill": "procedural",
      "bloom": "apply",
      "difficulty": 3,
      "expected_time_sec": 120,
      "misconceptions": { "0": "forgot_product_rule", "1": "confused_sin_cos_derivative" },
      "sympy_check": { "expected": "2*x*sin(x) + x**2*cos(x)", "free_vars": ["x"] },
      "assets": { "fig1": "assets/fig1.png" }   // optional, tier-2 only or data-URI (≤256KB)
    }
  ]
}
```

Authoring ergonomics (what makes external-AI authoring actually easy):

- **Markdown shorthand everywhere** (`stem_md`, `options_md`, `explanation_md`): plain
  markdown with `$…$`/`$$…$$` LaTeX and ```mermaid fences — exactly what LLMs emit
  natively. The import normalizer parses these into blocks via the **same parser as OCR
  extractions**. Full block form (`"stem": [...]`) is also accepted for authors who want
  precision (charts, tables, geo blocks).
- **Minimal required fields**: `type`, stem, answer. Everything else is optional but
  warned about ("no concepts → this question won't appear in diagnostics").
- `sympy_check` optional; when present it is **verified on import** (expected parses,
  distractors not equivalent) — deterministic wrong answers get caught before any student
  sees them.
- Data-URI images allowed but capped (256KB total); bigger assets → use tier 2.
- `.caq.json` extension (plain `.json` also accepted).

### Tier 2 — `qpkg` (quiz package): zip for full-fidelity user-to-user sharing

```
my-quiz.qpkg  (zip)
  manifest.json      { "format": "caq-pkg", "version": 1, "generator": "CourseAssistant 1.2",
                       "items": [{"path": "quiz.json", "sha256": "..."}, ...] }
  quiz.json          caq/v1 document (questions inline or split)
  questions/*.json   (optional split form, referenced by id)
  assets/            images referenced by relative path
  license.txt        (optional — sharing terms)
```

- Checksums in manifest → integrity verified on import (corrupted/truncated transfer
  detected, not silently half-imported).
- Exports include all metadata, distractor-misconception maps, sympy_check, rubrics —
  a shared quiz behaves identically to a generated one.
- **Question-only export** (selection from bank) and **section/chapter assessment export**
  (multiple quizzes) use the same package layout (`quiz.json` lists them).

## Import pipeline (both tiers, one path)

```
source: UI paste | UI file upload | inbox directory | course-package import
→ parse + schema validate (JSON Schema, version check → migration if older format)
→ normalize (_md → blocks via extraction parser; answer per type; units/pint)
→ contract validation (same validators as quizgen P4):
    sympy checks, distractor equivalence, metadata completeness, block lint,
    image/asset integrity (tier 2: checksums)
→ concept mapping: concepts matched by name/alias (exact → fuzzy → embedding);
    unmapped offered as: create new concept | attach as plain tag | drop
→ dedup check vs existing bank (content hash + embedding similarity) → ask user
→ **Import preview UI**: per-question rows with validation status (ok / warnings /
    errors), accept-all-valid button, partial import allowed (invalid flagged `review`)
→ commit: questions enter bank flagged `imported` (+ provenance), quiz/activity created
  in chosen course/section
```

Nothing enters the bank unvalidated; nothing is silently dropped.

## Watched inbox directory

Reuses the linked-folder scanner (ADR-017 machinery) pointed at a dedicated import inbox:

```
<app-data>/inbox/        — or any user-configured folder
  *.caq.json / *.json / *.qpkg / *.apkg
```

- Periodic scan (default 5 min) + on startup + manual rescan; new files → staged import
  (jobs table, type `import`), processed files renamed `.imported`, invalid → `.rejected`
  + error report next to them (so an external tool can read the verdict).
- UI shows staged imports with preview before commit (unless "auto-accept valid" is on).
- This is the zero-friction path: an AI agent (or the user's other machine) drops a file
  in the folder and the app picks it up.

## External-AI authoring kit (the "AI writes my quiz" flow)

In-app **"Import → Author with AI"** helper:

1. **Schema card**: compact, copyable format spec (the caq/v1 subset + 2–3 examples).
2. **Prompt builder**: user picks topic/concepts, question count, types, difficulty —
   the app renders a ready-to-paste prompt containing the schema + constraints
   (LaTeX required for math, misconception map per distractor, `sympy_check` where
   possible). User pastes into any external AI, gets JSON back.
3. **Paste-back box**: paste JSON → same import pipeline with live validation preview.
4. A `schema.json` + `AUTHORING.md` also live at the inbox root so agentic tools can
   self-serve the spec from disk.

Round-trip safety: the external AI's output is *never trusted* — validators decide.

## API surface

```
POST   /api/v1/imports                    (body: file | pasted JSON; ?dry_run=true)
GET    /api/v1/imports/{id}               staged import + validation results
POST   /api/v1/imports/{id}/commit        { course_id, section_id?, concept_mapping }
DELETE /api/v1/imports/{id}
GET    /api/v1/exports/quiz/{id}          → .caq.json | .qpkg download
GET    /api/v1/exports/questions          → selection-based package
GET    /api/v1/imports/schema             → caq/v1 JSON Schema (for the authoring kit)
```

## Security

- Zip: bomb guard (entry count, uncompressed-size caps), path-traversal check on extract,
  asset mime whitelist, no executable content.
- JSON: schema depth/size limits; asset data-URI caps; LaTeX/Mermaid rendered through the
  same sanitizing renderers as internal content (no raw HTML passthrough anywhere).
- Provenance recorded (`imported_from`, generator string) — every imported question is
  traceable to its origin file.

## Schema additions (doc 03)

```
staged_imports   id, source (ui_upload | paste | inbox | course_pkg), path, format
                 (caq_v1 | qpkg_v1 | anki), status (staged | validated | committed |
                 rejected), validation(json), provenance(json), created_at
settings         inbox_path, inbox_auto_accept, inbox_scan_interval_sec
questions        + provenance(json: imported_from, generator, original_id)
```

## Roadmap placement

- **Phase 4** (quiz engine): caq/v1 single-file import (paste + upload) with contract
  validation & preview — cheap because validators already exist; `.caq.json` export.
- **Phase 7**: qpkg export/import with assets, watched inbox directory, external-AI
  authoring kit (prompt builder + schema card), Anki import consolidation under the same
  staged-import pipeline.
