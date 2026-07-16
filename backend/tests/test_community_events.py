from queue import Empty
from uuid import uuid4

import pytest

from app.services.community_events import CommunityEventBroker


def test_community_event_broker_fans_out_and_unsubscribes() -> None:
    broker = CommunityEventBroker()
    user_id = uuid4()
    first = broker.subscribe(user_id)
    second = broker.subscribe(user_id)

    broker.publish(user_id, {"type": "notification", "notification_type": "direct_message"})

    assert first.get(timeout=0.1)["notification_type"] == "direct_message"
    assert second.get(timeout=0.1)["notification_type"] == "direct_message"

    broker.unsubscribe(user_id, second)
    broker.publish(user_id, {"type": "notification", "notification_type": "follow"})

    assert first.get(timeout=0.1)["notification_type"] == "follow"
    with pytest.raises(Empty):
        second.get(timeout=0.05)
