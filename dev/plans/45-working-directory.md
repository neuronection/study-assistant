# Plan 45 — Working directory: user-visible, changeable data location (Settings → Data + setup wizard step)

User-requested (2026-08-28). The data directory (`app.db`, `blobs/`, `backups/`,
`cache/`, …) was env-only (`SA_DATA_DIR`) — invisible in the UI and unchangeable
without editing files. ADR-101.

## Goal

1. **Visible** — the effective working directory, its platform default, and whether a
   custom location is pending are readable from the UI.
2. **Changeable** — the user can point the app at a different directory (empty, or an
   existing Study Assistant data dir with `app.db`); the change is persisted in a
   launcher-independent pointer file and **applies on the next app restart** (SQLite +
   blob store bind at boot).
3. **Discoverable** — a wizard step (after Welcome) shows the default path with an
   optional change; Settings → Data gains the same editor as a card.

## Non-goals

- Live/runtime data-dir switching (no engine/blob-store re-binding while running).
- Automatic data migration/copy to the new location — moving existing data is the
  documented Settings → Data backup/restore flow (or point at a dir that already
  holds an `app.db`).
- Overriding the `SA_DATA_DIR` env/.env escape hatch — env stays the strongest
  layer; the pointer is consulted only when env is unset.

## Backend

- `core/working_dir.py`: pointer file (`<config_dir>/working-dir.txt`, single absolute
  path; missing/garbage → ignored). `core/config.py`: `_platform_config_base()`
  (APPDATA / `~/Library/Application Support` / `XDG_CONFIG_HOME`|`~/.config`) →
  `default_config_dir()`; new `Settings.config_dir` (`SA_CONFIG_DIR`, for tests and
  hermetic packaging); `data_dir` factory: pointer → `default_data_dir()` (env still
  wins via pydantic-settings).
- `api/config.py` (`/config/working-dir`): `GET` → `{path, default_path, custom,
  restart_pending}`; `POST /working-dir/validate` → `{valid, reason, exists, empty,
  has_app_db}` (reason codes: `relative_path`, `already_current`, `inside_current`,
  `contains_current`, `not_a_directory`, `not_writable`, `not_empty`, `invalid_path`;
  writability probed via a temp file, non-existent targets checked against their
  nearest existing ancestor); `PUT` → validate + write pointer +
  `{path, restart_required: true}`; `DELETE` → clear pointer.
- conftest `client` fixture passes `config_dir=tmp_path / "config"` (hermetic).

## Frontend

- `lib/api.ts`: `WorkingDirInfo`/`WorkingDirValidation` + 4 calls.
- `features/settings/WorkingDirEditor.tsx` — shared editor (path input, validate with
  reason feedback, Save enabled only for a validated changed path, Use-default,
  Reset-to-default, restart-pending banner with Undo). Mounted as a card in
  Settings → Data (top) and as wizard step 2.
- Wizard grows to 8 steps (`workingDir` between Welcome and Provider); the fresh-DB
  gate means a restart into a new empty dir re-opens the wizard naturally.
- i18n `settings.workingDir*` + `onboarding.workingDir*`.

## Tests

- Backend `test_working_dir.py`: fresh GET all-default; validation matrix (relative /
  already-current / inside-current / junk-dir not_empty / app.db dir valid / unwritable /
  creatable-through-ancestor); PUT writes pointer + GET reports custom+pending; same-as-current
  422; DELETE clears; boot resolution via `SA_CONFIG_DIR` pointer + `SA_DATA_DIR` precedence.
- Frontend: `WorkingDirEditor.test.tsx` (render, invalid feedback, save → pending banner,
  reset); wizard test updated for 8 steps + working-dir step.

## ADR-101 (append to 06-decisions-and-risks.md on merge-back)

| 101 | **Working directory = the app data directory, changeable in the UI via a config-dir pointer file that applies on restart; env `SA_DATA_DIR` stays the strongest layer; targets must be empty or existing SA data dirs — no automatic data copy (plan 45, user request 2026-08-28)** | The engine, blob store and backup scheduler bind paths at boot, so a runtime switch would mean re-binding every long-lived component mid-flight — restart-application is the honest contract, and the fresh-DB wizard gate makes a restart into an empty dir re-open onboarding naturally. Persistence lives in `<platform config dir>/StudyAssistant/working-dir.txt` (not inside the data dir it elects, not env) so it survives data resets and launcher env rewrites (the snap/XDG gotcha); `SA_DATA_DIR`/`.env` keeps precedence as the power-user escape hatch, and the UI shows whether a pending pointer differs from the running dir (`restart_pending`). Target policy (empty dir, or existing dir with `app.db`) keeps the switch safe without a data-copy operation; moving real data is the existing backup/restore flow, which is also the only path that carries a consistent snapshot. Alternatives rejected: live re-binding (unsafe, touches every `app.state` component); pointer inside the data dir (lost on reset, wrong when migrating off the default); auto-copy on switch (GB-scale long operation needing jobs/cancel UX for a one-time concern backup/restore already solves); config stored in the DB (the DB lives in the directory being elected — circular). |
