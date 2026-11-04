import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message

from config import BOT_TOKEN, is_admin
from database import init_db
from handlers import register_handlers

logging.basicConfig(level=logging.INFO)


async def fallback(message: Message):
    if is_admin(message.from_user.id):
        await message.answer(
            "Команды:\n"
            "/tickets [open|closed|all] — обращения\n"
            "/stats — статистика"
        )
        return
    await message.answer("Чтобы оставить обращение — /start")


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан в переменных окружения")
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    register_handlers(dp)
    dp.message.register(fallback)  # fallback последним
    await init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
