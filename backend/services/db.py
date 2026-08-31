import hashlib
import json
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "app.db"

SESSION_TTL_DAYS = 30
PBKDF2_ITERATIONS = 200_000
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthError(Exception):
    pass


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def _cursor():
    conn = _connect()
    try:
        yield conn.cursor()
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _cursor() as cur:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        cur.execute(
            """CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )"""
        )
        cur.execute(
            """CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                source TEXT NOT NULL,
                intro TEXT NOT NULL,
                key_points TEXT NOT NULL,
                roadmap TEXT NOT NULL,
                detected_language TEXT,
                done_topics TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            )"""
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_analyses_user ON analyses(user_id)")

        # Migration for databases created before done_topics existed.
        cur.execute("PRAGMA table_info(analyses)")
        columns = {row["name"] for row in cur.fetchall()}
        if "done_topics" not in columns:
            cur.execute("ALTER TABLE analyses ADD COLUMN done_topics TEXT NOT NULL DEFAULT '[]'")


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS).hex()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_user(email: str, password: str) -> int:
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        raise AuthError("Enter a valid email address")
    if len(password) < 8:
        raise AuthError("Password must be at least 8 characters")

    salt = secrets.token_hex(16)
    password_hash = _hash_password(password, salt)

    with _cursor() as cur:
        try:
            cur.execute(
                "INSERT INTO users (email, password_hash, password_salt, created_at) VALUES (?, ?, ?, ?)",
                (email, password_hash, salt, _now()),
            )
        except sqlite3.IntegrityError:
            raise AuthError("An account with that email already exists")
        return cur.lastrowid


def verify_user(email: str, password: str) -> int:
    email = email.strip().lower()
    with _cursor() as cur:
        cur.execute("SELECT id, password_hash, password_salt FROM users WHERE email = ?", (email,))
        row = cur.fetchone()

    if row is None:
        raise AuthError("Invalid email or password")

    if _hash_password(password, row["password_salt"]) != row["password_hash"]:
        raise AuthError("Invalid email or password")

    return row["id"]


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires_at = now.replace(microsecond=0) + timedelta(days=SESSION_TTL_DAYS)

    with _cursor() as cur:
        cur.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, user_id, now.isoformat(), expires_at.isoformat()),
        )
    return token


def get_user_from_token(token: str) -> dict | None:
    with _cursor() as cur:
        cur.execute(
            """SELECT users.id AS id, users.email AS email, sessions.expires_at AS expires_at
               FROM sessions JOIN users ON users.id = sessions.user_id
               WHERE sessions.token = ?""",
            (token,),
        )
        row = cur.fetchone()

    if row is None:
        return None
    if datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
        return None
    return {"id": row["id"], "email": row["email"]}


def delete_session(token: str) -> None:
    with _cursor() as cur:
        cur.execute("DELETE FROM sessions WHERE token = ?", (token,))


def save_analysis(user_id: int, source: str, analysis: dict, detected_language: str | None) -> int:
    with _cursor() as cur:
        cur.execute(
            """INSERT INTO analyses (user_id, source, intro, key_points, roadmap, detected_language, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                source,
                analysis["intro"],
                json.dumps(analysis["key_points"]),
                json.dumps(analysis["roadmap"]),
                detected_language,
                _now(),
            ),
        )
        return cur.lastrowid


def _count_topics(roadmap: list[dict]) -> int:
    total = 0
    for topic in roadmap:
        total += 1
        total += len(topic.get("children") or [])
    return total


def list_analyses(user_id: int) -> list[dict]:
    with _cursor() as cur:
        cur.execute(
            "SELECT id, source, intro, roadmap, done_topics, created_at FROM analyses WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        )
        rows = cur.fetchall()

    result = []
    for r in rows:
        total = _count_topics(json.loads(r["roadmap"]))
        done = len(json.loads(r["done_topics"]))
        result.append(
            {
                "id": r["id"],
                "source": r["source"],
                "intro": r["intro"],
                "created_at": r["created_at"],
                "done_count": done,
                "total_count": total,
            }
        )
    return result


def get_analysis(user_id: int, analysis_id: int) -> dict | None:
    with _cursor() as cur:
        cur.execute(
            "SELECT * FROM analyses WHERE id = ? AND user_id = ?",
            (analysis_id, user_id),
        )
        row = cur.fetchone()

    if row is None:
        return None

    return {
        "id": row["id"],
        "source": row["source"],
        "intro": row["intro"],
        "key_points": json.loads(row["key_points"]),
        "roadmap": json.loads(row["roadmap"]),
        "detected_language": row["detected_language"],
        "done_topics": json.loads(row["done_topics"]),
        "created_at": row["created_at"],
    }


def set_done_topics(user_id: int, analysis_id: int, done_topics: list[str]) -> bool:
    """Overwrite the set of done topic headings for one analysis. Returns
    False if the analysis doesn't exist or isn't owned by this user."""
    with _cursor() as cur:
        cur.execute(
            "UPDATE analyses SET done_topics = ? WHERE id = ? AND user_id = ?",
            (json.dumps(done_topics), analysis_id, user_id),
        )
        return cur.rowcount > 0
