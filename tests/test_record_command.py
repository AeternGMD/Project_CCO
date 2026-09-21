import importlib.util
import os
import sys
import time
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

from services.record_resolver import RecordCatalog, resolve_record_command

with patch.dict(os.environ, {'BOT_TOKEN': 'test', 'CHANNEL_ID': '-1'}):
    if 'aiomysql' not in sys.modules and importlib.util.find_spec('aiomysql') is None:
        with patch.dict(sys.modules, {'aiomysql': types.ModuleType('aiomysql')}):
            from handlers import admin, record_input
    else:
        from handlers import admin, record_input

from aiogram.types import Message
from database import models


def level(lid, name, creator='Creator'):
    return {'level_id': lid, 'level_name': name, 'creator': creator}


PLAYERS = [{'id': 1, 'nickname': 'Mr'}, {'id': 2, 'nickname': 'Mr Spaced'},
           {'id': 3, 'nickname': 'player'}]
LEVELS = [level(1, 'Tidal Wave'), level(2, 'Bloodbath'), level(3, 'Spaced Tidal Wave'),
          level(4, 'Theory of Everything 2'), level(5, 'Level'), level(6, 'Level 60'),
          level(7, 'Shared', 'A'), level(8, 'Shared', 'B'), level(9, '123'),
          level(123, 'Other'), level(10, "Don't Stop"), level(11, 'Name, Part Two')]
CATALOG = RecordCatalog(PLAYERS, LEVELS)


class ResolverTests(unittest.TestCase):
    def test_multiword_names_numbers_apostrophes_and_quotes(self):
        cases = [
            ('/r Mr Spaced Theory of Everything 2', 2, [4]),
            ('/r player Tidal Wave, Bloodbath', 3, [1, 2]),
            ('/record@bot Mr Spaced: Tidal Wave, Theory of Everything 2', 2, [1, 4]),
            ('/r "Mr Spaced" "Tidal Wave" 100', 2, [1]),
            ("/r player Don't Stop", 3, [10]),
            ('/r player "Name, Part Two" 75', 3, [11]),
            ('/r @2: Tidal Wave, Theory of Everything 2', 2, [1, 4]),
            ('/r PLAYER tidal   wave', 3, [1]),
        ]
        for command, pid, lids in cases:
            with self.subTest(command=command):
                plans = resolve_record_command(command, CATALOG)
                self.assertEqual(1, len(plans))
                self.assertEqual(pid, plans[0].player_id)
                self.assertEqual(lids, [group[0].level_id for group in plans[0].groups])

    def test_overlapping_player_names_do_not_choose_longest_silently(self):
        plans = resolve_record_command('/r Mr Spaced Tidal Wave', CATALOG)
        self.assertEqual([1, 2], [plan.player_id for plan in plans])
        self.assertEqual([3, 1], [plan.groups[0][0].level_id for plan in plans])
        self.assertEqual(2, resolve_record_command('/r Mr Spaced: Tidal Wave', CATALOG)[0].player_id)

    def test_trailing_number_can_be_name_or_progress(self):
        options = resolve_record_command('/r player Level 60', CATALOG)[0].groups[0]
        self.assertEqual({(6, ((0, 100),)), (5, ((0, 60),))},
                         {(option.level_id, option.progresses) for option in options})
        explicit = resolve_record_command('/r player Level = 60%', CATALOG)[0].groups[0]
        self.assertEqual(1, len(explicit))
        self.assertEqual(5, explicit[0].level_id)
        quoted = resolve_record_command('/r player "Level 60"', CATALOG)[0].groups[0]
        self.assertEqual([6], [o.level_id for o in quoted])

    def test_numeric_name_is_never_interpreted_as_a_level_id(self):
        options = resolve_record_command('/r player 123', CATALOG)[0].groups[0]
        self.assertEqual({9}, {o.level_id for o in options})
        for action in ('add', 'del'):
            for value in ('#123', '1', '#1'):
                with self.subTest(action=action, value=value), self.assertRaises(ValueError):
                    resolve_record_command(f'/r player {value}', CATALOG, action)

    def test_choice_label_uses_creator_and_position_not_global_id(self):
        catalog = RecordCatalog(PLAYERS, [dict(level(1537, 'Shared', 'A'), position=10),
                                          dict(level(1538, 'Shared', 'B'), position=20)])
        options = resolve_record_command('/r player Shared', catalog)[0].groups[0]
        self.assertIn('Топ-10', options[0].label)
        self.assertIn('[A]', options[0].label)
        self.assertNotIn('1537', options[0].label)
        self.assertIn('[B]', options[1].label)

    def test_runs_and_individual_progress_in_batch(self):
        groups = resolve_record_command('/r Mr Spaced: Tidal Wave 60 | 40-100, Bloodbath = 100', CATALOG)[0].groups
        self.assertEqual(((0, 60), (40, 100)), groups[0][0].progresses)
        self.assertEqual(((0, 100),), groups[1][0].progresses)

    def test_same_named_levels_remain_distinct(self):
        options = resolve_record_command('/r player Shared', CATALOG)[0].groups[0]
        self.assertEqual({7, 8}, {o.level_id for o in options})

    def test_unknown_invalid_and_empty_input_rejected(self):
        for command in ('/r', '/r player', '/r player Missing', '/r player Bloodbath,',
                        '/r player ,Bloodbath', '/r player Bloodbath,,Tidal Wave',
                        '/r player Bloodbath, Missing', '/r player Bloodbath = 101',
                        '/r player Bloodbath = 70-40', '/r player Bloodbath = 20',
                        '/r player "Unclosed', '/r player Bloodbath = '):
            with self.subTest(command=command), self.assertRaises(ValueError):
                resolve_record_command(command, CATALOG)

    def test_delete_resolves_numeric_name_without_progress(self):
        plan = resolve_record_command('/dr Mr Spaced: Level 60', CATALOG, 'del')[0]
        self.assertEqual([6], [o.level_id for o in plan.groups[0]])


class HandlerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        record_input._pending.clear()
        self.catalog_patch = patch.object(record_input, 'get_record_catalog', AsyncMock(return_value=CATALOG))
        self.catalog_patch.start()
        self.addCleanup(self.catalog_patch.stop)
        self.write_patch = patch.object(admin, 'process_record_action', AsyncMock())
        self.write = self.write_patch.start()
        self.addCleanup(self.write_patch.stop)
        self.message = Mock(spec=Message)
        self.message.message_id = 77
        self.message.from_user = types.SimpleNamespace(id=100)
        self.message.chat = types.SimpleNamespace(id=200)
        self.message.answer = AsyncMock(return_value=self.message)
        self.message.edit_text = AsyncMock(return_value=self.message)

    async def start(self, text):
        self.message.text = text
        await admin.cmd_record(self.message)

    async def click(self, work, index, owner=100):
        query = types.SimpleNamespace(from_user=types.SimpleNamespace(id=owner),
                                      message=self.message, answer=AsyncMock())
        await record_input.choose_record(query, record_input.RecordChoice(token=work.token, index=index))
        return query

    async def test_bulk_deduplicates_names(self):
        await self.start('/r Mr Spaced: Tidal Wave, Bloodbath, tidal wave')
        self.assertEqual([(self.message, 'add', 2, 1, 0, 100), (self.message, 'add', 2, 2, 0, 100)],
                         [call.args for call in self.write.await_args_list])

    async def test_unknown_aborts_entire_batch(self):
        await self.start('/r player Bloodbath, Missing')
        self.write.assert_not_awaited()
        self.assertIn('Ничего не изменено', self.message.answer.await_args.args[0])

    async def test_removed_id_input_never_writes_and_delete_error_uses_delete_example(self):
        for command in ('/r player Bloodbath, #1', '/dr player #1'):
            self.message.text = command
            if command.startswith('/dr'):
                await admin.cmd_del_record(self.message)
                text = self.message.answer.await_args.args[0]
                self.assertIn('Пример: /dr', text)
                self.assertNotIn('= 60%', text)
                self.assertNotIn('Пример: /r ', text)
            else:
                await admin.cmd_record(self.message)
            self.write.assert_not_awaited()

    async def test_player_then_level_selection_and_double_click(self):
        await self.start('/r Mr Spaced Tidal Wave, Shared')
        self.write.assert_not_awaited()
        work = next(iter(record_input._pending.values()))
        # Other administrators cannot choose for the command author.
        await self.click(work, 1, owner=999)
        self.assertIn(work.token, record_input._pending)
        await self.click(work, 1)
        self.write.assert_not_awaited()
        work = next(iter(record_input._pending.values()))
        await self.click(work, 1)
        self.assertEqual([1, 8], [call.args[3] for call in self.write.await_args_list])
        await self.click(work, 1)
        self.assertEqual(2, self.write.await_count)

    async def test_expiry_cancellation_and_catalog_change_do_not_write(self):
        for mode in ('expired', 'cancel', 'changed'):
            with self.subTest(mode=mode):
                record_input._pending.clear()
                await self.start('/r player Shared')
                work = next(iter(record_input._pending.values()))
                if mode == 'expired':
                    work.expires = time.monotonic() - 1
                if mode == 'changed':
                    models.invalidate_record_catalog()
                await self.click(work, -1 if mode == 'cancel' else 0)
                self.write.assert_not_awaited()

    async def test_pending_state_is_bounded(self):
        for i in range(record_input.MAX_PENDING + 5):
            work = record_input.PendingRecord(str(i), i, 200, 'add', [], 0, time.monotonic() + 300)
            record_input.remember(work)
        self.assertEqual(record_input.MAX_PENDING, len(record_input._pending))
        self.assertNotIn('0', record_input._pending)


if __name__ == '__main__':
    unittest.main()
