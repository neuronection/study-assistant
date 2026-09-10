import contextlib

import keyring

SERVICE = "StudyAssistant"
LEGACY_SERVICE = "CourseAssistant"


def get_secret(ref: str) -> str | None:
    try:
        value = keyring.get_password(SERVICE, ref)
        if value is None:
            legacy = keyring.get_password(LEGACY_SERVICE, ref)
            if legacy is not None:
                keyring.set_password(SERVICE, ref, legacy)
                return legacy
        return value
    except Exception:
        return None


def set_secret(ref: str, value: str) -> None:
    try:
        keyring.set_password(SERVICE, ref, value)
    except Exception as error:
        raise RuntimeError(
            "no usable OS keyring backend — the API key cannot be stored locally"
        ) from error


def delete_secret(ref: str) -> None:
    with contextlib.suppress(Exception):
        keyring.delete_password(SERVICE, ref)
