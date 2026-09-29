"""Error-display helpers shared by the chat and job surfaces."""

from __future__ import annotations

import re

_MAX_DETAIL = 300

# Credential-shaped material that must never be persisted into transcript
# markers, job rows, or SSE error events (uniform chat error display).
_URL_CREDS = re.compile(r"(://)[^/\s:@]+:[^/\s@]+@")
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}")
_KEY_SHAPED = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9]{16,}|xox[abpos]-[A-Za-z0-9-]{8,}|AKIA[0-9A-Z]{8,})\b"
)
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\b")
_SECRET_ASSIGN = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|authorization|bearer)(\s*[=:]\s*)\S+"
)


def sanitize_error_detail(text: str, limit: int = _MAX_DETAIL) -> str:
    """Scrub credential-shaped material from an error string before it is
    persisted or rendered, then truncate to the display budget.

    Provider/connection errors can carry DSNs, bearer tokens, or API keys
    in their message — those must not land in the transcript marker rows,
    job errors, or the error card. The message stays useful for debugging
    (class name, HTTP status, provider wording) without the secrets.
    """
    scrubbed = _URL_CREDS.sub(r"\1***:***@", text)
    scrubbed = _BEARER.sub("Bearer ***", scrubbed)
    scrubbed = _KEY_SHAPED.sub("***", scrubbed)
    scrubbed = _JWT.sub("***", scrubbed)
    scrubbed = _SECRET_ASSIGN.sub(lambda m: f"{m.group(1)}{m.group(2)}***", scrubbed)
    return scrubbed[:limit]
