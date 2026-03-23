import sqlite3
from contextlib import contextmanager
from config import DATABASE_PATH


def init_db():
    """Initialize the SQLite database with required tables."""
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                name TEXT,
                picture TEXT,
                access_token TEXT,
                refresh_token TEXT,
                token_expiry TEXT,
                auto_archive_enabled INTEGER DEFAULT 1,
                auto_archive_categories TEXT DEFAULT 'newsletter,marketing,notification,social',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                gmail_id TEXT NOT NULL,
                thread_id TEXT,
                from_address TEXT,
                from_name TEXT,
                subject TEXT,
                snippet TEXT,
                body TEXT,
                date TEXT,
                is_read INTEGER DEFAULT 0,
                importance TEXT DEFAULT 'medium',
                category TEXT DEFAULT 'general',
                processed INTEGER DEFAULT 0,
                included_in_briefing INTEGER DEFAULT 0,
                archived INTEGER DEFAULT 0,
                unsubscribed INTEGER DEFAULT 0,
                UNIQUE(user_id, gmail_id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                email_id INTEGER,
                gmail_draft_id TEXT,
                subject TEXT,
                to_address TEXT,
                body TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (email_id) REFERENCES emails(id)
            );

            CREATE TABLE IF NOT EXISTS rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                rule_text TEXT NOT NULL,
                rule_json TEXT,
                active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS briefings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                content TEXT,
                email_count INTEGER DEFAULT 0,
                important_count INTEGER DEFAULT 0,
                date TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS style_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                sample_text TEXT NOT NULL,
                context TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                email_ids TEXT DEFAULT '[]',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """)


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
