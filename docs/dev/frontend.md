# Frontend

The frontend is a single-page React 19 + TypeScript (strict) app built with
Vite and Tailwind 4. It talks to the backend over REST and WebSocket only, so
the same build runs inside the pywebview desktop window, in the browser during
development, and behind nginx in the Docker stack. This page covers routing,
state, the typed API client, the shared component library and i18n. Visual and
component conventions live in [ui-conventions.md](ui-conventions.md).

## Stack

| Concern | Choice |
|---|---|
| Framework | React 19 |
| Build | Vite 8, `vite build` |
| Language | TypeScript strict (`tsc --noEmit` in the gate) |
| Styling | Tailwind 4 + `@neuronection/assistant-ui` design tokens |
| Routing | TanStack Router |
| Server state | TanStack Query |
| Client state | Zustand |
| Editor / math / diagrams | Tiptap, KaTeX, MathLive, mermaid |
| Visualization | Plotly.js (charts), JSXGraph (geometry), lazy-loaded |
| Tests | vitest (jsdom) + Playwright e2e |

Dependencies are pinned in `frontend/package.json`; the app's own version
mirrors the root release version.

## Routing

All routes live in `frontend/src/app/router.tsx` (TanStack Router), wrapped by
an `AppShell` root. The main areas:

| Route | Page |
|---|---|
| `/` | Home (Today cockpit: Study now, recents, plan, stats) |
| `/review` | Cross-course review queue |
| `/study/session` | The guided Study-now flow |
| `/chat` | Tutor chat (sessions and proposals) |
| `/courses`, `/courses/$courseId` | Courses grid and course workspace |
| `/courses/$courseId/n/$nodeId` | Node workspace (Materials/Notes/Practice tabs) |
| `/library`, `/library/$materialId` | Library navigator and material detail |
| `/quiz/$activityId` | Quiz runner |
| `/exercises/$exerciseId` | Exercise player |
| `/note/$noteId` | Note editor focus page |
| `/scores` | Scores and analytics |
| `/jobs` | Background activity |
| `/settings` | Settings (providers, models, tasks, data, interface) |
| `/about` | About |

Legacy deep links (`/quiz`, `/exercises`, `/notes`, `/flashcards`,
`/courses/$courseId/chapters/$chapterId`) redirect to the current routes.

## Providers and state

`frontend/src/main.tsx` composes the app providers: TanStack Query (server
cache), the router, and `MotionConfig` with `reducedMotion="user"`. Query keys
are stable and shared — for example course trees use `['tree', String(id)]` so
the sidebar, palette and recents resolve titles from one cache.

Client-only state uses small Zustand stores in `frontend/src/lib/` (chat store,
dock geometry, interface preferences, recents, capture, review nudges, focus
timer). Prefer a store over prop-drilling for cross-cutting UI state; keep
server data in Query.

## The typed API client

`frontend/src/lib/api/` is the only place the app talks to the backend. It is
split by domain (`materials.ts`, `courses.ts`, `chat.ts`, `quiz.ts`,
`exercises.ts`, `notes.ts`, `flashcards.ts`, `analytics.ts`, `jobs.ts`,
`settings.ts`, `system.ts`, `ai.ts`, `sources.ts`, `folders.ts`) over a shared
client core that handles base URL, errors and the profile header.

Request and response types come from the generated schema:

- `frontend/openapi.json` — exported from the FastAPI app by
  `scripts/export-openapi.py`.
- `frontend/src/lib/api-schema.d.ts` — produced from it by `openapi-typescript`.

Regenerate with `pnpm api:types` after any endpoint change and commit both
files; CI drift-guards them. Hand-write types only for client-side-only shapes.
Entity ids are opaque strings end to end — the generated schema is the wire
truth (`PlanItem.id`, `course_id`, `job_id`, … are `string`); never coerce them
with `Number(...)` or parse them. Client-local numeric ids (exercise-ordering
position ids, pending-drawing placeholder refs) are the only exceptions,
registered in `frontend/src/lib/api/hand-types.ts`; DOM pointer ids are not API
shapes.
The WebSocket client lives in `lib/` and subscribes to the same topics the
backend publishes (see [api.md](api.md) and [jobs.md](jobs.md)).

