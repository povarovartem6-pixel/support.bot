import logging

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove

from config import CATEGORIES, STATUS_LABELS, ADMIN_IDS, is_admin
from database import create_ticket, save_admin_message
from keyboards import category_kb, admin_reply_kb, cancel_kb

router = Router()


class UserFlow(StatesGroup):
    writing_message = State()


def extract_media(message: Message):
    if message.photo:
        return "photo", message.photo[-1].file_id
    if message.video:
        return "video", message.video.file_id
    if message.document:
        return "document", message.document.file_id
    if message.voice:
        return "voice", message.voice.file_id
    if message.audio:
        return "audio", message.audio.file_id
    if message.sticker:
        return "sticker", message.sticker.file_id
    if message.animation:
        return "animation", message.animation.file_id
    return None, None


@router.message(Command("start"))
async def start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Здравствуйте! Это бот поддержки.\n"
        "Выберите категорию обращения:",
        reply_markup=category_kb(),
    )


@router.callback_query(F.data.startswith("cat:"))
async def choose_category(cb: CallbackQuery, state: FSMContext):
    code = cb.data.split(":", 1)[1]
    name = CATEGORIES.get(code)
    if not name:
        await cb.answer("Неизвестная категория")
        return
    await state.update_data(category=code)
    await state.set_state(UserFlow.writing_message)
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer(
        f"Категория: {name}\n\n"
        "Напишите текст или отправьте файл/фото/голосовое:",
        reply_markup=cancel_kb(),
    )
    await cb.answer()


@router.message(UserFlow.writing_message, F.text == "❌ Отмена")
async def cancel_user(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Отменено. Чтобы начать заново — /start",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(UserFlow.writing_message)
async def receive_user_message(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    category = data.get("category", "question")
    text = message.text or message.caption or ""
    media_type, file_id = extract_media(message)

    if not text and not file_id:
        await message.answer("Пришлите текст, фото или файл.")
        return

    ticket_id = await create_ticket(
        user_id=message.from_user.id,
        username=message.from_user.username,
        category=category,
        text=text,
        media_type=media_type,
        file_id=file_id,
    )

    cat_name = CATEGORIES.get(category, category)
    header = (
        f"📨 <b>Обращение #{ticket_id}</b>\n"
        f"Категория: {cat_name}\n"
        f"Статус: {STATUS_LABELS['open']}\n"
        f"От: @{message.from_user.username or '—'} (id {message.from_user.id})\n\n"
        f"{text or '<медиа>'}"
    )

    for admin_id in ADMIN_IDS:
        try:
            if file_id:
                sender = {
                    "photo": bot.send_photo,
                    "video": bot.send_video,
                    "document": bot.send_document,
                    "voice": bot.send_voice,
                    "audio": bot.send_audio,
                    "sticker": bot.send_sticker,
                    "animation": bot.send_animation,
                }[media_type]
                sent = await sender(
                    admin_id, file_id,
                    caption=header,
                    reply_markup=admin_reply_kb(ticket_id),
                )
            else:
                sent = await bot.send_message(
                    admin_id, header, reply_markup=admin_reply_kb(ticket_id)
                )
            await save_admin_message(ticket_id, admin_id, sent.message_id)
        except Exception:
            logging.exception("send to admin failed")

    await state.clear()
    await message.answer(
        f"✅ Обращение #{ticket_id} принято. Мы ответим вам здесь.",
        reply_markup=ReplyKeyboardRemove(),
    )
