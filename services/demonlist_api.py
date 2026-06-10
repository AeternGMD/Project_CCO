import aiohttp
import logging
from database.models import upsert_level, get_player_by_id, get_player_records, update_record_status, add_record

logger = logging.getLogger(__name__)

# Base API configuration. Adjust endpoints as needed per demonlist.org api-docs.
# Assuming typical REST structure for levels and players.
API_BASE_URL = "https://api.demonlist.org"
LEVELS_ENDPOINT = f"{API_BASE_URL}/level/classic/list"
PLAYER_ENDPOINT = f"{API_BASE_URL}/user/record/list"

async def fetch_levels(progress_callback=None) -> int:
    """
    Fetches the list of levels from the demonlist.org API and updates the local cache.
    Returns the number of levels updated.
    """
    updated_count = 0
    try:
        async with aiohttp.ClientSession() as session:
            # The exact endpoint structure may vary. Adjusting to a common format.
            # Assuming it returns a list of dicts: [{"id": 1, "name": "Tidal Wave", "position": 1}, ...]
            async with session.get(LEVELS_ENDPOINT) as response:
                response.raise_for_status()
                data = await response.json()
                
                levels = data.get('data', {}).get('levels', [])
                    
                total_levels = len(levels)
                for i, lvl in enumerate(levels):
                    level_id = lvl.get('id')
                    ingame_id = lvl.get('ingame_id')
                    level_name = lvl.get('name')
                    position = lvl.get('placement')
                    
                    if level_id and level_name and position:
                        creator_obj = lvl.get('holder') or lvl.get('publisher') or lvl.get('creator') or lvl.get('verifier')
                        creator = 'Unknown'
                        if isinstance(creator_obj, dict):
                            creator = creator_obj.get('username') or creator_obj.get('name', 'Unknown')
                        elif isinstance(creator_obj, str):
                            creator = creator_obj
                            
                        await upsert_level(int(level_id), str(level_name), int(position), creator, ingame_id=ingame_id)
                        updated_count += 1
                        
                    if progress_callback and i % 300 == 0:
                        await progress_callback(i, total_levels)
                        
                if progress_callback:
                    await progress_callback(total_levels, total_levels)
                        
        logger.info(f"Successfully updated {updated_count} levels in cache.")
        return updated_count
    except Exception as e:
        logger.error(f"Failed to fetch levels from API: {e}")
        return updated_count

async def sync_player_records(player_id: int):
    """
    Fetches a player's profile from the API using demonlist_id.
    Cross-references with local records. Translates matching Manual 100% records to Verified.
    """
    player = await get_player_by_id(player_id)
    if not player or not player['api_sync'] or player['demonlist_id'] == "-":
        return

    demonlist_id = player['demonlist_id']
    try:
        async with aiohttp.ClientSession() as session:
            offset = 0
            limit = 50
            verified_level_ids = set()
            
            while True:
                url = f"{PLAYER_ENDPOINT}?user_id={demonlist_id}&limit={limit}&offset={offset}"
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.warning(f"Failed to fetch player records for ID {demonlist_id}")
                        break
                    
                    data = await response.json()
                    api_records = data.get('data', {}).get('records', [])
                    
                    if not api_records:
                        break
                        
                    # Collect all level IDs the player has beaten 100% according to API
                    for rec in api_records:
                        progress = rec.get('percent', 100)
                        status = rec.get('status', 'accepted')
                        if progress == 100 and status == 'accepted':
                            level_info = rec.get('level', {})
                            if 'id' in level_info:
                                verified_level_ids.add(int(level_info['id']))
                                
                    if len(api_records) < limit:
                        break
                    offset += limit
                            
            # Get local records
            local_records = await get_player_records(player_id)
            local_level_ids = set()
            
            for rec in local_records:
                local_level_ids.add(rec['level_id'])
                if rec['status'] == 'Manual' and rec['progress_start'] == 0 and rec['progress_end'] == 100:
                    if rec['level_id'] in verified_level_ids:
                        await update_record_status(rec['id'], 'Verified')
                        logger.info(f"Verified record ID {rec['id']} for player {player['nickname']}")
                        
            # Auto-add verified levels that are missing in local DB
            for v_level_id in verified_level_ids:
                if v_level_id not in local_level_ids:
                    await add_record(player_id, v_level_id, 0, 100, 'Verified')
                    logger.info(f"Auto-added verified level {v_level_id} for player {player['nickname']}")
                            
    except Exception as e:
        logger.error(f"Error syncing player {player['nickname']} records: {e}")
