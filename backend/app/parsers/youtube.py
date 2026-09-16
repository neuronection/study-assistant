"""YouTube metadata + captions via yt-dlp.

The yt-dlp entry points are module-level functions so tests can inject fakes;
the suite's network guard stays intact because nothing here performs network
I/O without going through them.
"""

import re
from typing import Any
from urllib.parse import urlparse

from .base import ParsedDocument, ParserError

YOUTUBE_HOSTS = frozenset(
    {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtu.be",
    }
)


def extract_info(url: str, options: dict[str, Any]) -> dict[str, Any]:
    import yt_dlp  # type: ignore[import-untyped]

    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, **options}) as ydl:
        return dict(ydl.extract_info(url, download=False))


def download_audio(url: str, target_dir: str) -> tuple[str, str]:
    """Download bestaudio into target_dir; returns (file_path, title)."""
    import os

    import yt_dlp

    options = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(target_dir, "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        info = dict(ydl.extract_info(url, download=True))
        path = ydl.prepare_filename(info)
    if not os.path.isfile(path):
        raise ParserError(f"audio download produced no file for {url}")
    return path, str(info.get("title") or "")


def is_youtube_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    return (parsed.hostname or "").lower() in YOUTUBE_HOSTS


def _format_anchor(seconds: float) -> str:
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _vtt_timestamp(value: str) -> float | None:
    parts = value.strip().replace(",", ".").split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(parts[0])
    except (TypeError, ValueError):
        return None


def captions_to_markdown(data: bytes) -> str:
    """Render WebVTT-style caption data into [mm:ss] markdown paragraphs."""
    text = data.decode("utf-8", errors="replace")
    lines: list[str] = []
    last_text: str | None = None
    current_start: float | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if (
            not line
            or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE"))
            or line.isdigit()
        ):
            continue
        if "-->" in line:
            start = _vtt_timestamp(line.split("-->")[0])
            if start is not None:
                current_start = start
            continue
        cleaned = re.sub(r"<[^>]+>", "", line).strip()
        if not cleaned:
            continue
        if cleaned == last_text:
            continue
        anchor = (
            f"[{_format_anchor(current_start)}] " if current_start is not None else ""
        )
        lines.append(f"{anchor}{cleaned}")
        last_text = cleaned
    return "\n\n".join(lines)


def _pick_caption(tracks: dict[str, Any] | None, language: str | None) -> bytes | None:
    if not isinstance(tracks, dict) or not tracks:
        return None
    preferred: list[str] = []
    if language:
        lowered = language.lower()
        preferred.append(lowered)
        base = lowered.split("-")[0]
        if base != lowered:
            preferred.append(base)
    preferred.extend(["en", "en-us", "en-gb", "en-orig"])
    ordered = [key for key in tracks if key.lower() in preferred]
    ordered += [key for key in tracks if key.lower() not in preferred]
    for key in ordered:
        variants = tracks[key] if isinstance(tracks[key], list) else []
        for variant in variants:
            data = variant.get("data") if isinstance(variant, dict) else None
            if data:
                return bytes(data)
    return None


def _subtitle_langs(language: str | None) -> list[str]:
    langs: list[str] = []
    if language:
        lowered = language.lower()
        langs.append(lowered)
        base = lowered.split("-")[0]
        if base != lowered:
            langs.append(base)
    langs.extend(["en", "en-US", "en-GB", "en-orig"])
    return list(dict.fromkeys(langs))


class YouTubeParser:
    def __init__(self, language: str | None = None) -> None:
        self._language = language

    def matches(self, url: str) -> bool:
        return is_youtube_url(url)

    def fetch(self, url: str) -> ParsedDocument:
        options = {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": _subtitle_langs(self._language),
        }
        try:
            info = extract_info(url, options)
        except Exception as error:
            raise ParserError(
                f"YouTube extraction failed for {url} ({error}). YouTube may have "
                "changed; try updating yt-dlp."
            ) from error
        video_id = str(info.get("id") or "")
        channel = str(info.get("channel") or info.get("uploader") or "").strip()
        duration = info.get("duration")
        title = str(info.get("title") or "").strip()

        metadata: dict[str, Any] = {"source": "youtube", "url": url}
        if video_id:
            metadata["video_id"] = video_id
        if channel:
            metadata["channel"] = channel
        if isinstance(duration, (int, float)) and duration > 0:
            metadata["duration_sec"] = int(duration)

        data = _pick_caption(info.get("subtitles"), self._language) or _pick_caption(
            info.get("automatic_captions"), self._language
        )
        markdown: str | None = None
        if data:
            transcript = captions_to_markdown(data)
            if transcript:
                header_lines = [f"# {title}", ""]
                if channel:
                    header_lines.append(f"Channel: {channel}")
                if isinstance(duration, (int, float)) and duration > 0:
                    header_lines.append(f"Duration: {_format_anchor(duration)}")
                header_lines.extend(["", "## Transcript", ""])
                markdown = "\n".join(header_lines) + transcript
        if markdown is None:
            metadata["parse_note"] = (
                "no captions available — transcribe the audio instead"
            )
        return ParsedDocument(
            title=title[:300],
            markdown=markdown,
            metadata=metadata,
            kind_hint=None,
            blob=None,
        )
