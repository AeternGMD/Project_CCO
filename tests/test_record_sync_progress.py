import types
import unittest
from unittest.mock import AsyncMock, patch

from handlers import admin
from services import demonlist_api as api
from utils.sync_progress import progress_bar, record_sync_text


class RecordSyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_paged_sync_backfills_links_and_reports_unchanged_records(self):
        player = dict(id=1, nickname='Fenya', api_sync=True, demonlist_id='7369')
        urls = [
            'https://www.youtube.com/watch?v=2cbTmRwfs0I?si=5SlgCS-Bw1sY1dzs',
            'https://www.youtube.com/watch?v=t6BBOIausH8?si=WwPvyT-Y2VyKtlSA',
            'https://youtu.be/5-wbdFlLle4?si=OpuISfUkXdXK0El3',
        ]
        records = [dict(level={'id': i}, percent=100, status='accepted', video_url=url)
                   for i, url in enumerate(urls, 1)]
        local = [dict(id=i, level_id=i, progress_start=0, progress_end=100,
                      status='Verified', video_url=None) for i in (1, 2, 3)]
        progress = AsyncMock()
        with (
            patch.object(api, 'get_player_by_id', AsyncMock(return_value=player)),
            patch.object(api, 'PAGE_SIZE', 2),
            patch.object(api, '_request_collection', AsyncMock(side_effect=[records[:2], records[2:]])) as fetch,
            patch.object(api, 'get_player_records', AsyncMock(return_value=local)),
            patch.object(api, 'update_record_status', AsyncMock()) as update,
            patch.object(api, 'add_record', AsyncMock()) as add,
        ):
            self.assertTrue(await api.sync_player_records(1, progress_callback=progress))
        self.assertEqual([0, 2], [c.args[3]['offset'] for c in fetch.await_args_list])
        self.assertEqual(3, update.await_count)
        add.assert_not_awaited()
        self.assertEqual('https://www.youtube.com/watch?v=5-wbdFlLle4', update.await_args.args[2])
        self.assertEqual(('records', 3, 3), progress.await_args.args)
        self.assertIn(('download', 2, None), [c.args for c in progress.await_args_list])

    async def test_partial_progress_does_not_block_completion_and_broken_reporter_does_not_abort(self):
        player = dict(id=1, nickname='Player', api_sync=True, demonlist_id='1')
        row = dict(level={'id': 2}, percent=100, status='accepted', video_url='https://youtu.be/5-wbdFlLle4')
        local = [dict(id=1, level_id=2, progress_start=0, progress_end=75, status='Manual')]
        with (
            patch.object(api, 'get_player_by_id', AsyncMock(return_value=player)),
            patch.object(api, '_request_collection', AsyncMock(return_value=[row])),
            patch.object(api, 'get_player_records', AsyncMock(return_value=local)),
            patch.object(api, 'update_record_status', AsyncMock()) as update,
            patch.object(api, 'add_record', AsyncMock()) as add,
            self.assertLogs(api.logger, level='WARNING'),
        ):
            self.assertTrue(await api.sync_player_records(1, progress_callback=AsyncMock(side_effect=RuntimeError('Telegram offline'))))
        update.assert_not_awaited()
        add.assert_awaited_once_with(1, 2, 0, 100, 'Verified', video_url='https://www.youtube.com/watch?v=5-wbdFlLle4')

    async def test_manual_sync_filters_players_counts_failures_and_throttles_edits(self):
        msg = types.SimpleNamespace(edit_text=AsyncMock())
        message = types.SimpleNamespace(answer=AsyncMock(return_value=msg))
        players = [dict(id=i, nickname=f'Player{i}', api_sync=True, demonlist_id=str(i)) for i in (1, 2)]
        players += [dict(id=3, nickname='Disabled', api_sync=False, demonlist_id='3'),
                    dict(id=4, nickname='No ID', api_sync=True, demonlist_id='-')]

        async def sync(pid, progress_callback):
            for i in range(101):
                await progress_callback('records', i, 100)
            return pid == 1

        with (
            patch.object(admin, 'fetch_levels', AsyncMock(return_value=1800)),
            patch('database.models.get_all_players', AsyncMock(return_value=players)),
            patch.object(admin, 'sync_player_records', side_effect=sync) as process,
        ):
            await admin.cmd_info_update(message)
        self.assertEqual([1, 2], [c.args[0] for c in process.await_args_list])
        self.assertLess(msg.edit_text.await_count, 10)
        final = msg.edit_text.await_args.args[0]
        self.assertIn('2/2 · 100%', final)
        self.assertIn('Успешно: 1; с ошибкой: 1', final)


class ProgressTextTests(unittest.TestCase):
    def test_progress_text_has_player_and_record_bars(self):
        text = record_sync_text(1800, 1, 4, 'Fenya', 'records', 20, 50)
        self.assertIn('1/4 · 25%', text)
        self.assertIn('20/50 · 40%', text)
        self.assertIn('Fenya', text)
        self.assertIn('Получено: 50', record_sync_text(1800, 0, 4, 'Fenya', 'download', 50))
        self.assertIn('0/0 · 100%', progress_bar(0, 0))
