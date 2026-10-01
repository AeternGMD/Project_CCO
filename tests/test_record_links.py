from contextlib import asynccontextmanager
import types
import unittest
from unittest.mock import AsyncMock, patch

from handlers import public, record_input, admin, inline
from services import demonlist_api as api
from services.record_resolver import RecordCatalog
from database import models, connection
from utils.record_links import youtube_url, LinkedText, link_status
from utils.profile_pages import split_profile_text


URL = 'https://www.youtube.com/watch?v=9aFft6uyyk8'
PLAYER = {'id': 42, 'nickname': '😀 <Player>', 'platform': 'pc', 'location': '-'}


def completion(i, video=URL):
    return dict(id=i, level_id=i, level_name=f'😀 Level_{i:04d}', creator='Author',
                position=i, progress_start=0, progress_end=100, status='Manual', video_url=video)


class LinkTests(unittest.TestCase):
    def test_youtube_validation_and_normalization(self):
        for url in (URL, URL + '&amp;ab_channel=Test', 'https://youtu.be/9aFft6uyyk8?t=4',
                    URL + '?si=sharing-token', URL + '%3Fsi%3Dsharing-token',
                    'https://m.youtube.com/shorts/9aFft6uyyk8', 'https://youtube.com/live/9aFft6uyyk8'):
            self.assertEqual(URL, youtube_url(url))
        for url in (None, '', 'javascript:alert(1)', 'https://youtube.com.evil.test/watch?v=9aFft6uyyk8',
                    'https://youtube.com@evil.test/watch?v=9aFft6uyyk8', 'https://youtube.com/channel/test',
                    'https://youtu.be/not-video', 'https://[broken'):
            self.assertIsNone(youtube_url(url))

    def test_fenya_urls_with_duplicate_question_mark(self):
        cases = {
            'https://www.youtube.com/watch?v=2cbTmRwfs0I?si=5SlgCS-Bw1sY1dzs': '2cbTmRwfs0I',
            'https://www.youtube.com/watch?v=t6BBOIausH8?si=WwPvyT-Y2VyKtlSA': 't6BBOIausH8',
            'https://www.youtube.com/watch?v=hhEIuysc7u4?si=evLmROm3QrnJ10Wr': 'hhEIuysc7u4',
            'https://youtu.be/5-wbdFlLle4?si=OpuISfUkXdXK0El3': '5-wbdFlLle4',
        }
        for source, video_id in cases.items():
            self.assertEqual(f'https://www.youtube.com/watch?v={video_id}', youtube_url(source))
        self.assertIsNone(youtube_url('https://youtube.com.evil.test/watch?v=hhEIuysc7u4?si=x'))
        self.assertIsNone(youtube_url('https://youtube.com/watch?v=hhEIuysc7u4EXTRA'))

    def test_status_links_survive_all_pages_and_keep_unicode_offsets(self):
        records = [completion(i, URL if i % 2 else None) for i in range(1, 301)]
        linked_count = 0
        page = 1
        while True:
            text, markup = public.generate_player_profile_page(PLAYER, None, records, set(), page)
            encoded = text.encode('utf-16-le')
            self.assertLessEqual(len(encoded) // 2, 4096)
            for entity in text.entities:
                self.assertEqual('Внесено вручную', encoded[entity.offset*2:(entity.offset+entity.length)*2].decode('utf-16-le'))
                self.assertEqual(URL, entity.url)
            linked_count += len(text.entities)
            pages = [public.ProfileCallback.unpack(b.callback_data).page for row in markup.inline_keyboard for b in row]
            if page + 1 not in pages:
                break
            page += 1
        self.assertEqual(150, linked_count)
        brief, _ = public.generate_player_profile_page(PLAYER, None, records, set())
        self.assertEqual(3, len(brief.entities))

    def test_no_video_keeps_original_plain_status(self):
        record = completion(1, None)
        text = public.generate_player_profile_text(PLAYER, None, [record], set())
        self.assertIn('Внесено вручную', text)
        self.assertEqual([], text.entities)
        record['status'] = 'Verified'
        text = public.generate_player_profile_text(PLAYER, None, [record], set())
        self.assertIn('Подтверждено Demonlist', text)
        self.assertEqual([], text.entities)

    def test_entity_across_page_boundary_is_safely_clipped(self):
        entities = []
        link_status(entities, '😀', 'Внесено вручную', completion(1))
        text = LinkedText('😀Внесено вручную', entities)
        pages = split_profile_text(text, limit=5)
        self.assertEqual(text, ''.join(pages))
        self.assertEqual(len('Внесено вручную'), sum(e.length for p in pages for e in p.entities))


class LinkHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_101_levels_sent_in_bounded_messages_without_loss(self):
        levels = [dict(level_name=f'Level_{i:04d}' + '😀' * 40, creator='Creator',
                       position=i, victors_count=2) for i in range(1, 102)]
        for command in ('/lp 1-101', '/lp 101-1'):
            message = types.SimpleNamespace(text=command, answer=AsyncMock())
            with patch('database.models.get_levels_with_victors', AsyncMock(return_value=levels)) as fetch:
                await public.cmd_lvlp(message)
            fetch.assert_awaited_once_with(1, 101)
            messages = [call.args[0] for call in message.answer.await_args_list]
            self.assertGreater(len(messages), 1)
            self.assertTrue(all(len(p.encode('utf-16-le')) // 2 <= 4096 for p in messages))
            self.assertTrue(all(''.join(messages).count(row['level_name']) == 1 for row in levels))

    async def test_manual_link_passed_to_write_and_bulk_link_rejected(self):
        catalog = RecordCatalog([dict(id=42, nickname='Tester')],
                                [dict(level_id=1, level_name='Level', creator='A')])
        message = types.SimpleNamespace(text=f'/r Tester: Level {URL}', from_user=types.SimpleNamespace(id=1),
                                        chat=types.SimpleNamespace(id=2), answer=AsyncMock())
        with patch.object(record_input, 'get_record_catalog', AsyncMock(return_value=catalog)), \
                patch.object(admin, 'process_record_action', AsyncMock()) as write:
            await record_input.handle_record_command(message)
            self.assertEqual(URL, write.await_args.kwargs['video_url'])
            write.reset_mock()
            message.text = f'/r Tester: Level, Level {URL}'
            await record_input.handle_record_command(message)
            write.assert_not_awaited()
            self.assertIn('одному уровню', message.answer.await_args.args[0])

    async def test_api_backfills_existing_verified_record_and_imports_video(self):
        player = dict(PLAYER, api_sync=True, demonlist_id='1')
        rows = [dict(percent=100, status='accepted', video_url=URL + '&amp;x=1', level={'id': i}) for i in (1, 2)]
        local = completion(1, None)
        local['status'] = 'Verified'
        with (
            patch.object(api, 'get_player_by_id', AsyncMock(return_value=player)),
            patch.object(api, '_request_collection', AsyncMock(return_value=rows)),
            patch.object(api, 'get_player_records', AsyncMock(return_value=[local])),
            patch.object(api, 'update_record_status', AsyncMock()) as update,
            patch.object(api, 'add_record', AsyncMock()) as add,
        ):
            self.assertTrue(await api.sync_player_records(42))
        update.assert_awaited_once_with(1, 'Verified', URL)
        add.assert_awaited_once_with(42, 2, 0, 100, 'Verified', video_url=URL)

    async def test_existing_completion_video_is_preserved_when_reentered_without_url(self):
        conn = types.SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())
        conn.execute.return_value = types.SimpleNamespace(fetchone=AsyncMock(return_value={'video_url': URL}))

        @asynccontextmanager
        async def connect():
            yield conn

        with patch.object(models, 'get_db_connection', connect):
            await models.add_record(42, 1, 0, 100, 'Manual')
        inserts = [c for c in conn.execute.await_args_list if 'INSERT INTO records' in c.args[0]]
        self.assertEqual(URL, inserts[0].args[1][-1])

    async def test_migration_adds_optional_column_without_deleting_records(self):
        conn = types.SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())

        @asynccontextmanager
        async def connect():
            yield conn

        with patch.object(connection, 'get_db_connection', connect):
            await connection.init_db()
        sql = '\n'.join(c.args[0] for c in conn.execute.await_args_list)
        self.assertIn('ADD COLUMN IF NOT EXISTS video_url', sql)
        self.assertNotIn('DELETE FROM', sql)
        self.assertNotIn('DROP', sql)

    async def test_inline_profile_passes_link_entities_to_telegram(self):
        query = types.SimpleNamespace(query='Tester', answer=AsyncMock())
        with (
            patch.object(inline, 'search_players', AsyncMock(return_value=[PLAYER])),
            patch.object(inline, 'search_levels', AsyncMock(return_value=[])),
            patch.object(inline, 'get_player_records', AsyncMock(return_value=[completion(1)])),
            patch.object(inline, 'get_leaderboard', AsyncMock(return_value=[])),
            patch.object(inline, 'get_ambiguous_level_names', AsyncMock(return_value=set())),
        ):
            await inline.inline_search(query)
        content = query.answer.await_args.args[0][0].input_message_content
        self.assertEqual(URL, content.entities[0].url)
        self.assertTrue(content.disable_web_page_preview)

    async def test_level_card_links_verified_status(self):
        row = dict(completion(1), status='Verified', nickname='😀 Player')
        cursor = types.SimpleNamespace(fetchall=AsyncMock(return_value=[row]))
        conn = types.SimpleNamespace(execute=AsyncMock(return_value=cursor))

        @asynccontextmanager
        async def connect():
            yield conn

        with patch.object(connection, 'get_db_connection', connect):
            text = await public.generate_level_info_text(completion(1))
        entity = text.entities[0]
        self.assertEqual(URL, entity.url)
        self.assertEqual('Подтверждено Demonlist', text.encode('utf-16-le')[
            entity.offset*2:(entity.offset+entity.length)*2].decode('utf-16-le'))


if __name__ == '__main__':
    unittest.main()
