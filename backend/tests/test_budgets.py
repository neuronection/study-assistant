from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import text

from app.ai.gateway import BudgetExceeded, LLMGateway, Message, ResolvedModel
from app.core.config import Settings
from app.domain.models import TaskAssignment
from app.main import create_app
from app.storage.db import make_engine, make_session_factory

MODEL = ResolvedModel(
    provider_id=1,
    provider_type="openai_compatible",
    base_url="http://localhost/v1",
    external_id="costy",
    label="costy",
    caps=["text"],
    api_key=None,
    cost_in=3.0,
    cost_out=15.0,
)


def ok_transport(calls: list[httpx.Request]) -> httpx.BaseTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}
                ]
            },
        )

    return httpx.MockTransport(handler)


def usage_transport(calls: list[httpx.Request]) -> httpx.BaseTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "usage": {
                    "prompt_tokens": 5,
                    "completion_tokens": 2,
                    "total_tokens": 7,
                    "prompt_tokens_details": {"cached_tokens": 3},
                },
            },
        )

    return httpx.MockTransport(handler)


@pytest.fixture
def session_factory(tmp_path: Path) -> Any:
    from alembic.config import Config

    from alembic import command

    db_path = tmp_path / "app.db"
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(alembic_cfg, "head")
    engine = make_engine(db_path)
    factory = make_session_factory(engine)
    yield factory
    engine.dispose()


def seed_assignment(factory: Any, task: str, cap: float | None) -> None:
    with factory() as session:
        row = session.get(TaskAssignment, task)
        if row is None:
            row = TaskAssignment(task=task, model_id=None, fallback_model_id=None)
            session.add(row)
        params = dict(row.params or {})
        if cap is None:
            params.pop("monthly_cap_usd", None)
        else:
            params["monthly_cap_usd"] = cap
        row.params = params
        session.commit()


def test_generate_ledger_records_tokens_and_cost(session_factory: Any) -> None:
    calls: list[httpx.Request] = []
    gateway = LLMGateway(session_factory, transport=ok_transport(calls))
    output = gateway.generate(
        "chat",
        [Message(role="user", content="a" * 400)],
        model=MODEL,
    )
    assert output == "ok"
    with session_factory() as session:
        row = session.execute(
            text(
                "SELECT task, model, input_tokens, output_tokens, cost_usd "
                "FROM ai_interactions WHERE context_type = 'gateway'"
            )
        ).one()
    assert row[0] == "chat"
    assert row[1] == "costy"
    assert row[2] == 100
    assert row[3] == 1
    assert row[4] is not None and row[4] > 0


def test_generate_ledger_records_real_provider_usage(session_factory: Any) -> None:
    calls: list[httpx.Request] = []
    gateway = LLMGateway(session_factory, transport=usage_transport(calls))
    output = gateway.generate(
        "chat",
        [Message(role="user", content="a" * 4000)],
        model=MODEL,
    )
    assert output == "ok"
    with session_factory() as session:
        row = session.execute(
            text(
                "SELECT input_tokens, output_tokens, cached_input_tokens, cost_usd "
                "FROM ai_interactions WHERE context_type = 'gateway'"
            )
        ).one()
    assert row[0] == 5
    assert row[1] == 2
    assert row[2] == 3
    expected_cost = round(
        (5 - 3) / 1_000_000 * 3.0
        + 3 / 1_000_000 * 3.0 * 0.1
        + 2 / 1_000_000 * 15.0,
        6,
    )
    assert row[3] == expected_cost


def test_budget_exceeded_blocks_call(session_factory: Any) -> None:
    calls: list[httpx.Request] = []
    gateway = LLMGateway(session_factory, transport=ok_transport(calls))
    seed_assignment(session_factory, "chat", 0.01)
    with session_factory() as session:
        session.execute(
            text(
                "INSERT INTO ai_interactions "
                "(context_type, task, model, input_tokens, output_tokens, cost_usd, "
                "created_at) VALUES ('gateway', 'chat', 'costy', 1, 1, 5.0, "
                "CURRENT_TIMESTAMP)"
            )
        )
        session.commit()
    with pytest.raises(BudgetExceeded) as error:
        gateway.generate("chat", [Message(role="user", content="hi")], model=MODEL)
    assert "budget" in str(error.value).lower()
    assert calls == []


def test_budget_ignored_without_cap_or_with_none_cost(session_factory: Any) -> None:
    calls: list[httpx.Request] = []
    gateway = LLMGateway(session_factory, transport=ok_transport(calls))
    seed_assignment(session_factory, "chat", None)
    gateway.generate("chat", [Message(role="user", content="hi")], model=MODEL)
    assert len(calls) == 1

    cheap = ResolvedModel(
        provider_id=1,
        provider_type="openai_compatible",
        base_url="http://localhost/v1",
        external_id="free-local",
        label="free-local",
        caps=["text"],
        api_key=None,
    )
    seed_assignment(session_factory, "chat", 0.000001)
    with session_factory() as session:
        session.execute(text("DELETE FROM ai_interactions"))
        session.commit()
    gateway.generate("chat", [Message(role="user", content="hi")], model=cheap)
    assert len(calls) == 2


def test_costs_endpoint_and_budget_api(tmp_path: Path, session_factory: Any) -> None:
    calls: list[httpx.Request] = []
    from fastapi.testclient import TestClient

    settings = Settings(data_dir=tmp_path, log_level="WARNING")
    gateway = LLMGateway(session_factory, transport=ok_transport(calls))
    app = create_app(
        settings,
        gateway=gateway,
        embedder=None,
        describer=None,
    )
    with TestClient(app) as client:
        put = client.put(
            "/api/v1/tasks/chat/budget", json={"monthly_cap_usd": 2.5}
        )
        assert put.status_code == 200, put.text
        assert put.json()["monthly_cap_usd"] == 2.5

        tasks = client.get("/api/v1/tasks").json()
        chat_task = next(entry for entry in tasks if entry["task"] == "chat")
        assert chat_task["monthly_cap_usd"] == 2.5

        client.put("/api/v1/tasks/chat/budget", json={"monthly_cap_usd": 0.5})
        gateway.generate(
            "chat", [Message(role="user", content="hello")], model=MODEL
        )

        costs = client.get("/api/v1/analytics/costs")
        assert costs.status_code == 200
        body = costs.json()
        chat_entry = next(entry for entry in body["per_task"] if entry["task"] == "chat")
        assert chat_entry["calls"] == 1
        assert chat_entry["monthly_cap_usd"] == 0.5
        assert chat_entry["cost_usd"] > 0
        assert body["total_usd"] > 0
