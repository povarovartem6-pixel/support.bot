import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message

from config import BOT_TOKEN, ADMIN_IDS, is_admin
from database import init_db
from handlers import register_handlers

# Включаем подробные логи
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан в переменных окружения!")
    
    logging.info(f"Бот запускается. Админы: {ADMIN_IDS}")

    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    # 1. Сначала подключаем все конкретные хэндлеры (юзер, админ)
    register_handlers(dp)
    logging.info("Хэндлеры из папки handlers успешно подключены.")

    # 2. Fallback (ловим всё остальное) регистрируем СТРОГО ПОСЛЕ них
    @dp.message()
    async def fallback(message: Message):
        logging.info(f"Сработал fallback от пользователя {message.from_user.id}")
        if is_admin(message.from_user.id):
            await message.answer(
                "Команды администратора:\n"
                "/tickets [open|closed|all]\n"
                "/stats"
            )
        else:
            await message.answer("Чтобы оставить обращение — нажмите /start")

    await init_db()
    logging.info("База данных инициализирована.")
    
    # Сбрасываем старые накопившиеся сообщения, чтобы не было конфликтов
    await bot.delete_webhook(drop_pending_updates=True) 
    
    logging.info("Запускаем polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
