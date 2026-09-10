# Study Assistant documentation

Complete documentation for the as-built application. `docs/STATUS.md` is the single
source of truth for what exists; these pages describe how it works and how to use it.

| Page | Contents |
|---|---|
| [STATUS.md](STATUS.md) | Current phase, module-by-module status, changelog, open issues |
| [architecture.md](architecture.md) | System architecture: process, backend, frontend, storage, jobs, events |
| [features.md](features.md) | Feature catalog — what exists today, mapped to the product plan |
| [ai.md](ai.md) | AI layer: providers, models, task routing, OCR, chat RAG, tutor, audit |
| [math-verification.md](math-verification.md) | The math trust layer: equivalence chain + hint-leak guard |
| [data-model.md](data-model.md) | SQLite schema as built (tables, indexes, derived structures) |
| [import-export.md](import-export.md) | `caq/v1` quiz interchange format specification |
| [usage/](usage/) | End-user guides, one per feature area |

Developer-only material (plans, roadmap, ADRs, risk register) lives in `dev/` and is
**gitignored — local-only**.
