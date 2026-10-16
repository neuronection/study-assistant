#!/usr/bin/env bash
# check-extensions-structure — the D24 structure probe (ADR-0040 / plan 32
# Phase 7; BLOCKING since the Phase 9 closeout). Findings print as WARN;
# pass --strict to fail on any finding — the family-convergence workflow
# runs this probe with --strict, so a finding fails CI. Ported from
# career's reference probe (plan 32 Phase 1) with study-scoped rules.
#
# Probes:
#  1 scoped engine code only in the subsystem home — the pre-D24 paths are
#    gone (app/search/, services/platform/mcp_servers.py,
#    api/mcp_servers.py, parsers/mcp_parse.py) while the content pipeline
#    keeps its home (app/parsers/ stays — core ingestion, D24 rule 1),
#    orchestration stays in services/ (the external-source scheduler) and
#    MCP client construction stays in ai/
#  2 no dynamic code loading under the subsystem home (D2's gate point:
#    imported artifacts are data, never importlib'd into the process) and
#    no sys.path mutation (data-dir content is spawned, never importable)
#  3 AI-layer MCP adapters stay in app/ai (ADR-0012 alignment gate R2):
#    fastmcp/mcp imports appear only under backend/app/ai/ — the same
#    CLASS_RE the vendored gate runs, so probe and gate never disagree
#  4 vendored family contract modules exist at their ledgered paths
#    (backend/app/extensions/{polite_http,contract,conformance}.py, the
#    contracts/ artifact set, and the ADR-0035 trio at
#    backend/app/extensions/search/) — drift vs the dev canonicals is the
#    dev repo's sync --check gates, not this probe
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STRICT=0
[[ "${1:-}" == "--strict" ]] && STRICT=1

findings=0
note() { echo "WARN: $1"; findings=$((findings + 1)); }
ok() { echo "ok:   $1"; }

# 1 — old paths gone, scoped homes in place
for gone in \
  "backend/app/search" \
  "backend/app/services/platform/mcp_servers.py" \
  "backend/app/api/mcp_servers.py" \
  "backend/app/parsers/mcp_parse.py"; do
  if [ -e "$ROOT/$gone" ]; then
    note "pre-D24 path still present: $gone (engine code lives in backend/app/extensions/)"
  else
    ok "pre-D24 path absent: $gone"
  fi
done
if [ -d "$ROOT/backend/app/parsers" ]; then
  ok "content pipeline keeps its home (app/parsers/ — core ingestion, D24 rule 1)"
else
  note "backend/app/parsers/ missing — it is core ingestion, not extension-shaped (D24 rule 1)"
fi
if [ -f "$ROOT/backend/app/services/platform/external_source_scheduler.py" ]; then
  ok "external-source scheduler stays in services/ (orchestration, rule 4)"
else
  note "services/platform/external_source_scheduler.py missing — sync orchestration belongs in services/ (D24 rule 4)"
fi
if [ -f "$ROOT/backend/app/ai/mcp_client.py" ]; then
  ok "AI-layer MCP client stays in ai/ (mcp_client.py, ADR-0012)"
else
  note "backend/app/ai/mcp_client.py missing — MCP client construction stays in ai/"
fi

# 2 — no dynamic code loading under the subsystem home (D2's gate point:
# imported artifacts are data, never importlib'd into the process).
# sys.path mutations are equally banned — landing data-dir content on
# sys.path would make the content-addressed clone importable, the exact
# hole D2 closes.
importlib_hits="$(grep -rn -E "importlib\.(import_module|machinery|util|reload)|SourceFileLoader|exec_module" "$ROOT/backend/app/extensions" 2>/dev/null | grep -v __pycache__ || true)"
if [ -n "$importlib_hits" ]; then
  note "importlib usage under app/extensions (imported code is never importlib'd — D2):"
  echo "$importlib_hits" | sed 's/^/      /'
else
  ok "no importlib under app/extensions (D2 gate point)"
fi
syspath_hits="$(grep -rn -E "sys\.path\.(append|insert)|PYTHONPATH" "$ROOT/backend/app/extensions" 2>/dev/null | grep -v __pycache__ || true)"
if [ -n "$syspath_hits" ]; then
  note "sys.path/PYTHONPATH mutation under app/extensions (data-dir content is spawned, never importable — D2):"
  echo "$syspath_hits" | sed 's/^/      /'
else
  ok "no sys.path mutation under app/extensions (imported content is data, never a module path)"
fi

# 3 — fastmcp/mcp imports only under backend/app/ai/ (same CLASS_RE as the
# vendored check-ai-alignment gate R2, so the two checks agree by construction)
mcp_hits="$(
  grep -rln -E 'from fastmcp[. ]import|from mcp[.](server|client|shared)[. ]import' "$ROOT/backend/app" 2>/dev/null \
  | grep -v __pycache__ | grep -v "^$ROOT/backend/app/ai/" || true)"
if [ -n "$mcp_hits" ]; then
  note "fastmcp/mcp imports outside app/ai/ (ADR-0012 alignment gate R2):"
  echo "$mcp_hits" | sed 's/^/      /'
else
  ok "fastmcp/mcp imports confined to app/ai/ (ADR-0012)"
fi

# 4 — vendored family contract set at ledgered paths
for vendored in \
  "backend/app/extensions/polite_http.py" \
  "backend/app/extensions/contract.py" \
  "backend/app/extensions/conformance.py" \
  "backend/app/extensions/search/providers_contract.py" \
  "backend/app/extensions/search/providers_contract.fixtures.json" \
  "backend/app/extensions/search/providers_catalog.json" \
  "contracts/extension-charter.json" \
  "contracts/extension-manifest.schema.json" \
  "contracts/extension-sources.schema.json" \
  "contracts/capability-rpc.schema.json" \
  "contracts/capability-rpc.md" \
  "contracts/extension-contract.fixtures.json" \
  "contracts/polite_http.fixtures.json"; do
  if [ -f "$ROOT/$vendored" ]; then
    ok "vendored: $vendored"
  else
    note "vendored contract module missing: $vendored (run ../dev/scripts/sync-extension-contract.sh --project study-assistant / sync-search-providers.sh)"
  fi
done

echo
if [ "$findings" -gt 0 ]; then
  echo "extensions structure: $findings finding(s)"
  if [ "$STRICT" -eq 1 ]; then
    exit 1
  fi
  echo "warning-level run (plan 32 Phase 9: CI invokes this probe --strict)"
  exit 0
fi
echo "extensions structure: OK"
