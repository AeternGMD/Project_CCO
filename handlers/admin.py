import os
from html import escape
from utils.command_help import command_help
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
from services.demonlist_api import DemonlistAPIError, LevelUpdateBusy, fetch_levels, sync_player_records
from services.notifications import send_record_notification
from config import DB_PATH
from handlers.record_input import handle_record_command, router as record_input_router

router = Router()
router.message.filter(AdminFilter())
router.include_router(record_input_router)

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

@router.message(Command("add_player", "ap", ignore_case=True))
async def cmd_add_player(message: Message):
    import shlex
    try:
        args = shlex.split(message.text)
    except ValueError:
        args = message.text.split()
        
    if len(args) != 6:
        await message.answer(command_help("ap", admin=True), parse_mode="HTML")
        return
        
    nick = args[1]
    demonlist_id_raw = args[2]
    platform = args[3]
    api = args[-1]
    location = " ".join(args[4:-1])
    
    api_sync = api.lower() in ['yes', '1', 'true']
    demonlist_id = extract_demonlist_id(demonlist_id_raw)
    
    if await get_player_by_nick(nick):
        await message.answer("Игрок с таким ником уже есть. Изменить профиль: /help ep.")
        return
        
    await add_player(nick, demonlist_id, platform, location, api_sync)
    await message.answer(f"✅ Игрок {nick} добавлен.")

@router.message(Command("toggle_notifications", "tn", ignore_case=True))
async def cmd_toggle_notifications(message: Message):
    from database.models import get_setting, set_setting
    current = await get_setting("notifications_enabled", "true")
    new_state = "false" if current == "true" else "true"
    await set_setting("notifications_enabled", new_state)
    status = "включены 🔔" if new_state == "true" else "выключены 🔕"
    await message.answer(f"Уведомления о прохождениях {status}.")

@router.message(Command("restart", "res", ignore_case=True))
async def cmd_restart(message: Message):
    import sys
    import os
    from database.models import set_setting
    await set_setting("restart_notify", str(message.from_user.id))
    await message.answer("Перезапускаю бота…")
    args = [sys.executable] + sys.argv
    args = [f'"{a}"' if ' ' in a else a for a in args]
    os.execv(sys.executable, args)

