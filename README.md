# Support Bot

Telegram-бот поддержки с категориями, медиа, статусами и статистикой.

## Переменные окружения

- `BOT_TOKEN` — токен от @BotFather (обязательно)
- `ADMIN_IDS` — id операторов через запятую, например `123456789,987654321`
- `NOTIFY_CHAT_ID` — опционально, отдельный чат для уведомлений
- `DB_PATH` — путь к SQLite (по умолчанию `support.db`)

## Запуск локально

```bash
pip install -r requirements.txt
export BOT_TOKEN="..."
export ADMIN_IDS="123456789"
python main.py
