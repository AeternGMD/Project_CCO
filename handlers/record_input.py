"""Resolve all ambiguities before writing; bounded, short-lived button state."""
from collections import OrderedDict
from dataclasses import dataclass, field
import secrets
import time

from aiogram import Router
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.models import get_record_catalog_version
from services.record_catalog import get_record_catalog
from services.record_resolver import resolve_record_command
from utils.filters import AdminFilter

router = Router()
PENDING_TTL = 300
MAX_PENDING = 64
_pending = OrderedDict()


class RecordChoice(CallbackData, prefix='recordchoice'):
    token: str
    index: int


@dataclass
class PendingRecord:
    token: str
    owner_id: int
    chat_id: int
    action: str
    plans: list
    version: int
    expires: float
    plan: object = None
    selected: dict = field(default_factory=dict)
    group_index: int = -1
    choices: list = field(default_factory=list)
    message_id: int = 0


def remember(work):
    for token, old in list(_pending.items()):
        if old.expires <= time.monotonic() or (old.owner_id, old.chat_id) == (work.owner_id, work.chat_id):
            _pending.pop(token, None)
    while len(_pending) >= MAX_PENDING:
        _pending.popitem(last=False)
    _pending[work.token] = work


async def handle_record_command(message: Message, action='add'):
    catalog = await get_record_catalog()
    try:
        plans = resolve_record_command(message.text, catalog, action)
    except ValueError as exc:
        example = '/r Mr Spaced: Tidal Wave, Bloodbath' if action == 'add' else '/dr Mr Spaced: Tidal Wave, Bloodbath'
        help_command = '/help r' if action == 'add' else '/help dr'
        await message.answer(f'{exc}\n\nПример: {example}\nПодробнее: {help_command}', parse_mode=None)
        return
    work = PendingRecord(
        secrets.token_hex(6), message.from_user.id, message.chat.id, action,
        plans, get_record_catalog_version(), time.monotonic() + PENDING_TTL,
    )
    await advance(message, work)


async def advance(message, work, edit=False):
    if work.plan is None and len(work.plans) == 1:
        work.plan = work.plans[0]
    if work.plan is None:
        work.group_index = -1
        work.choices = work.plans
        labels = [f'@{p.player_id} {p.nickname[:40]}: {p.groups[0][0].label}' for p in work.plans]
        prompt = 'Команду можно понять по-разному. Выберите игрока и первый уровень:'
    else:
        for index, options in enumerate(work.plan.groups):
            if len(options) == 1:
                work.selected[index] = options[0]
        work.group_index = next((i for i in range(len(work.plan.groups)) if i not in work.selected), -1)
        if work.group_index == -1:
            await apply_plan(message, work, edit)
            return
        work.choices = work.plan.groups[work.group_index]
        labels = [option.label for option in work.choices]
        verb = 'зачисление' if work.action == 'add' else 'удаление'
        prompt = (f'Игрок: {work.plan.nickname}. Уточните {verb} '
                  f'для уровня {work.group_index + 1}/{len(work.plan.groups)}:')

    # Descriptions include placement/progress; short numeric buttons identify
    # options without relying on Telegram's button-label clipping.
    text = prompt + '\n\n' + '\n'.join(f'{i}. {label[:75]}' for i, label in enumerate(labels, 1))
    text += '\n\nДо завершения выбора рекорды не меняются. Выбрать может автор команды в течение 5 минут.'
    builder = InlineKeyboardBuilder()
    for i in range(len(labels)):
        builder.button(text=str(i + 1), callback_data=RecordChoice(token=work.token, index=i).pack())
    builder.adjust(5)
    builder.button(text='Отмена', callback_data=RecordChoice(token=work.token, index=-1).pack())
    if edit:
        sent = await message.edit_text(text, reply_markup=builder.as_markup(), parse_mode=None)
    else:
        sent = await message.answer(text, reply_markup=builder.as_markup(), parse_mode=None)
    work.message_id = sent.message_id
    remember(work)


@router.callback_query(RecordChoice.filter(), AdminFilter())
async def choose_record(query: CallbackQuery, callback_data: RecordChoice):
    work = _pending.get(callback_data.token)
    if work is None or work.expires <= time.monotonic():
        _pending.pop(callback_data.token, None)
        await query.answer('Время выбора истекло или команда уже обработана. Отправьте её заново.', show_alert=True)
        return
    if (query.from_user.id != work.owner_id or not isinstance(query.message, Message)
            or query.message.chat.id != work.chat_id or query.message.message_id != work.message_id):
        await query.answer('Эти кнопки доступны только автору исходной команды.', show_alert=True)
        return
    index = callback_data.index
    if index < -1 or index >= len(work.choices):
        await query.answer('Неверный вариант.', show_alert=True)
        return
    # Consume before awaiting to prevent duplicate writes from rapid clicks.
    _pending.pop(work.token)
    await query.answer()
    if index == -1:
        await query.message.edit_text('Отменено. Рекорды не изменены.', reply_markup=None)
        return
    if work.group_index == -1:
        work.plan = work.choices[index]
    else:
        work.selected[work.group_index] = work.choices[index]
    work.token = secrets.token_hex(6)
    await advance(query.message, work, edit=True)


async def apply_plan(message, work, edit):
    # Refresh the lazy cache to observe edits made while buttons were displayed.
    catalog = await get_record_catalog()
    player = catalog.players_by_id.get(work.plan.player_id)
    choices = [work.selected[i] for i in range(len(work.plan.groups))]
    if (work.version != get_record_catalog_version() or player is None
            or player['nickname'] != work.plan.nickname
            or any(option.level_id not in catalog.levels_by_id
                   or catalog.levels_by_id[option.level_id]['level_name'] != option.name
                   for option in choices)):
        await message.answer('Данные игроков или уровней изменились. Ничего не изменено этой командой; отправьте её заново.')
        return
    if edit:
        await message.edit_text('Выбор завершён. Обрабатываю команду…', reply_markup=None)
    from handlers.admin import process_record_action
    seen = set()
    for option in choices:
        for start, end in option.progresses:
            identity = (option.level_id, start, end)
            if identity in seen:
                continue
            seen.add(identity)
            await process_record_action(message, work.action, work.plan.player_id,
                                        option.level_id, start, end)
