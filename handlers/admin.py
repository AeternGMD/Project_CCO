import os
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.filters.callback_data import CallbackData
from utils.filters import AdminFilter
from database.models import (
    add_player, get_player_by_nick, delete_player, update_player,
    get_level_by_id, get_levels_by_name, add_record, delete_record,
    get_player_by_id
)
from services.calculator import get_leaderboard, calculate_progress_eligibility
from services.demonlist_api import fetch_levels, sync_player_records
from services.notifications import send_record_notification
from config import DB_PATH

router = Router()
router.message.filter(AdminFilter())

class RecordCallback(CallbackData, prefix="rec"):
    action: str
    player_id: int
    level_id: int
    progress_start: int
    progress_end: int

def extract_demonlist_id(val: str) -> str:
    if val == "-": return val
    if "demonlist.org/profile/" in val:
        return val.rstrip('/').split('/')[-1]
    return val

@router.message(Command("add_player"))
async def cmd_add_player(message: Message):
    import shlex
    try:
        args = shlex.split(message.text)
    except ValueError:
        args = message.text.split()
        
    if len(args) != 6:
        await message.answer(
            "❌ Ошибка формата!\n"
            "Использование: /add_player [Ник] [Demonlist_ID] [Платформа] [Город] [API: 1/0]\n\n"
            "⚠️ Важно: Если ник или город содержит пробелы, ОБЯЗАТЕЛЬНО используйте двойные кавычки!\n"
            "Пример: /add_player \"Mr Spaced\" 123 pc \"Нижний Тагил\" 1"
        )
        return
        
    nick = args[1]
    demonlist_id_raw = args[2]
    platform = args[3]
    api = args[-1]
    location = " ".join(args[4:-1])
    
    api_sync = api.lower() in ['yes', '1', 'true']
    demonlist_id = extract_demonlist_id(demonlist_id_raw)
    
    if await get_player_by_nick(nick):
        await message.answer("❌ Игрок с таким ником уже существует.")
        return
        
    await add_player(nick, demonlist_id, platform, location, api_sync)
    await message.answer(f"✅ Игрок {nick} успешно добавлен.")

@router.message(Command("toggle_notifications"))
async def cmd_toggle_notifications(message: Message):
    from database.models import get_setting, set_setting
    current = await get_setting("notifications_enabled", "true")
    new_state = "false" if current == "true" else "true"
    await set_setting("notifications_enabled", new_state)
    status = "включены 🔔" if new_state == "true" else "выключены 🔕"
    await message.answer(f"Уведомления в канале теперь {status}.")

@router.message(Command("restart"))
async def cmd_restart(message: Message):
    import sys
    import os
    from database.models import set_setting
    await set_setting("restart_notify", str(message.from_user.id))
    await message.answer("🔄 Бот перезапускается...")
    args = [sys.executable] + sys.argv
    args = [f'"{a}"' if ' ' in a else a for a in args]
    os.execv(sys.executable, args)

