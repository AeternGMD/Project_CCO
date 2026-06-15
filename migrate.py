import asyncio
import aiosqlite
from config import DB_PATH

async def main():
    async with aiosqlite.connect(DB_PATH) as conn:
        try:
            await conn.execute('ALTER TABLE players DROP COLUMN tg_id')
        except Exception as e:
            print(f"Error dropping tg_id: {e}")
            
        try:
            await conn.execute('ALTER TABLE levels_cache ADD COLUMN ingame_id INTEGER')
        except Exception as e:
            print(f"Error adding ingame_id: {e}")
            
        await conn.commit()

asyncio.run(main())
