import aiosqlite
import logging
from config import DB_PATH
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

@asynccontextmanager
async def get_db_connection():
    """Returns an active aiosqlite connection context manager."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        yield conn

async def init_db():
    """Initializes the database schema if it doesn't exist."""
    logger.info("Initializing database...")
    async with get_db_connection() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id INTEGER,
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
                position INTEGER NOT NULL
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
        
        await conn.commit()
        
        try:
            await conn.execute("ALTER TABLE levels_cache ADD COLUMN creator TEXT DEFAULT 'Unknown'")
            await conn.commit()
        except aiosqlite.OperationalError:
            pass
            
    logger.info("Database initialized successfully.")
