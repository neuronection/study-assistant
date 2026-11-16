# Model pricing and call cost

Study Assistant resolves model prices through the family contract and records
the cost on the AI audit row at call time. This page covers the ledger fields,
the resolver and the Data & Cost surface.

## Contract

The vendored files are:

- `backend/app/ai/model_pricing.py` — pure stdlib reference resolver.
- `backend/app/ai/model_pricing_data.py` — generated `MODEL_PRICING_ROWS`,
  `MODEL_PRICING_COMPILED` and coverage exceptions.
- `backend/tests/fixtures/model-pricing.fixtures.json` — the cross-language
  fixture wall (also run by the desktop TS resolver).

Do not hand-edit them; change the family canonical and re-run
`scripts/sync-model-pricing.mjs`. Built-ins are standard-tier list prices;
unknown stays unpriced.

## Resolution

`resolve_price()` walks: explicit `ai_price_overrides` row → loopback/mDNS
zero → built-in → unknown. Within a class, exact/alias beats a
delimiter-aware prefix, then the resolved model before the requested model.
An override binds a preset key (`provider_key`) or a custom provider row
(`provider_ref`); a blank row applies only to non-local providers.

## Ledger

`ai_interactions` carries:

- `cost_micros` (nullable integer; null = unpriced),
- `usage_source` (`provider|estimated|partial|unknown`),
- `estimate_method` (for estimated token counts),
- `price_source` (`user|builtin|local|legacy|unknown`),
- `price_version` (contract row hash, override row identity, or
  `pre-contract` for migrated rows),
- `model_external_id` and `provider_key`.

The gateway resolves at write time. `GET /api/v1/analytics/costs` only sums
recorded micros; it never reprices historical calls. The old float
`cost_usd` and `models.cost_in/cost_out` columns were migrated once to
overrides and dropped.

## Budgets

`task_assignments.params.monthly_cap_micros` is the money cap (the API keeps
the USD-facing `monthly_cap_usd` field and converts at the boundary). Null-cost
rows count as zero in the cap, the same conservative undercount as before.

## Data & Cost

`frontend/src/features/settings/DataCostCard.tsx` lives on the Data tab and
reads `/analytics/costs` + `/ai/prices`. `PUT /api/v1/ai/prices` upserts an
override; `DELETE /api/v1/ai/prices/{id}` removes it. The editor is
deployment/owner scoped in this single-user product.

## Verification

```bash
cd backend && uv run pytest tests/test_budgets.py tests/test_cost_provenance_migration.py
cd frontend && pnpm typecheck
```
