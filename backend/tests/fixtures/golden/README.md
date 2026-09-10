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
