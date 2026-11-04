from aiogram import Router, F, Bot
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove

from config import (
    CATEGORIES, STATUS_LABELS, is_admin,
)
from database import (
    get_ticket, save_reply, mark_answered, set_status,
    get_admin_messages, list_tickets, get_stats,
)
from keyboards import admin_reply_kb, answered_kb, closed_kb, cancel_kb
from handlers.user import extract_media

router = Router()


class AdminFlow(StatesGroup):
    writing_reply = State()


@router.callback_query(F.data.startswith("reply:"))
async def admin_click_reply(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("Нет доступа", show_alert=True)
        return
    ticket_id = int(cb.data.split(":", 1)[1])
    ticket = await get_ticket(ticket_id)
    if not ticket:
        await cb.answer("Обращение не найдено", show_alert=True)
        return
    if ticket[7] == "closed":
        await cb.answer("Обращение закрыто. Сначала переоткройте.", show_alert=True)
        return

    await state.update_data(ticket_id=ticket_id)
    await state.set_state(AdminFlow.writing_reply)
    await cb.message.answer(
        f"Напишите ответ пользователю по обращению #{ticket_id}:",
        reply_markup=cancel_kb(),
    )
    await cb.answer()


@router.message(AdminFlow.writing_reply, F.text == "❌ Отмена")
async def cancel_admin(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer("Отменено.", reply_markup=ReplyKeyboardRemove())


@router.message(AdminFlow.writing_reply)
async def admin_send_reply(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    ticket_id = data.get("ticket_id")
    ticket = await get_ticket(ticket_id)
    if not ticket:
        await message.answer("Обращение не найдено.")
        await state.clear()
        return

    _, user_id, username, category, text, media_type, file_id, status, assigned_to = ticket
    reply_text = message.text or message.caption or ""
    mt, fid = extract_media(message)

    if not reply_text and not fid:
        await message.answer("Пустой ответ. Напишите текст или пришлите медиа.")
        return

    try:
        if reply_text:
            await bot.send_message(
                user_id,
                f"💬 <b>Ответ поддержки по обращению #{ticket_id}</b>\n\n{reply_text}",
            )
        if fid:
            sender = {
                "photo": bot.send_photo,
                "video": bot.send_video,
                "document": bot.send_document,
                "voice": bot.send_voice,
                "audio": bot.send_audio,
                "sticker": bot.send_sticker,
                "animation": bot.send_animation,
            }[mt]
            await sender(user_id, fid, caption=f"💬 Ответ по обращению #{ticket_id}")

        await save_reply(ticket_id, message.from_user.id, reply_text or f"<{mt}>")
        await mark_answered(ticket_id, message.from_user.id)

        for chat_id, msg_id in await get_admin_messages(ticket_id):
            try:
                await bot.edit_message_reply_markup(
                    chat_id=chat_id,
                    message_id=msg_id,
                    reply_markup=answered_kb(ticket_id, message.from_user.id),
                )
            except Exception:
                pass

        await message.answer("✅ Ответ отправлен.", reply_markup=ReplyKeyboardRemove())
    except Exception as e:
        await message.answer(
            f"❌ Не удалось отправить: {e}",
            reply_markup=ReplyKeyboardRemove(),
        )

    await state.clear()


@router.callback_query(F.data.startswith("close:"))
async def close_ticket(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("Нет доступа", show_alert=True)
        return
    ticket_id = int(cb.data.split(":", 1)[1])
    await set_status(ticket_id, "closed")
    try:
        await cb.message.edit_reply_markup(reply_markup=closed_kb(ticket_id))
    except Exception:
        pass
    await cb.answer("Обращение закрыто")


@router.callback_query(F.data.startswith("reopen:"))
async def reopen_ticket(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("Нет доступа", show_alert=True)
        return
    ticket_id = int(cb.data.split(":", 1)[1])
    await set_status(ticket_id, "open")
    try:
        await cb.message.edit_reply_markup(reply_markup=admin_reply_kb(ticket_id))
    except Exception:
        pass
    await cb.answer("Обращение переоткрыто")


@router.callback_query(F.data == "noop")
async def noop(cb: CallbackQuery):
    await cb.answer("Уже отвечено")


@router.message(Command("tickets"))
async def cmd_tickets(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return
    arg = (command.args or "open").strip().lower()
    if arg not in ("open", "closed", "all"):
        arg = "open"
    rows = await list_tickets(None if arg == "all" else arg)
    if not rows:
        await message.answer(f"Обращений ({arg}) нет.")
        return
    lines = [
        f"#{r[0]} [{r[1]}] {STATUS_LABELS.get(r[3], r[3])} @{r[2] or '—'}: {r[4]}"
        for r in rows
    ]
    await message.answer(f"Обращения ({arg}):\n\n" + "\n".join(lines))


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if not is_admin(message.from_user.id):
        return
    by_status, by_cat, replies_count = await get_stats()
    total = sum(by_status.values())
    lines = ["📊 <b>Статистика</b>", f"Всего: {total}"]
    for s, label in STATUS_LABELS.items():
        lines.append(f"{label}: {by_status.get(s, 0)}")
    lines.append("")
    for code, name in CATEGORIES.items():
        lines.append(f"{name}: {by_cat.get(code, 0)}")
    lines.append(f"\nОтветов операторов: {replies_count}")
    await message.answer("\n".join(lines))
