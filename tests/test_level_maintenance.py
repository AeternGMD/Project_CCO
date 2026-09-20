import asyncio
from contextlib import asynccontextmanager
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

if 'aiomysql' not in sys.modules:
    try:
        import aiomysql
    except ImportError:
        sys.modules['aiomysql'] = types.ModuleType('aiomysql')

from database import models
from services import demonlist_api as api, level_scheduler, record_catalog


class MaintenanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_manual_and_scheduled_runs_share_lock(self):
        entered, release = asyncio.Event(), asyncio.Event()

        async def download(progress):
            entered.set()
            await release.wait()
            return 1837

        with patch.object(api, '_update_levels', side_effect=download) as update:
            first = asyncio.create_task(api.fetch_levels())
            try:
                await entered.wait()
                with self.assertRaises(api.LevelUpdateBusy):
                    await api.fetch_levels()
                self.assertEqual(1, update.await_count)
            finally:
                release.set()
                self.assertEqual(1837, await first)
        self.assertFalse(api._update_lock.locked())

    async def test_timeout_releases_lock_for_next_run(self):
        async def hang(progress):
            await asyncio.Event().wait()

        with patch.object(api, 'UPDATE_TIMEOUT', 0.01), patch.object(api, '_update_levels', side_effect=hang):
            with self.assertRaises(api.DemonlistAPIError):
                await api.fetch_levels()
        self.assertFalse(api._update_lock.locked())
        with patch.object(api, '_update_levels', AsyncMock(return_value=5)):
            self.assertEqual(5, await api.fetch_levels())

    async def test_scheduler_waits_an_hour_and_survives_error_and_busy_run(self):
        delays = []

        async def tick(delay):
            delays.append(delay)
            if len(delays) == 4:
                raise asyncio.CancelledError()

        with (
            patch.object(level_scheduler.asyncio, 'sleep', side_effect=tick),
            patch.object(level_scheduler, 'fetch_levels', AsyncMock(side_effect=[
                RuntimeError('offline'), api.LevelUpdateBusy(), 1837,
            ])) as update,
            self.assertLogs(level_scheduler.logger, level='INFO') as logs,
        ):
            with self.assertRaises(asyncio.CancelledError):
                await level_scheduler.run_hourly_level_updates()
        self.assertAlmostEqual(3600, delays[0], delta=1)
        self.assertEqual(3, update.await_count)
        self.assertTrue(all(not call.args and not call.kwargs for call in update.await_args_list))
        self.assertTrue(any('completed: 1837' in line for line in logs.output))

    async def test_cancelled_download_cancels_child_requests_and_unlocks(self):
        entered = asyncio.Event()
        stopped = []

        async def page(*args):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.append(True)

        with patch.object(api, '_request_collection', side_effect=page):
            task = asyncio.create_task(api._fetch_all_levels(object()))
            await entered.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(api.PAGE_WINDOW, len(stopped))

    async def test_catalog_warm_lookup_performs_no_queries_and_invalidation_reloads(self):
        conn = types.SimpleNamespace(execute=AsyncMock())
        cursors = [types.SimpleNamespace(fetchall=AsyncMock(return_value=rows)) for rows in (
            [{'id': 1, 'nickname': 'Player'}], [{'level_id': 1, 'level_name': 'Level'}],
        )]
        conn.execute.side_effect = cursors + cursors + cursors

        @asynccontextmanager
        async def connection():
            yield conn

        with patch.object(record_catalog, '_catalog', None), patch.object(record_catalog, 'get_db_connection', connection):
            first = await record_catalog.get_record_catalog()
            for _ in range(50):
                self.assertIs(first, await record_catalog.get_record_catalog())
            self.assertEqual(2, conn.execute.await_count)
            models.invalidate_record_catalog()
            self.assertIsNot(first, await record_catalog.get_record_catalog())
            self.assertEqual(4, conn.execute.await_count)
            with patch.object(record_catalog, '_loaded_at', 0):
                await record_catalog.get_record_catalog()
            self.assertEqual(6, conn.execute.await_count)

    async def test_level_batch_commits_or_rolls_back_without_invalidating_on_failure(self):
        for error in (None, RuntimeError('database error'), asyncio.CancelledError()):
            with self.subTest(error=type(error).__name__):
                conn = types.SimpleNamespace(begin=AsyncMock(), executemany=AsyncMock(side_effect=error),
                                             commit=AsyncMock(), rollback=AsyncMock())

                @asynccontextmanager
                async def connection():
                    yield conn

                before = models.get_record_catalog_version()
                with patch.object(models, 'get_db_connection', connection):
                    if error:
                        with self.assertRaises(type(error)):
                            await models.upsert_levels([(1, 'Level', 1, 'Creator', None)])
                        conn.rollback.assert_awaited_once()
                        conn.commit.assert_not_awaited()
                        self.assertEqual(before, models.get_record_catalog_version())
                    else:
                        await models.upsert_levels([(1, 'Level', 1, 'Creator', None)])
                        conn.commit.assert_awaited_once()
                        conn.rollback.assert_not_awaited()
                        self.assertGreater(models.get_record_catalog_version(), before)


if __name__ == '__main__':
    unittest.main()
