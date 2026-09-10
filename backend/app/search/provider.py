import httpx
from sqlalchemy.orm import Session

from ..domain.models import Profile
from ..pipelines.convert import html_to_markdown

SEARCH_FLAVORS = ("tavily", "searxng")
SEARCH_CONNECT_TIMEOUT = 1.5
SEARCH_READ_TIMEOUT = 10.0
SEARCH_RESULT_LIMIT = 5
FETCH_MAX_CHARS = 4000
SEARCH_KEYRING_REF = "search:api_key"


class SearchError(ValueError):
    pass


def search_provider_config(session: Session, profile_id: int) -> dict[str, str] | None:
    profile = session.get(Profile, profile_id)
    preferences = profile.preferences if profile is not None else None
    if not isinstance(preferences, dict):
        return None
    raw = preferences.get("search_provider")
    if not isinstance(raw, dict):
        return None
    base_url = str(raw.get("base_url", "")).strip().rstrip("/")
    flavor = str(raw.get("flavor", "")).strip()
    if not base_url or flavor not in SEARCH_FLAVORS:
        return None
    return {"base_url": base_url, "flavor": flavor}


def _client(transport: httpx.BaseTransport | None) -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(
            SEARCH_CONNECT_TIMEOUT,
            read=SEARCH_READ_TIMEOUT,
            write=SEARCH_READ_TIMEOUT,
            pool=SEARCH_CONNECT_TIMEOUT,
        ),
        transport=transport,
        follow_redirects=True,
    )


def perform_search(
    base_url: str,
    flavor: str,
    query: str,
    *,
    api_key: str = "",
    transport: httpx.BaseTransport | None = None,
    limit: int = SEARCH_RESULT_LIMIT,
) -> list[dict[str, str]]:
    if flavor not in SEARCH_FLAVORS:
        raise SearchError(f"unknown search flavor '{flavor}'")
    query = query.strip()
    if not query:
        raise SearchError("empty search query")
    try:
        with _client(transport) as client:
            if flavor == "tavily":
                payload: dict[str, object] = {"query": query, "max_results": limit}
                if api_key:
                    payload["api_key"] = api_key
                response = client.post(
                    f"{base_url}/search",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
            else:
                response = client.get(
                    f"{base_url}/search",
                    params={"q": query, "format": "json"},
                )
    except httpx.HTTPError as error:
        raise SearchError(f"search request failed: {error}") from error
    if response.status_code != 200:
        raise SearchError(f"search provider returned {response.status_code}")
    try:
        body = response.json()
    except ValueError as error:
        raise SearchError("search provider returned non-JSON output") from error
    rows = body.get("results") if isinstance(body, dict) else None
    if not isinstance(rows, list):
        raise SearchError("search provider response missing results list")
    hits: list[dict[str, str]] = []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url", "")).strip()
        if not url:
            continue
        hits.append(
            {
                "title": str(row.get("title", "")).strip() or url,
                "url": url,
                "content": str(row.get("content", "")).strip()[:800],
            }
        )
    return hits


def perform_fetch(
    url: str,
    *,
    transport: httpx.BaseTransport | None = None,
    max_chars: int = FETCH_MAX_CHARS,
) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        raise SearchError("FETCH expects an http(s) URL")
    try:
        with _client(transport) as client:
            response = client.get(url)
    except httpx.HTTPError as error:
        raise SearchError(f"fetch failed: {error}") from error
    if response.status_code != 200:
        raise SearchError(f"fetch returned {response.status_code}")
    content_type = response.headers.get("content-type", "")
    text = (
        html_to_markdown(response.text)
        if "html" in content_type
        else response.text
    )
    text = text.strip()
    if len(text) > max_chars:
        text = text[:max_chars] + "…"
    if not text:
        raise SearchError("fetch returned no readable content")
    return text
