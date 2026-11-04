import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
NOTIFY_CHAT_ID = os.getenv("NOTIFY_CHAT_ID")  # опционально
NOTIFY_CHAT_ID = int(NOTIFY_CHAT_ID) if NOTIFY_CHAT_ID else None

DB_PATH = os.getenv("DB_PATH", "support.db")

CATEGORIES = {
    "complaint": "😡 Жалоба",
    "question": "❓ Вопрос",
    "suggestion": "💡 Предложение",
}

STATUS_LABELS = {"open": "🟢 Открыт", "closed": "🔴 Закрыт"}


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def notify_chat() -> int:
    return NOTIFY_CHAT_ID or (ADMIN_IDS[0] if ADMIN_IDS else 0)
