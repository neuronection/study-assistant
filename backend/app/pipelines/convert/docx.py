from collections.abc import Callable
from io import BytesIO
from typing import Any

import mammoth

from .html import html_to_markdown

StoreImage = Callable[[bytes, str | None], int]


def docx_to_markdown(data: bytes, store_image: StoreImage) -> str:
    def convert_image(image: Any) -> dict[str, str]:
        with image.open() as payload:
            content = payload.read()
        image_id = store_image(content, image.content_type)
        return {"src": f"ca-image://{image_id}"}

    result = mammoth.convert_to_html(
        BytesIO(data),
        convert_image=mammoth.images.img_element(convert_image),
    )
    return html_to_markdown(result.value)
