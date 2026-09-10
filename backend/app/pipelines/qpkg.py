import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

PKG_FORMAT = "caq-pkg"
PKG_VERSION = 1
MANIFEST_NAME = "manifest.json"
DOC_NAME = "quiz.json"


@dataclass(frozen=True)
class PkgContent:
    document: dict[str, Any]
    license: str | None


def build_qpkg(document: dict[str, Any], generator: str) -> bytes:
    doc_bytes = json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")
    doc_sha = hashlib.sha256(doc_bytes).hexdigest()
    manifest = {
        "format": PKG_FORMAT,
        "version": PKG_VERSION,
        "generator": generator,
        "items": [{"path": DOC_NAME, "sha256": doc_sha}],
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2))
        archive.writestr(DOC_NAME, doc_bytes)
    return buffer.getvalue()


def read_qpkg(data: bytes) -> PkgContent:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as error:
        raise HTTPException(status_code=422, detail="not a .qpkg file") from error
    names = archive.namelist()
    if MANIFEST_NAME not in names or DOC_NAME not in names:
        raise HTTPException(status_code=422, detail="package is incomplete")
    try:
        manifest = json.loads(archive.read(MANIFEST_NAME))
    except ValueError as error:
        raise HTTPException(status_code=422, detail="unreadable manifest") from error
    if manifest.get("format") != PKG_FORMAT:
        raise HTTPException(status_code=422, detail="unsupported package format")
    doc_bytes = archive.read(DOC_NAME)
    expected = {
        item["path"]: item["sha256"] for item in manifest.get("items", []) if "path" in item
    }
    actual = hashlib.sha256(doc_bytes).hexdigest()
    if DOC_NAME in expected and expected[DOC_NAME] != actual:
        raise HTTPException(
            status_code=422, detail="integrity check failed — package is corrupted"
        )
    try:
        document = json.loads(doc_bytes)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="quiz.json is not valid JSON") from error
    license_text: str | None = None
    if "license.txt" in names:
        license_text = archive.read("license.txt").decode("utf-8", errors="replace")
    return PkgContent(document=document, license=license_text)
