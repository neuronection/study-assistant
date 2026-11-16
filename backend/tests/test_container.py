import struct

import pytest

from app.services.media.container import LectureContainerError, concat_and_validate


def box(kind: bytes, payload: bytes = b"") -> bytes:
    return struct.pack(">I", 8 + len(payload)) + kind + payload


def test_valid_webm_and_mp4_are_concatenated() -> None:
    header = b"\x1aE\xdf\xa3" + b"\x00" * 8
    segment = b"\x18S\x80g" + b"\x00" * 4
    cluster = b"\x1fC\xb6u" + b"\x00" * 4
    data, mime = concat_and_validate(
        [header + segment + cluster, cluster], "audio/webm;codecs=opus"
    )
    assert mime == "audio/webm"
    assert data.startswith(b"\x1aE\xdf\xa3")

    mp4 = box(b"ftyp", b"isom") + box(b"moov", b"\x00" * 8) + box(b"mdat", b"payload")
    valid, mp4_mime = concat_and_validate([mp4[:20], mp4[20:]], "audio/mp4")
    assert valid == mp4
    assert mp4_mime == "audio/mp4"


def test_broken_containers_are_refused() -> None:
    with pytest.raises(LectureContainerError):
        concat_and_validate([b"not-a-container"], "audio/webm")
    with pytest.raises(LectureContainerError):
        concat_and_validate([box(b"ftyp", b"isom") + b"\x00"], "audio/mp4")


def test_unknown_container_is_not_guessed() -> None:
    with pytest.raises(LectureContainerError):
        concat_and_validate([b"RIFF....WAVE"], "audio/wav")
