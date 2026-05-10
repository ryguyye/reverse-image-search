from unittest.mock import AsyncMock, patch

from selfwatch import scheduler, watches


async def test_tick_runs_due_watches(temp_db):
    w1 = watches.create(name="a", cadence_minutes=10, webhook_url=None, image_url="https://a.com/i")
    w2 = watches.create(name="b", cadence_minutes=10, webhook_url=None, image_url="https://b.com/i")

    fake_run = AsyncMock()
    with patch.object(watches, "run", fake_run):
        ran = await scheduler.tick()

    assert ran == 2
    called_ids = {call.args[0].id for call in fake_run.call_args_list}
    assert called_ids == {w1.id, w2.id}


async def test_tick_swallows_run_errors(temp_db):
    watches.create(name="a", cadence_minutes=10, webhook_url=None, image_url="https://a.com/i")

    async def boom(_watch):
        raise RuntimeError("simulated")

    with patch.object(watches, "run", boom):
        ran = await scheduler.tick()

    assert ran == 1
