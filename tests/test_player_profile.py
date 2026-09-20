import importlib.util
import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

# Rendering and handler tests use mocked database calls, not a MySQL server.
if "aiomysql" not in sys.modules and importlib.util.find_spec("aiomysql") is None:
    with patch.dict(sys.modules, {"aiomysql": types.ModuleType("aiomysql")}):
        from handlers import public, inline
else:
    from handlers import public, inline

from aiogram.types import Message
from utils.profile_pages import split_profile_text


PLAYER = {"id": 42, "nickname": "Tester", "platform": "pc", "location": "-"}


def record(position, start=0, end=100):
    return {
        "level_id": position, "level_name": f"Level_{position:04d}",
        "position": position, "creator": "Creator", "status": "Manual",
        "progress_start": start, "progress_end": end,
    }


class ProfileTests(unittest.TestCase):
    def test_all_completions_sorted_with_status_and_separate_progresses(self):
        records = [record(i) for i in range(12, 0, -1)]
        records[0]["status"] = "Verified"
        records.extend([record(13, end=75), record(14, start=30)])
        text = public.generate_player_profile_text(PLAYER, None, records, {"level_0012"})
        self.assertIn("Пройденные уровни (12)", text)
        completion_text, progress_text = text.split("📈 Прогрессы:")
        indices = [completion_text.index(f"Level_{i:04d}") for i in range(1, 13)]
        self.assertEqual(sorted(indices), indices)
        self.assertIn("Level_0012 [Creator] (Топ-12) - Подтверждено", completion_text)
        self.assertNotIn("Level_0013", completion_text)
        self.assertIn("75%", progress_text)
        self.assertIn("30-100%", progress_text)

    def test_empty_profile_needs_no_navigation(self):
        text, markup = public.generate_player_profile_page(PLAYER, None, [], set())
        self.assertIn("Нет пройденных уровней", text)
        self.assertIn("ID игрока в боте: @42", text)
        self.assertIsNone(markup)

    def test_long_unicode_lines_are_split_without_losing_text(self):
        text = "😀" * 4500 + "\n" + "Уровень\n" * 800
        pages = split_profile_text(text)
        self.assertEqual(text, "".join(pages))
        self.assertTrue(all(len(page.encode("utf-16-le")) // 2 <= 3800 for page in pages))

    def test_every_level_is_reachable_by_navigation_within_telegram_limit(self):
        records = [record(i) for i in range(1, 201)]
        for row in records:
            row["level_name"] += "😀" * 200
        texts = []
        page = 1
        while True:
            text, markup = public.generate_player_profile_page(PLAYER, None, records, set(), page)
            self.assertLessEqual(len(text.encode("utf-16-le")) // 2, 4096)
            texts.append(text)
            buttons = [button for row in markup.inline_keyboard for button in row]
            callbacks = [public.ProfileCallback.unpack(button.callback_data) for button in buttons]
            self.assertTrue(all(cb.player_id == PLAYER["id"] for cb in callbacks))
            if page > 1:
                self.assertIn(page - 1, [cb.page for cb in callbacks])
            next_pages = [cb.page for cb in callbacks if cb.page > page]
            if not next_pages:
                break
            self.assertEqual([page + 1], next_pages)
            page = next_pages[0]
            self.assertLess(page, 201)
        self.assertGreater(page, 1)
        full_text = "".join(texts)
        for row in records:
            self.assertEqual(1, full_text.count(row["level_name"]))
        last, _ = public.generate_player_profile_page(PLAYER, None, records, set(), 99999)
        self.assertEqual(texts[-1], last)


class ProfileHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_page_callback_edits_both_regular_and_inline_profiles(self):
        records = [record(i) for i in range(1, 201)]
        for is_inline in (False, True):
            with self.subTest(inline=is_inline):
                message = Mock(spec=Message)
                message.edit_text = AsyncMock()
                query = types.SimpleNamespace(
                    answer=AsyncMock(), message=None if is_inline else message,
                    inline_message_id="inline-id" if is_inline else None,
                    bot=types.SimpleNamespace(edit_message_text=AsyncMock()),
                )
                with (
                    patch("database.models.get_player_by_id", AsyncMock(return_value=PLAYER)),
                    patch("database.models.get_ambiguous_level_names", AsyncMock(return_value=set())),
                    patch.object(public, "get_leaderboard", AsyncMock(return_value=[])),
                    patch.object(public, "get_player_records", AsyncMock(return_value=records)),
                ):
                    await public.cb_profile(query, public.ProfileCallback(player_id=42, page=2))
                query.answer.assert_awaited_once()
                edit = query.bot.edit_message_text if is_inline else message.edit_text
                edit.assert_awaited_once()
                self.assertIn("Страница 2/", edit.await_args.args[0])
                if is_inline:
                    self.assertEqual("inline-id", edit.await_args.kwargs["inline_message_id"])

    async def test_inline_search_sends_first_page_and_navigation(self):
        query = types.SimpleNamespace(query="Tester", answer=AsyncMock())
        with (
            patch.object(inline, "search_players", AsyncMock(return_value=[PLAYER])),
            patch.object(inline, "search_levels", AsyncMock(return_value=[])),
            patch.object(inline, "get_leaderboard", AsyncMock(return_value=[])),
            patch.object(inline, "get_player_records", AsyncMock(return_value=[record(i) for i in range(1, 201)])),
            patch.object(inline, "get_ambiguous_level_names", AsyncMock(return_value=set())),
        ):
            await inline.inline_search(query)
        result = query.answer.await_args.args[0][0]
        self.assertIn("Пройденные уровни (200)", result.input_message_content.message_text)
        self.assertLessEqual(len(result.input_message_content.message_text), 4096)
        self.assertIsNotNone(result.reply_markup)


if __name__ == "__main__":
    unittest.main()
