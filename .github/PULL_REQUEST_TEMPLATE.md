## Summary

What changes and why (link the plan/issue if one exists).

## Verification

- [ ] Backend: `ruff check . && mypy . && pytest` green
- [ ] Frontend: `pnpm lint && pnpm typecheck && pnpm test && pnpm build` green
- [ ] `pnpm e2e` green (if the change touches a user flow)
- [ ] Golden evals green (`pytest tests/evals/`, if pipelines changed)

## Docs duty

- [ ] `docs/STATUS.md` updated (same commit)
- [ ] Affected docs updated (architecture / features / ai / data-model /
      import-export / usage guides)
- [ ] CHANGELOG updated if this is a release-relevant change
