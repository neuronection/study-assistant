import asyncio
from collections import defaultdict
from typing import Any

type Event = dict[str, Any]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[Event]]] = defaultdict(set)
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self, topic: str, queue: asyncio.Queue[Event]) -> None:
        self._subscribers[topic].add(queue)

    def unsubscribe(self, topic: str, queue: asyncio.Queue[Event]) -> None:
        self._subscribers[topic].discard(queue)
        if not self._subscribers[topic]:
            self._subscribers.pop(topic, None)

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        for queue in list(self._subscribers.get(topic, ())):
            queue.put_nowait({"topic": topic, "payload": payload})

    def publish_threadsafe(self, topic: str, payload: dict[str, Any]) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        loop.call_soon_threadsafe(self.publish, topic, payload)
