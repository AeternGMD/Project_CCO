from typing import List, Dict, Any, Optional
from database.models import (
    get_player_records, get_total_levels, get_all_players,
    get_all_player_scores, is_leaderboard_dirty, clear_leaderboard_dirty
)

_leaderboard_cache = None

async def calculate_player_score(player_id: int) -> Optional[float]:
    """
    Calculates the score for a single player (used for fast recalculations if needed).
    """
    records = await get_player_records(player_id)
    total_levels = await get_total_levels()
    
    completions = [r for r in records if r['progress_start'] == 0 and r['progress_end'] == 100]
    
    if not completions:
        return None
    
    completions.sort(key=lambda x: x['position'])
    top_5_positions = [c['position'] for c in completions[:5]]
    
    penalty_value = total_levels + 1
    while len(top_5_positions) < 5:
        top_5_positions.append(penalty_value)
        
    return sum(top_5_positions) / 5.0

async def calculate_hypothetical_score(player_id: int, new_level_positions: List[int]) -> Optional[float]:
    """
    Calculates score if the player were to beat new_level_positions.
    """
    records = await get_player_records(player_id)
    total_levels = await get_total_levels()
    
    completions = [r['position'] for r in records if r['progress_start'] == 0 and r['progress_end'] == 100]
    completions.extend(new_level_positions)
    
    if not completions:
        return None
    
    completions.sort()
    top_5_positions = completions[:5]
    
    penalty_value = total_levels + 1
    while len(top_5_positions) < 5:
        top_5_positions.append(penalty_value)
        
    return sum(top_5_positions) / 5.0

async def calculate_progress_eligibility(player_id: int, level_position: int) -> bool:
    """
    Checks if a progress on a level would mathematically enter the top-5 hardest.
    """
    records = await get_player_records(player_id)
    completions = [r for r in records if r['progress_start'] == 0 and r['progress_end'] == 100]
    
    if len(completions) < 5:
        return True
    
    completions.sort(key=lambda x: x['position'])
    top_5_positions = [c['position'] for c in completions[:5]]
    
    return level_position <= top_5_positions[-1]

async def get_leaderboard(filter_platform: Optional[str] = None, filter_location: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Returns the leaderboard. Uses a global cache and efficient SQL calculations to avoid N+1 queries.
    """
    global _leaderboard_cache
    
    if _leaderboard_cache is None or is_leaderboard_dirty():
        players = await get_all_players()
        scores = await get_all_player_scores()
        
        full_lb = []
        for p in players:
            score = scores.get(p['id'])
            if score is not None:
                full_lb.append({
                    'player': dict(p), # Convert aiosqlite.Row to dict
                    'score': score
                })
                
        # Sort ascending by score (lower is better)
        full_lb.sort(key=lambda x: x['score'])
        
        # Assign ranks
        for i, entry in enumerate(full_lb):
            entry['rank'] = i + 1
            
        _leaderboard_cache = full_lb
        clear_leaderboard_dirty()
        
    # Apply filters to the cached leaderboard
    lb = _leaderboard_cache
    if filter_platform:
        lb = [e for e in lb if e['player']['platform'].lower() == filter_platform.lower()]
    if filter_location:
        lb = [e for e in lb if e['player']['location'].lower() == filter_location.lower()]
        
    return lb
