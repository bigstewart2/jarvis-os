import asyncio

from core.events.bus import EventBus


async def test_single_subscriber_receives_event():
    bus = EventBus()
    queue = bus.subscribe()

    await bus.publish({"type": "skill_invoked", "skill_id": "echo"})

    event = await asyncio.wait_for(queue.get(), timeout=1)
    assert event == {"type": "skill_invoked", "skill_id": "echo"}


async def test_multiple_subscribers_all_receive_event():
    bus = EventBus()
    queue_a = bus.subscribe()
    queue_b = bus.subscribe()

    await bus.publish({"type": "ping"})

    assert await asyncio.wait_for(queue_a.get(), timeout=1) == {"type": "ping"}
    assert await asyncio.wait_for(queue_b.get(), timeout=1) == {"type": "ping"}


async def test_unsubscribe_stops_delivery():
    bus = EventBus()
    queue = bus.subscribe()
    bus.unsubscribe(queue)

    await bus.publish({"type": "ping"})

    assert queue.empty()
