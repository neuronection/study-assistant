"""Model price overrides and effective rates (plan 58 P1)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, cast
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.model_pricing import resolve_price
from ..ai.model_pricing_data import MODEL_PRICING_COMPILED, MODEL_PRICING_ROWS
from ..domain.models import AiModel, AiPriceOverride, Provider
from .deps import get_session

router = APIRouter(prefix="/ai", tags=["ai"])


class PriceOverrideIn(BaseModel):
    provider_key: str | None = Field(default=None, max_length=40)
    provider_ref: str | None = Field(default=None, max_length=40)
    model: str = Field(min_length=1, max_length=200)
    match: Literal["exact", "prefix"] = "exact"
    input_micros_per_million: int = Field(ge=0)
    output_micros_per_million: int = Field(ge=0)
    metering: Literal["tokens", "input_only", "output_only"] = "tokens"


class PriceOverrideOut(PriceOverrideIn):
    id: str
    updated_at: str


class EffectivePriceOut(BaseModel):
    provider: str | None
    provider_id: str | None
    model: str
    source: str
    input_micros_per_million: int
    output_micros_per_million: int
    metering: str
    reviewed_at: str | None = None
    price_version: str | None = None


class PricesOut(BaseModel):
    overrides: list[PriceOverrideOut]
    effective: list[EffectivePriceOut]


def _is_local(base_url: str) -> bool:
    host = (urlparse(base_url).hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local")


def _override_out(row: AiPriceOverride) -> PriceOverrideOut:
    return PriceOverrideOut(
        id=str(row.id),
        provider_key=row.provider_key,
        provider_ref=str(row.provider_ref) if row.provider_ref else None,
        model=row.model,
        match=cast(Literal["exact", "prefix"], row.match),
        input_micros_per_million=int(row.input_micros_per_million),
        output_micros_per_million=int(row.output_micros_per_million),
        metering=cast(Literal["tokens", "input_only", "output_only"], row.metering),
        updated_at=row.updated_at.isoformat(),
    )


def _override_dicts(session: Session) -> list[dict[str, Any]]:
    return [
        {
            "providerRef": str(row.provider_ref) if row.provider_ref else None,
            "provider": row.provider_key,
            "model": row.model,
            "match": row.match,
            "inputMicrosPerMillion": int(row.input_micros_per_million),
            "outputMicrosPerMillion": int(row.output_micros_per_million),
            "metering": row.metering,
            "id": str(row.id),
            "updatedAt": row.updated_at.isoformat(),
        }
        for row in session.scalars(select(AiPriceOverride))
    ]


@router.get("/prices", response_model=PricesOut)
def list_prices(session: Session = Depends(get_session)) -> PricesOut:
    overrides = _override_dicts(session)
    effective: list[EffectivePriceOut] = []
    for model in session.scalars(select(AiModel).where(AiModel.enabled.is_(True))):
        provider = session.get(Provider, model.provider_id)
        if provider is None or not provider.enabled:
            continue
        is_local = (
            bool(provider.is_local)
            if provider.is_local is not None
            else _is_local(provider.base_url)
        )
        resolution = resolve_price(
            rows=MODEL_PRICING_ROWS,
            compiled=MODEL_PRICING_COMPILED,
            model=model.external_id,
            provider_key=provider.preset_key,
            provider_row_id=provider.id,
            is_local=is_local,
            user_rows=overrides,
        )
        if resolution is None:
            effective.append(
                EffectivePriceOut(
                    provider=provider.preset_key or provider.name,
                    provider_id=provider.id,
                    model=model.external_id,
                    source="unknown",
                    input_micros_per_million=0,
                    output_micros_per_million=0,
                    metering="tokens",
                )
            )
            continue
        effective.append(
            EffectivePriceOut(
                provider=provider.preset_key or provider.name,
                provider_id=provider.id,
                model=model.external_id,
                source=resolution.source,
                input_micros_per_million=resolution.input_micros_per_million,
                output_micros_per_million=resolution.output_micros_per_million,
                metering=resolution.metering,
                reviewed_at=resolution.reviewed_at,
                price_version=resolution.price_version,
            )
        )
    return PricesOut(
        overrides=[_override_out(row) for row in session.scalars(select(AiPriceOverride))],
        effective=effective,
    )


@router.put("/prices", response_model=PriceOverrideOut)
def put_price(body: PriceOverrideIn, session: Session = Depends(get_session)) -> PriceOverrideOut:
    if body.provider_key and body.provider_ref:
        raise HTTPException(status_code=422, detail="bind provider_key or provider_ref, not both")
    if body.provider_ref is not None and session.get(Provider, body.provider_ref) is None:
        raise HTTPException(status_code=422, detail="unknown provider_ref")
    query = select(AiPriceOverride).where(AiPriceOverride.model == body.model)
    query = query.where(
        AiPriceOverride.provider_key.is_(None)
        if body.provider_key is None
        else AiPriceOverride.provider_key == body.provider_key
    )
    query = query.where(
        AiPriceOverride.provider_ref.is_(None)
        if body.provider_ref is None
        else AiPriceOverride.provider_ref == body.provider_ref
    )
    query = query.where(AiPriceOverride.match == body.match)
    row = session.scalars(query).first()
    if row is None:
        row = AiPriceOverride(
            provider_key=body.provider_key,
            provider_ref=body.provider_ref,
            model=body.model,
            match=body.match,
            input_micros_per_million=body.input_micros_per_million,
            output_micros_per_million=body.output_micros_per_million,
            metering=body.metering,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        session.add(row)
    else:
        row.input_micros_per_million = body.input_micros_per_million
        row.output_micros_per_million = body.output_micros_per_million
        row.metering = body.metering
        row.updated_at = datetime.now(UTC)
    session.commit()
    return _override_out(row)


@router.delete("/prices/{override_id}", status_code=204)
def delete_price(override_id: str, session: Session = Depends(get_session)) -> None:
    row = session.get(AiPriceOverride, override_id)
    if row is None:
        raise HTTPException(status_code=404, detail="price override not found")
    session.delete(row)
    session.commit()
