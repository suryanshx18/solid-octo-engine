import sqlite3
from datetime import datetime, timezone

DB_NAME = "chaoscore.db"


def now():
    return datetime.now(timezone.utc).isoformat()


def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            coins INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            added_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS coin_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            reason TEXT,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            host_id INTEGER,
            game_type TEXT,
            status TEXT,
            current_turn INTEGER DEFAULT 0,
            created_at TEXT,
            ended_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS game_players (
            game_id INTEGER,
            user_id INTEGER,
            position INTEGER,
            joined_at TEXT,
            PRIMARY KEY(game_id, user_id)
        )
    """)

    conn.commit()
    conn.close()


# ---------------- USER ----------------

def add_user(user_id, username=None, first_name=None):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT OR IGNORE INTO users
        (user_id, username, first_name, coins, created_at)
        VALUES (?, ?, ?, 0, ?)
    """, (user_id, username, first_name, now()))

    cur.execute("""
        UPDATE users
        SET username = ?, first_name = ?
        WHERE user_id = ?
    """, (username, first_name, user_id))

    conn.commit()
    conn.close()


def get_user(user_id):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM users WHERE user_id = ?",
        (user_id,)
    ).fetchone()
    conn.close()
    return row


def get_balance(user_id):
    row = get_user(user_id)

    if not row:
        return 0

    return row["coins"]


def change_coins(user_id, amount, reason=""):
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "UPDATE users SET coins = coins + ? WHERE user_id = ?",
        (amount, user_id)
    )

    cur.execute("""
        INSERT INTO coin_transactions
        (user_id, amount, reason, created_at)
        VALUES (?, ?, ?, ?)
    """, (user_id, amount, reason, now()))

    conn.commit()
    conn.close()


# ---------------- ADMINS ----------------

def is_admin(user_id):
    conn = get_db()

    row = conn.execute(
        "SELECT user_id FROM admins WHERE user_id = ?",
        (user_id,)
    ).fetchone()

    conn.close()

    return row is not None


def add_admin(user_id):
    conn = get_db()

    conn.execute("""
        INSERT OR IGNORE INTO admins
        (user_id, added_at)
        VALUES (?, ?)
    """, (user_id, now()))

    conn.commit()
    conn.close()


def remove_admin(user_id):
    conn = get_db()

    conn.execute(
        "DELETE FROM admins WHERE user_id = ?",
        (user_id,)
    )

    conn.commit()
    conn.close()


# ---------------- LEADERBOARD ----------------

def leaderboard(limit=10):
    conn = get_db()

    rows = conn.execute("""
        SELECT user_id, username, first_name, coins
        FROM users
        ORDER BY coins DESC
        LIMIT ?
    """, (limit,)).fetchall()

    conn.close()

    return rows


# ---------------- GAME ----------------

def create_game(chat_id, host_id, game_type="parchi"):
    conn = get_db()

    cur = conn.cursor()

    cur.execute("""
        INSERT INTO games
        (chat_id, host_id, game_type, status, current_turn, created_at)
        VALUES (?, ?, ?, 'lobby', 0, ?)
    """, (
        chat_id,
        host_id,
        game_type,
        now()
    ))

    game_id = cur.lastrowid

    conn.commit()
    conn.close()

    return game_id


def get_game(game_id):
    conn = get_db()

    row = conn.execute("""
        SELECT *
        FROM games
        WHERE id = ?
    """, (game_id,)).fetchone()

    conn.close()

    return row


def get_active_game(chat_id):
    conn = get_db()

    row = conn.execute("""
        SELECT *
        FROM games
        WHERE chat_id = ?
        AND status IN ('lobby', 'active')
        ORDER BY id DESC
        LIMIT 1
    """, (chat_id,)).fetchone()

    conn.close()

    return row


def update_game(game_id, status=None, current_turn=None):
    conn = get_db()

    if status is not None and current_turn is not None:
        conn.execute("""
            UPDATE games
            SET status = ?, current_turn = ?
            WHERE id = ?
        """, (status, current_turn, game_id))

    elif status is not None:
        conn.execute("""
            UPDATE games
            SET status = ?
            WHERE id = ?
        """, (status, game_id))

    elif current_turn is not None:
        conn.execute("""
            UPDATE games
            SET current_turn = ?
            WHERE id = ?
        """, (current_turn, game_id))

    conn.commit()
    conn.close()


def end_game(game_id):
    conn = get_db()

    conn.execute("""
        UPDATE games
        SET status = 'ended',
            ended_at = ?
        WHERE id = ?
    """, (now(), game_id))

    conn.commit()
    conn.close()


def add_game_player(game_id, user_id, position):
    conn = get_db()

    conn.execute("""
        INSERT OR IGNORE INTO game_players
        (game_id, user_id, position, joined_at)
        VALUES (?, ?, ?, ?)
    """, (
        game_id,
        user_id,
        position,
        now()
    ))

    conn.commit()
    conn.close()


def remove_game_player(game_id, user_id):
    conn = get_db()

    conn.execute("""
        DELETE FROM game_players
        WHERE game_id = ?
        AND user_id = ?
    """, (game_id, user_id))

    conn.commit()
    conn.close()


def get_game_players(game_id):
    conn = get_db()

    rows = conn.execute("""
        SELECT gp.*, u.username, u.first_name
        FROM game_players gp
        JOIN users u ON gp.user_id = u.user_id
        WHERE gp.game_id = ?
        ORDER BY gp.position ASC
    """, (game_id,)).fetchall()

    conn.close()

    return rows


def get_game_player(game_id, user_id):
    conn = get_db()

    row = conn.execute("""
        SELECT gp.*, u.username, u.first_name
        FROM game_players gp
        JOIN users u ON gp.user_id = u.user_id
        WHERE gp.game_id = ?
        AND gp.user_id = ?
    """, (game_id, user_id)).fetchone()

    conn.close()

    return row
