from aiogram.filters import BaseFilter
from aiogram.types import Message
from database.models import is_admin
from config import ROOT_ID

class AdminFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return await is_admin(message.from_user.id)

class RootFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return message.from_user.id == ROOT_ID
