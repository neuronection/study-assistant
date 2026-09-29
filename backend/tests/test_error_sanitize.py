"""Error-detail sanitization (uniform chat error display).

Credential-shaped material must never reach transcript markers, job
rows, or SSE error events.
"""

from app.core.errors import sanitize_error_detail


def test_scrubs_url_credentials() -> None:
    assert (
        sanitize_error_detail("could not connect to postgres://admin:hunter2@db:5432/x")
        == "could not connect to postgres://***:***@db:5432/x"
    )


def test_scrubs_bearer_and_api_keys() -> None:
    assert "sk-abc123XYZ_secret" not in sanitize_error_detail(
        "provider rejected key sk-abc123XYZ_secret with 401"
    )
    assert "hunter2token" not in sanitize_error_detail("Authorization: Bearer hunter2token")


def test_scrubs_secret_assignments() -> None:
    scrubbed = sanitize_error_detail("login failed for password=hunter2 user=bob")
    assert "hunter2" not in scrubbed
    assert "bob" in scrubbed


def test_scrubs_jwt_shaped_tokens() -> None:
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdefghijklmnop"
    assert jwt not in sanitize_error_detail(f"stale token {jwt} rejected")


def test_keeps_useful_debug_text() -> None:
    detail = sanitize_error_detail(
        "provider request for model 'fake-native' failed: HTTP 500 service unavailable"
    )
    assert detail == (
        "provider request for model 'fake-native' failed: HTTP 500 service unavailable"
    )


def test_truncates_to_budget() -> None:
    assert len(sanitize_error_detail("x" * 5000)) == 300
    assert len(sanitize_error_detail("y" * 5000, 4000)) == 4000
