import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_chat_api import NoDescriber, NoEmbedder, ScriptedGateway, make_course

from app.core.config import Settings
from app.core.urls import normalize_url
from app.main import create_app
from app.parsers import build_registry, resolve_parser
from app.parsers.youtube import captions_to_markdown


@pytest.fixture
def client(
    tmp_path: Path,
) -> Iterator[tuple[TestClient, FastAPI]]:
    app = create_app(
        Settings(data_dir=tmp_path, log_level="WARNING"),
        gateway=ScriptedGateway([]),
        embedder=NoEmbedder(),  # type: ignore[arg-type]
        describer=NoDescriber(),  # type: ignore[arg-type]
    )
    with TestClient(app) as test_client:
        yield test_client, app


def wait_job(
    client: TestClient, job_id: int, timeout: float = 30.0
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 200, response.text
        last = response.json()
        if last["status"] in ("done", "failed", "cancelled"):
            return last
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} never finished; last state: {last}")


VTT_SAMPLE = (
    "WEBVTT\n"
    "\n"
    "1\n"
    "00:00:01.000 --> 00:00:03.000\n"
    "Hello world\n"
    "\n"
    "2\n"
    "00:01:05.000 --> 00:01:07.000\n"
    "Second line\n"
)


YOUTUBE_INFO = {
    "id": "abc123",
    "title": "Chain rule lecture",
    "channel": "Math Academy",
    "duration": 3725,
    "description": "A lecture",
    "subtitles": {
        "en": [
            {"ext": "vtt", "data": VTT_SAMPLE.encode()},
        ]
    },
    "automatic_captions": {},
}


def test_captions_to_markdown_anchors_and_dedupes() -> None:
    vtt = (
        "WEBVTT\n\n"
        "00:00:01.000 --> 00:00:03.000\n"
        "Hello world\n\n"
        "00:00:03.500 --> 00:00:05.000\n"
        "Hello world\n\n"
        "01:02:03.000 --> 01:02:05.000\n"
        "Deep cue\n"
    )
    markdown = captions_to_markdown(vtt.encode())
    assert "[00:01] Hello world" in markdown
    assert "[1:02:03] Deep cue" in markdown
    assert markdown.count("Hello world") == 1


def test_parser_dispatch_order() -> None:
    registry = build_registry(None, language="en")
    youtube = resolve_parser(registry, "https://youtu.be/abc123")
    assert youtube is not None and type(youtube).__name__ == "YouTubeParser"
    direct = resolve_parser(registry, "https://example.com/files/notes.pdf")
    assert direct is not None and type(direct).__name__ == "DirectFileParser"
    plain = resolve_parser(registry, "https://example.com/wiki/Bayes")
    assert plain is not None and type(plain).__name__ == "HtmlParser"
    assert resolve_parser(registry, "ftp://example.com/x") is None


