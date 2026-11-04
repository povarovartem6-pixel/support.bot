import asyncio
import logging
import os
from datetime import datetime
import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)

# ================= НАСТРОЙКИ =================
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
# Твой ID (8361478292) прописан как запасной, если Bothost не передаст переменную
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "8361478292").split(",") if x.strip()]
DB_PATH = "support.db"

CATEGORIES = {
    "complaint": "😡 Жалоба",
    "question": "❓ Вопрос",
    "suggestion": "💡 Предложение",
}
STATUS_LABELS = {"open": "🟢 Открыт", "closed": "🔴 Закрыт"}

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# ================= СОСТОЯНИЯ (FSM) =================
class UserFlow(StatesGroup):
    writing_message = State()

class AdminFlow(StatesGroup):
    writing_reply = State()

# ================= БАЗА ДАННЫХ =================
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                username TEXT, category TEXT NOT NULL, text TEXT, media_type TEXT,
                file_id TEXT, status TEXT NOT NULL DEFAULT 'open', assigned_to INTEGER,
                created_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id INTEGER NOT NULL,
                admin_id INTEGER NOT NULL, text TEXT, created_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ticket_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id INTEGER NOT NULL,
                admin_chat INTEGER, admin_msg_id INTEGER
            )
        """)
        await db.commit()

async def create_ticket(user_id, username, category, text, media_type, file_id) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO tickets (user_id, username, category, text, media_type, file_id, created_at) VALUES (?,?,?,?,?,?,?)",
            (user_id, username, category, text, media_type, file_id, datetime.utcnow().isoformat()),
        )
        await db.commit()
        return cur.lastrowid

async def get_ticket(ticket_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,))
        return await cur.fetchone()

async def save_reply(ticket_id, admin_id, text):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO replies (ticket_id, admin_id, text, created_at) VALUES (?,?,?,?)",
                         (ticket_id, admin_id, text, datetime.utcnow().isoformat()))
        await db.execute("UPDATE tickets SET assigned_to=? WHERE id=?", (admin_id, ticket_id))
        await db.commit()

async def set_status(ticket_id: int, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE tickets SET status=? WHERE id=?", (status, ticket_id))
        await db.commit()

async def save_admin_message(ticket_id, admin_chat, admin_msg_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO ticket_messages (ticket_id, admin_chat, admin_msg_id) VALUES (?,?,?)",
                         (ticket_id, admin_chat, admin_msg_id))
        await db.commit()

async def get_admin_messages(ticket_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT admin_chat, admin_msg_id FROM ticket_messages WHERE ticket_id=?", (ticket_id,))
        return await cur.fetchall()

# ================= КЛАВИАТУРЫ =================
def category_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=name, callback_data=f"cat:{code}")] for code, name in CATEGORIES.items()
    ])

def admin_reply_kb(ticket_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Ответить", callback_data=f"reply:{ticket_id}")]
    ])

def answered_kb(ticket_id: int, operator_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ Отвечено (оператор {operator_id})", callback_data="noop")],
        [InlineKeyboardButton(text="🔒 Закрыть", callback_data=f"close:{ticket_id}")]
    ])

def closed_kb(ticket_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔓 Переоткрыть", callback_data=f"reopen:{ticket_id}")]
    ])

def cancel_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)

def extract_media(message: Message):
    if message.photo: return "photo", message.photo[-1].file_id
    if message.video: return "video", message.video.file_id
    if message.document: return "document", message.document.file_id
    if message.voice: return "voice", message.voice.file_id
    if message.audio: return "audio", message.audio.file_id
    if message.sticker: return "sticker", message.sticker.file_id
    if message.animation: return "animation", message.animation.file_id
    return None, None

# ================= ХЭНДЛЕРЫ ПОЛЬЗОВАТЕЛЯ =================
@dp.message(Command("start"))
async def start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Здравствуйте! Это бот поддержки.\nВыберите категорию обращения:", reply_markup=category_kb())

@dp.callback_query(F.data.startswith("cat:"))
async def choose_category(cb: CallbackQuery, state: FSMContext):
    code = cb.data.split(":", 1)[1]
    name = CATEGORIES.get(code)
    if not name: return await cb.answer("Неизвестная категория")
    await state.update_data(category=code)
    await state.set_state(UserFlow.writing_message)
    try: await cb.message.edit_reply_markup(reply_markup=None)
    except: pass
    await cb.message.answer(f"Категория: {name}\n\nНапишите текст или отправьте файл:", reply_markup=cancel_kb())
    await cb.answer()

@dp.message(UserFlow.writing_message, F.text == "❌ Отмена")
async def cancel_user(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено. Чтобы начать заново — /start", reply_markup=ReplyKeyboardRemove())

@dp.message(UserFlow.writing_message)
async def receive_user_message(message: Message, state: FSMContext):
    data = await state.get_data()
    category = data.get("category", "question")
    text = message.text or message.caption or ""
    media_type, file_id = extract_media(message)

    if not text and not file_id: return await message.answer("Пришлите текст, фото или файл.")

    ticket_id = await create_ticket(message.from_user.id, message.from_user.username, category, text, media_type, file_id)
    cat_name = CATEGORIES.get(category, category)
    header = f"📨 <b>Обращение #{ticket_id}</b>\nКатегория: {cat_name}\nОт: @{message.from_user.username or '—'} (id {message.from_user.id})\n\n{text or '<медиа>'}"

    for admin_id in ADMIN_IDS:
        try:
            if file_id:
                sender = {"photo": bot.send_photo, "video": bot.send_video, "document": bot.send_document, "voice": bot.send_voice, "audio": bot.send_audio, "sticker": bot.send_sticker, "animation": bot.send_animation}[media_type]
                sent = await sender(admin_id, file_id, caption=header, reply_markup=admin_reply_kb(ticket_id))
            else:
                sent = await bot.send_message(admin_id, header, reply_markup=admin_reply_kb(ticket_id))
            await save_admin_message(ticket_id, admin_id, sent.message_id)
        except Exception: logging.exception("send to admin failed")

    await state.clear()
    await message.answer(f"✅ Обращение #{ticket_id} принято.", reply_markup=ReplyKeyboardRemove())

# ================= ХЭНДЛЕРЫ АДМИНА =================
@dp.callback_query(F.data.startswith("reply:"))
async def admin_click_reply(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return await cb.answer("Нет доступа", show_alert=True)
    ticket_id = int(cb.data.split(":", 1)[1])
    ticket = await get_ticket(ticket_id)
    if not ticket: return await cb.answer("Не найдено", show_alert=True)
    if ticket[7] == "closed": return await cb.answer("Закрыто", show_alert=True)

    await state.update_data(ticket_id=ticket_id)
    await state.set_state(AdminFlow.writing_reply)
    await cb.message.answer(f"Напишите ответ по обращению #{ticket_id}:", reply_markup=cancel_kb())
    await cb.answer()

@dp.message(AdminFlow.writing_reply, F.text == "❌ Отмена")
async def cancel_admin(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.clear()
    await message.answer("Отменено.", reply_markup=ReplyKeyboardRemove())

@dp.message(AdminFlow.writing_reply)
async def admin_send_reply(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    data = await state.get_data()
    ticket_id = data.get("ticket_id")
    ticket = await get_ticket(ticket_id)
    if not ticket: return await message.answer("Не найдено.")

    user_id = ticket[1]
    reply_text = message.text or message.caption or ""
    mt, fid = extract_media(message)

    if not reply_text and not fid: return await message.answer("Пустой ответ.")

    try:
        if reply_text:
            await bot.send_message(user_id, f"💬 <b>Ответ поддержки #{ticket_id}</b>\n\n{reply_text}")
        if fid:
            sender = {"photo": bot.send_photo, "video": bot.send_video, "document": bot.send_document, "voice": bot.send_voice, "audio": bot.send_audio, "sticker": bot.send_sticker, "animation": bot.send_animation}[mt]
            await sender(user_id, fid, caption=f"💬 Ответ #{ticket_id}")

        await save_reply(ticket_id, message.from_user.id, reply_text or f"<{mt}>")

        for chat_id, msg_id in await get_admin_messages(ticket_id):
            try: await bot.edit_message_reply_markup(chat_id=chat_id, message_id=msg_id, reply_markup=answered_kb(ticket_id, message.from_user.id))
            except: pass
        await message.answer("✅ Ответ отправлен.", reply_markup=ReplyKeyboardRemove())
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=ReplyKeyboardRemove())
    await state.clear()

@dp.callback_query(F.data.startswith("close:"))
async def close_ticket(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return await cb.answer("Нет доступа", show_alert=True)
    ticket_id = int(cb.data.split(":", 1)[1])
    await set_status(ticket_id, "closed")
    try: await cb.message.edit_reply_markup(reply_markup=closed_kb(ticket_id))
    except: pass
    await cb.answer("Закрыто")

@dp.callback_query(F.data.startswith("reopen:"))
async def reopen_ticket(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return await cb.answer("Нет доступа", show_alert=True)
    ticket_id = int(cb.data.split(":", 1)[1])
    await set_status(ticket_id, "open")
    try: await cb.message.edit_reply_markup(reply_markup=admin_reply_kb(ticket_id))
    except: pass
    await cb.answer("Переоткрыто")

@dp.callback_query(F.data == "noop")
async def noop(cb: CallbackQuery): await cb.answer("Уже отвечено")

# ================= ЗАПУСК =================
async def main():
    if not BOT_TOKEN: raise RuntimeError("BOT_TOKEN не задан!")
    logging.info(f"Старт. Админы: {ADMIN_IDS}")
    await init_db()
    
    @dp.message()
    async def fallback(message: Message):
        logging.info(f"Сработал fallback от {message.from_user.id}")
        await message.answer("Чтобы оставить обращение — нажмите /start")

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
