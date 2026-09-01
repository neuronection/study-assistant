import json
import time
from typing import Any

import httpx

from .gateway import LLMGateway, ResolvedModel, TaskUnassigned

EMBEDDINGS_TASK = "embeddings"


class GatewayEmbedder:
    def __init__(self, gateway: LLMGateway, transport: httpx.BaseTransport | None = None) -> None:
        self._gateway = gateway
        self._transport = transport if transport is not None else gateway.transport

    def embed(self, texts: list[str]) -> tuple[str, list[list[float]]] | None:
        try:
            resolved = self._gateway.resolve(EMBEDDINGS_TASK)
        except TaskUnassigned:
            return None
        started = time.monotonic()
        with httpx.Client(timeout=180, transport=self._transport) as client:
            vectors = _embed_with(client, resolved, texts)
        self._gateway.record_usage(
            EMBEDDINGS_TASK, resolved, "\n".join(texts), int((time.monotonic() - started) * 1000)
        )
        return resolved.external_id, vectors


def _embed_with(
    client: httpx.Client, model: ResolvedModel, texts: list[str]
) -> list[list[float]]:
    if model.provider_type == "google":
        return _embed_google(client, model, texts)
    if model.provider_type == "openai_compatible":
        return _embed_openai(client, model, texts)
    raise RuntimeError(
        f"provider '{model.provider_type}' does not offer embeddings; assign an embeddings model"
    )


def _embed_google(
    client: httpx.Client, model: ResolvedModel, texts: list[str]
) -> list[list[float]]:
    response = client.post(
        f"{model.base_url}/v1beta/models/{model.external_id}:batchEmbedContents",
        params={"key": model.api_key},
        json={
            "requests": [
                {
                    "model": f"models/{model.external_id}",
                    "content": {"parts": [{"text": text}]},
                }
                for text in texts
            ]
        },
    )
    response.raise_for_status()
    return [item["values"] for item in response.json()["embeddings"]]


def _embed_openai(
    client: httpx.Client, model: ResolvedModel, texts: list[str]
) -> list[list[float]]:
    response = client.post(
        f"{model.base_url}/embeddings",
        headers={"Authorization": f"Bearer {model.api_key}"} if model.api_key else {},
        json={"model": model.external_id, "input": texts},
    )
    response.raise_for_status()
    data: list[dict[str, Any]] = response.json()["data"]
    ordered = sorted(data, key=lambda item: item["index"])
    return [item["embedding"] for item in ordered]


def serialize_vector(vector: list[float]) -> str:
    return json.dumps(vector)
