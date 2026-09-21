from aiogram import Bot
from config import CHANNEL_ID
from utils.display import platform_label
from typing import List, Dict, Any, Optional

async def send_record_notification(
    bot: Bot, 
    player_nickname: str, 
    platform: str, 
    level_name: str, 
    level_position: int, 
    old_leaderboard: List[Dict[str, Any]], 
    new_leaderboard: List[Dict[str, Any]],
    record_deleted: bool = False,
    progress_start: int = 0,
    progress_end: int = 100,
    is_eligible: bool = True
):
    """
    Constructs and sends a notification to the TG channel about a record change.
    """
    
    # Do not notify on deletions
    if record_deleted:
        return
        
    # Do not notify on progress, only 100% completions
    if progress_end < 100 or progress_start > 0:
        return
        
    # Do not notify if level does not enter top 5 hardest
    if not is_eligible:
        return
    
    # Find player in old and new leaderboards
    old_entry = next((item for item in old_leaderboard if item['player']['nickname'] == player_nickname), None)
    new_entry = next((item for item in new_leaderboard if item['player']['nickname'] == player_nickname), None)
    
    old_place = old_entry['rank'] if old_entry else None
    new_place = new_entry['rank'] if new_entry else None
    
    # Base text
    action_text = "прошёл уровень"
            
    text = f"[{platform_label(platform)}] {player_nickname} {action_text} {level_name} (топ-{level_position}).\n"
    
    # Places
    old_place_str = old_place if old_place is not None else "вне рейтинга"
    new_place_str = new_place if new_place is not None else "вне рейтинга"
    
    if old_place == new_place:
        text += f"Место в рейтинге: {new_place_str} — без изменений.\n"
    else:
        text += f"Место в рейтинге: {old_place_str} → {new_place_str}.\n"
    
    # Show neighbors only if the player's place changed and they are still in the top
    if new_place is not None and old_place != new_place:
            neighbors_text = []
            
            above_entry = next((item for item in new_leaderboard if item['rank'] == new_place - 1), None)
            if above_entry:
                neighbors_text.append(f"🔼 Выше: {above_entry['player']['nickname']}")
                
            below_entry = next((item for item in new_leaderboard if item['rank'] == new_place + 1), None)
            if below_entry:
                neighbors_text.append(f"🔽 Ниже: {below_entry['player']['nickname']}")
                
            if neighbors_text:
                text += " | ".join(neighbors_text) + "\n"
    
    # Edge cases
    if new_place == 1 and old_place != 1:
        text += "👑 Новый лидер рейтинга!\n"
    if old_place is None and new_place is not None:
        text += "🌟 Первое прохождение в рейтинге!\n"
    if new_place is None and old_place is not None:
        text += f"📉 {player_nickname} покидает рейтинг.\n"
        
    from database.models import get_setting
    enabled = await get_setting("notifications_enabled", "true")
    if enabled == "true":
        await bot.send_message(CHANNEL_ID, text.strip())
