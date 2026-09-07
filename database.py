"""
database.py
============
All persistence for the Telegram Games Bot lives here: SQLite schema,
player/admin/owner management, the virtual coin economy, game result
logging, bans, and bot-wide statistics.

Every query is parameterized. No raw string interpolation of user input
ever reaches SQL.
"""

from __future__ import annotations

import os
import sqlite3
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional, Iterable

logger = logging.getLogger("games_bot.database")

# --------------------------------------------------------------------------
# Configuration constants (used across bot.py / game1.py / game2.py / game3.py)
# --------------------------------------------------------------------------

DB_PATH = os.environ.get("BOT_DB_PATH", "games_bot.db")
OWNER_ID = int(os.environ.get("OWNER_ID", "0") or 0)

STARTING_COINS = 1000          # coins a brand-new player receives
MIN_PLAYERS_DEFAULT = 2
MAX_PLAYERS_DEFAULT = 8

# Per-game min/max players
GAME_LIMITS = {
    "raja": (4, 4),
    "impostor": (4, 10),
    "4card": (2, 4),
    "antakshari": (2, 8),
    "cards": (2, 6),
    "box": (2, 4),
    "ludo": (2, 4),
    "rangers": (2, 6),
    "business": (2, 4),
}

# Timeouts (seconds)
LOBBY_TIMEOUT = 90
TURN_TIMEOUT = 30
DISCUSSION_TIMEOUT = 60
VOTE_TIMEOUT = 30

# Reward structure (virtual coins, configurable)
REWARDS = {
    "first": 500,
    "second": 250,
    "participation": 50,
}

# Aviator / Flip config
FLIP_WIN_MULTIPLIER = 2.0
FLIP_LOSE_MULTIPLIER = 0.2
AVIATOR_PRESET_AMOUNTS = (50, 100, 250, 500)
AVIATOR_MAX_MULTIPLIER = 20.0

