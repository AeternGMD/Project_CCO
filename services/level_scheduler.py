"""In-process hourly maintenance. Intentionally has no Telegram dependency."""
import asyncio
import logging

from services.demonlist_api import fetch_levels, LevelUpdateBusy

logger = logging.getLogger(__name__)
UPDATE_INTERVAL = 3600


async def run_hourly_level_updates():
    loop = asyncio.get_running_loop()
    deadline = loop.time() + UPDATE_INTERVAL
    while True:
        await asyncio.sleep(max(0, deadline - loop.time()))
        try:
            updated = await fetch_levels()
            logger.info('Hourly level update completed: %s levels', updated)
        except LevelUpdateBusy:
            logger.info('Hourly level update skipped: update already running')
        except Exception:
            logger.exception('Hourly level update failed; retrying next hour')
        # Monotonic hourly cadence; no catch-up burst after a long suspension.
        deadline += UPDATE_INTERVAL
        if deadline <= loop.time():
            deadline = loop.time() + UPDATE_INTERVAL
