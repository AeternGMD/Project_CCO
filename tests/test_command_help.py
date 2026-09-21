import ast
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch
import xml.etree.ElementTree as ET

from utils.command_help import PUBLIC_HELP, ADMIN_HELP, ROOT_HELP, command_help, help_overview
from utils.display import platform_label

if 'aiomysql' not in sys.modules and importlib.util.find_spec('aiomysql') is None:
    with patch.dict(sys.modules, {'aiomysql': types.ModuleType('aiomysql')}):
        from handlers import public, admin
else:
    from handlers import public, admin

from aiogram.types import Message


class HelpTests(unittest.TestCase):
    def test_every_registered_command_has_help_and_all_aliases_match(self):
        registered = set()
        base = Path(__file__).resolve().parents[1]
        for filename in ('public.py', 'admin.py', 'root.py'):
            tree = ast.parse((base / 'handlers' / filename).read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'Command':
                    registered.update(arg.value for arg in node.args if isinstance(arg, ast.Constant))
        documented = set()
        for section in (PUBLIC_HELP, ADMIN_HELP, ROOT_HELP):
            for aliases, expected in section.items():
                documented.update(aliases)
                for alias in aliases:
                    self.assertEqual(expected, command_help('/' + alias.upper() + '@bot', root=True))
        self.assertEqual(registered - {'start', 'help'}, documented)

    def test_help_is_valid_html_and_fits_in_one_telegram_message(self):
        texts = list(PUBLIC_HELP.values()) + list(ADMIN_HELP.values()) + list(ROOT_HELP.values())
        texts += [help_overview(), help_overview(admin=True), help_overview(root=True)]
        for text in texts:
            with self.subTest(text=text[:50]):
                root = ET.fromstring('<root>' + text + '</root>')
                self.assertTrue(all(element.tag in ('root', 'b', 'code') for element in root.iter()))
                self.assertLess(len(text.encode('utf-16-le')) // 2, 4096)

    def test_help_respects_roles(self):
        self.assertNotIn('/backup', help_overview())
        self.assertNotIn('/add_admin', help_overview(admin=True))
        self.assertIn('/add_admin', help_overview(root=True))
        self.assertIn('недоступна', command_help('backup'))
        self.assertIn('недоступна', command_help('add_admin', admin=True))
        self.assertIn('назначить администратора', command_help('add_admin', root=True))

    def test_help_matches_backup_ban_restart_and_level_input(self):
        self.assertIn('backup.sql', command_help('backup', admin=True))
        self.assertNotIn('database.db', command_help('backup', admin=True))
        self.assertIn('30d', command_help('ban', admin=True))
        self.assertIn('Код из GitHub не скачивает', command_help('restart', admin=True))
        self.assertIn('топ-5', command_help('p'))
        for command in ('r', 'dr'):
            self.assertNotIn('#1537', command_help(command, admin=True))

    def test_platform_labels_do_not_change_unknown_values(self):
        self.assertEqual('ПК', platform_label('PC'))
        self.assertEqual('Мобильное устройство', platform_label('mob'))
        self.assertEqual('Мобильное устройство', platform_label('mobile'))
        self.assertEqual('other', platform_label('other'))


class HelpHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_help_uses_explicit_html_and_applies_access_control(self):
        message = types.SimpleNamespace(text='/help r', from_user=types.SimpleNamespace(id=-123), answer=AsyncMock())
        for access in (False, True):
            with patch('database.models.is_admin', AsyncMock(return_value=access)):
                await public.cmd_start(message)
            self.assertEqual('HTML', message.answer.await_args.kwargs['parse_mode'])
            self.assertEqual(command_help('r', admin=access), message.answer.await_args.args[0])

    async def test_profile_command_sends_compact_profile_without_ids(self):
        player = {'id': 42, 'nickname': 'Mr Spaced', 'platform': 'pc', 'location': '-'}
        records = [dict(level_id=i, level_name=f'Level_{i:04d}', position=i, creator='Creator',
                        progress_start=0, progress_end=100, status='Manual') for i in range(1, 501)]
        message = types.SimpleNamespace(text='/p Mr Spaced', answer=AsyncMock())
        with (
            patch.object(public, 'get_player_by_nick', AsyncMock(return_value=player)) as lookup,
            patch.object(public, 'get_player_records', AsyncMock(return_value=records)),
            patch.object(public, 'get_leaderboard', AsyncMock(return_value=[])),
            patch('database.models.get_ambiguous_level_names', AsyncMock(return_value=set())),
        ):
            await public.cmd_profile(message)
        lookup.assert_awaited_once_with('Mr Spaced')
        text = message.answer.await_args.args[0]
        self.assertEqual(5, text.count('Level_'))
        self.assertNotIn('@42', text)
        self.assertNotIn('ID игрока', text)

    async def test_try_looks_up_numeric_names_not_ids(self):
        message = Mock(spec=Message)
        message.answer = AsyncMock()
        state = types.SimpleNamespace(clear=AsyncMock())
        player = {'id': 42, 'nickname': 'Tester'}
        row = dict(level_id=9, level_name='123', position=1)
        with (
            patch('database.models.get_ambiguous_level_names', AsyncMock(return_value=set())),
            patch.object(public, 'get_levels_by_name', AsyncMock(return_value=[row])) as lookup,
            patch.object(public, 'get_level_by_id', AsyncMock()) as by_id,
            patch('services.calculator.calculate_hypothetical_score', AsyncMock(return_value=1.0)) as calculate,
            patch('services.calculator.get_leaderboard', AsyncMock(return_value=[])),
        ):
            await public.process_try_query(message, state, player, ['123'], [], [], set())
        lookup.assert_awaited_once_with('123')
        by_id.assert_not_awaited()
        calculate.assert_awaited_once_with(42, [9])

    async def test_legacy_record_path_also_uses_name_lookup(self):
        message = types.SimpleNamespace(answer=AsyncMock())
        with (
            patch.object(admin, 'get_levels_by_name', AsyncMock(return_value=[])) as lookup,
            patch.object(admin, 'get_level_by_id', AsyncMock()) as by_id,
        ):
            await admin.handle_level_query(message, 42, '123', 'add', 0, 100)
        lookup.assert_awaited_once_with('123')
        by_id.assert_not_awaited()

    async def test_try_reports_when_there_is_nothing_new(self):
        message = Mock(spec=Message)
        message.answer = AsyncMock()
        state = types.SimpleNamespace(clear=AsyncMock())
        with patch('database.models.get_ambiguous_level_names', AsyncMock(return_value=set())):
            await public.process_try_query(message, state, {'id': 42}, [], [], [], set())
        self.assertIn('Нет новых прохождений', message.answer.await_args.args[0])

    async def test_range_limit_matches_documented_thirty_levels(self):
        message = types.SimpleNamespace(text='/lp 1-31', answer=AsyncMock())
        with patch('database.models.get_levels_with_victors', AsyncMock(return_value=[])) as lookup:
            await public.cmd_lvlp(message)
            lookup.assert_not_awaited()
            message.text = '/lp 1-30'
            await public.cmd_lvlp(message)
            lookup.assert_awaited_once_with(1, 30)


if __name__ == '__main__':
    unittest.main()
