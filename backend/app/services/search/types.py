from collections.abc import Callable

EmbedQuery = Callable[[str], tuple[str, list[list[float]]] | None]
