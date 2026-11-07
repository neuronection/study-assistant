from fastapi.testclient import TestClient


def test_oauth_callback_is_reachable_without_the_profile_header(client: TestClient) -> None:
    """The provider redirect is a browser navigation: no X-Profile-Id.

    The route resolves the link's own profile and verifies the session user
    owns it; the single-use state remains principal-bound. An unknown link
    still redirects to the UI error state instead of 400ing in middleware.
    """
    response = client.get(
        "/api/v1/calendar/oauth/callback?code=abc&state=missing-link.nonce",
        headers={"X-Profile-Id": ""},
        follow_redirects=False,
    )
    assert response.status_code == 302, response.text
    assert "calendar_status=error" in response.headers["location"]
