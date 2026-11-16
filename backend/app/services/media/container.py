from typing import Final

EBML_HEADER: Final = b"\x1aE\xdf\xa3"
SEGMENT_ID: Final = b"\x18S\x80g"
CLUSTER_ID: Final = b"\x1fC\xb6u"
MP4_HEADER: Final = b"ftyp"
OGG_HEADER: Final = b"OggS"


class LectureContainerError(ValueError):
    pass


def base_mime(mime: str) -> str:
    return (mime or "").split(";", 1)[0].strip().lower()


def _webm_problems(data: bytes) -> list[str]:
    problems: list[str] = []
    if not data.startswith(EBML_HEADER):
        problems.append("WebM data does not start with an EBML header")
    header_count = data.count(EBML_HEADER)
    if header_count == 0:
        problems.append("WebM data has no EBML header")
    elif header_count > 1:
        problems.append("WebM data contains more than one EBML header")
    if SEGMENT_ID not in data:
        problems.append("WebM data has no segment")
    if CLUSTER_ID not in data:
        problems.append("WebM data has no cluster")
    return problems


def _read_box(data: bytes, offset: int) -> tuple[int, bytes]:
    if offset + 8 > len(data):
        raise LectureContainerError("MP4 box header is truncated")
    size = int.from_bytes(data[offset : offset + 4], "big")
    kind = data[offset + 4 : offset + 8]
    header = 8
    if size == 1:
        if offset + 16 > len(data):
            raise LectureContainerError("MP4 extended box header is truncated")
        size = int.from_bytes(data[offset + 8 : offset + 16], "big")
        header = 16
    elif size == 0:
        size = len(data) - offset
    if size < header:
        raise LectureContainerError("MP4 box size is smaller than its header")
    if offset + size > len(data):
        raise LectureContainerError("MP4 box extends past the end of the recording")
    return size, kind


def _mp4_problems(data: bytes) -> list[str]:
    problems: list[str] = []
    offset = 0
    kinds: list[bytes] = []
    while offset < len(data):
        try:
            size, kind = _read_box(data, offset)
        except LectureContainerError as error:
            problems.append(str(error))
            break
        kinds.append(kind)
        offset += size
    if offset != len(data):
        problems.append("MP4 boxes do not tile the recording exactly")
    if not kinds or kinds[0] != MP4_HEADER:
        problems.append("MP4 data does not start with ftyp")
    if kinds.count(MP4_HEADER) > 1:
        problems.append("MP4 data contains more than one ftyp box")
    if not any(kind in (b"moov", b"moof") for kind in kinds):
        problems.append("MP4 data has no movie or fragment metadata")
    return problems


def _ogg_problems(data: bytes) -> list[str]:
    problems: list[str] = []
    if not data.startswith(OGG_HEADER):
        problems.append("Ogg data does not start with an Ogg page")
    if data.count(OGG_HEADER) < 1:
        problems.append("Ogg data has no pages")
    return problems


def concat_and_validate(parts: list[bytes], mime: str) -> tuple[bytes, str]:
    if not parts:
        raise LectureContainerError("recording has no parts")
    data = b"".join(parts)
    normalized = base_mime(mime)
    if normalized in ("audio/webm", "video/webm"):
        problems = _webm_problems(data)
        normalized = "video/webm" if normalized.startswith("video/") else "audio/webm"
    elif normalized in ("audio/ogg", "video/ogg", "application/ogg"):
        problems = _ogg_problems(data)
        normalized = "audio/ogg"
    elif normalized in ("audio/mp4", "video/mp4", "audio/x-m4a", "audio/m4a"):
        problems = _mp4_problems(data)
        normalized = "video/mp4" if normalized.startswith("video/") else "audio/mp4"
    else:
        if data.startswith(EBML_HEADER):
            problems = _webm_problems(data)
            normalized = "audio/webm"
        elif len(data) >= 8 and data[4:8] == MP4_HEADER:
            problems = _mp4_problems(data)
            normalized = "audio/mp4"
        elif data.startswith(OGG_HEADER):
            problems = _ogg_problems(data)
            normalized = "audio/ogg"
        else:
            raise LectureContainerError(
                "the recording container is not WebM or MP4; keeping the parts but refusing "
                "to publish an unplayable file"
            )
    if problems:
        raise LectureContainerError("; ".join(problems))
    return data, normalized
