from __future__ import annotations

from queue import Empty, Full, Queue
from threading import Lock
from typing import Any
from uuid import UUID


class CommunityEventBroker:
    """In-process fan-out for short-lived community event streams.

    Durable state remains in PostgreSQL.  The stream only tells connected
    clients when to refresh, so reconnecting or missing an event cannot lose
    a notification or a direct message.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._subscribers: dict[UUID, set[Queue[dict[str, Any]]]] = {}

    def subscribe(self, user_id: UUID) -> Queue[dict[str, Any]]:
        subscription: Queue[dict[str, Any]] = Queue(maxsize=32)
        with self._lock:
            self._subscribers.setdefault(user_id, set()).add(subscription)
        return subscription

    def unsubscribe(self, user_id: UUID, subscription: Queue[dict[str, Any]]) -> None:
        with self._lock:
            subscribers = self._subscribers.get(user_id)
            if subscribers is None:
                return
            subscribers.discard(subscription)
            if not subscribers:
                self._subscribers.pop(user_id, None)

    def publish(self, user_id: UUID, event: dict[str, Any]) -> None:
        with self._lock:
            subscribers = tuple(self._subscribers.get(user_id, ()))
        for subscription in subscribers:
            try:
                subscription.put_nowait(event)
            except Full:
                try:
                    subscription.get_nowait()
                except Empty:
                    pass
                try:
                    subscription.put_nowait(event)
                except Full:
                    pass


community_event_broker = CommunityEventBroker()
