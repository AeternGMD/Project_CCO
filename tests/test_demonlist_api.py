import sys
import types
import unittest
from unittest.mock import AsyncMock, call, patch


# These tests do not open a database connection. A tiny driver stub keeps them
# runnable in the lightweight development environment, which lacks aiomysql.
fake_aiomysql = types.ModuleType("aiomysql")
fake_aiomysql.DictCursor = object()
fake_aiomysql.create_pool = AsyncMock()
sys.modules.setdefault("aiomysql", fake_aiomysql)

from services import demonlist_api


def make_level(level_id, placement):
    return {
        "id": level_id,
        "ingame_id": 100_000 + level_id,
        "placement": placement,
        "name": f"Level {placement}",
        "holder": "Creator",
    }


class FakeResponse:
    def __init__(self, levels):
        self.levels = levels

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def raise_for_status(self):
        return None

    async def json(self):
        return {"message": "success", "data": {"levels": self.levels}}


class FakeSession:
    def __init__(self, pages):
        self.pages = pages
        self.offsets = []

    def get(self, endpoint, params):
        offset = params["offset"]
        self.offsets.append(offset)
        return FakeResponse(self.pages.get(offset, []))


class FakeClientSession:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class DemonlistAPITests(unittest.IsolatedAsyncioTestCase):
    async def test_fetches_level_list_in_small_pages(self):
        first_page = [make_level(i, i) for i in range(1, 51)]
        second_page = [make_level(51, 51), make_level(52, 52)]
        session = FakeSession({0: first_page, 50: second_page})

        levels = await demonlist_api._fetch_all_levels(session)

        self.assertEqual(52, len(levels))
        self.assertEqual(list(range(1, 53)), [level["placement"] for level in levels])
        self.assertIn(0, session.offsets)
        self.assertIn(50, session.offsets)

    async def test_fetch_levels_writes_one_database_batch(self):
        raw_levels = [make_level(7, 1), make_level(8, 2)]
        progress = AsyncMock()

        with (
            patch.object(demonlist_api.aiohttp, "ClientSession", return_value=FakeClientSession()),
            patch.object(demonlist_api, "_fetch_all_levels", AsyncMock(return_value=raw_levels)),
            patch.object(demonlist_api, "upsert_levels", AsyncMock()) as upsert,
        ):
            updated = await demonlist_api.fetch_levels(progress_callback=progress)

        self.assertEqual(2, updated)
        upsert.assert_awaited_once_with([
            (7, "Level 1", 1, "Creator", 100_007),
            (8, "Level 2", 2, "Creator", 100_008),
        ])
        self.assertEqual([call(0, 2), call(2, 2)], progress.await_args_list)

    def test_rejects_an_invalid_api_shape(self):
        with self.assertRaises(demonlist_api.DemonlistAPIError):
            demonlist_api._get_collection({"message": "success"}, "levels")


if __name__ == "__main__":
    unittest.main()
