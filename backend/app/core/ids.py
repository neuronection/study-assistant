"""UUID string id normalization (plan 81 C, ADR-198).

`Uuid(as_uuid=False)` binds a Python string as its 32-hex form and reads it
back hyphenated, so the ORM/API surface and the stored column disagree on
presentation. Code that compares ids in raw SQL or in Python must pick one
form explicitly: `hex_id` for anything that touches the database directly,
`uuid_str` for values that leave a raw-SQL boundary and join the ORM world.
"""

from uuid import UUID


def hex_id(value: str) -> str:
    return UUID(str(value)).hex


def uuid_str(value: str) -> str:
    return str(UUID(str(value)))