@router.message(Command("update"))
async def cmd_update(message: Message):
    import asyncio
    import sys
    import os
    await message.answer("⬇️ Скачиваю обновления с GitHub...")
    proc = await asyncio.create_subprocess_shell("git pull origin main", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await proc.communicate()
    
    out_text = stdout.decode('utf-8', errors='ignore').strip()
    err_text = stderr.decode('utf-8', errors='ignore').strip()
    
    if proc.returncode == 0:
        if "Already up to date." in out_text or "Уже обновлено." in out_text:
            await message.answer("✅ Бот уже обновлен до последней версии.")
        else:
            from database.models import set_setting
            await set_setting("restart_notify", str(message.from_user.id))
            await message.answer(f"✅ Обновление загружено:\n<pre>{out_text}</pre>\n\n🔄 Перезапускаюсь...")
            args = [sys.executable] + sys.argv
            args = [f'"{a}"' if ' ' in a else a for a in args]
            os.execv(sys.executable, args)
    else:
        await message.answer(f"❌ Ошибка обновления:\n<pre>{err_text}</pre>")

@router.message(Command("del_player"))
async def cmd_del_player(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /del_player [Ник]")
        return
        
    nick = args[1]
    player = await get_player_by_nick(nick)
    if not player:
        await message.answer("❌ Игрок не найден.")
        return
        
    await delete_player(player['id'])
    await message.answer(f"✅ Игрок {nick} удален.")

@router.message(Command("edit_player"))
async def cmd_edit_player(message: Message):
    import shlex
    try:
        args = shlex.split(message.text)
    except ValueError:
        args = message.text.split()
        
    if len(args) != 4:
        await message.answer(
            "❌ Использование: /edit_player [Ник] [Поле] [Новое_Значение]\n"
            "Поля: platform, location, api_sync, contacts, demonlist_id\n\n"
            "⚠️ Важно: Если значение содержит пробелы, ОБЯЗАТЕЛЬНО используйте кавычки!\n"
            "Пример: /edit_player Kwikzy location \"Нижний Тагил\""
        )
        return
        
    nick = args[1]
    field = args[2].lower()
    value = args[3]
    
    player = await get_player_by_nick(nick)
    if not player:
        await message.answer("❌ Игрок не найден.")
        return
        
    valid_fields = ['platform', 'location', 'api_sync', 'contacts', 'demonlist_id']
    if field not in valid_fields:
        await message.answer(f"❌ Неверное поле. Допустимые: {', '.join(valid_fields)}")
        return
        
    update_data = {}
    if field == 'api_sync':
        update_data[field] = value.lower() in ['yes', '1', 'true']
    elif field == 'demonlist_id':
        update_data[field] = extract_demonlist_id(value)
    else:
        update_data[field] = value
        
    await update_player(player['id'], **update_data)
    await message.answer(f"✅ Профиль {nick} обновлен.")

def parse_progress(prog_str: str):
    prog_str = prog_str.replace('%', '')
    if '-' in prog_str:
        start, end = prog_str.split('-')
        return int(start), int(end)
    return 0, int(prog_str)

@router.message(Command("record"))
async def cmd_record(message: Message):
    import shlex
    try:
        args = shlex.split(message.text)
    except ValueError:
        args = message.text.split()
        
    if len(args) < 3:
        await message.answer("Использование: /record [\"Ник\"] [\"Название_или_ID\"] [Прогресс]\nПример: /record \"f f i z z\" \"Bloodlust\" 100")
        return
        
    nick = args[1]
    level_query = args[2]
    
    progress_str = args[3] if len(args) >= 4 else "100"
    
    try:
        progress_start, progress_end = parse_progress(progress_str)
    except ValueError:
        await message.answer("❌ Ошибка: неверный формат прогресса. Если ник или уровень содержит пробелы, оберните их в кавычки!\nПример: /record \"f f i z z\" \"Bloodlust\" 100")
        return
        
    player = await get_player_by_nick(nick)
    if not player:
        await message.answer("❌ Игрок не найден.")
        return
        
    await handle_level_query(message, player['id'], level_query, "add", progress_start, progress_end)

@router.message(Command("del_record"))
async def cmd_del_record(message: Message):
    import shlex
    try:
        args = shlex.split(message.text)
    except ValueError:
        args = message.text.split()
        
    if len(args) < 3:
        await message.answer("Использование: /del_record [\"Ник\"] [\"Уровень\"]")
        return
        
    nick = args[1]
    level_query = args[2]
    
    player = await get_player_by_nick(nick)
    if not player:
        await message.answer("❌ Игрок не найден.")
        return
        
    await handle_level_query(message, player['id'], level_query, "del", 0, 100)

async def handle_level_query(message: Message, player_id: int, query: str, action: str, progress_start: int, progress_end: int):
    levels = []
    if query.isdigit():
        lvl = await get_level_by_id(int(query))
        if lvl:
            levels.append(lvl)
    
    if not levels:
        levels = await get_levels_by_name(query)
        
    if not levels:
        await message.answer("❌ Уровень не найден в кэше.")
        return
        
    if len(levels) == 1:
        await process_record_action(message, action, player_id, levels[0]['level_id'], progress_start, progress_end)
    else:
        # Collision! Need inline keyboard
        builder = []
        for lvl in levels:
            cb_data = RecordCallback(
                action=action, 
                player_id=player_id, 
                level_id=lvl['level_id'], 
                progress_start=progress_start, 
                progress_end=progress_end
            ).pack()
            creator_str = dict(lvl).get('creator', 'Unknown')
            builder.append([InlineKeyboardButton(text=f"Топ-{lvl['position']} - {lvl['level_name']} [{creator_str}]", callback_data=cb_data)])
        
        kb = InlineKeyboardMarkup(inline_keyboard=builder)
        await message.answer("Найдено уровней с таким названием: ", reply_markup=kb)

@router.callback_query(RecordCallback.filter())
async def cb_record_action(query: CallbackQuery, callback_data: RecordCallback, bot: Bot):
    await process_record_action(
        query.message, 
        callback_data.action, 
        callback_data.player_id, 
        callback_data.level_id, 
        callback_data.progress_start, 
        callback_data.progress_end,
        bot
    )
    await query.message.delete()
    await query.answer()

async def process_record_action(message: Message, action: str, player_id: int, level_id: int, progress_start: int, progress_end: int, bot: Bot = None):
    if bot is None:
        bot = message.bot
        
    player = await get_player_by_id(player_id)
    level = await get_level_by_id(level_id)
    
    old_leaderboard = await get_leaderboard()
    
    if action == "add":
        # Check progress rules
        if progress_end < 100:
            if (progress_end - progress_start) < 40:
                await message.answer("❌ Прогресс должен покрывать минимум 40% уровня.")
                return
            is_eligible = await calculate_progress_eligibility(player_id, level['position'])
            if not is_eligible:
                await message.answer("❌ Этот уровень не войдет в топ-5 хардестов игрока. Прогресс не записан.")
                return
                
        await add_record(player_id, level_id, progress_start, progress_end, "Manual")
        
        creator_str = dict(level).get('creator', 'Unknown')
        
        if progress_start > 0:
            prog_str = f"{progress_start}-{progress_end}%"
        else:
            prog_str = f"{progress_end}%"
            
        await message.answer(f"✅ Добавлено: {level['level_name']} [{creator_str}] ({prog_str}) для {player['nickname']}")
        
        # Notify globally if it's a new 100% completion
        if progress_end == 100:
            new_leaderboard = await get_leaderboard()
            await send_record_notification(
                bot, player['nickname'], player['platform'], level['level_name'], 
                level['position'], old_leaderboard, new_leaderboard, record_deleted=False,
                progress_start=progress_start, progress_end=progress_end
            )
        
    elif action == "del":
        await delete_record(player_id, level_id)
        creator_str = dict(level).get('creator', 'Unknown')
        await message.answer(f"🗑 Рекорд удален: {level['level_name']} [{creator_str}] для {player['nickname']}")
        
        new_leaderboard = await get_leaderboard()
        await send_record_notification(
            bot, player['nickname'], player['platform'], level['level_name'], 
            level['position'], old_leaderboard, new_leaderboard, record_deleted=True
        )

@router.message(Command("info_update"))
async def cmd_info_update(message: Message):
    msg = await message.answer("🔄 Загрузка данных с сайта...")
    
    async def update_progress(current, total):
        if total == 0:
            return
        percent = current / total
        bar_length = 20
        filled = int(bar_length * percent)
        bar = "█" * filled + "░" * (bar_length - filled)
        text = f"🔄 Обновление базы уровней...\n[{bar}] {current}/{total}"
        try:
            await msg.edit_text(text)
        except:
            pass
            
    updated = await fetch_levels(progress_callback=update_progress)
    
    await msg.edit_text(f"✅ База уровней обновлена ({updated}).\n🔄 Синхронизация профилей...")
    
    # Run sync for all players in background
    from database.models import get_all_players
    players = await get_all_players()
    for p in players:
        if p['api_sync']:
            await sync_player_records(p['id'])
            
    await msg.edit_text(f"✅ База уровней и профили игроков успешно обновлены!\nОбновлено уровней: {updated}")

@router.message(Command("backup"))
async def cmd_backup(message: Message):
    if os.path.exists(DB_PATH):
        db_file = FSInputFile(DB_PATH)
        await message.answer_document(db_file, caption="Резервная копия базы данных.")
    else:
        await message.answer("❌ База данных не найдена.")

@router.message(Command("restore"))
async def cmd_restore(message: Message, bot: Bot):
    if not message.reply_to_message or not message.reply_to_message.document:
        await message.answer("❌ Вы должны ответить на сообщение с файлом database.db.")
        return
        
    doc = message.reply_to_message.document
    if not doc.file_name.endswith('.db'):
        await message.answer("❌ Неверный формат файла.")
        return
        
    await bot.download(doc, destination=DB_PATH)
    await message.answer("✅ База данных успешно восстановлена!")

# --- Управление банами ---

@router.message(Command("ban"))
async def cmd_ban(message: Message):
    args = message.text.split(maxsplit=2)
    if len(args) < 2:
        await message.answer("Использование: /ban <user_id> [время: 1m/м, 2h/ч, 3d/д] [причина]")
        return
        
    try:
        user_id = int(args[1])
    except ValueError:
        await message.answer("❌ Неверный формат user_id.")
        return
        
    banned_until = None
    reason = None
    
    if len(args) == 3:
        parts = args[2].split(maxsplit=1)
        time_str = parts[0]
        import re
        match = re.match(r"^(\d+)([mмhчdд])$", time_str.lower())
        if match:
            val = int(match.group(1))
            unit = match.group(2)
            
            if unit in ('m', 'м'):
                delta = val * 60
            elif unit in ('h', 'ч'):
                delta = val * 3600
            elif unit in ('d', 'д'):
                delta = val * 86400
                
            import time
            banned_until = int(time.time()) + delta
            
            if len(parts) > 1:
                reason = parts[1]
        else:
            reason = args[2]
            
    from database.models import ban_user
    await ban_user(user_id, banned_until, reason)
    
    if banned_until:
        import datetime
        dt = datetime.datetime.fromtimestamp(banned_until).strftime('%Y-%m-%d %H:%M:%S')
        await message.answer(f"✅ Пользователь <code>{user_id}</code> забанен до {dt}.\nПричина: {reason or 'Не указана'}")
    else:
        await message.answer(f"✅ Пользователь <code>{user_id}</code> забанен навсегда.\nПричина: {reason or 'Не указана'}")

@router.message(Command("unban"))
async def cmd_unban(message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /unban <user_id>")
        return
        
    try:
        user_id = int(args[1])
    except ValueError:
        await message.answer("❌ Неверный формат user_id.")
        return
        
    from database.models import unban_user
    if await unban_user(user_id):
        await message.answer(f"✅ Пользователь <code>{user_id}</code> разбанен.")
    else:
        await message.answer(f"❌ Пользователь <code>{user_id}</code> не найден в списке забаненных.")
