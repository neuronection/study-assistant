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

## Feature layout

```
frontend/src/
├── app/          router + providers
├── features/     home, library, courses, chat, quiz, practice, exercises,
│                 review, scores, planner, settings, onboarding, jobs,
│                 discovery, study-session, ai, about
├── components/   block renderers, widgets, editor, canvas, materials,
│                 layout (AppShell, FileDock), ui shims
└── lib/          api client, stores, i18n, constants, formatting
```

Feature folders own their components and hooks; `components/` holds renderers
and primitives shared across features. The block renderers (text+KaTeX, math,
mermaid, table, code, drawing, chart, geo) render the one structured content
format described in [architecture.md](architecture.md).

## i18n

The app uses `react-i18next` with catalogs in `frontend/src/locales/` (English,
Greek, German). English is the source catalog; every user-facing string is a
key. An ESLint rule errors on hardcoded strings and
`scripts/translations/check_translations.py` (run via `pnpm i18n`) gates
completeness. Locale formatting uses the platform `Intl` APIs rather than
translated formats.
