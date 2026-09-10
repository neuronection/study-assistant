from typing import Any

RRF_K = 60

TIER_WEIGHT_EXACT = 1.0
TIER_WEIGHT_PREFIX = 0.9
TIER_WEIGHT_TRIGRAM = 0.7
TIER_WEIGHT_VECTOR = 0.8


def fuse_rrf(
    rankings: list[tuple[list[dict[str, Any]], float]],
    *,
    key: str,
    limit: int,
) -> list[dict[str, Any]]:
    scores: dict[int, float] = {}
    entries: dict[int, dict[str, Any]] = {}
    for ranking, weight in rankings:
        for rank, hit in enumerate(ranking):
            item_id = int(hit[key])
            scores[item_id] = scores.get(item_id, 0.0) + weight / (RRF_K + rank + 1)
            entries.setdefault(item_id, hit)
    ranked = sorted(scores, key=lambda item_id: scores[item_id], reverse=True)
    return [
        {**entries[item_id], key: item_id, "score": scores[item_id]}
        for item_id in ranked[:limit]
    ]
