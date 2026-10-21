from sqlalchemy import text
from sqlalchemy.orm import Session

from ..core.ids import hex_id
from ..domain.models import Material

_FTS_TABLES = ("material_fts", "material_fts_trigram")


def sync_material_fts(
    session: Session, material: Material, markdown: str, drawing_ocr: str = ""
) -> None:
    body = f"{markdown}\n{drawing_ocr}".strip() if drawing_ocr else markdown
    for table in _FTS_TABLES:
        session.execute(
            text(f"DELETE FROM {table} WHERE material_id = :material_id"),
            {"material_id": hex_id(material.id)},
        )
        session.execute(
            text(
                f"INSERT INTO {table} (title, markdown, description, topics, "
                "material_id) VALUES (:title, :markdown, :description, :topics, "
                ":material_id)"
            ),
            {
                "title": material.title,
                "markdown": body,
                "description": "",
                "topics": "",
                "material_id": hex_id(material.id),
            },
        )


def delete_material_fts(session: Session, material_id: str) -> None:
    for table in _FTS_TABLES:
        session.execute(
            text(f"DELETE FROM {table} WHERE material_id = :material_id"),
            {"material_id": hex_id(material_id)},
        )
