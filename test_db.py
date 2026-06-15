import asyncio
import time
from database.connection import init_connection, close_connection
from services.calculator import get_leaderboard

async def run_test():
    await init_connection()
    start_time = time.time()
    lb = await get_leaderboard()
    end_time = time.time()
    
    print(f"Calculated leaderboard for {len(lb)} players in {end_time - start_time:.4f} seconds.")
    
    start_time_cache = time.time()
    lb2 = await get_leaderboard()
    end_time_cache = time.time()
    print(f"Calculated cached leaderboard in {end_time_cache - start_time_cache:.6f} seconds.")
    
    await close_connection()

if __name__ == "__main__":
    asyncio.run(run_test())