@router.message(Command("del_player", "dp", ignore_case=True))
async def cmd_del_player(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Удалить профиль и все рекорды: /dp Mr Spaced\nКавычки не нужны. Удаление выполняется сразу, без подтверждения.")
        return
        
    nick = args[1]
    player = await get_player_by_nick(nick)
    if not player:
        await message.answer("Игрок не найден. Проверьте ник.")
        return
        
    await delete_player(player['id'])
    await message.answer(f"✅ Профиль {nick} и его рекорды удалены.")

@router.message(Command("edit_player", "ep", ignore_case=True))
async def cmd_edit_player(message: Message):
    import shlex
    try:
        args = shlex.split(message.text)
    except ValueError:
        args = message.text.split()
        
    if len(args) != 4:
        await message.answer(command_help("ep", admin=True), parse_mode="HTML")
        return
        
    nick = args[1]
    field = args[2].lower()
    value = args[3]
    
    player = await get_player_by_nick(nick)
    if not player:
        await message.answer("Игрок не найден. Проверьте ник.")
        return
        
    valid_fields = ['platform', 'location', 'api_sync', 'contacts', 'demonlist_id', 'nickname']
    if field not in valid_fields:
        await message.answer(f"Неизвестное поле. Доступны: {', '.join(valid_fields)}")
        return
        
    update_data = {}
    if field == 'api_sync':
        update_data[field] = value.lower() in ['yes', '1', 'true']
    elif field == 'demonlist_id':
        update_data[field] = extract_demonlist_id(value)
    elif field == 'nickname':
        if await get_player_by_nick(value):
            await message.answer(f"❌ Игрок с ником {value} уже существует.")
            return
        update_data[field] = value
    else:
        update_data[field] = value
        
    await update_player(player['id'], **update_data)
    await message.answer(f"✅ Профиль {nick} обновлён.")

@router.message(Command("record", "r", ignore_case=True))
async def cmd_record(message: Message):
    await handle_record_command(message)

@router.message(Command("del_record", "dr", ignore_case=True))
async def cmd_del_record(message: Message):
    await handle_record_command(message, action='del')

async def handle_level_query(message: Message, player_id: int, query: str, action: str, progress_start: int, progress_end: int):
    levels = await get_levels_by_name(query)
        
    if not levels:
        await message.answer(f"Уровень «{query}» не найден. Укажите название, не ID.")
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
        await message.answer(f"Найдено несколько уровней «{query}». Выберите нужный:", reply_markup=kb)

@router.callback_query(RecordCallback.filter(), AdminFilter())
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
    if not player or not level:
        await message.answer('Игрок или уровень больше не найден. Повторите команду с актуальными данными.')
        return
    
    old_leaderboard = await get_leaderboard()
    
    if action == "add":
        from services.calculator import calculate_progress_eligibility
        is_eligible = await calculate_progress_eligibility(player_id, level['position'])
        
        # Check progress rules
        if progress_end < 100:
            if (progress_end - progress_start) < 40:
                await message.answer("❌ Прогресс должен покрывать минимум 40% уровня.")
                return
                
                
        await add_record(player_id, level_id, progress_start, progress_end, "Manual")
        
        creator_str = dict(level).get('creator', 'Unknown')
        
        if progress_start > 0:
            prog_str = f"{progress_start}-{progress_end}%"
        else:
            prog_str = f"{progress_end}%"
            
        await message.answer(f"✅ {player['nickname']} · {level['level_name']} [{creator_str}] · {prog_str} — записано.")
        
        # Notify globally if it's a new 100% completion
        if progress_end == 100:
            new_leaderboard = await get_leaderboard()
            await send_record_notification(
                bot, player['nickname'], player['platform'], level['level_name'], 
                level['position'], old_leaderboard, new_leaderboard, record_deleted=False,
                progress_start=progress_start, progress_end=progress_end, is_eligible=is_eligible
            )
        
    elif action == "del":
        deleted_count = await delete_record(player_id, level_id)
        if deleted_count > 0:
            creator_str = dict(level).get('creator', 'Unknown')
            await message.answer(f"🗑 {player['nickname']} · {level['level_name']} [{creator_str}] — рекорды удалены.")
            
            new_leaderboard = await get_leaderboard()
            await send_record_notification(
                bot, player['nickname'], player['platform'], level['level_name'], 
                level['position'], old_leaderboard, new_leaderboard, record_deleted=True
            )
        else:
            await message.answer("У игрока нет рекордов на этом уровне. Ничего не изменено.")

@router.message(Command("link", ignore_case=True))
async def cmd_link(message: Message):
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer("Пример: /link Kwikzy 123456789\nНужен числовой Telegram ID, не @username. Ник пока должен быть без пробелов.")
        return
    nick = args[1]
    if not args[2].isdigit():
        await message.answer("❌ Telegram ID должен быть числом.")
        return
    tg_id = int(args[2])
    
    player = await get_player_by_nick(nick)
    if not player:
        await message.answer("Игрок не найден. Проверьте ник.")
        return
        
    from database.models import link_player_tg
    await link_player_tg(player['id'], tg_id)
    await message.answer(f"✅ Telegram {tg_id} привязан к профилю {player['nickname']}.")

@router.message(Command("unlink", ignore_case=True))
async def cmd_unlink(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Укажите ник: /unlink Mr Spaced\nКавычки не нужны. Профиль и рекорды сохранятся.")
        return
    nick = args[1]
    
    player = await get_player_by_nick(nick)
    if not player:
        await message.answer("Игрок не найден. Проверьте ник.")
        return
        
    from database.models import unlink_player_tg
    await unlink_player_tg(player['id'])
    await message.answer(f"✅ Telegram отвязан от профиля {player['nickname']}.")

@router.message(Command("info_update", "iu", ignore_case=True))
async def cmd_info_update(message: Message):
    msg = await message.answer("Обновляю уровни из Demonlist…")
    
    async def update_progress(current, total):
        if total == 0:
            return
        percent = current / total
        bar_length = 20
        filled = int(bar_length * percent)
        bar = "█" * filled + "░" * (bar_length - filled)
        text = f"Сохраняю уровни…\n[{bar}] {current}/{total}"
        try:
            await msg.edit_text(text)
        except:
            pass
            
    try:
        updated = await fetch_levels(progress_callback=update_progress)
    except LevelUpdateBusy:
        await msg.edit_text('⏳ Обновление уровней уже выполняется. Попробуйте позже.')
        return
    except DemonlistAPIError as exc:
        await msg.edit_text(
            "Не удалось обновить уровни. Возможна ошибка Demonlist, сети или базы данных. "
            "Повторите команду позже.\n\n"
            f"Подробности: {exc}"
        )
        return
    
    await msg.edit_text(f"✅ Обновлено уровней: {updated}.\nСинхронизирую прохождения игроков…")
    
    # Run sync for all players in background
    from database.models import get_all_players
    players = await get_all_players()
    failed_profiles = 0
    for p in players:
        if p['api_sync']:
            if not await sync_player_records(p['id']):
                failed_profiles += 1

    if failed_profiles:
        await msg.edit_text(
            f"⚠️ Уровни обновлены, но часть профилей не синхронизирована.\n"
            f"Обновлено уровней: {updated}\n"
            f"Профилей с ошибкой: {failed_profiles}"
        )
    else:
        await msg.edit_text(
            f"✅ Уровни и профили с включённой синхронизацией обновлены.\n"
            f"Обновлено уровней: {updated}"
        )

@router.message(Command("backup", "bkp", ignore_case=True))
async def cmd_backup(message: Message):
    import subprocess
    import os
    backup_path = "backup.sql"
    try:
        with open(backup_path, "wb") as f:
            import asyncio
            
            db_host = os.environ.get('DB_HOST', '127.0.0.1')
            db_user = os.environ.get('DB_USER', 'bot')
            db_pass = os.environ.get('DB_PASSWORD', 'botpassword')
            db_name = os.environ.get('DB_NAME', 'gdbot')
            db_port = os.environ.get('DB_PORT', '3306')
            
            proc = await asyncio.create_subprocess_exec(
                "mysqldump", "--skip-ssl", "--protocol=tcp", "-h", db_host, "-P", db_port, "-u", db_user, f"-p{db_pass}", db_name,
                stdout=f
            )
            await proc.communicate()
            if proc.returncode != 0:
                raise Exception("mysqldump failed")
        db_file = FSInputFile(backup_path)
        await message.answer_document(db_file, caption="Резервная копия базы (.sql). Сохраните файл в надёжном месте и не публикуйте его.")
        os.remove(backup_path)
    except Exception as e:
        await message.answer(f"Не удалось создать резервную копию: {e}")

@router.message(Command("restore"))
async def cmd_restore(message: Message, bot: Bot):
    print(f"DEBUG: /restore received from {message.from_user.id}")

    if not message.reply_to_message or not message.reply_to_message.document:
        print("DEBUG: Not replying to a document")
        await message.answer("Отправьте доверенную копию .sql или .db и ответьте на неё командой /restore.\nПеред восстановлением сохраните текущую базу: /backup.")
        return
        
    doc = message.reply_to_message.document
    is_sqlite = doc.file_name.endswith('.db')
    is_sql = doc.file_name.endswith('.sql')
    
    if not is_sqlite and not is_sql:
        await message.answer("Нужна резервная копия .sql или .db. Отправьте файл и ответьте на него командой /restore.")
        return
        
    backup_path = "restore.db" if is_sqlite else "restore.sql"
    
    msg = await message.answer("Скачиваю резервную копию…")
    await bot.download(doc, destination=backup_path)
    
    try:
        if is_sql:
            await msg.edit_text("Восстанавливаю базу из .sql…")
            with open(backup_path, "rb") as f:
                import asyncio
                
                db_host = os.environ.get('DB_HOST', '127.0.0.1')
                db_user = os.environ.get('DB_USER', 'bot')
                db_pass = os.environ.get('DB_PASSWORD', 'botpassword')
                db_name = os.environ.get('DB_NAME', 'gdbot')
                db_port = os.environ.get('DB_PORT', '3306')
                
                proc = await asyncio.create_subprocess_exec(
                    "mysql", "--skip-ssl", "--protocol=tcp", "-h", db_host, "-P", db_port, "-u", db_user, f"-p{db_pass}", db_name,
                    stdin=f
                )
                try:
                    await asyncio.wait_for(proc.communicate(), timeout=30.0)
                except asyncio.TimeoutError:
                    proc.kill()
                    raise Exception("Восстановление не завершилось за 30 секунд. Проверьте журнал сервера и состояние базы перед повторной попыткой.")
                if proc.returncode != 0:
                    raise Exception("mysql restore failed")
            await msg.edit_text("✅ База восстановлена из .sql.")
        else:
            await msg.edit_text("Переношу данные из старой копии .db в MariaDB…")
            from database.migrate import migrate_sqlite_to_mysql
            await migrate_sqlite_to_mysql(backup_path)
            await msg.edit_text("✅ Данные из .db перенесены в MariaDB.")
    except Exception as e:
        await msg.edit_text(f"Восстановление не завершено. База могла измениться частично. Подробности: {e}")
    finally:
        from database.models import invalidate_level_caches
        invalidate_level_caches()
        if os.path.exists(backup_path):
            os.remove(backup_path)

# --- Управление банами ---

@router.message(Command("ban", "b", ignore_case=True))
async def cmd_ban(message: Message):
    args = message.text.split(maxsplit=2)
    if len(args) < 2:
        await message.answer("Пример: /ban 123456789 30d Спам\nСрок: 10m — минуты, 2h — часы, 3d — дни. Без срока — бессрочно.")
        return
        
    try:
        user_id = int(args[1])
    except ValueError:
        await message.answer("Укажите числовой Telegram ID, например 123456789.")
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
        await message.answer(f"✅ Пользователь <code>{user_id}</code> заблокирован до {dt} (время сервера).\nПричина: {escape(reason) if reason else 'Не указана'}", parse_mode="HTML")
    else:
        await message.answer(f"✅ Пользователь <code>{user_id}</code> заблокирован бессрочно.\nПричина: {escape(reason) if reason else 'Не указана'}", parse_mode="HTML")

@router.message(Command("unban", "ub", ignore_case=True))
async def cmd_unban(message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Пример: /unban 123456789 — снять блокировку по Telegram ID.")
        return
        
    try:
        user_id = int(args[1])
    except ValueError:
        await message.answer("Укажите числовой Telegram ID, например 123456789.")
        return
        
    from database.models import unban_user
    if await unban_user(user_id):
        await message.answer(f"✅ Пользователь <code>{user_id}</code> разблокирован.", parse_mode="HTML")
    else:
        await message.answer(f"❌ Пользователь <code>{user_id}</code> не заблокирован.", parse_mode="HTML")
