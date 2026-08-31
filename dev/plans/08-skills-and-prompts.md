# 08 — Skills, Behavior Contracts & Prompt System

Users author and customize AI behavior through the UI. Three concepts:

1. **Task** — a fixed pipeline step (`tutor.hint`, `quiz.generate`, `chat.answer`, …; the
   list from doc 04).
2. **Skill** — a named behavior binding for a task: prompt templates + params + output
   schema + a **behavior contract**. Seeded in code ("system skills"), editable in the UI.
3. **Behavior contract** — machine-checkable constraints per skill, enforced by
   deterministic validators on every generation. Violations trigger a repair loop, never
   reach the user silently.

```
resolve(task, course) → skill (system → course-type → course, most specific wins)
→ render prompt (Jinja2, whitelisted context vars)
→ LLM structured output
→ contract.validate(output, context)          ← deterministic, per constraint
   ├─ pass → emit
   └─ fail → repair (regenerate with violation feedback, max 2) → flag
→ persist + log skill_version_id in ai_interactions
```

## Behavior contracts (the "hint button must not tell the result" guarantee)

Contracts are declarative constraint lists per skill; each constraint maps to a validator
(deterministic first, LLM-judge only where unavoidable, marked as such).

Example — `tutor.hint`:

```jsonc
{
  "constraints": [
    {"kind": "hint_level_exact",  "level": "{{hint_level}}"},     // only the requested ladder level
    {"kind": "no_answer_reveal",  "answer_ref": "expected"},     // NEVER the final answer
    {"kind": "no_full_solution"},                                 // unless level 5
    {"kind": "max_blocks", "n": 3},
    {"kind": "max_words", "n": 90}
  ]
}
```

`no_answer_reveal` validator (deterministic): extract every math expression and number
from the generated hint → check **none is equivalent to the expected answer** via the doc-04
equivalence chain (SymPy simplify → numeric sampling → solveset) plus normalized string
check for numerals. If the hint contains `x²·cos(x²)` and so does the answer — violation,
regenerate. This is the hard guarantee that the hint button only hints.

Other seeded contracts:

| Skill | Key constraints (deterministic unless noted) |
|---|---|
| `quiz.generate` | exact count & type mix per blueprint; distractors NOT answer-equivalent (SymPy); every question cites ≥1 chunk; dedup vs bank (embedding τ) |
| `quiz.explain_wrong` | must reference the chosen distractor; no_answer_reveal does NOT apply (post-answer) but "answer first, then why" shape enforced |
| `chat.answer` | claims about material carry citations; uncited claims get the "not from your material" marker (LLM-judge, spot-checked) |
| `chat.quiz_context` | wraps `chat.answer` when an **open quiz/exercise attempt** is in context: full `no_answer_reveal` (deterministic, equivalence chain) against that attempt's expected answer; lifts automatically on submit |
| `tutor.socratic` | output must be a question (ends with `?` heuristic + LLM-judge); no_answer_reveal |
| `tutor.worked_solution` | each stated equality passes step-equivalence check (SymPy); level-5 gate honored |
| `quiz.help_hint` | identical contract family to `tutor.hint` (no_answer_reveal, exact level, length); additionally **exam-mode refusal**: API rejects the call when the parent attempt is in exam mode regardless of prompt content |
| `notes.cleanup` / `notes.summarize` | no new claims beyond source (LLM-judge); length bounds |
| `flashcards.generate` | atomic (one fact/card); cloze gap count = 1; dedup |
| `grade.freeform` | verdict ∈ {correct, partial, incorrect}; rationale cites rubric rows |
| `ocr.page` | schema lint: LaTeX parses, Mermaid parses, reading order monotonic |

## Prompt authoring UI

**Settings → Skills tab** (4th tab, after Tasks): task list with active skill + resolution
chain badge; **full editor opens a workspace page**:

- **Template editor**: system + user templates (Jinja2), context-variable sidebar with
  types & docs (`{{hint_level}}`, `{{section.objectives}}`, `{{retrieved_chunks}}`…),
  syntax highlighting, insert-variable buttons.
- **Live preview**: renders the prompt against a chosen real section/material/exercise.
- **Test-run sandbox**: execute the skill on real context → output + **validator results
  (pass/fail per constraint)** + tokens/cost. No silent breakage: a template that fails
  its own contract shows it immediately.
- **Contract panel**: constraint list; safe subset editable in UI (levels, lengths,
  toggles); adding novel constraint kinds is code-only (validators are code by design).
- **Versions**: every save = new version; diff view, rollback, "restore system default".
- **Scope picker**: save as System default / Course type / This course; effective-resolution
  preview shows which scope wins and why.
- **Share**: export/import skill pack (JSON: template + contract + params + version).

## Skill scoping & course types

`course_type` is a first-class concept (seeded: `math`, `science`, `language`,
`programming`, `generic`; user-definable). Courses reference one. Resolution:

```
course override  >  course-type skill  >  system default (code-seeded)
```

Example: `math` course type ships `tutor.hint` biased to Socratic nudges + LaTeX-heavy
constraints; a `history` course type ships a variant with date/name precision constraints.
Same app, same contracts engine, different pedagogy.

## Schema additions (doc 03)

```
skills          id, task, key ("tutor.hint"), name, description, is_system
skill_versions  id, skill_id, scope_type (system | course_type | course), scope_ref,
                version, system_template, user_template, params(json),
                contract(json), is_active, created_at
                UNIQUE(skill_id, scope_type, scope_ref, version)
course_types    id, key, name, description (seeded, user-extensible)
courses.course_type_id  FK nullable
ai_interactions.skill_version_id  FK   (replaces free-text prompt_version)
```

## Engineering notes

- System skills are **seeded idempotently from code** (`app/ai/skills/`) into the DB on
  startup; user edits fork into new versions — code remains the reset point, DB is the
  live source at runtime.
- Contract validators live in `app/ai/contracts/` (pure functions: output × context →
  violations); one registry keyed by constraint kind; the same validators run in pipeline
  tests and in the sandbox UI.
- Templates render server-side only; UI preview uses the same renderer (no drift).
- `skill_version_id` on every `ai_interactions` row keeps full reproducibility: which
  prompt, which contract, which model, what result.
