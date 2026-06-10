from typing import List, Dict, Any, Optional
from database.models import get_player_records, get_total_levels, get_all_players

async def calculate_player_score(player_id: int) -> Optional[float]:
    """
    Calculates the score for a player based on their top 5 hardest completions.
    Formula: (P1 + P2 + P3 + P4 + P5) / 5
    Missing slots (if completions < 5) are penalized with (total_levels + 1).
    Players with 0 completions return None.
    """
    records = await get_player_records(player_id)
    total_levels = await get_total_levels()
    
    # Filter only 100% completions
    completions = [r for r in records if r['progress_start'] == 0 and r['progress_end'] == 100]
    
    if not completions:
        return None
    
    # Sort by level position (lowest position number is hardest)
    completions.sort(key=lambda x: x['position'])
    
    top_5_positions = [c['position'] for c in completions[:5]]
    
    # Fill missing slots with penalty
    penalty_value = total_levels + 1
    while len(top_5_positions) < 5:
        top_5_positions.append(penalty_value)
        
    score = sum(top_5_positions) / 5.0
    return score

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
    Does not check the >=50% rule, that should be done by the handler before calling this.
    """
    records = await get_player_records(player_id)
    completions = [r for r in records if r['progress_start'] == 0 and r['progress_end'] == 100]
    
    if len(completions) < 5:
        return True # Any level can be in top 5 if there are empty slots
    
    completions.sort(key=lambda x: x['position'])
    top_5_positions = [c['position'] for c in completions[:5]]
    
    # If the level's position is strictly better (lower) than the 5th worst level, it's eligible
    return level_position <= top_5_positions[-1]

async def get_leaderboard(filter_platform: Optional[str] = None, filter_location: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Returns the leaderboard.
    """
    players = await get_all_players()
    leaderboard = []
    
    for p in players:
        if filter_platform and p['platform'].lower() != filter_platform.lower():
            continue
        if filter_location and p['location'].lower() != filter_location.lower():
            continue
            
        score = await calculate_player_score(p['id'])
        if score is not None:
            leaderboard.append({
                'player': p,
                'score': score
            })
            
    # Sort ascending by score (lower is better)
    leaderboard.sort(key=lambda x: x['score'])
    
    # Assign ranks
    for i, entry in enumerate(leaderboard):
        entry['rank'] = i + 1
        
    return leaderboard
