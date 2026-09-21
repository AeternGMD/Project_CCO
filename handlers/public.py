from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData
from aiogram.exceptions import TelegramBadRequest
from utils.profile_pages import split_profile_text
from utils.display import platform_label
from services.calculator import get_leaderboard
from database.models import get_player_by_nick, get_player_records, get_levels_by_name, get_level_by_id

class TryState(StatesGroup):
    resolving = State()

class TryResolveCallback(CallbackData, prefix="tryres"):
    level_id: int
    
class LvlCallback(CallbackData, prefix="lvl"):
    level_id: int

class TopCallback(CallbackData, prefix="top"):
    page: int
    filter_type: str

class ProfileCallback(CallbackData, prefix="profile"):
    player_id: int
    page: int

def filter_best_progresses(progresses, group_by_key='level_id'):
    from collections import defaultdict
    by_group = defaultdict(list)
    for p in progresses:
        by_group[p[group_by_key]].append(p)
        
    filtered = []
    for progs in by_group.values():
        from_0 = [p for p in progs if p['progress_start'] == 0]
        to_100 = [p for p in progs if p['progress_end'] == 100 and p['progress_start'] != 0]
        others = [p for p in progs if p['progress_start'] != 0 and p['progress_end'] != 100]
        
        if from_0:
            filtered.append(max(from_0, key=lambda x: x['progress_end']))
        if to_100:
            filtered.append(min(to_100, key=lambda x: x['progress_start']))
        filtered.extend(others)
        
    return filtered

router = Router()

@router.message(Command("start", "help", ignore_case=True))
async def cmd_start(message: Message):
    from database.models import is_admin
    from config import ROOT_ID
    from utils.command_help import command_help, help_overview

    access = dict(admin=await is_admin(message.from_user.id),
                  root=message.from_user.id == ROOT_ID)
    args = message.text.split(maxsplit=1)
    text = command_help(args[1].strip(), **access) if len(args) > 1 else help_overview(**access)
    await message.answer(text, parse_mode="HTML")

async def send_leaderboard(message_or_query, leaderboard: list, title: str, filter_type: str, page: int = 1):
    if not leaderboard:
        if hasattr(message_or_query, 'message'):
            try:
                await message_or_query.message.edit_text(f"{title}\n\nВ этом рейтинге пока нет игроков с прохождениями.")
            except Exception:
                pass
        else:
            await message_or_query.answer(f"{title}\n\nВ этом рейтинге пока нет игроков с прохождениями.")
        return
        
    per_page = 15
    total_pages = (len(leaderboard) + per_page - 1) // per_page
    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages
        
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    page_data = leaderboard[start_idx:end_idx]
    
    text = f"🏆 {title} · {page}/{total_pages}\n\n"
    
    from database.models import get_ambiguous_level_names, get_players_records
    ambiguous_names = await get_ambiguous_level_names()
    
    player_ids = [entry['player']['id'] for entry in page_data]
    records_by_player = await get_players_records(player_ids)
    
    for entry in page_data:
        p = entry['player']
        loc_str = "Не указан" if p['location'] == "-" else p['location']
        text += f"{entry['rank']}. {p['nickname']} | {loc_str} | Ср. балл: {entry['score']:.2f}\n"
        
        records = records_by_player.get(p['id'], [])
        completions = [r for r in records if r['progress_start'] == 0 and r['progress_end'] == 100]
        completions.sort(key=lambda x: x['position'])
        top_5 = completions[:5]
        
        progresses = [r for r in records if not (r['progress_start'] == 0 and r['progress_end'] == 100)]
        progresses = filter_best_progresses(progresses, 'level_id')
        progresses.sort(key=lambda x: x['position'])
        
        if top_5:
            hardest_texts = []
            for c in top_5:
                name = c['level_name']
                if name.lower() in ambiguous_names:
                    name += f" [{dict(c).get('creator', 'Unknown')}]"
                hardest_texts.append(name)
            text += "   ⚔️ Самые сложные: " + ", ".join(hardest_texts) + "\n"
            
        if progresses:
            from collections import defaultdict
            grouped_progs = defaultdict(list)
            for p_rec in progresses:
                prog_str = f"{p_rec['progress_end']}%" if p_rec['progress_start'] == 0 else f"{p_rec['progress_start']}-{p_rec['progress_end']}%"
                name = p_rec['level_name']
                if name.lower() in ambiguous_names:
                    name += f" [{dict(p_rec).get('creator', 'Unknown')}]"
                if prog_str not in grouped_progs[name]:
                    grouped_progs[name].append(prog_str)
                
            prog_texts = []
            for lvl_name, p_list in list(grouped_progs.items())[:3]:
                prog_texts.append(f"{lvl_name} {' | '.join(p_list)}")
            text += f"   📈 Прогресс: {', '.join(prog_texts)}\n"
        text += "\n"
        
    builder = InlineKeyboardBuilder()
    if page > 1:
        builder.button(text="⬅️ Назад", callback_data=TopCallback(page=page-1, filter_type=filter_type[:50]).pack())
    if page < total_pages:
        builder.button(text="Вперёд ➡️", callback_data=TopCallback(page=page+1, filter_type=filter_type[:50]).pack())
    builder.adjust(2)
    
    markup = builder.as_markup() if total_pages > 1 else None
    
    if hasattr(message_or_query, 'message'):
        try:
            await message_or_query.message.edit_text(text, reply_markup=markup)
        except Exception:
            pass
    else:
        await message_or_query.answer(text, reply_markup=markup)

