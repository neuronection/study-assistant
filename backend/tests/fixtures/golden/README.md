# Golden OCR fixtures

Real evaluation fixtures for the OCR/quizgen/grading golden sets (plan 04, ADR-019).

**These must be the author's real material, not synthetic samples** — real scans share
failure modes (skew, bleed-through, marginalia, messy handwriting) that synthetic ones
don't reproduce.

Collect and commit here:

- `pages/` — ~20 real scanned math pages (mixed: clean print, degraded print, diagrams)
- `handwriting/` — ~10 worst-case handwriting photos (whiteboards, notebook shots)
- `expected/` — hand-corrected expected extractions (markdown + LaTeX), one per fixture,
  same filename with `.md` extension

Naming: `pages/scan-<nn>-<short-desc>.png`, `handwriting/hw-<nn>-<short-desc>.jpg`.

The eval suite that consumes these (`tests/evals/`) lands in Phase 1; thresholds are
defined in plan 04 ("Prompt & evaluation governance"). Until then this directory records
the collection obligation.

**Plan 84 C (2026-10-22):** the gate now exists — `tests/evals/test_ocr_golden.py`
scores per-page routing, native PDF extraction and hybrid assembly against
`tests/evals/ocr_thresholds.json` (block structure, math-fence integrity, numeric
fidelity). Files here are picked up automatically; each fixture needs a matching
`expected/<same-stem>.md`, and a test asserts that once the first real scan lands.
The default run is deterministic (no live OCR); the vision half is opt-in with
`SA_EVAL_LIVE=1`. Three synthetic fixtures exercise the mechanics in the meantime.
