from app.pipelines.chunking import chunk_markdown


def test_empty_markdown_yields_no_chunks() -> None:
    assert chunk_markdown("") == []


def test_short_markdown_is_single_chunk() -> None:
    assert chunk_markdown("one paragraph") == ["one paragraph"]


def test_paragraphs_merge_up_to_limit() -> None:
    paragraphs = [f"paragraph {i} " + "x" * 100 for i in range(10)]
    chunks = chunk_markdown("\n\n".join(paragraphs), max_chars=350)
    assert all(len(chunk) <= 350 for chunk in chunks)
    assert len(chunks) > 1
    joined = "\n\n".join(chunks)
    for paragraph in paragraphs:
        assert paragraph in joined


def test_oversized_paragraph_is_hard_split() -> None:
    text = "y" * 3000
    chunks = chunk_markdown(text, max_chars=1200)
    assert [len(chunk) for chunk in chunks] == [1200, 1200, 600]
    assert "".join(chunks) == text