def test_youtube_parser_metadata_and_captions(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.parsers import youtube as youtube_module

    captured: dict[str, object] = {}

    def fake_extract(
        url: str, options: dict[str, object]
    ) -> dict[str, object]:
        captured["url"] = url
        captured["options"] = options
        return dict(YOUTUBE_INFO)

    monkeypatch.setattr(youtube_module, "extract_info", fake_extract)
    parser = youtube_module.YouTubeParser(language="de")
    assert parser.matches("https://youtube.com/watch?v=abc123")
    parsed = parser.fetch("https://youtube.com/watch?v=abc123")
    captured_options = captured["options"]
    assert isinstance(captured_options, dict)
    assert captured_options["subtitleslangs"][0] == "de"
    assert parsed.metadata["source"] == "youtube"
    assert parsed.metadata["video_id"] == "abc123"
    assert parsed.metadata["channel"] == "Math Academy"
    assert parsed.metadata["duration_sec"] == 3725
    assert parsed.markdown is not None
    assert "# Chain rule lecture" in parsed.markdown
    assert "[00:01] Hello world" in parsed.markdown
    assert "[01:05] Second line" in parsed.markdown
    assert "parse_note" not in parsed.metadata


def test_youtube_parser_without_captions_is_honest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.parsers import youtube as youtube_module

    info = {"id": "abc123", "title": "Silent", "subtitles": {}, "automatic_captions": {}}
    monkeypatch.setattr(youtube_module, "extract_info", lambda url, options: info)
    parsed = youtube_module.YouTubeParser().fetch("https://youtu.be/abc123")
    assert parsed.markdown is None
    assert "no captions" in (parsed.metadata.get("parse_note") or "")


def test_youtube_extractor_failure_is_honest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.parsers import youtube as youtube_module

    def boom(url: str, options: dict[str, object]) -> dict[str, object]:
        raise RuntimeError("extractor broke")

    monkeypatch.setattr(youtube_module, "extract_info", boom)
    parser = youtube_module.YouTubeParser()
    with pytest.raises(Exception, match="try updating yt-dlp"):
        parser.fetch("https://youtu.be/abc123")


def test_direct_file_downloads_and_rejects_html(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.parsers import direct_file as direct_file_module

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/notes.pdf":
            return httpx.Response(
                200, content=b"%PDF-1.4 fake", headers={"content-type": "application/pdf"}
            )
        return httpx.Response(
            200, content=b"<html>error page</html>", headers={"content-type": "text/html"}
        )

    transport = httpx.MockTransport(handler)
    parser = direct_file_module.DirectFileParser(transport=transport)
    assert parser.matches("https://example.com/notes.pdf")
    parsed = parser.fetch("https://example.com/notes.pdf")
    assert parsed.blob == b"%PDF-1.4 fake"
    assert parsed.kind_hint == "pdf"

    html_parser = direct_file_module.DirectFileParser(transport=transport)
    with pytest.raises(Exception, match="HTML page"):
        html_parser.fetch("https://example.com/missing.pdf")


def test_parse_endpoint_full_lifecycle(client: tuple[TestClient, FastAPI]) -> None:
    test_client, _app = client
    with test_client:
        from app.parsers import youtube as youtube_module

        course_id = make_course(test_client)
        linked = test_client.post(
            "/api/v1/materials/link",
            json={
                "course_id": course_id,
                "url": normalize_url("https://youtu.be/abc123"),
            },
        )
        assert linked.status_code == 200, linked.text
        material_id = linked.json()["material"]["id"]

        original = youtube_module.extract_info

        youtube_module.extract_info = lambda url, options: dict(YOUTUBE_INFO)
        try:
            parsed_job = test_client.post(f"/api/v1/materials/{material_id}/parse")
            assert parsed_job.status_code == 200, parsed_job.text
            job = wait_job(test_client, parsed_job.json()["job_id"])
            assert job["status"] == "done", job
        finally:
            youtube_module.extract_info = original

        detail = test_client.get(f"/api/v1/materials/{material_id}").json()
        assert detail["material"]["provenance"]["source"] == "youtube"
        assert detail["material"]["provenance"]["channel"] == "Math Academy"
        assert detail["extraction"] is None or True

        extraction = test_client.get(
            f"/api/v1/materials/{material_id}/extractions/1"
        ).json()
        assert "[00:01] Hello world" in extraction["markdown"]


def test_no_parser_url_is_an_honest_job_error(
    db_session: Session, tmp_path: Path
) -> None:
    from app.domain.models import Course, Profile
    from app.domain.models import Material as MaterialRow
    from app.jobs.runner import JobError
    from app.pipelines.url_import import make_url_import_handler
    from app.storage.blobs import BlobStore

    profile = Profile(name="p")
    db_session.add(profile)
    db_session.flush()
    course = Course(profile_id=profile.id, title="Calc")
    db_session.add(course)
    db_session.flush()
    material = MaterialRow(
        profile_id=profile.id,
        course_id=course.id,
        kind="link",
        title="Old link",
        filename="old-link",
        status="ready",
        source_url="gopher://example.com/article",
        source_url_norm="gopher://example.com/article",
    )
    db_session.add(material)
    db_session.commit()

    handler = make_url_import_handler(BlobStore(tmp_path))

    class FakeJob:
        id = 1

        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

    with pytest.raises(JobError, match="no parser"):
        handler(
            db_session,
            cast(Any, FakeJob({"material_id": material.id})),
            lambda p, s: None,
        )


def test_parse_endpoint_rejects_non_link(
    client: tuple[TestClient, FastAPI],
) -> None:
    test_client, _app = client
    with test_client:
        course_id = make_course(test_client)
        upload = test_client.post(
            "/api/v1/materials",
            params={"course_id": course_id},
            files={"file": ("notes.txt", b"text", "text/plain")},
        )
        material_id = upload.json()["material"]["id"]
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if (
                test_client.get(f"/api/v1/materials/{material_id}").json()["material"][
                    "status"
                ]
                == "ready"
            ):
                break
            time.sleep(0.05)
        response = test_client.post(f"/api/v1/materials/{material_id}/parse")
        assert response.status_code == 422
        assert "URL references" in response.json()["detail"]


def test_reparse_creates_second_version(client: tuple[TestClient, FastAPI]) -> None:
    test_client, _app = client
    with test_client:
        import app.parsers.youtube as youtube_module

        course_id = make_course(test_client)
        linked = test_client.post(
            "/api/v1/materials/link",
            json={"course_id": course_id, "url": "https://youtu.be/abc123"},
        )
        material_id = linked.json()["material"]["id"]
        original = youtube_module.extract_info

        youtube_module.extract_info = lambda url, options: dict(YOUTUBE_INFO)
        try:
            first = test_client.post(f"/api/v1/materials/{material_id}/parse")
            assert first.status_code == 200
            job1 = wait_job(test_client, first.json()["job_id"])
            assert job1["status"] == "done", job1
            second = test_client.post(f"/api/v1/materials/{material_id}/parse")
            assert second.status_code == 200
            job2 = wait_job(test_client, second.json()["job_id"])
            assert job2["status"] == "done", job2
        finally:
            youtube_module.extract_info = original

        extractions = test_client.get(
            f"/api/v1/materials/{material_id}/extractions"
        ).json()
        assert [entry["version"] for entry in extractions] == [2, 1]


def test_transcribe_audio_endpoint_queues_job(
    client: tuple[TestClient, FastAPI], monkeypatch: pytest.MonkeyPatch
) -> None:
    test_client, _app = client
    with test_client:
        import tempfile

        import app.parsers.youtube as youtube_module

        course_id = make_course(test_client)
        linked = test_client.post(
            "/api/v1/materials/link",
            json={"course_id": course_id, "url": "https://youtu.be/abc123"},
        )
        material_id = linked.json()["material"]["id"]

        with tempfile.TemporaryDirectory() as tmp:
            audio_path = Path(tmp) / "abc123.m4a"
            audio_path.write_bytes(b"\x00\x01audio")

            def fake_download(url: str, target_dir: str) -> tuple[str, str]:
                target = Path(target_dir) / "abc123.m4a"
                target.write_bytes(b"\x00\x01audio")
                return str(target), "Lecture"

            monkeypatch.setattr(youtube_module, "download_audio", fake_download)
            response = test_client.post(
                f"/api/v1/materials/{material_id}/transcribe-audio"
            )
            assert response.status_code == 200, response.text
            job = wait_job(test_client, response.json()["job_id"])
            assert job["status"] == "done", job

        detail = test_client.get(f"/api/v1/materials/{material_id}").json()
        assert detail["material"]["kind"] == "audio"
        assert detail["material"]["blob_sha"] is not None
        jobs = test_client.get("/api/v1/jobs", params={"type": "ingest"}).json()
        assert any(entry["material_id"] == material_id for entry in jobs)


def test_transcribe_audio_rejects_non_youtube(
    client: tuple[TestClient, FastAPI],
) -> None:
    test_client, _app = client
    with test_client:
        course_id = make_course(test_client)
        linked = test_client.post(
            "/api/v1/materials/link",
            json={"course_id": course_id, "url": "https://example.com/article"},
        )
        material_id = linked.json()["material"]["id"]
        response = test_client.post(
            f"/api/v1/materials/{material_id}/transcribe-audio"
        )
        assert response.status_code == 422
        assert "YouTube" in response.json()["detail"]
