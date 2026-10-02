"""Job handler registry (plan 20 Phase 4 split).

`build_job_runner` wires the typed `make_*_handler` pipelines over the
app-state services into the `JobRunner`, and stashes the chat turn locks
on `app.state`. Kept out of the app factory so `main.py` stays wiring.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from ..ai.graphs.chat_turn_adapter import ChatTurnEngine
from ..api.chat import SessionTurnLocks, make_chat_turn_handler
from ..core.vocab import WsTopic
from ..pipelines.compose import make_compose_handler
from ..pipelines.drawing_ocr import make_drawing_ocr_handler
from ..pipelines.genesis import make_genesis_handler
from ..pipelines.image_ocr import make_image_ocr_handler
from ..pipelines.ingest import make_ingest_handler
from ..pipelines.postprocess import make_postprocess_handler
from ..pipelines.url_import import make_url_import_handler
from .runner import JobRunner


def build_job_runner(app: FastAPI) -> JobRunner:
    """Build the `JobRunner` over `app.state` services; set `turn_locks`."""

    def _chat_turn_group(job: Any) -> str | None:
        if job.type != "chat_turn":
            return None
        chat_session_id = (job.payload or {}).get("chat_session_id")
        if chat_session_id is None:
            return None
        return WsTopic.chat(chat_session_id)

    def _turn_engine() -> ChatTurnEngine | None:
        return getattr(app.state, "chat_turns", None)

    app.state.turn_locks = SessionTurnLocks()
    return JobRunner(
        app.state.session_factory,
        app.state.bus,
        handlers={
            "ingest": make_ingest_handler(app.state.blobs, app.state.ocr, app.state.gateway),
            "postprocess": make_postprocess_handler(
                app.state.embedder.embed, app.state.describer.describe
            ),
            "chat_turn": make_chat_turn_handler(
                app.state.gateway,
                app.state.embedder,
                app.state.bus,
                turn_engine_provider=_turn_engine,
                search_transport_provider=lambda: getattr(app.state, "search_transport", None),
                turn_locks=app.state.turn_locks,
            ),
            "drawing_ocr": make_drawing_ocr_handler(app.state.gateway, app.state.blobs),
            "image_ocr": make_image_ocr_handler(app.state.gateway, app.state.blobs),
            "genesis": make_genesis_handler(
                app.state.gateway, app.state.blobs, app.state.embedder.embed
            ),
            "compose": make_compose_handler(
                app.state.gateway, app.state.blobs, app.state.embedder.embed
            ),
            "url_import": make_url_import_handler(
                app.state.blobs,
                lambda: getattr(app.state, "search_transport", None),
            ),
        },
        group_key=_chat_turn_group,
    )
