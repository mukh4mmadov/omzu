import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "assistant.db"


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex[:12]


class SQLiteStore:
    def __init__(self, path: Path = DB):
        self.path = path
        with self._con() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY, title TEXT, created TEXT, updated TEXT, user_id TEXT DEFAULT 'local');
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY, conversation_id TEXT, role TEXT, content TEXT, extra TEXT, created TEXT);
            CREATE TABLE IF NOT EXISTS feedback (
                message_id TEXT PRIMARY KEY, rating INTEGER, correction TEXT, created TEXT, user_id TEXT DEFAULT 'local');
            CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id);
            """)
            for table in ("conversations", "feedback"):
                cols = [r[1] for r in c.execute(f"PRAGMA table_info({table})")]
                if "user_id" not in cols:
                    c.execute(f"ALTER TABLE {table} ADD COLUMN user_id TEXT DEFAULT 'local'")

    @contextmanager
    def _con(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        finally:
            con.close()

    def ensure_conversation(self, cid: str | None, first_message: str, user_id: str = "local") -> str:
        with self._con() as c:
            if cid and c.execute("SELECT 1 FROM conversations WHERE id=? AND user_id=?", (cid, user_id)).fetchone():
                return cid
            cid = new_id()
            title = first_message[:60] + ("…" if len(first_message) > 60 else "")
            c.execute("INSERT INTO conversations(id, title, created, updated, user_id) VALUES (?,?,?,?,?)",
                      (cid, title, now(), now(), user_id))
            return cid

    def list_conversations(self, user_id: str = "local", limit: int = 200) -> list[dict]:
        with self._con() as c:
            rows = c.execute("SELECT id, title, updated FROM conversations WHERE user_id=? "
                             "ORDER BY updated DESC LIMIT ?", (user_id, limit)).fetchall()
        return [dict(r) for r in rows]

    def delete_conversation(self, cid: str, user_id: str = "local"):
        with self._con() as c:
            if c.execute("DELETE FROM conversations WHERE id=? AND user_id=?", (cid, user_id)).rowcount:
                c.execute("DELETE FROM messages WHERE conversation_id=?", (cid,))

    def add_message(self, cid: str, role: str, content: str, extra: dict | None = None, mid: str | None = None) -> str:
        mid = mid or new_id()
        with self._con() as c:
            c.execute("INSERT INTO messages VALUES (?,?,?,?,?,?)",
                      (mid, cid, role, content, json.dumps(extra, ensure_ascii=False) if extra else None, now()))
            c.execute("UPDATE conversations SET updated=? WHERE id=?", (now(), cid))
        return mid

    def history(self, cid: str) -> list[dict]:
        with self._con() as c:
            rows = c.execute("SELECT role, content FROM messages WHERE conversation_id=? ORDER BY created, rowid",
                             (cid,)).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in rows]

    def messages(self, cid: str, user_id: str = "local") -> list[dict]:
        with self._con() as c:
            if not c.execute("SELECT 1 FROM conversations WHERE id=? AND user_id=?", (cid, user_id)).fetchone():
                return []
            rows = c.execute(
                "SELECT m.id, m.role, m.content, m.extra, f.rating FROM messages m "
                "LEFT JOIN feedback f ON f.message_id = m.id WHERE m.conversation_id=? ORDER BY m.created, m.rowid",
                (cid,)).fetchall()
        return [{"id": r["id"], "role": r["role"], "content": r["content"],
                 "extra": json.loads(r["extra"]) if r["extra"] else None, "rating": r["rating"]} for r in rows]

    def save_feedback(self, message_id: str, rating: int, correction: str | None, user_id: str = "local"):
        with self._con() as c:
            c.execute("INSERT OR REPLACE INTO feedback(message_id, rating, correction, created, user_id) VALUES (?,?,?,?,?)",
                      (message_id, rating, correction, now(), user_id))

    def export_feedback(self) -> list[dict]:
        with self._con() as c:
            rows = c.execute("""
                SELECT f.rating, f.correction, a.content AS answer,
                       (SELECT u.content FROM messages u WHERE u.conversation_id = a.conversation_id
                        AND u.role='user' AND u.rowid < a.rowid ORDER BY u.rowid DESC LIMIT 1) AS question
                FROM feedback f JOIN messages a ON a.id = f.message_id""").fetchall()
        return [dict(r) for r in rows]
