from typing import List, Optional, Dict, Any
from database.connection import get_db_connection

# --- Admin Operations ---

_admins_cache = None

async def is_admin(tg_id: int) -> bool:
    from config import ROOT_ID
    if tg_id == ROOT_ID:
        return True
        
    global _admins_cache
    if _admins_cache is None:
        async with get_db_connection() as conn:
            cursor = await conn.execute("SELECT tg_id FROM admins")
            rows = await cursor.fetchall()
            _admins_cache = {r['tg_id'] for r in rows}
            
    return tg_id in _admins_cache

async def add_admin(tg_id: int):
    async with get_db_connection() as conn:
        await conn.execute("INSERT OR IGNORE INTO admins (tg_id) VALUES (?)", (tg_id,))
        await conn.commit()
    global _admins_cache
    if _admins_cache is not None:
        _admins_cache.add(tg_id)

async def del_admin(tg_id: int):
    async with get_db_connection() as conn:
        await conn.execute("DELETE FROM admins WHERE tg_id = ?", (tg_id,))
        await conn.commit()
    global _admins_cache
    if _admins_cache is not None:
        _admins_cache.discard(tg_id)

# --- Player Operations ---

async def add_player(nickname: str, demonlist_id: str, platform: str, location: str, api_sync: bool, contacts: Optional[str] = None):
    async with get_db_connection() as conn:
        await conn.execute('''
            INSERT INTO players (nickname, demonlist_id, platform, location, api_sync, contacts)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (nickname, demonlist_id, platform, location, api_sync, contacts))
        await conn.commit()
    mark_leaderboard_dirty()

async def get_player_by_nick(nickname: str) -> Optional[dict]:
    async with get_db_connection() as conn:
        cursor = await conn.execute("SELECT * FROM players WHERE nickname COLLATE NOCASE = ?", (nickname,))
        return await cursor.fetchone()

async def get_player_by_id(player_id: int) -> Optional[dict]:
    async with get_db_connection() as conn:
        cursor = await conn.execute("SELECT * FROM players WHERE id = ?", (player_id,))
        return await cursor.fetchone()

async def get_player_by_tg(tg_id: int) -> Optional[dict]:
    async with get_db_connection() as conn:
        cursor = await conn.execute("SELECT * FROM players WHERE tg_id = ?", (tg_id,))
        return await cursor.fetchone()

async def link_player_tg(player_id: int, tg_id: int):
    async with get_db_connection() as conn:
        await conn.execute("UPDATE players SET tg_id = ? WHERE id = ?", (tg_id, player_id))
        await conn.commit()

async def unlink_player_tg(player_id: int):
    async with get_db_connection() as conn:
        await conn.execute("UPDATE players SET tg_id = NULL WHERE id = ?", (player_id,))
        await conn.commit()

async def get_all_players() -> List[dict]:
    async with get_db_connection() as conn:
        cursor = await conn.execute("SELECT * FROM players")
        return await cursor.fetchall()

async def search_players(query: str, limit: int = 10) -> List[dict]:
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
    mark_leaderboard_dirty()

async def delete_player(player_id: int):
    async with get_db_connection() as conn:
        await conn.execute("DELETE FROM players WHERE id = ?", (player_id,))
        await conn.commit()
    mark_leaderboard_dirty()

# --- Level Operations ---

_ambiguous_names_cache = None
_total_levels_cache = None
_leaderboard_dirty = True

def mark_leaderboard_dirty():
    global _leaderboard_dirty
    _leaderboard_dirty = True

def is_leaderboard_dirty() -> bool:
    return _leaderboard_dirty

def clear_leaderboard_dirty():
    global _leaderboard_dirty
    _leaderboard_dirty = False

def invalidate_level_caches():
    global _ambiguous_names_cache, _total_levels_cache
    _ambiguous_names_cache = None
    _total_levels_cache = None
    mark_leaderboard_dirty()

async def upsert_level(level_id: int, level_name: str, position: int, creator: str = "Unknown", ingame_id: Optional[int] = None):
    async with get_db_connection() as conn:
        await conn.execute('''
            INSERT INTO levels_cache (level_id, level_name, position, creator, ingame_id)
            VALUES (?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
                level_name=VALUES(level_name),
                position=VALUES(position),
                creator=VALUES(creator),
                ingame_id=VALUES(ingame_id)
        ''', (level_id, level_name, position, creator, ingame_id))
        await conn.commit()
    invalidate_level_caches()

async def get_ambiguous_level_names() -> set:
    global _ambiguous_names_cache
    if _ambiguous_names_cache is None:
        async with get_db_connection() as conn:
            cursor = await conn.execute("SELECT level_name FROM levels_cache GROUP BY level_name COLLATE NOCASE HAVING count(*) > 1")
            rows = await cursor.fetchall()
            _ambiguous_names_cache = {r['level_name'].lower() for r in rows}
    return _ambiguous_names_cache

async def get_total_levels() -> int:
    global _total_levels_cache
    if _total_levels_cache is None:
        async with get_db_connection() as conn:
            cursor = await conn.execute("SELECT COUNT(*) as cnt FROM levels_cache")
            row = await cursor.fetchone()
            _total_levels_cache = row['cnt'] if row else 0
    return _total_levels_cache

async def get_level_by_id(level_id: int) -> Optional[dict]:
    async with get_db_connection() as conn:
        cursor = await conn.execute("SELECT * FROM levels_cache WHERE level_id = ?", (level_id,))
        return await cursor.fetchone()

async def get_levels_by_name(level_name: str) -> List[dict]:
    async with get_db_connection() as conn:
        cursor = await conn.execute("SELECT * FROM levels_cache WHERE level_name COLLATE NOCASE = ? ORDER BY position ASC", (level_name,))
        return await cursor.fetchall()

async def search_levels(query: str, limit: int = 10) -> List[dict]:
    async with get_db_connection() as conn:
        cursor = await conn.execute("SELECT * FROM levels_cache WHERE level_name LIKE ? ORDER BY position ASC LIMIT ?", (f"%{query}%", limit))
        return await cursor.fetchall()

async def get_levels_with_victors(start_pos: int, end_pos: int) -> List[dict]:
    async with get_db_connection() as conn:
        cursor = await conn.execute('''
            SELECT l.*, COUNT(DISTINCT r.player_id) as victors_count
            FROM levels_cache l
            LEFT JOIN records r ON l.level_id = r.level_id AND r.progress_start = 0 AND r.progress_end = 100
            WHERE l.position >= ? AND l.position <= ?
            GROUP BY l.level_id
            ORDER BY l.position ASC
        ''', (start_pos, end_pos))
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
    mark_leaderboard_dirty()

async def get_player_records(player_id: int) -> List[dict]:
    async with get_db_connection() as conn:
        cursor = await conn.execute('''
            SELECT r.*, l.level_name, l.position, l.creator 
            FROM records r
            JOIN levels_cache l ON r.level_id = l.level_id
            WHERE r.player_id = ?
        ''', (player_id,))
        return await cursor.fetchall()

async def get_players_records(player_ids: List[int]) -> Dict[int, List[dict]]:
    if not player_ids: return {}
    placeholders = ",".join("?" for _ in player_ids)
    async with get_db_connection() as conn:
        cursor = await conn.execute(f'''
            SELECT r.*, l.level_name, l.position, l.creator 
            FROM records r
            JOIN levels_cache l ON r.level_id = l.level_id
            WHERE r.player_id IN ({placeholders})
        ''', player_ids)
        rows = await cursor.fetchall()
        
    from collections import defaultdict
    result = defaultdict(list)
    for r in rows:
        result[r['player_id']].append(r)
    return result

async def get_record(player_id: int, level_id: int) -> Optional[dict]:
    async with get_db_connection() as conn:
        cursor = await conn.execute('''
            SELECT * FROM records WHERE player_id = ? AND level_id = ?
        ''', (player_id, level_id))
        return await cursor.fetchone()

async def delete_record(player_id: int, level_id: int) -> int:
    async with get_db_connection() as conn:
        cursor = await conn.execute("DELETE FROM records WHERE player_id = ? AND level_id = ?", (player_id, level_id))
        await conn.commit()
        rowcount = cursor.rowcount
    mark_leaderboard_dirty()
    return rowcount

async def update_record_status(record_id: int, status: str):
    async with get_db_connection() as conn:
        await conn.execute("UPDATE records SET status = ? WHERE id = ?", (status, record_id))
        await conn.commit()
    mark_leaderboard_dirty()

# --- Settings ---

async def get_setting(key: str, default: str = None) -> Optional[str]:
    async with get_db_connection() as conn:
        cursor = await conn.execute("SELECT value FROM settings WHERE `key` = ?", (key,))
        row = await cursor.fetchone()
        return row['value'] if row else default

async def set_setting(key: str, value: str):
    async with get_db_connection() as conn:
        await conn.execute('''
            INSERT INTO settings (`key`, value)
            VALUES (?, ?)
            ON DUPLICATE KEY UPDATE value=VALUES(value)
        ''', (key, str(value)))
        await conn.commit()

# --- Bans ---

async def ban_user(user_id: int, banned_until: int = None, reason: str = None):
    async with get_db_connection() as conn:
        await conn.execute('''
            INSERT INTO banned_users (user_id, banned_until, reason)
            VALUES (?, ?, ?)
            ON DUPLICATE KEY UPDATE 
                banned_until=VALUES(banned_until),
                reason=VALUES(reason)
        ''', (user_id, banned_until, reason))
        await conn.commit()

async def unban_user(user_id: int) -> bool:
    async with get_db_connection() as conn:
        cursor = await conn.execute("DELETE FROM banned_users WHERE user_id = ?", (user_id,))
        await conn.commit()
        return cursor.rowcount > 0

async def get_ban_info(user_id: int) -> Optional[dict]:
    async with get_db_connection() as conn:
        cursor = await conn.execute("SELECT * FROM banned_users WHERE user_id = ?", (user_id,))
        return await cursor.fetchone()

# --- Fast Scoring (No N+1 queries) ---

async def get_all_player_scores() -> Dict[int, float]:
    """Efficiently calculate scores for all players in one DB pass."""
    total_levels = await get_total_levels()
    
    async with get_db_connection() as conn:
        cursor = await conn.execute('''
            SELECT r.player_id, l.position
            FROM records r
            JOIN levels_cache l ON r.level_id = l.level_id
            WHERE r.progress_start = 0 AND r.progress_end = 100
            ORDER BY r.player_id, l.position ASC
        ''')
        rows = await cursor.fetchall()
        
    scores = {}
    from collections import defaultdict
    completions_by_player = defaultdict(list)
    for row in rows:
        if len(completions_by_player[row['player_id']]) < 5:
            completions_by_player[row['player_id']].append(row['position'])
            
    for player_id, positions in completions_by_player.items():
        while len(positions) < 5:
            positions.append(total_levels + 1)
        scores[player_id] = sum(positions) / 5.0
        
    return scores