# --------------------------------------------------------------------------
# Connection helpers
# --------------------------------------------------------------------------


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    """Create all required tables if they do not already exist."""
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id       INTEGER PRIMARY KEY,
                username      TEXT,
                first_name    TEXT,
                coins         INTEGER NOT NULL DEFAULT 0,
                games_played  INTEGER NOT NULL DEFAULT 0,
                wins          INTEGER NOT NULL DEFAULT 0,
                losses        INTEGER NOT NULL DEFAULT 0,
                banned        INTEGER NOT NULL DEFAULT 0,
                created_at    TEXT NOT NULL,
                updated_at    TEXT NOT NULL
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS admins (
                user_id     INTEGER PRIMARY KEY,
                added_by    INTEGER NOT NULL,
                created_at  TEXT NOT NULL
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS game_results (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id     INTEGER NOT NULL,
                game_name   TEXT NOT NULL,
                winner_id   INTEGER,
                players     TEXT NOT NULL,
                created_at  TEXT NOT NULL
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS known_chats (
                chat_id     INTEGER PRIMARY KEY,
                chat_type   TEXT NOT NULL,
                title       TEXT,
                created_at  TEXT NOT NULL
            )
            """
        )
        conn.commit()
    logger.info("Database initialised at %s", DB_PATH)


# --------------------------------------------------------------------------
# User / player management
# --------------------------------------------------------------------------


def get_user(user_id: int) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return cur.fetchone()


def register_user(user_id: int, username: Optional[str], first_name: Optional[str], starting_coins: Optional[int] = None) -> sqlite3.Row:
    """Register the user if new, otherwise refresh their username/name/activity."""
    existing = get_user(user_id)
    now = _now()
    with get_conn() as conn:
        if existing is None:
            conn.execute(
                """
                INSERT INTO users (user_id, username, first_name, coins, games_played,
                                    wins, losses, banned, created_at, updated_at)
                VALUES (?, ?, ?, ?, 0, 0, 0, 0, ?, ?)
                """,
                (user_id, username or "", first_name or "Player", STARTING_COINS if starting_coins is None else max(0, int(starting_coins)), now, now),
            )
        else:
            conn.execute(
                "UPDATE users SET username = ?, first_name = ?, updated_at = ? WHERE user_id = ?",
                (username or existing["username"], first_name or existing["first_name"], now, user_id),
            )
    return get_user(user_id)


def touch_activity(user_id: int) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE users SET updated_at = ? WHERE user_id = ?", (_now(), user_id))


def user_exists(user_id: int) -> bool:
    return get_user(user_id) is not None


def is_banned(user_id: int) -> bool:
    row = get_user(user_id)
    return bool(row and row["banned"])


def set_banned(user_id: int, banned: bool) -> bool:
    if not user_exists(user_id):
        return False
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET banned = ?, updated_at = ? WHERE user_id = ?",
            (1 if banned else 0, _now(), user_id),
        )
    return True


# --------------------------------------------------------------------------
# Coin economy - ALL coin mutation goes through these functions
# --------------------------------------------------------------------------


def get_balance(user_id: int) -> int:
    row = get_user(user_id)
    return int(row["coins"]) if row else 0


def add_coins(user_id: int, amount: int) -> int:
    """Add coins (amount must be >= 0). Returns new balance."""
    if amount < 0:
        raise ValueError("add_coins requires a non-negative amount")
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET coins = coins + ?, updated_at = ? WHERE user_id = ?",
            (amount, _now(), user_id),
        )
        row = conn.execute("SELECT coins FROM users WHERE user_id = ?", (user_id,)).fetchone()
    return int(row["coins"]) if row else 0


def take_coins(user_id: int, amount: int) -> bool:
    """
    Remove coins, never allowing the balance to go negative.
    Returns True on success, False if the user doesn't have enough coins.
    """
    if amount < 0:
        raise ValueError("take_coins requires a non-negative amount")
    with get_conn() as conn:
        row = conn.execute("SELECT coins FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if row is None or row["coins"] < amount:
            return False
        conn.execute(
            "UPDATE users SET coins = coins - ?, updated_at = ? WHERE user_id = ?",
            (amount, _now(), user_id),
        )
    return True


def transfer_coins(from_id: int, to_id: int, amount: int) -> bool:
    """Peer-to-peer coin transfer. Atomic: both succeed or neither does."""
    if amount <= 0:
        return False
    with get_conn() as conn:
        row = conn.execute("SELECT coins FROM users WHERE user_id = ?", (from_id,)).fetchone()
        if row is None or row["coins"] < amount:
            return False
        if conn.execute("SELECT 1 FROM users WHERE user_id = ?", (to_id,)).fetchone() is None:
            return False
        conn.execute(
            "UPDATE users SET coins = coins - ?, updated_at = ? WHERE user_id = ?",
            (amount, _now(), from_id),
        )
        conn.execute(
            "UPDATE users SET coins = coins + ?, updated_at = ? WHERE user_id = ?",
            (amount, _now(), to_id),
        )
    return True


# --------------------------------------------------------------------------
# Stats
# --------------------------------------------------------------------------


def record_game_stat(user_id: int, won: bool) -> None:
    with get_conn() as conn:
        if won:
            conn.execute(
                "UPDATE users SET games_played = games_played + 1, wins = wins + 1, updated_at = ? WHERE user_id = ?",
                (_now(), user_id),
            )
        else:
            conn.execute(
                "UPDATE users SET games_played = games_played + 1, losses = losses + 1, updated_at = ? WHERE user_id = ?",
                (_now(), user_id),
            )


def get_leaderboard(limit: int = 10) -> list[sqlite3.Row]:
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT user_id, username, first_name, coins FROM users "
            "WHERE banned = 0 ORDER BY coins DESC LIMIT ?",
            (limit,),
        )
        return cur.fetchall()


def get_rank(user_id: int) -> Optional[int]:
    row = get_user(user_id)
    if not row:
        return None
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT COUNT(*) AS c FROM users WHERE coins > ? AND banned = 0", (row["coins"],)
        )
        higher = cur.fetchone()["c"]
    return higher + 1


# --------------------------------------------------------------------------
# Game results
# --------------------------------------------------------------------------


def record_game_result(chat_id: int, game_name: str, winner_id: Optional[int], players: Iterable[int]) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO game_results (chat_id, game_name, winner_id, players, created_at) VALUES (?, ?, ?, ?, ?)",
            (chat_id, game_name, winner_id, ",".join(str(p) for p in players), _now()),
        )


# --------------------------------------------------------------------------
# Admin / owner management
# --------------------------------------------------------------------------


def is_owner(user_id: int) -> bool:
    return OWNER_ID != 0 and user_id == OWNER_ID


def is_admin(user_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,)).fetchone()
    return row is not None


def is_owner_or_admin(user_id: int) -> bool:
    return is_owner(user_id) or is_admin(user_id)


def add_admin(user_id: int, added_by: int) -> bool:
    if is_admin(user_id):
        return False
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO admins (user_id, added_by, created_at) VALUES (?, ?, ?)",
            (user_id, added_by, _now()),
        )
    return True


def remove_admin(user_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
    return cur.rowcount > 0


def list_admins() -> list[sqlite3.Row]:
    with get_conn() as conn:
        cur = conn.execute(
            """
            SELECT admins.user_id AS user_id, users.username AS username, users.first_name AS first_name
            FROM admins LEFT JOIN users ON admins.user_id = users.user_id
            ORDER BY admins.created_at ASC
            """
        )
        return cur.fetchall()


# --------------------------------------------------------------------------
# Known chats (for /broadcast) & bot-wide stats (for /info)
# --------------------------------------------------------------------------


def register_chat(chat_id: int, chat_type: str, title: Optional[str]) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO known_chats (chat_id, chat_type, title, created_at) VALUES (?, ?, ?, ?)",
            (chat_id, chat_type, title, _now()),
        )
        # keep title fresh
        conn.execute(
            "UPDATE known_chats SET title = ?, chat_type = ? WHERE chat_id = ?",
            (title, chat_type, chat_id),
        )


def list_all_chat_ids() -> list[int]:
    with get_conn() as conn:
        cur = conn.execute("SELECT chat_id FROM known_chats")
        return [r["chat_id"] for r in cur.fetchall()]


def list_private_user_ids() -> list[int]:
    with get_conn() as conn:
        cur = conn.execute("SELECT chat_id FROM known_chats WHERE chat_type = 'private'")
        return [r["chat_id"] for r in cur.fetchall()]


def get_bot_stats() -> dict:
    with get_conn() as conn:
        total_users = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        total_banned = conn.execute("SELECT COUNT(*) AS c FROM users WHERE banned = 1").fetchone()["c"]
        total_groups = conn.execute(
            "SELECT COUNT(*) AS c FROM known_chats WHERE chat_type IN ('group','supergroup')"
        ).fetchone()["c"]
        total_coins = conn.execute("SELECT COALESCE(SUM(coins),0) AS c FROM users").fetchone()["c"]
        total_games = conn.execute("SELECT COUNT(*) AS c FROM game_results").fetchone()["c"]
        # "active" = touched in the last 24 hours
        active_24h = conn.execute(
            "SELECT COUNT(*) AS c FROM users WHERE datetime(updated_at) >= datetime('now', '-1 day')"
        ).fetchone()["c"]
        active_7d = conn.execute(
            "SELECT COUNT(*) AS c FROM users WHERE datetime(updated_at) >= datetime('now', '-7 day')"
        ).fetchone()["c"]
    return {
        "total_users": total_users,
        "banned_users": total_banned,
        "total_groups": total_groups,
        "total_coins_in_circulation": total_coins,
        "total_games_played": total_games,
        "active_last_24h": active_24h,
        "active_24h": active_24h,
        "active_7d": active_7d,
        "groups": total_groups,
        "total_games": total_games,
    }


# --------------------------------------------------------------------------
# Backwards-compatible aliases used by bot.py / older game modules
# --------------------------------------------------------------------------

def get_coins(user_id: int) -> int:
    return get_balance(user_id)


def update_stats(user_id: int, won: bool) -> None:
    record_game_stat(user_id, won)


def is_admin_db(user_id: int) -> bool:
    return is_admin(user_id)


def ban_user(user_id: int) -> bool:
    return set_banned(user_id, True)


def unban_user(user_id: int) -> bool:
    return set_banned(user_id, False)


def get_all_user_ids() -> list[int]:
    with get_conn() as conn:
        cur = conn.execute("SELECT user_id FROM users")
        return [int(r["user_id"]) for r in cur.fetchall()]


def get_all_group_chat_ids() -> list[int]:
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT chat_id FROM known_chats WHERE chat_type IN ('group','supergroup')"
        )
        return [int(r["chat_id"]) for r in cur.fetchall()]


def touch_user(user_id: int) -> None:
    touch_activity(user_id)
