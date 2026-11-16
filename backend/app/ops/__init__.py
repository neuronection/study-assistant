"""Deployment ops (ADR-0062 v7 §3-§5, ADR-0064): the one-shot `migrate`
mode's orchestration and its guards.

`app.ops.migrations` - tri-state resolution (split/legacy/broken), owner-side
provisioning (roles, grants, default privileges, extensions), Alembic,
checkpoint schema, re-grant. Invoked by `docker/entrypoint.sh migrate`;
`create_app` never calls any of it.
"""
