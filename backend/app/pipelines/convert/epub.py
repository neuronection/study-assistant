from io import BytesIO

from ebooklib import ITEM_DOCUMENT, epub

from .docx import StoreImage
from .html import html_to_markdown


def epub_to_markdown(data: bytes, store_image: StoreImage | None = None) -> str:
    del store_image
    book = epub.read_epub(BytesIO(data))
    sections: list[str] = []
    for item in book.get_items_of_type(ITEM_DOCUMENT):
        markdown = html_to_markdown(item.get_content().decode("utf-8", errors="replace"))
        if not markdown.strip():
            continue
        title = (item.title or "").strip()
        sections.append(f"# {title}\n\n{markdown}" if title else markdown)
    if not sections:
        raise ValueError("epub contains no readable chapters")
    return "\n\n".join(sections) + "\n"
