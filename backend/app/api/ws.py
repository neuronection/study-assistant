import asyncio
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..core.events import EventBus

router = APIRouter(tags=["system"])


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    bus: EventBus = websocket.app.state.bus
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    subscribed: set[str] = set()

    async def sender() -> None:
        while True:
            event = await queue.get()
            await websocket.send_json(event)

    sender_task = asyncio.create_task(sender())
    try:
        while True:
            message = await websocket.receive_json()
            msg_type = message.get("type")
            topic = message.get("topic")
            if msg_type == "subscribe" and isinstance(topic, str):
                bus.subscribe(topic, queue)
                subscribed.add(topic)
                queue.put_nowait({"type": "subscribed", "topic": topic})
            elif msg_type == "unsubscribe" and isinstance(topic, str):
                bus.unsubscribe(topic, queue)
                subscribed.discard(topic)
                queue.put_nowait({"type": "unsubscribed", "topic": topic})
            elif msg_type == "publish" and isinstance(topic, str):
                bus.publish(topic, message.get("payload", {}))
            elif msg_type == "ping":
                queue.put_nowait({"type": "pong"})
            else:
                queue.put_nowait({"type": "error", "error": "unknown_message"})
    except WebSocketDisconnect:
        pass
    finally:
        sender_task.cancel()
        for topic in subscribed:
            bus.unsubscribe(topic, queue)
