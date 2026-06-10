import time
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery, InlineQuery
from database.models import get_ban_info, is_admin

class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, limit: float = 2.5):
        self.limit = limit
        self.users_cache: Dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        
        user_id = None
        if isinstance(event, Message):
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
        elif isinstance(event, InlineQuery):
            user_id = event.from_user.id
            
        if user_id:
            # 1. Проверка на бан
            ban_info = await get_ban_info(user_id)
            if ban_info:
                banned_until = ban_info['banned_until']
                if banned_until is None or banned_until > time.time():
                    # Пользователь забанен, игнорируем апдейт
                    return
                else:
                    # Бан истек, можно было бы разбанить, но пока просто пропускаем
                    pass
            
            # 2. Проверка на админа
            admin = await is_admin(user_id)
            if admin:
                return await handler(event, data)
                
            # 3. Rate limit (Анти-спам)
            current_time = time.time()
            last_time = self.users_cache.get(user_id, 0)
            
            if current_time - last_time < self.limit:
                # Спам, игнорируем
                return
                
            self.users_cache[user_id] = current_time

        return await handler(event, data)
