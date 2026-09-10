# Security Policy

## Supported scope

Study Assistant is a **local-first desktop/web application**. The supported
security scope is:

- the local FastAPI process and its API (bound to `127.0.0.1` by default),
- the SQLite database, blob store, and backup archives on disk,
- the OS keyring integration (API keys are stored via the system keyring,
  never in files, environment blocks, or the database),
- the desktop shell (pywebview/WebKitGTK) and the served SPA,
- the AI provider integrations (keys are sent only to the provider base URLs
  you configure).

Out of scope by design: multi-tenancy, server deployments, and accounts — the
app has none. Anything that requires exposing the service beyond localhost is
a deployment concern of the operator, not a supported configuration.

## Reporting a vulnerability

Please report security issues privately rather than opening a public issue:

- **Email**: constliakos@gmail.com (put "study-assistant security" in the subject), or
- **GitHub Security Advisory**: use "Report a vulnerability" on the
  [Security tab](https://github.com/neuronection/study-assistant/security/advisories/new).

Include a description, the affected version (`python -m studyassistant` prints
it; also in Settings → About), and reproduction steps. You will get an
acknowledgement within a few days and a fix timeline once the issue is
triaged. Fixes land as patch releases; reporters are credited in the release
notes unless they prefer otherwise.

## AI-specific notes

The AI trust boundary is documented in the repository: model output is
untrusted input. Deterministic validators (math equivalence chain, prompt
contracts, import validators) gate everything the model produces before it can
affect grading, storage, or tool execution. Reportable issues include any path
where model output reaches deterministic grading, the tool sandbox, or file
exports without passing those gates.
