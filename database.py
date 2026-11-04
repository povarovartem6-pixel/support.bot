import aiosqlite
from datetime import datetime

from config import DB_PATH


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                category TEXT NOT NULL,
                text TEXT,
                media_type TEXT,
                file_id TEXT,
                status TEXT NOT NULL DEFAULT 'open',
                assigned_to INTEGER,
                created_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                admin_id INTEGER NOT NULL,
                text TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(ticket_id) REFERENCES tickets(id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ticket_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                admin_chat INTEGER,
                admin_msg_id INTEGER,
                FOREIGN KEY(ticket_id) REFERENCES tickets(id)
            )
        """)
        await db.commit()


async def create_ticket(user_id, username, category, text, media_type, file_id) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO tickets (user_id, username, category, text, media_type, file_id, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (user_id, username, category, text, media_type, file_id,
             datetime.utcnow().isoformat()),
        )
        await db.commit()
        return cur.lastrowid


async def get_ticket(ticket_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id, user_id, username, category, text, media_type, file_id, status, assigned_to "
            "FROM tickets WHERE id=?",
            (ticket_id,),
        )
        return await cur.fetchone()


async def save_reply(ticket_id, admin_id, text):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO replies (ticket_id, admin_id, text, created_at) VALUES (?,?,?,?)",
            (ticket_id, admin_id, text, datetime.utcnow().isoformat()),
        )
        await db.commit()


async def mark_answered(ticket_id, admin_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE tickets SET assigned_to=? WHERE id=?",
            (admin_id, ticket_id),
        )
        await db.commit()


async def set_status(ticket_id: int, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE tickets SET status=? WHERE id=?", (status, ticket_id))
        await db.commit()


async def save_admin_message(ticket_id, admin_chat, admin_msg_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO ticket_messages (ticket_id, admin_chat, admin_msg_id) VALUES (?,?,?)",
            (ticket_id, admin_chat, admin_msg_id),
        )
        await db.commit()


async def get_admin_messages(ticket_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT admin_chat, admin_msg_id FROM ticket_messages WHERE ticket_id=?",
            (ticket_id,),
        )
        return await cur.fetchall()


async def list_tickets(status: str | None = None, limit: int = 10):
    query = "SELECT id, category, username, status, substr(text,1,60) FROM tickets"
    params = ()
    if status:
        query += " WHERE status=?"
        params = (status,)
    query += " ORDER BY id DESC LIMIT ?"
    params = params + (limit,)
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(query, params)
        return await cur.fetchall()


async def get_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT status, COUNT(*) FROM tickets GROUP BY status")
        by_status = dict(await cur.fetchall())
        cur = await db.execute("SELECT category, COUNT(*) FROM tickets GROUP BY category")
        by_cat = dict(await cur.fetchall())
        cur = await db.execute("SELECT COUNT(*) FROM replies")
        replies_count = (await cur.fetchone())[0]
    return by_status, by_cat, replies_count
