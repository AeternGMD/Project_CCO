from typing import List, Optional, Dict, Any
import aiosqlite
from database.connection import get_db_connection

# --- Admin Operations ---

async def is_admin(tg_id: int) -> bool:
    from config import ROOT_ID
    if tg_id == ROOT_ID:
        return True
    async with get_db_connection() as conn:
        cursor = await conn.execute("SELECT 1 FROM admins WHERE tg_id = ?", (tg_id,))
        return await cursor.fetchone() is not None

async def add_admin(tg_id: int):
    async with get_db_connection() as conn:
        await conn.execute("INSERT OR IGNORE INTO admins (tg_id) VALUES (?)", (tg_id,))
        await conn.commit()

async def del_admin(tg_id: int):
    async with get_db_connection() as conn:
        await conn.execute("DELETE FROM admins WHERE tg_id = ?", (tg_id,))
        await conn.commit()

# --- Player Operations ---

async def add_player(nickname: str, demonlist_id: str, platform: str, location: str, api_sync: bool, tg_id: Optional[int] = None, contacts: Optional[str] = None):
    async with get_db_connection() as conn:
        await conn.execute('''
            INSERT INTO players (tg_id, nickname, demonlist_id, platform, location, api_sync, contacts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (tg_id, nickname, demonlist_id, platform, location, api_sync, contacts))
        await conn.commit()

async def get_player_by_nick(nickname: str) -> Optional[aiosqlite.Row]:
    async with get_db_connection() as conn:
        cursor = await conn.execute("SELECT * FROM players WHERE nickname COLLATE NOCASE = ?", (nickname,))
        return await cursor.fetchone()

async def get_player_by_id(player_id: int) -> Optional[aiosqlite.Row]:
    async with get_db_connection() as conn:
        cursor = await conn.execute("SELECT * FROM players WHERE id = ?", (player_id,))
        return await cursor.fetchone()

async def get_all_players() -> List[aiosqlite.Row]:
    async with get_db_connection() as conn:
        cursor = await conn.execute("SELECT * FROM players")
        return await cursor.fetchall()

async def search_players(query: str, limit: int = 10) -> List[aiosqlite.Row]:
    async with get_db_connection() as conn:
        cursor = await conn.execute("SELECT * FROM players WHERE nickname LIKE ? LIMIT ?", (f"%{query}%", limit))
        return await cursor.fetchall()

async def update_player(player_id: int, **kwargs):
    if not kwargs:
        return
    set_clause = ", ".join([f"{k} = ?" for k in kwargs.keys()])
    values = list(kwargs.values())
    values.append(player_id)
    
    async with get_db_connection() as conn:
        await conn.execute(f"UPDATE players SET {set_clause} WHERE id = ?", values)
        await conn.commit()

async def delete_player(player_id: int):
    async with get_db_connection() as conn:
        await conn.execute("DELETE FROM players WHERE id = ?", (player_id,))
        await conn.commit()

# --- Level Operations ---

async def upsert_level(level_id: int, level_name: str, position: int, creator: str = "Unknown"):
    async with get_db_connection() as conn:
        await conn.execute('''
            INSERT INTO levels_cache (level_id, level_name, position, creator)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(level_id) DO UPDATE SET
                level_name=excluded.level_name,
                position=excluded.position,
                creator=excluded.creator
        ''', (level_id, level_name, position, creator))
        await conn.commit()

async def get_ambiguous_level_names() -> set:
    async with get_db_connection() as conn:
        cursor = await conn.execute("SELECT level_name FROM levels_cache GROUP BY level_name COLLATE NOCASE HAVING count(*) > 1")
        rows = await cursor.fetchall()
        return {r[0].lower() for r in rows}

async def get_total_levels() -> int:
    async with get_db_connection() as conn:
        cursor = await conn.execute("SELECT COUNT(*) as cnt FROM levels_cache")
        row = await cursor.fetchone()
        return row['cnt'] if row else 0

async def get_level_by_id(level_id: int) -> Optional[aiosqlite.Row]:
    async with get_db_connection() as conn:
        cursor = await conn.execute("SELECT * FROM levels_cache WHERE level_id = ?", (level_id,))
        return await cursor.fetchone()

async def get_levels_by_name(level_name: str) -> List[aiosqlite.Row]:
    async with get_db_connection() as conn:
        cursor = await conn.execute("SELECT * FROM levels_cache WHERE level_name COLLATE NOCASE = ? ORDER BY position ASC", (level_name,))
        return await cursor.fetchall()

async def search_levels(query: str, limit: int = 10) -> List[aiosqlite.Row]:
    async with get_db_connection() as conn:
        cursor = await conn.execute("SELECT * FROM levels_cache WHERE level_name LIKE ? ORDER BY position ASC LIMIT ?", (f"%{query}%", limit))
        return await cursor.fetchall()

# --- Record Operations ---

async def add_record(player_id: int, level_id: int, progress_start: int, progress_end: int, status: str):
    async with get_db_connection() as conn:
        # If progress is 100%, delete old records for this level
        if progress_start == 0 and progress_end == 100:
            await conn.execute("DELETE FROM records WHERE player_id = ? AND level_id = ?", (player_id, level_id))
        else:
            if progress_start == 0:
                cursor = await conn.execute("SELECT id FROM records WHERE player_id = ? AND level_id = ? AND progress_start = 0 AND progress_end >= ?", (player_id, level_id, progress_end))
                if await cursor.fetchone():
                    return
                await conn.execute("DELETE FROM records WHERE player_id = ? AND level_id = ? AND progress_start = 0 AND progress_end < ?", (player_id, level_id, progress_end))
            elif progress_end == 100:
                cursor = await conn.execute("SELECT id FROM records WHERE player_id = ? AND level_id = ? AND progress_end = 100 AND progress_start <= ?", (player_id, level_id, progress_start))
                if await cursor.fetchone():
                    return
                await conn.execute("DELETE FROM records WHERE player_id = ? AND level_id = ? AND progress_end = 100 AND progress_start > ?", (player_id, level_id, progress_start))
        
        await conn.execute('''
            INSERT INTO records (player_id, level_id, progress_start, progress_end, status)
            VALUES (?, ?, ?, ?, ?)
        ''', (player_id, level_id, progress_start, progress_end, status))
        await conn.commit()

async def get_player_records(player_id: int) -> List[aiosqlite.Row]:
    async with get_db_connection() as conn:
        cursor = await conn.execute('''
            SELECT r.*, l.level_name, l.position, l.creator 
            FROM records r
            JOIN levels_cache l ON r.level_id = l.level_id
            WHERE r.player_id = ?
        ''', (player_id,))
        return await cursor.fetchall()

async def get_record(player_id: int, level_id: int) -> Optional[aiosqlite.Row]:
    async with get_db_connection() as conn:
        cursor = await conn.execute('''
            SELECT * FROM records WHERE player_id = ? AND level_id = ?
        ''', (player_id, level_id))
        return await cursor.fetchone()

async def delete_record(player_id: int, level_id: int):
    async with get_db_connection() as conn:
        await conn.execute("DELETE FROM records WHERE player_id = ? AND level_id = ?", (player_id, level_id))
        await conn.commit()

async def update_record_status(record_id: int, status: str):
    async with get_db_connection() as conn:
        await conn.execute("UPDATE records SET status = ? WHERE id = ?", (status, record_id))
        await conn.commit()

# --- Settings ---

async def get_setting(key: str, default: str = None) -> Optional[str]:
    async with get_db_connection() as conn:
        cursor = await conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cursor.fetchone()
        return row['value'] if row else default

async def set_setting(key: str, value: str):
    async with get_db_connection() as conn:
        await conn.execute('''
            INSERT INTO settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
        ''', (key, str(value)))
        await conn.commit()

# --- Bans ---

async def ban_user(user_id: int, banned_until: int = None, reason: str = None):
    async with get_db_connection() as conn:
        await conn.execute('''
            INSERT INTO banned_users (user_id, banned_until, reason)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET 
                banned_until=excluded.banned_until,
                reason=excluded.reason
        ''', (user_id, banned_until, reason))
        await conn.commit()

async def unban_user(user_id: int) -> bool:
    async with get_db_connection() as conn:
        cursor = await conn.execute("DELETE FROM banned_users WHERE user_id = ?", (user_id,))
        await conn.commit()
        return cursor.rowcount > 0

async def get_ban_info(user_id: int) -> Optional[aiosqlite.Row]:
    async with get_db_connection() as conn:
        cursor = await conn.execute("SELECT * FROM banned_users WHERE user_id = ?", (user_id,))
        return await cursor.fetchone()
