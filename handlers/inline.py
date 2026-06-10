import hashlib
from aiogram import Router
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent
from database.models import search_players, search_levels, get_player_records, get_ambiguous_level_names
from services.calculator import get_leaderboard

router = Router()

@router.inline_query()
async def inline_search(inline_query: InlineQuery):
    query = inline_query.query.strip()
    
    results = []
    
    # 1. Search Players
    players = await search_players(query, limit=5)
    lb = await get_leaderboard() if players else []
    ambiguous_names = await get_ambiguous_level_names()
    
    for player in players:
        entry = next((item for item in lb if item['player']['id'] == player['id']), None)
        
        text = f"👤 Профиль {player['nickname']}\n"
        text += f"Платформа: {player['platform']}\n"
        text += f"Город: {'Неизвестно' if player['location'] == '-' else player['location']}\n"
        if entry:
            text += f"Средний балл: {entry['score']:.2f}\n"
            text += f"Место в топе: {entry['rank']}\n"
            
        records = await get_player_records(player['id'])
        completions = [r for r in records if r['progress_start'] == 0 and r['progress_end'] == 100]
        completions.sort(key=lambda x: x['position'])
        top_5 = completions[:5]
        
        if top_5:
            text += "\n🔥 Топ-5 уровней:\n"
            for i, c in enumerate(top_5, 1):
                name = c['level_name']
                if name.lower() in ambiguous_names:
                    name += f" [{dict(c).get('creator', 'Unknown')}]"
                text += f"{i}. {name} (Топ-{c['position']}) - {c['status']}\n"
                
        result_id = hashlib.md5(f"player_{player['id']}".encode()).hexdigest()
        score_str = f"{entry['score']:.2f}" if entry else "0"
        desc = f"Место: {entry['rank'] if entry else 'N/A'} | Балл: {score_str}"
        
        results.append(
            InlineQueryResultArticle(
                id=result_id,
                title=f"👤 Игрок: {player['nickname']}",
                description=desc,
                input_message_content=InputTextMessageContent(message_text=text)
            )
        )
        
    # 2. Search Levels
    levels = await search_levels(query, limit=10)
    for lvl in levels:
        lvl_name = lvl['level_name']
        creator = dict(lvl).get('creator', 'Unknown')
        
        text = f"⚙️ Уровень {lvl_name} [{creator}]\n"
        text += f"Позиция: Топ-{lvl['position']} в Demonlist\n"
        
        # We could add top players here if we want, but it requires joining records and calculating scores.
        # Let's keep it simple for now to avoid slow inline queries.
        
        result_id = hashlib.md5(f"level_{lvl['level_id']}".encode()).hexdigest()
        
        results.append(
            InlineQueryResultArticle(
                id=result_id,
                title=f"⚙️ Уровень: {lvl_name} [{creator}]",
                description=f"Топ-{lvl['position']} в Demonlist",
                input_message_content=InputTextMessageContent(message_text=text)
            )
        )
        
    # Return results
    await inline_query.answer(results[:50], cache_time=5, is_personal=False)
