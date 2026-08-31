# Plan 44 — First-run setup wizard: providers → models → task defaults → first course → first files

User-requested (2026-08-28). A fresh install lands on an empty Today page with no
guidance; AI setup requires knowing three Settings tabs and their interdependencies
(provider → discovered models → capability defaults). ADR-100.

## Goal

1. **Auto-open on fresh install** — a full-screen wizard overlay appears on launch when
   the DB has no provider and no course (server truth), unless the user dismissed it
   (localStorage `ca-onboarding-done`).
2. **Core 7 steps, fully skippable** — Welcome → AI provider → Enable models →
   Capability defaults → First course → First files → Done. Every step has Skip;
   the whole wizard is re-openable from Settings → Providers (empty state), the Home
   onboarding card, and the header (X = skip-all).
3. **Reuse, don't fork** — the wizard orchestrates the same endpoints the Settings
   dialogs use (`POST /providers` auto-discover, `PATCH /models/{id}` enable,
   `PUT /tasks/defaults/{requires}`, `POST /courses`, `POST /onboarding/sample`,
   `POST /materials` via `useMaterialUpload` + `UploadDropzone`).

## Non-goals

- Appearance/theme step, profile renaming (later round if wanted).
- Forcing AI setup — the app is usable without it (notes/library work fine).
- A server-side "completed" flag — localStorage + server emptiness heuristics suffice.

## Backend

- `GET /api/v1/onboarding/state` → `{has_provider, has_enabled_model,
  defaults_set: [requires…], has_course, has_material}` — one round trip, the single
  server-side truth for the gate and the Done-step summary.

## Frontend

- `lib/api.ts`: `OnboardingState` + `getOnboardingState()`.
- `features/onboarding/wizardStore.ts` — zustand `{open, openWizard, closeWizard}`.
- `features/onboarding/OnboardingWizard.tsx` — gate (`['onboarding-state']` query +
  localStorage flag; error → never auto-open), full-screen overlay chrome (fixed
  inset-0, centered card, step dots, Back / Skip-all / Next footer), step state
  (`course: {id, title} | null` shared between CourseStep and FilesStep).
- Steps (`features/onboarding/steps/`): `WelcomeStep`, `ProviderStep` (preset/name/
  base_url/key — same fields as `ProviderFormDialog` create mode), `ModelsStep`
  (enable toggles over discovered models + Enable all), `DefaultsStep` (four
  capability selects over enabled+cap-matching models), `CourseStep` (create /
  load sample / skip), `FilesStep` (`UploadDropzone` + `useMaterialUpload` on the
  created course), `DoneStep` (summary from refetched state + open-course CTA).
- Mount `<OnboardingWizard />` in `AppShell`; buttons in ProvidersTab empty state +
  Home onboarding card call `openWizard()`.
- i18n: `onboarding.*` keys in `en.json`.

## Tests

- Backend: `test_onboarding_state.py` — fresh all-false; provider+model+defaults+
  course+material flip the flags.
- Frontend: `OnboardingWizard.test.tsx` — auto-open on fresh+not-dismissed; skip
  persists the flag and closes; no auto-open when providers exist; navigation
  welcome→provider→models; course create wires FilesStep; Done summary renders.

## ADR-100 (append to 06-decisions-and-risks.md on merge-back)

| 100 | **First-run wizard: server-truth gate (no provider AND no course), localStorage dismissal, fully skippable core-7 steps orchestrating the existing settings/upload endpoints; one aggregate `GET /onboarding/state` instead of client-side inference (plan 44, user request 2026-08-28)** | A fresh install should offer, not force: every step is skippable and the wizard never blocks (no route change — an overlay over AppShell; fetch error ⇒ never auto-open). The gate reads server truth in one query (`has_provider && has_course` both false = fresh) because localStorage alone cannot know a restored/second-browser DB; the `ca-onboarding-done` localStorage flag only encodes "user said skip" (same `ca-*` convention as profiles/course). Steps reuse the exact Settings/upload endpoints (no compound wizard API) so wizard and Settings can never drift; the only new surface is the read-only state aggregate. Uploads ride `useMaterialUpload` (junk filtering, nested folders, dedup) on the just-created course; ingest continues in the background like any upload. Alternatives rejected: a dedicated `/welcome` route (steals nav, harder to re-open mid-use); a server-side completion flag (per-profile state for what is a per-machine onboarding concern); duplicating provider-form logic in the wizard (drift with Settings); forcing AI config before continue (app is functional without it). |
