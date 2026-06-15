import aiomysql
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

_global_pool = None

class MySQLCursorWrapper:
    def __init__(self, cursor):
        self.cursor = cursor
        
    async def fetchone(self):
        return await self.cursor.fetchone()
        
    async def fetchall(self):
        return await self.cursor.fetchall()
        
    @property
    def rowcount(self):
        return self.cursor.rowcount

class MySQLConnectionWrapper:
    def __init__(self, conn):
        self.conn = conn

    async def execute(self, sql, args=None):
        # Convert SQLite syntax to MySQL syntax dynamically
        sql = sql.replace('?', '%s')
        sql = sql.replace('COLLATE NOCASE', '')
        sql = sql.replace('AUTOINCREMENT', 'AUTO_INCREMENT')
        sql = sql.replace('INSERT OR IGNORE', 'INSERT IGNORE')
        
        cursor = await self.conn.cursor(aiomysql.DictCursor)
        await cursor.execute(sql, args)
        return MySQLCursorWrapper(cursor)

    async def commit(self):
        await self.conn.commit()

    async def rollback(self):
        await self.conn.rollback()

async def init_connection():
    global _global_pool
    if _global_pool is None:
        _global_pool = await aiomysql.create_pool(
            host='127.0.0.1',
            port=33060,
            user='bot',
            password='botpassword',
            db='gdbot',
            autocommit=False
        )

async def close_connection():
    global _global_pool
    if _global_pool:
        _global_pool.close()
        await _global_pool.wait_closed()
        _global_pool = None

@asynccontextmanager
async def get_db_connection():
    if _global_pool is None:
        await init_connection()
    async with _global_pool.acquire() as conn:
        yield MySQLConnectionWrapper(conn)

async def init_db():
    """Initializes the database schema if it doesn't exist."""
    logger.info("Initializing database...")
    async with get_db_connection() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTO_INCREMENT,
                nickname VARCHAR(255) UNIQUE NOT NULL,
                demonlist_id VARCHAR(255) NOT NULL,
                platform VARCHAR(50) NOT NULL,
                location VARCHAR(255) NOT NULL,
                contacts TEXT,
                api_sync BOOLEAN NOT NULL DEFAULT 1,
                tg_id BIGINT DEFAULT NULL
            )
        ''')
        
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS levels_cache (
                level_id INTEGER PRIMARY KEY,
                level_name VARCHAR(255) NOT NULL,
                position INTEGER NOT NULL,
                creator VARCHAR(255) DEFAULT 'Unknown',
                ingame_id INTEGER
            )
        ''')
        
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTO_INCREMENT,
                player_id INTEGER NOT NULL,
                level_id INTEGER NOT NULL,
                progress_start INTEGER NOT NULL DEFAULT 0,
                progress_end INTEGER NOT NULL,
                status VARCHAR(50) NOT NULL,
                FOREIGN KEY (player_id) REFERENCES players (id) ON DELETE CASCADE,
                FOREIGN KEY (level_id) REFERENCES levels_cache (level_id) ON DELETE CASCADE
            )
        ''')
        
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                tg_id BIGINT PRIMARY KEY
            )
        ''')
        
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                `key` VARCHAR(255) PRIMARY KEY,
                value TEXT NOT NULL
            )
        ''')
        
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS banned_users (
                user_id BIGINT PRIMARY KEY,
                banned_until BIGINT,
                reason TEXT
            )
        ''')
        
        await conn.commit()
        
        try:
            await conn.execute("ALTER TABLE levels_cache ADD COLUMN creator VARCHAR(255) DEFAULT 'Unknown'")
            await conn.commit()
        except Exception:
            pass
            
        try:
            await conn.execute("ALTER TABLE players ADD COLUMN tg_id BIGINT DEFAULT NULL")
            await conn.commit()
        except Exception:
            pass
            
    logger.info("Database initialized successfully.")
