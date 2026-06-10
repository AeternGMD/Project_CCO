from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from utils.filters import RootFilter
from database.models import add_admin, del_admin

router = Router()
# All handlers in this router require Root privileges
router.message.filter(RootFilter())

@router.message(Command("add_admin"))
async def cmd_add_admin(message: Message):
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: /add_admin [TG_ID]")
        return
        
    try:
        tg_id = int(args[1])
        await add_admin(tg_id)
        await message.answer(f"✅ Администратор {tg_id} добавлен.")
    except ValueError:
        await message.answer("❌ Ошибка: TG_ID должен быть числом.")

@router.message(Command("del_admin"))
async def cmd_del_admin(message: Message):
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: /del_admin [TG_ID]")
        return
        
    try:
        tg_id = int(args[1])
        await del_admin(tg_id)
        await message.answer(f"✅ Администратор {tg_id} удален.")
    except ValueError:
        await message.answer("❌ Ошибка: TG_ID должен быть числом.")
