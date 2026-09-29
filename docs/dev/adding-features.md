# Adding features

This page collects the end-to-end recipes for the common change types, in the
order you should do them. Each recipe names the files to touch, the tests to
add, and the docs to update in the same commit. Read
[development.md](development.md) for the setup and gate, and
[architecture.md](architecture.md) for where things live.

## Before you start

- Confirm the change is in scope for the current phase (`docs/STATUS.md`).
- Check whether the shared library already has the UI you need
  ([ui-conventions.md](ui-conventions.md)).
- Check whether the family guidelines already record a decision that constrains
  the change (the family `dev/guidelines/` and the repo's ADR register — the
  latter lives in the family dev repo's `projects/study-assistant/plans/`;
  there is no repo-root `dev/` anymore).

## A new API endpoint

1. Add the handler and its Pydantic DTOs to the right router in
   `backend/app/api/`, using the existing error conventions
   ([api.md](api.md)).
2. Put business logic in a service under `backend/app/services/<group>/` — the
   router should stay thin.
3. Wire a new router into `api/router.py` if needed.
4. Add a test with the `client` fixture ([testing.md](testing.md)).
5. Run `pnpm api:types` and commit `frontend/openapi.json` +
   `frontend/src/lib/api-schema.d.ts`.
6. Add the client function in `frontend/src/lib/api/<domain>.ts`.
7. Update [api.md](api.md) and `docs/STATUS.md`.

## A schema change

Follow [migrations.md](migrations.md): model-first in
`backend/app/domain/models/`, a `00NN` revision with a tested downgrade, bump
the three head-assertion tests, and add a "Migration notes" entry to
[data-model.md](data-model.md).

## A background job

Follow the recipe at the end of [jobs.md](jobs.md): a TypedDict payload, a
pipeline handler factory, registration in `main.py`, and enqueue via
`JobRunner.enqueue`. Add a retry/round-trip test.

## An AI task or behavior

Anything under `backend/app/ai/` follows the family AI rules (gateway-only
model access, validated structured output, HITL for writes). Steps:

1. Add the task definition and its capability requirements to the task registry
   in `backend/app/ai/tasks.py`; the provider/model UI picks it up.
2. Implement the call through the gateway; validate output with a contract.
3. Seed or update the relevant skill prompt under `backend/app/ai/skills/`
   (prompts are seeded from code; the DB is the live runtime source).
4. Add tests with a mocked transport; update [ai.md](ai.md) and
   `docs/STATUS.md`.

For chat proposals, follow the HITL contract described in [ai.md](ai.md) —
grounding, review cards, and approve-time revalidation are not optional.

## A new frontend page or feature

1. Create `frontend/src/features/<feature>/` with the components and hooks.
2. Add the route in `frontend/src/app/router.tsx`.
3. Fetch through `frontend/src/lib/api/<domain>.ts` (never `fetch` directly);
   hold client-only state in a small Zustand store in `lib/`.
4. Compose library components via `components/ui/*` shims; add every
   user-facing string as an i18next key and run `pnpm i18n`.
5. Add vitest tests; add a Playwright spec if the bug can only appear in a real
   browser ([testing.md](testing.md)).
6. Update the matching [user guide](../user/README.md) page and `docs/STATUS.md`.

## A new UI component for the library

If two or more family apps need it, it belongs in
`@neuronection/assistant-ui`, not here: propose the component upstream, release
it, then add a re-export shim under `components/ui/`. Single-app UI stays in the
app. See [ui-conventions.md](ui-conventions.md).

## A user-visible change

Every user-visible change adds a `## [Unreleased]` entry to
[`CHANGELOG.md`](https://github.com/neuronection/study-assistant/blob/main/CHANGELOG.md)
(CI-enforced) and updates the matching page under `docs/user/`. User guides
describe what the UI actually says — if they disagree, the interface wins and
the guide is a bug.

## The same-commit checklist

- [ ] Code + tests for the new behavior.
- [ ] `pnpm verify:backend` and `pnpm verify:frontend` green.
- [ ] `pnpm api:types` run if any endpoint changed (schema + types committed).
- [ ] `docs/STATUS.md` updated; the specific page from the table in the
      `sa-docs-sync` skill updated.
- [ ] `CHANGELOG.md` `## [Unreleased]` entry for user-visible changes.
- [ ] No secrets, no unverified claims, no new bare-string vocabularies.
