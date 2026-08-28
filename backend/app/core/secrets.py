import keyring

SERVICE = "StudyAssistant"
LEGACY_SERVICE = "CourseAssistant"


def get_secret(ref: str) -> str | None:
    value = keyring.get_password(SERVICE, ref)
    if value is None:
        legacy = keyring.get_password(LEGACY_SERVICE, ref)
        if legacy is not None:
            keyring.set_password(SERVICE, ref, legacy)
            return legacy
    return value


def set_secret(ref: str, value: str) -> None:
    keyring.set_password(SERVICE, ref, value)


def delete_secret(ref: str) -> None:
    keyring.delete_password(SERVICE, ref)
