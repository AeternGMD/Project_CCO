import asyncio
import aiosqlite
from config import DB_PATH

async def main():
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute('SELECT nickname, location FROM players')
        rows = await cursor.fetchall()
        for r in rows:
            print(f"{r[0]}: {r[1]}")
            
        # Fix Kwikzy manually since user asked
        await conn.execute("UPDATE players SET location = 'Нижний Тагил' WHERE nickname = 'Kwikzy'")
        # Also fix any other players with 'Нижний'
        await conn.execute("UPDATE players SET location = 'Нижний Тагил' WHERE location = 'Нижний'")
        await conn.commit()

asyncio.run(main())
