# Demo tour captures

How the README GIF, the screenshot gallery (`docs/SCREENSHOTS.md`) and
`docs/images/tour.manifest.json` are regenerated for Study Assistant —
the reproducible demo presentation embedded in the README, the docs and
the Neuronection website. The pipeline lives in `scripts/ui-capture/`
(family-standard vendored runner + this repo's config and scene catalog);
anyone can regenerate the exact same assets from a seeded demo instance.

## The demo instance

Captures always run against a demo instance: synthetic students, courses
and material seeded by `scripts/seed-demo.py` into an isolated demo data
dir, served by the backend itself in webapp mode (single origin, so no
separate dev server). Demo login: `ava.lindqvist@demo.study.local` /
`DemoStudy!2026` (all demo users share the password).

## Regenerating the tour

Two terminals:

```bash
# 1. seed the demo workspace (creates dev/demo-data/study.sqlite3)
bash scripts/ui-capture/seed-demo.sh

# 2. serve the app on :8200 — server identity (login UI) on the demo dir
SA_IDENTITY_MODE=server SA_DATA_DIR="$PWD/dev/demo-data" ./scripts/webapp.sh

# 3. capture: seed check → screenshots → gallery → manifest → GIF
./scripts/capture_ui.sh
```

Single scene / strict mode / gallery-only rebuilds:

```bash
./scripts/capture_ui.sh --scene today
./scripts/capture_ui.sh --viewport mobile
./scripts/capture_ui.sh --strict
./scripts/capture_ui.sh --gallery-only
```

Recommended system tools (otherwise the GIF step is skipped and PNGs stay
large): `pngquant`, `gifsicle`, `ffmpeg`.

## What gets committed

- `docs/images/*.png` + `docs/images/visual-tour.gif` +
  `docs/images/tour.manifest.json` — all generated, all committed.
- `docs/SCREENSHOTS.md` (+ `SCREENSHOTS.MOBILE.md` when mobile is
  captured) — the generated gallery, registered in `docs/docs-tree.json`.
- Scenes live in `scripts/ui-capture/scenes.mjs`: add a page = add an
  object; per-scene `narration` lines feed the future AI-video tour.

## After the first capture (one-time wiring)

1. Register the gallery in `docs/docs-tree.json` — a "Visual Tour" item
   (`file: "SCREENSHOTS.md"`) in the user guide's *Start here* category,
   and mirror it in `docs/user/README.md`.
2. Embed the GIF in `README.md` under the header badges:

   ```html
   <a href="docs/SCREENSHOTS.md"><img src="docs/images/visual-tour.gif" width="800" alt="Study Assistant visual tour"></a>
   ```

Recapture on every release and whenever the UI changes visibly —
screenshots are documentation and follow the same-commit rule.
