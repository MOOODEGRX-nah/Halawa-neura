"""
قاعدة بيانات محلية سريعة (SQLite) — كل بياناتك تبقى على جهازك
"""
import sqlite3
from datetime import datetime
from pathlib import Path


class NeuraDatabase:
    def __init__(self, db_path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL;")  # أسرع للقراءة والكتابة
        self._create()

    def _create(self):
        c = self.conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS conversations(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_message TEXT, jarvis_response TEXT, created_at TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS memory(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE, value TEXT, category TEXT, created_at TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS tasks(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT, done INTEGER DEFAULT 0, created_at TEXT)""")
        self.conn.commit()

    # ===== المحادثات =====
    def save_conversation(self, user_msg, reply):
        self.conn.execute(
            "INSERT INTO conversations(user_message, jarvis_response, created_at) VALUES(?,?,?)",
            (user_msg, reply, datetime.now().isoformat()))
        self.conn.commit()

    def recent_conversations(self, n=6):
        rows = self.conn.execute(
            "SELECT user_message, jarvis_response FROM conversations ORDER BY id DESC LIMIT ?",
            (n,)).fetchall()
        return list(reversed(rows))

    def search_conversations(self, q, limit=20):
        return self.conn.execute(
            "SELECT user_message, jarvis_response, created_at FROM conversations "
            "WHERE user_message LIKE ? OR jarvis_response LIKE ? ORDER BY id DESC LIMIT ?",
            (f"%{q}%", f"%{q}%", limit)).fetchall()

    # ===== الذاكرة =====
    def remember(self, key, value, category="general"):
        self.conn.execute(
            "INSERT OR REPLACE INTO memory(key, value, category, created_at) VALUES(?,?,?,?)",
            (key, value, category, datetime.now().isoformat()))
        self.conn.commit()

    def recall(self, key):
        row = self.conn.execute("SELECT value FROM memory WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def all_memories(self):
        return dict(self.conn.execute("SELECT key, value FROM memory").fetchall())

    # ===== المهام =====
    def add_task(self, title):
        self.conn.execute("INSERT INTO tasks(title, created_at) VALUES(?,?)",
                          (title, datetime.now().isoformat()))
        self.conn.commit()

    def list_tasks(self):
        return self.conn.execute("SELECT id, title, done FROM tasks ORDER BY id").fetchall()

    def set_task_done(self, task_id, done):
        self.conn.execute("UPDATE tasks SET done=? WHERE id=?", (1 if done else 0, task_id))
        self.conn.commit()

    # ===== إحصائيات =====
    def stats(self):
        c = self.conn.cursor()
        return {
            "conversations": c.execute("SELECT COUNT(*) FROM conversations").fetchone()[0],
            "memories": c.execute("SELECT COUNT(*) FROM memory").fetchone()[0],
            "tasks": c.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],
        }

    def close(self):
        self.conn.close()