@router.callback_query(TopCallback.filter())
async def cb_top(query: CallbackQuery, callback_data: TopCallback):
    page = callback_data.page
    ftype = callback_data.filter_type
    
    if ftype == "all":
        lb = await get_leaderboard()
        title = "Общий рейтинг"
    elif ftype == "mob":
        lb = await get_leaderboard(filter_platform="mob")
        title = "Рейтинг мобильных игроков"
    elif ftype.startswith("loc="):
        loc = ftype[4:]
        lb = await get_leaderboard(filter_location=loc)
        title = f"Рейтинг по городу: {loc}"
    else:
        return
        
    await send_leaderboard(query, lb, title, ftype, page)
    try:
        await query.answer()
    except Exception:
        pass

@router.message(Command("top", "t", ignore_case=True))
async def cmd_top(message: Message):
    lb = await get_leaderboard()
    await send_leaderboard(message, lb, "Общий рейтинг", "all")

@router.message(Command("top_mobile", "tm", ignore_case=True))
async def cmd_top_mobile(message: Message):
    lb = await get_leaderboard(filter_platform="mob")
    await send_leaderboard(message, lb, "Рейтинг мобильных игроков", "mob")

@router.message(Command("top_location", "tl", ignore_case=True))
async def cmd_top_location(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Укажите город: /tl Москва\nС пробелами — без кавычек: /tl Нижний Тагил")
        return
        
    location = args[1]
    if location == "-" or location.lower() == "неизвестно":
        await message.answer("Укажите город из профиля игрока, например: /tl Москва.")
        return
        
    lb = await get_leaderboard(filter_location=location)
    await send_leaderboard(message, lb, f"Рейтинг по городу: {location}", f"loc={location}")

def generate_player_profile_text(player, entry, records, ambiguous_names, *, expanded=False):
    score_str = f"{entry['score']:.2f}" if entry else "—"
    place_str = f"{entry['rank']}" if entry else "Вне рейтинга — нет прохождений"
    
    completions = [r for r in records if r['progress_start'] == 0 and r['progress_end'] == 100]
    completions.sort(key=lambda x: x['position'])
    
    progresses = [r for r in records if not (r['progress_start'] == 0 and r['progress_end'] == 100)]
    progresses = filter_best_progresses(progresses, 'level_id')
    progresses.sort(key=lambda x: x['position'])
    
    text = f"👤 Профиль {player['nickname']}\n"
    loc_str = "Не указан" if player['location'] == "-" else player['location']
    text += f"Платформа: {platform_label(player['platform'])}\nГород: {loc_str}\n"
    text += f"Средний балл: {score_str}\nМесто в рейтинге: {place_str}\n\n"
    
    text += f"🏆 Пройдено уровней: {len(completions)}\n"
    if completions:
        text += "Все прохождения:\n" if expanded else "Самые сложные — топ-5:\n"
    if not completions:
        text += "Пока нет прохождений.\n"
    else:
        for i, c in enumerate(completions if expanded else completions[:5], 1):
            name = c['level_name']
            if name.lower() in ambiguous_names:
                name += f" [{dict(c).get('creator', 'Unknown')}]"
            if not expanded and len(name) > 120:
                name = name[:119] + "…"
            
            status_text = "Подтверждено Demonlist" if c['status'] == 'Verified' else ("Внесено вручную" if c['status'] == 'Manual' else c['status'])
            text += f"{i}. {name} (Топ-{c['position']}) — {status_text}\n"
        
    if progresses:
        text += "\n📈 Прогресс:\n"
        from collections import defaultdict
        grouped_progs = defaultdict(list)
        for p in progresses:
            prog_str = f"{p['progress_end']}%" if p['progress_start'] == 0 else f"{p['progress_start']}-{p['progress_end']}%"
            
            name = p['level_name']
            if name.lower() in ambiguous_names:
                name += f" [{dict(p).get('creator', 'Unknown')}]"
                
            if prog_str not in grouped_progs[(name, p['position'])]:
                grouped_progs[(name, p['position'])].append(prog_str)
            
        shown_progresses = list(grouped_progs.items())
        if not expanded:
            shown_progresses = shown_progresses[:3]
        for (lvl_name, pos), p_list in shown_progresses:
            if not expanded:
                lvl_name = lvl_name if len(lvl_name) <= 120 else lvl_name[:119] + "…"
                p_list = p_list[:3] + (["…"] if len(p_list) > 3 else [])
            text += f"- {lvl_name} (Топ-{pos}) {' | '.join(p_list)}\n"
        if not expanded and len(grouped_progs) > 3:
            text += "Остальной прогресс — в полном списке.\n"
            
    return text

def generate_player_profile_page(player, entry, records, ambiguous_names, page=0):
    # Page 0 is the compact profile. Positive pages preserve old callback links
    # and open the complete list, including the five hardest completions.
    page = max(0, page)
    if page == 0:
        text = generate_player_profile_text(player, entry, records, ambiguous_names)
        if not records:
            return text, None
        count = sum(r['progress_start'] == 0 and r['progress_end'] == 100 for r in records)
        builder = InlineKeyboardBuilder()
        builder.button(
            text=f"Все прохождения ({count})" if count else "Весь прогресс",
            callback_data=ProfileCallback(player_id=player['id'], page=1).pack(),
        )
        return text, builder.as_markup()

    pages = split_profile_text(
        generate_player_profile_text(player, entry, records, ambiguous_names, expanded=True)
    )
    page = max(1, min(page, len(pages)))
    text = pages[page - 1]
    text += f"\n\n📄 Страница {page}/{len(pages)}"
    builder = InlineKeyboardBuilder()
    if page > 1:
        builder.button(
            text="⬅️ Назад",
            callback_data=ProfileCallback(player_id=player['id'], page=page - 1).pack(),
        )
    if page < len(pages):
        builder.button(
            text="Вперёд ➡️",
            callback_data=ProfileCallback(player_id=player['id'], page=page + 1).pack(),
        )
    builder.adjust(2)
    builder.row(InlineKeyboardButton(
        text="К профилю", callback_data=ProfileCallback(player_id=player['id'], page=0).pack(),
    ))
    return text, builder.as_markup()


@router.callback_query(ProfileCallback.filter())
async def cb_profile(query: CallbackQuery, callback_data: ProfileCallback):
    from database.models import get_player_by_id, get_ambiguous_level_names

    player = await get_player_by_id(callback_data.player_id)
    if not player:
        await query.answer("Игрок не найден. Проверьте ник.", show_alert=True)
        return

    await query.answer()
    lb = await get_leaderboard()
    entry = next((item for item in lb if item['player']['id'] == player['id']), None)
    records = await get_player_records(player['id'])
    ambiguous_names = await get_ambiguous_level_names()
    text, markup = generate_player_profile_page(
        player, entry, records, ambiguous_names, callback_data.page
    )
    try:
        if query.inline_message_id:
            await query.bot.edit_message_text(
                text, inline_message_id=query.inline_message_id,
                reply_markup=markup, parse_mode=None,
            )
        elif isinstance(query.message, Message):
            await query.message.edit_text(text, reply_markup=markup, parse_mode=None)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


@router.message(Command("player", "profile", "p", ignore_case=True))
async def cmd_profile(message: Message):
    args = message.text.split(maxsplit=1)
    
    player = None
    if len(args) < 2 or args[1].lower() == "me":
        from database.models import get_player_by_tg
        player = await get_player_by_tg(message.from_user.id)
        if not player:
            await message.answer("Telegram ещё не привязан к профилю. Укажите ник: /p Mr Spaced.\nДля привязки обратитесь к администратору.")
            return
    else:
        nick = args[1]
        player = await get_player_by_nick(nick)
        if not player:
            await message.answer("Игрок не найден. Проверьте ник.")
            return
        
    lb = await get_leaderboard()
    entry = next((item for item in lb if item['player']['id'] == player['id']), None)
    records = await get_player_records(player['id'])
    
    from database.models import get_ambiguous_level_names
    ambiguous_names = await get_ambiguous_level_names()
    
    text, markup = generate_player_profile_page(player, entry, records, ambiguous_names)
    await message.answer(text, reply_markup=markup, parse_mode=None)

@router.message(Command("lvl", "level", ignore_case=True))
async def cmd_level(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Укажите название: /lvl Theory of Everything 2\nКавычки не нужны.")
        return
        
    query = args[1]
    levels = await get_levels_by_name(query)
        
    if not levels:
        await message.answer("Уровень не найден. Проверьте название; если его нет в базе, попросите администратора обновить список.")
        return
        
    if len(levels) > 1:
        builder = InlineKeyboardBuilder()
        for l in levels:
            creator_str = dict(l).get('creator', 'Unknown')
            cb_data = LvlCallback(level_id=l['level_id']).pack()
            builder.button(text=f"Топ-{l['position']} - {l['level_name']} [{creator_str}]", callback_data=cb_data)
        builder.adjust(1)
        await message.answer("Есть несколько уровней с таким названием. Выберите нужный:", reply_markup=builder.as_markup())
        return
        
    await render_level_info(levels[0], message)

async def generate_level_info_text(level) -> str:
    from database.connection import get_db_connection
    async with get_db_connection() as conn:
        cursor = await conn.execute('''
            SELECT r.*, p.nickname 
            FROM records r
            JOIN players p ON r.player_id = p.id
            WHERE r.level_id = ?
        ''', (level['level_id'],))
        level_records = await cursor.fetchall()
        
    completions = [r for r in level_records if r['progress_start'] == 0 and r['progress_end'] == 100]
    progresses = [r for r in level_records if not (r['progress_start'] == 0 and r['progress_end'] == 100)]
    progresses = filter_best_progresses(progresses, 'player_id')
    progresses.sort(key=lambda x: (x['progress_start'] != 0, x['progress_end']))
    
    creator_str = dict(level).get('creator', 'Unknown')
    ingame_id = dict(level).get('ingame_id')
    id_str = f" | ID в игре: {ingame_id}" if ingame_id else ""
    text = f"🌋 {level['level_name']} [{creator_str}] (Топ-{level['position']}{id_str})\n\n"
    
    text += f"🏆 Прошли ({len(completions)}):\n"
    if not completions:
        text += "- Пока никто\n"
    for c in completions:
        status_text = "Подтверждено Demonlist" if c['status'] == 'Verified' else ("Внесено вручную" if c['status'] == 'Manual' else c['status'])
        text += f"- {c['nickname']} ({status_text})\n"
        
    if progresses:
        from collections import defaultdict
        grouped_progs = defaultdict(list)
        for p in progresses:
            prog_str = f"{p['progress_end']}%" if p['progress_start'] == 0 else f"{p['progress_start']}-{p['progress_end']}%"
            if prog_str not in grouped_progs[p['nickname']]:
                grouped_progs[p['nickname']].append(prog_str)
            
        text += f"\n📈 Прогресс ({len(grouped_progs)}):\n"
        for nickname, p_list in grouped_progs.items():
            text += f"- {nickname} {' | '.join(p_list)}\n"
            
    return text

async def render_level_info(level, message_or_query):
    text = await generate_level_info_text(level)
            
    if hasattr(message_or_query, 'message'):
        try:
            await message_or_query.message.edit_text(text)
        except Exception:
            pass
    else:
        await message_or_query.answer(text)

@router.callback_query(LvlCallback.filter())
async def cb_lvl(query: CallbackQuery, callback_data: LvlCallback):
    lvl = await get_level_by_id(callback_data.level_id)
    await render_level_info(lvl, query)
    try:
        await query.answer()
    except Exception:
        pass

@router.message(Command("lvlp", "lp", ignore_case=True))
async def cmd_lvlp(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Укажите место или диапазон: /lp 1 или /lp 2-4.")
        return
        
    query = args[1].replace(" ", "")
    try:
        if "-" in query:
            start_pos, end_pos = map(int, query.split("-"))
        else:
            start_pos = end_pos = int(query)
    except ValueError:
        await message.answer("Укажите число или диапазон: /lp 1 или /lp 2-4.")
        return
        
    if start_pos > end_pos:
        start_pos, end_pos = end_pos, start_pos
        
    if start_pos < 1:
        await message.answer("Место в Demonlist должно быть от 1.")
        return
        
    from database.models import get_levels_with_victors
    
    if start_pos == end_pos:
        levels = await get_levels_with_victors(start_pos, end_pos)
        if not levels:
            await message.answer("❌ Уровень на таком месте не найден.")
            return
        await render_level_info(levels[0], message)
    else:
        if (end_pos - start_pos + 1) > 30:
            await message.answer("Слишком большой диапазон. Попробуйте /lp 1-30, затем /lp 31-60.")
            return
            
        levels = await get_levels_with_victors(start_pos, end_pos)
        if not levels:
            await message.answer("❌ Уровни в этом диапазоне не найдены.")
            return
            
        text = f"🌋 Места {start_pos}–{end_pos} в Demonlist:\n\n"
        for lvl in levels:
            creator_str = dict(lvl).get('creator', 'Unknown')
            victors = lvl['victors_count']
            text += f"{lvl['position']}. {lvl['level_name']} [{creator_str}] — прошли: {victors}\n"
            
        await message.answer(text)

@router.message(Command("try", ignore_case=True))
async def cmd_try(message: Message, state: FSMContext):
    import shlex
    try:
        args = shlex.split(message.text)
    except ValueError:
        args = message.text.split()
        
    if len(args) == 2:
        nick = "me"
        levels_str = args[1]
    elif len(args) >= 3:
        if args[1].lower() == "me":
            nick = "me"
            levels_str = " ".join(args[2:])
        else:
            nick = args[1]
            levels_str = " ".join(args[2:])
    else:
        await message.answer("Рассчитайте результат: /try me Bloodbath, Tartarus\nДля другого игрока: /try \"Mr Spaced\" Bloodbath\nРекорды не сохраняются. Подробнее: /help try.")
        return
        
    if nick == "me":
        from database.models import get_player_by_tg
        player = await get_player_by_tg(message.from_user.id)
        if not player:
            await message.answer("Telegram ещё не привязан к профилю. Укажите ник вместо me или попросите администратора привязать аккаунт.")
            return
    else:
        player = await get_player_by_nick(nick)
        if not player:
            await message.answer("Игрок не найден. Проверьте ник.")
            return
        
    records = await get_player_records(player['id'])
    completed_level_ids = {r['level_id'] for r in records if r['progress_start'] == 0 and r['progress_end'] == 100}
        
    level_names = [name.strip() for name in levels_str.split(",")]
    await process_try_query(message, state, player, level_names, [], [], completed_level_ids)

async def process_try_query(message_or_query, state: FSMContext, player, pending_names: list, new_level_ids: list, found_levels: list, completed_level_ids: set):
    from database.models import get_ambiguous_level_names
    ambiguous_names = await get_ambiguous_level_names()
    
    while pending_names:
        lvl_name = pending_names.pop(0)
        if not lvl_name:
            continue
            
        lvls = await get_levels_by_name(lvl_name)
        if not lvls:
            text = f"Уровень «{lvl_name}» не найден. Проверьте название."
            if hasattr(message_or_query, 'message'):
                try:
                    await message_or_query.message.edit_text(text)
                except Exception:
                    pass
            else:
                await message_or_query.answer(text)
            await state.clear()
            return
            
        if len(lvls) > 1:
            await state.set_state(TryState.resolving)
            await state.update_data(
                player_id=player['id'],
                pending_names=pending_names,
                new_level_ids=new_level_ids,
                found_levels=found_levels,
                completed_level_ids=list(completed_level_ids)
            )
            
            builder = InlineKeyboardBuilder()
            for l in lvls:
                creator_str = dict(l).get('creator', 'Unknown')
                cb_data = TryResolveCallback(level_id=l['level_id']).pack()
                builder.button(text=f"Топ-{l['position']} - {l['level_name']} [{creator_str}]", callback_data=cb_data)
            builder.adjust(1)
            
            text = f"Есть несколько уровней «{lvl_name}». Выберите нужный:"
            if hasattr(message_or_query, 'message'):
                try:
                    await message_or_query.message.edit_text(text, reply_markup=builder.as_markup())
                except Exception:
                    pass
            else:
                await message_or_query.answer(text, reply_markup=builder.as_markup())
            return
            
        lvl = lvls[0]
        if lvl['level_id'] not in completed_level_ids and lvl['level_id'] not in new_level_ids:
            name_disp = lvl['level_name']
            if name_disp.lower() in ambiguous_names:
                name_disp += f" [{dict(lvl).get('creator', 'Unknown')}]"
            new_level_ids.append(lvl['level_id'])
            found_levels.append(f"{name_disp} (Топ-{lvl['position']})")
        
    await state.clear()
    
    if not new_level_ids:
        text = "Нет новых прохождений для расчёта: указанные уровни уже пройдены или список пуст."
        if hasattr(message_or_query, 'message'):
            await message_or_query.message.edit_text(text, reply_markup=None)
        else:
            await message_or_query.answer(text)
        return
        
    from services.calculator import calculate_hypothetical_score, get_leaderboard
    
    new_score = await calculate_hypothetical_score(player['id'], new_level_ids)
    lb = await get_leaderboard()
    
    current_entry = next((e for e in lb if e['player']['id'] == player['id']), None)
    old_rank_str = str(current_entry['rank']) if current_entry else "—"
    old_score_str = f"{current_entry['score']:.2f}" if current_entry else "—"
    
    other_players = [e for e in lb if e['player']['id'] != player['id']]
    better_players = sum(1 for e in other_players if e['score'] < new_score)
    new_rank = better_players + 1
    
    if current_entry:
        diff = current_entry['rank'] - new_rank
        if diff > 0:
            diff_str = f"(🔼 {diff})"
        elif diff < 0:
            diff_str = f"(🔽 {abs(diff)})"
        else:
            diff_str = "(без изменений)"
    else:
        diff_str = "(вход в рейтинг)"
        
    text = (
        f"🔮 Что если {player['nickname']} пройдёт:\n"
        f"{', '.join(found_levels)}\n\n"
        f"📊 Баллы: {old_score_str} → {new_score:.2f}\n"
        f"🏆 Место в рейтинге: {old_rank_str} → {new_rank} {diff_str}"
    )
    if hasattr(message_or_query, 'message'):
        try:
            await message_or_query.message.edit_text(text)
        except Exception:
            pass
    else:
        await message_or_query.answer(text)

@router.callback_query(TryResolveCallback.filter(), TryState.resolving)
async def cb_try_resolve(query: CallbackQuery, callback_data: TryResolveCallback, state: FSMContext):
    data = await state.get_data()
    if not data:
        return
        
    level_id = callback_data.level_id
    lvl = await get_level_by_id(level_id)
    player_id = data['player_id']
    from database.models import get_player_by_id
    player = await get_player_by_id(player_id)
    
    from database.models import get_ambiguous_level_names
    ambiguous_names = await get_ambiguous_level_names()
    
    name_disp = lvl['level_name']
    if name_disp.lower() in ambiguous_names:
        name_disp += f" [{dict(lvl).get('creator', 'Unknown')}]"
        
    completed_level_ids = set(data.get('completed_level_ids', []))
    new_level_ids = data['new_level_ids']
    found_levels = data['found_levels']
    
    if lvl['level_id'] not in completed_level_ids and lvl['level_id'] not in new_level_ids:
        new_level_ids.append(lvl['level_id'])
        found_levels.append(f"{name_disp} (Топ-{lvl['position']})")
    
    # Remove the keyboard to prevent double clicks without deleting the message
    try:
        await query.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    
    await process_try_query(query, state, player, data['pending_names'], new_level_ids, found_levels, completed_level_ids)
    
    try:
        await query.answer()
    except Exception:
        pass

@router.message()
async def unknown_message(message: Message):
    if message.text and message.text.startswith('/'):
        await message.answer("Команда не найдена или недоступна. Список команд: /help.")
