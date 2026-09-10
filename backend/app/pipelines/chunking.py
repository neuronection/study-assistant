MAX_CHUNK_CHARS = 1200


def split_paragraphs(markdown: str) -> list[str]:
    return [part.strip() for part in markdown.split("\n\n") if part.strip()]


def _hard_split(text: str, limit: int) -> list[str]:
    return [text[i : i + limit] for i in range(0, len(text), limit)]


def chunk_markdown(markdown: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    chunks: list[str] = []
    current = ""
    for paragraph in split_paragraphs(markdown):
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_hard_split(paragraph, max_chars))
            continue
        if current and len(current) + len(paragraph) + 2 > max_chars:
            chunks.append(current)
            current = paragraph
        else:
            current = f"{current}\n\n{paragraph}" if current else paragraph
    if current:
        chunks.append(current)
    return chunks