## Shared UI library

`@neuronection/assistant-ui` is the family's first-party React component
library. `frontend/src/components/ui/*` are re-export **shims** — import paths
with an exit hatch — not local copies. Check the library first; if its API does
not fit, propose the change upstream and adopt the new release rather than
re-implementing locally. Styling uses `--as-*` tokens and `data-as-*`
attributes; app identity (brand colors, fonts) lives in
`frontend/src/theme.css`.

**No app file may shadow a library export** (plan 82 A, ADR-202): the library's
`audit-usage.mjs` scans `frontend/src` for filenames matching a library
component and fails on a local copy that does not import from
`@neuronection/assistant-ui`. Mermaid diagrams render through the library
`MermaidDiagram` (`components/ui/chat-markdown.ts`); `normalizeMathFences`
stays app-side in `components/editor/markdownFidelity.ts`, and the editor node
view (`CaMermaid`) owns its own diagnostic via `validateMermaidSource` (the
library renderer is presentational). App **hosts** that compose library chat
surfaces carry a `Study` prefix (`features/chat/StudyChatPanel.tsx`,
`StudyChatSessionList.tsx`) precisely so the detector keeps firing only on real
copies.

`vite.config.ts` sets `test.server.deps.inline: ['@neuronection/assistant-ui']`
so vitest transforms the library graph: without it, `vi.mock('mermaid')` and
friends cannot intercept dynamic imports made inside a published library chunk
(the renderer ran for real in jsdom and every mermaid test timed out).

## Feature layout

```
frontend/src/
├── app/          router + providers
├── features/     home, library, courses, chat, quiz, practice, exercises,
│                 review, scores, planner, settings, onboarding, jobs,
│                 discovery, study-session, ai, about
│   └── courses/workspace/   NodeWorkspace tab components (MaterialsTab,
│                            OverviewTab, NotesTab, CoverageTab, TutorTab,
│                            tabs.ts, navigation.ts, shared.tsx)
├── components/   block renderers, widgets, editor, canvas, materials,
│                 layout (AppShell, FileDock), ui shims
└── lib/          api client, stores, i18n, constants, formatting
```

Feature folders own their components and hooks; `components/` holds renderers
and primitives shared across features. The block renderers (text+KaTeX, math,
mermaid, table, code, drawing, chart, geo) render the one structured content
format described in [architecture.md](architecture.md).

## Lazy loading

Heavy renderers never sit in the initial route chunk. The rule (plan 84 D,
ADR-210) is **the component wrapper may be static; the heavy library must be
dynamically imported at the point of use**:

- **Plotly** (`plotly.js-dist-min`), **JSXGraph**, **mermaid** (via the library
  `MermaidDiagram`), **markmap** and **MathLive** already load through
  `import(...)` inside their renderer components.
- **Pyodide** (the 9.6 MB Python runtime behind code questions) is imported
  only when a code answer runs (`CodeAnswer` → `import('@/lib/pyodideRunner')`).
  Note: a type-only import written as `import { type X } from '…'` is still a
  static import to the bundler and defeats the split — use `import type { X }`
  (`vite build` warns `INEFFECTIVE_DYNAMIC_IMPORT` when this regresses).
- Add `manualChunks`/`codeSplitting.groups` only when a lazy seam leaves a
  bloated vendor chunk; the current groups are `react-vendor`,
  `framer-motion` and `katex`.

**Test suite split:** `NodeWorkspace`'s colocated block is split 1:1 into
`features/courses/workspace/__tests__/*` over one shared `harness.tsx`; each
file runs in its own vitest worker (`pnpm vitest workspace/__tests__/MaterialsTab`).

## i18n

The app uses `react-i18next` with catalogs in `frontend/src/locales/` (English,
Greek, German). English is the source catalog; every user-facing string is a
key. An ESLint rule errors on hardcoded strings and
`scripts/translations/check_translations.py` (run via `pnpm i18n`) gates
completeness. Locale formatting uses the platform `Intl` APIs rather than
translated formats.
