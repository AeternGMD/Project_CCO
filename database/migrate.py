import sqlite3
import logging
import asyncio
from database.connection import get_db_connection

logger = logging.getLogger(__name__)

async def migrate_sqlite_to_mysql(sqlite_path: str):
    def fetch_all():
        conn = sqlite3.connect(sqlite_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        data = {}
        for table in ['players', 'levels_cache', 'records', 'admins', 'settings', 'banned_users']:
            try:
                cur.execute(f"SELECT * FROM {table}")
                data[table] = [dict(row) for row in cur.fetchall()]
            except sqlite3.OperationalError:
                data[table] = [] # Table might not exist in older backups
        conn.close()
        return data

    data = await asyncio.to_thread(fetch_all)
    
    async with get_db_connection() as conn:
        # Admins
        for row in data.get('admins', []):
            await conn.execute("INSERT IGNORE INTO admins (tg_id) VALUES (%s)", (row['tg_id'],))
            
        # Settings
        for row in data.get('settings', []):
            await conn.execute("INSERT IGNORE INTO settings (`key`, value) VALUES (%s, %s)", (row['key'], row['value']))
            
        # Banned
        for row in data.get('banned_users', []):
            await conn.execute("INSERT IGNORE INTO banned_users (user_id, banned_until, reason) VALUES (%s, %s, %s)", 
                              (row['user_id'], row['banned_until'], row['reason']))
                              
        # Players
        for row in data.get('players', []):
            tg_id = row.get('tg_id', None)
            await conn.execute("""
                INSERT IGNORE INTO players (id, nickname, demonlist_id, platform, location, contacts, api_sync, tg_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (row['id'], row['nickname'], row['demonlist_id'], row['platform'], row['location'], row['contacts'], row['api_sync'], tg_id))
            
        # Levels Cache
        for row in data.get('levels_cache', []):
            creator = row.get('creator', 'Unknown')
            await conn.execute("""
                INSERT IGNORE INTO levels_cache (level_id, level_name, position, creator, ingame_id)
                VALUES (%s, %s, %s, %s, %s)
            """, (row['level_id'], row['level_name'], row['position'], creator, row.get('ingame_id')))
            
        # Records
        for row in data.get('records', []):
            await conn.execute("""
                INSERT IGNORE INTO records (id, player_id, level_id, progress_start, progress_end, status)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (row['id'], row['player_id'], row['level_id'], row['progress_start'], row['progress_end'], row['status']))
            
        await conn.commit()
