"""Lazy catalog: two narrow SELECTs per invalidation, dictionary lookups thereafter."""
import asyncio
import time

from database import models
from database.connection import get_db_connection
from services.record_resolver import RecordCatalog

_catalog = None
_version = -1
_loaded_at = 0.0
_lock = asyncio.Lock()
CATALOG_TTL = 300


async def get_record_catalog():
    global _catalog, _version, _loaded_at
    async with _lock:
        version = models.get_record_catalog_version()
        if (_catalog is not None and _version == version
                and time.monotonic() - _loaded_at < CATALOG_TTL):
            return _catalog
        async with get_db_connection() as conn:
            players = await conn.execute('SELECT id, nickname FROM players')
            players = await players.fetchall()
            levels = await conn.execute(
                'SELECT level_id, level_name, creator, position FROM levels_cache'
            )
            levels = await levels.fetchall()
        _catalog = RecordCatalog(players, levels)
        _version = version
        _loaded_at = time.monotonic()
        return _catalog
