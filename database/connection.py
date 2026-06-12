import aiosqlite
import logging
from config import DB_PATH
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

_global_conn = None

async def init_connection():
    global _global_conn
    if _global_conn is None:
        import os
        db_dir = os.path.dirname(DB_PATH)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            
        _global_conn = await aiosqlite.connect(DB_PATH)
        _global_conn.row_factory = aiosqlite.Row

async def close_connection():
    global _global_conn
    if _global_conn:
        await _global_conn.close()
        _global_conn = None

@asynccontextmanager
async def get_db_connection():
    """Returns an active aiosqlite connection context manager (using global connection)."""
    if _global_conn is None:
        await init_connection()
    yield _global_conn

async def init_db():
    """Initializes the database schema if it doesn't exist."""
    logger.info("Initializing database...")
    async with get_db_connection() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nickname TEXT UNIQUE NOT NULL,
                demonlist_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                location TEXT NOT NULL,
                contacts TEXT,
                api_sync BOOLEAN NOT NULL DEFAULT 1
            )
        ''')
        
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS levels_cache (
                level_id INTEGER PRIMARY KEY,
                level_name TEXT NOT NULL,
                position INTEGER NOT NULL,
                creator TEXT DEFAULT 'Unknown',
                ingame_id INTEGER
            )
        ''')
        
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER NOT NULL,
                level_id INTEGER NOT NULL,
                progress_start INTEGER NOT NULL DEFAULT 0,
                progress_end INTEGER NOT NULL,
                status TEXT NOT NULL,
                FOREIGN KEY (player_id) REFERENCES players (id) ON DELETE CASCADE,
                FOREIGN KEY (level_id) REFERENCES levels_cache (level_id) ON DELETE CASCADE
            )
        ''')
        
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                tg_id INTEGER PRIMARY KEY
            )
        ''')
        
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        ''')
        
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS banned_users (
                user_id INTEGER PRIMARY KEY,
                banned_until INTEGER,
                reason TEXT
            )
        ''')
        
        await conn.commit()
        
        try:
            await conn.execute("ALTER TABLE levels_cache ADD COLUMN creator TEXT DEFAULT 'Unknown'")
            await conn.commit()
        except aiosqlite.OperationalError:
            pass
            
    logger.info("Database initialized successfully.")
