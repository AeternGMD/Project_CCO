import importlib.util
import os
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

from utils.record_command import parse_record_command

# No real database or Telegram credentials are needed for handler tests.
with patch.dict(os.environ, {"BOT_TOKEN": "test", "CHANNEL_ID": "-1"}):
    if "aiomysql" not in sys.modules and importlib.util.find_spec("aiomysql") is None:
        with patch.dict(sys.modules, {"aiomysql": types.ModuleType("aiomysql")}):
            from handlers import admin
    else:
        from handlers import admin


class RecordParserTests(unittest.TestCase):
    def test_bulk_completions_and_quoted_names(self):
        cases = [
            ('/r player Bloodbath,Tartarus, Sonic Wave', 'player', ['Bloodbath', 'Tartarus', 'Sonic Wave']),
            ('/record@bot "Mr Spaced" "Tidal Wave", Bloodbath', 'Mr Spaced', ['Tidal Wave', 'Bloodbath']),
            ('/r player 123, 456', 'player', ['123', '456']),
            ('/r player "Name, Part Two", Other', 'player', ['Name, Part Two', 'Other']),
            ('/r player Bloodbath, bloodbath, Tartarus', 'player', ['Bloodbath', 'Tartarus']),
            ('/r player Theory of Everything 2, 8o', 'player', ['Theory of Everything 2', '8o']),
        ]
        for command, nick, names in cases:
            with self.subTest(command=command):
                self.assertEqual((nick, [(name, 0, 100) for name in names]), parse_record_command(command))

    def test_existing_single_level_progress_syntax(self):
        cases = [
            ('/r player Bloodbath', [('Bloodbath', 0, 100)]),
            ('/r player "Tidal Wave" 100', [('Tidal Wave', 0, 100)]),
            ('/r player Bloodbath 60% | 40-100', [('Bloodbath', 0, 60), ('Bloodbath', 40, 100)]),
            ('/r player "Name, Part Two" 75', [('Name, Part Two', 0, 75)]),
        ]
        for command, expected in cases:
            with self.subTest(command=command):
                self.assertEqual(('player', expected), parse_record_command(command))

    def test_invalid_lists_are_rejected_before_any_writes(self):
        for command in ('/r player', '/r player A,', '/r player ,A', '/r player A,,B',
                        '/r player A, ,B', '/r player "Unclosed, B', '/r player A, "", B'):
            with self.subTest(command=command), self.assertRaises(ValueError):
                parse_record_command(command)


class BulkRecordTests(unittest.IsolatedAsyncioTestCase):
    async def test_records_all_matches_and_continues_after_unknown_or_ambiguous_level(self):
        player = {"id": 42, "nickname": "Tester", "platform": "pc"}
        levels = {
            1: {"level_id": 1, "level_name": "Tidal Wave", "position": 1},
            2: {"level_id": 2, "level_name": "Bloodbath", "position": 2},
            3: {"level_id": 3, "level_name": "Shared", "position": 3},
            4: {"level_id": 4, "level_name": "Shared", "position": 4},
        }
        message = types.SimpleNamespace(
            text='/r Tester Tidal Wave, Missing, Shared, Bloodbath, Bloodbath',
            answer=AsyncMock(), bot=object(),
        )

        async def lookup(name):
            return [level for level in levels.values() if level['level_name'] == name]

        with (
            patch.object(admin, "get_player_by_nick", AsyncMock(return_value=player)),
            patch.object(admin, "get_player_by_id", AsyncMock(return_value=player)),
            patch.object(admin, "get_levels_by_name", AsyncMock(side_effect=lookup)),
            patch.object(admin, "get_level_by_id", AsyncMock(side_effect=levels.get)),
            patch.object(admin, "get_leaderboard", AsyncMock(return_value=[])),
            patch("services.calculator.calculate_progress_eligibility", AsyncMock(return_value=True)),
            patch.object(admin, "add_record", AsyncMock()) as add,
            patch.object(admin, "send_record_notification", AsyncMock()) as notify,
        ):
            await admin.cmd_record(message)

        self.assertEqual([(42, 1, 0, 100, 'Manual'), (42, 2, 0, 100, 'Manual')],
                         [call.args for call in add.await_args_list])
        self.assertEqual(2, notify.await_count)
        replies = [call.args[0] for call in message.answer.await_args_list]
        self.assertTrue(any('Missing' in text and 'не найден' in text for text in replies))
        keyboards = [call.kwargs['reply_markup'] for call in message.answer.await_args_list
                     if 'reply_markup' in call.kwargs]
        self.assertEqual(1, len(keyboards))
        choices = [admin.RecordCallback.unpack(row[0].callback_data) for row in keyboards[0].inline_keyboard]
        self.assertEqual([3, 4], [choice.level_id for choice in choices])
        self.assertTrue(all(choice.player_id == 42 and choice.progress_start == 0
                            and choice.progress_end == 100 for choice in choices))

    async def test_invalid_list_does_not_start_processing(self):
        message = types.SimpleNamespace(text='/r Tester Bloodbath,', answer=AsyncMock())
        with patch.object(admin, "handle_level_query", AsyncMock()) as handle:
            await admin.cmd_record(message)
        handle.assert_not_awaited()
        message.answer.assert_awaited_once()


if __name__ == '__main__':
    unittest.main()
