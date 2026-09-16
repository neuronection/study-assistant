import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

TRACKING_PARAM_PREFIXES = ("utm_",)
TRACKING_PARAMS = frozenset(
    {
        "fbclid",
        "gclid",
        "msclkid",
        "dclid",
        "twclid",
        "si",
        "ref",
        "ref_src",
        "ref_url",
        "igshid",
        "mc_cid",
        "mc_eid",
        "_hsenc",
        "_hsmi",
        "vero_id",
        "wickedid",
        "ttclid",
    }
)

YOUTUBE_HOSTS = frozenset(
    {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
)
YOUTUBE_SHORT_HOST = "youtu.be"
YOUTUBE_PATH_RE = re.compile(r"^/(?:watch/)?(?P<id>[\w-]{6,20})/?$")

DEFAULT_PORTS = {"http": 80, "https": 443}


def normalize_url(raw_url: str) -> str:
    text = (raw_url or "").strip()
    parsed = urlparse(text)
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    if not scheme or not host:
        return text

    port = parsed.port
    default_port = DEFAULT_PORTS.get(scheme)
    netloc = host
    if parsed.username:
        userinfo = parsed.username
        if parsed.password:
            userinfo += f":{parsed.password}"
        netloc = f"{userinfo}@{netloc}"
    if port is not None and port != default_port:
        netloc = f"{netloc}:{port}"

    path = parsed.path or ""
    while len(path) > 1 and path.endswith("/"):
        path = path[:-1]

    query_items = parse_qsl(parsed.query, keep_blank_values=True)
    filtered = [
        (key, value)
        for key, value in query_items
        if not key.lower().startswith(TRACKING_PARAM_PREFIXES)
        and key.lower() not in TRACKING_PARAMS
    ]

    video_id = _youtube_video_id(scheme, host, path, filtered)
    if host in YOUTUBE_HOSTS or host == YOUTUBE_SHORT_HOST:
        netloc = "youtube.com"
        if video_id is not None:
            path = "/watch"
            filtered = [("v", video_id)]

    filtered.sort()
    query = urlencode(filtered)

    return urlunparse((scheme, netloc, path, "", query, ""))


def _youtube_video_id(
    scheme: str, host: str, path: str, query_items: list[tuple[str, str]]
) -> str | None:
    if scheme not in ("http", "https"):
        return None
    if host == YOUTUBE_SHORT_HOST:
        match = YOUTUBE_PATH_RE.match(path)
        if match is not None:
            return match.group("id")
        return None
    if host in YOUTUBE_HOSTS:
        if path == "/watch":
            for key, value in query_items:
                if key == "v" and value:
                    return value
            return None
        for prefix in ("/shorts/", "/embed/", "/live/", "/v/"):
            if path.startswith(prefix):
                candidate = path[len(prefix) :].strip("/")
                if candidate and "/" not in candidate:
                    return candidate
        return None
    return None
