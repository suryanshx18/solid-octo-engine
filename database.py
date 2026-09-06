import sqlite3
from datetime import datetime

DB_NAME = "chaoscore.db"


def connect():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = connect()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            coins INTEGER DEFAULT 1000,
            games_played INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            betrayals INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            added_by INTEGER,
            added_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS coin_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER,
            target_user_id INTEGER,
            amount INTEGER,
            action TEXT,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS games (
            game_id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            host_id INTEGER,
            status TEXT,
            round INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS game_players (
            game_id INTEGER,
            user_id INTEGER,
            role TEXT,
            score INTEGER DEFAULT 0,
            alive INTEGER DEFAULT 1,
            secret_mission TEXT,
            PRIMARY KEY(game_id, user_id)
        )
    """)

    conn.commit()
    conn.close()


def ensure_user(user):
    conn = connect()
    cur = conn.cursor()

    cur.execute(
        "SELECT user_id FROM users WHERE user_id = ?",
        (user.id,)
    )

    if cur.fetchone() is None:
        cur.execute("""
            INSERT INTO users
            (user_id, username, first_name, coins, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            user.id,
            user.username,
            user.first_name,
            1000,
            datetime.utcnow().isoformat()
        ))
    else:
        cur.execute("""
            UPDATE users
            SET username = ?, first_name = ?
            WHERE user_id = ?
        """, (
            user.username,
            user.first_name,
            user.id
        ))

    conn.commit()
    conn.close()


def get_balance(user_id):
    conn = connect()
    cur = conn.cursor()

    cur.execute(
        "SELECT coins FROM users WHERE user_id = ?",
        (user_id,)
    )

    row = cur.fetchone()
    conn.close()

    return row["coins"] if row else 0


def change_coins(admin_id, target_user_id, amount, action):
    conn = connect()
    cur = conn.cursor()

    cur.execute(
        "SELECT coins FROM users WHERE user_id = ?",
        (target_user_id,)
    )

    row = cur.fetchone()

    if not row:
        conn.close()
        return None

    old_balance = row["coins"]

    if action == "add":
        new_balance = old_balance + amount

    else:
        new_balance = max(0, old_balance - amount)

    actual_change = new_balance - old_balance

    cur.execute("""
        UPDATE users
        SET coins = ?
        WHERE user_id = ?
    """, (
        new_balance,
        target_user_id
    ))

    cur.execute("""
        INSERT INTO coin_transactions
        (admin_id, target_user_id, amount, action, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (
        admin_id,
        target_user_id,
        actual_change,
        action,
        datetime.utcnow().isoformat()
    ))

    conn.commit()
    conn.close()

    return new_balance


def add_admin(user_id, added_by):
    conn = connect()
    cur = conn.cursor()

    cur.execute("""
        INSERT OR IGNORE INTO admins
        (user_id, added_by, added_at)
        VALUES (?, ?, ?)
    """, (
        user_id,
        added_by,
        datetime.utcnow().isoformat()
    ))

    conn.commit()
    conn.close()


def remove_admin(user_id):
    conn = connect()
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM admins WHERE user_id = ?",
        (user_id,)
    )

    conn.commit()
    conn.close()


def is_admin(user_id):
    conn = connect()
    cur = conn.cursor()

    cur.execute(
        "SELECT user_id FROM admins WHERE user_id = ?",
        (user_id,)
    )

    result = cur.fetchone()

    conn.close()

    return result is not None


def leaderboard(limit=20):
    conn = connect()
    cur = conn.cursor()

    cur.execute("""
        SELECT user_id, username, first_name, coins
        FROM users
        ORDER BY coins DESC
        LIMIT ?
    """, (limit,))

    rows = cur.fetchall()
    conn.close()

    return rows


def get_stats():
    conn = connect()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) AS count FROM users")
    users = cur.fetchone()["count"]

    cur.execute("SELECT COUNT(*) AS count FROM admins")
    admins = cur.fetchone()["count"]

    cur.execute("""
        SELECT COALESCE(SUM(coins), 0) AS total
        FROM users
    """)
    coins = cur.fetchone()["total"]

    cur.execute("""
        SELECT COUNT(*) AS count
        FROM games
        WHERE status = 'active'
    """)
    games = cur.fetchone()["count"]

    conn.close()

    return {
        "users": users,
        "admins": admins,
        "coins": coins,
        "games": games
    }


def create_game(chat_id, host_id):
    conn = connect()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO games
        (chat_id, host_id, status, round, created_at)
        VALUES (?, ?, 'lobby', 0, ?)
    """, (
        chat_id,
        host_id,
        datetime.utcnow().isoformat()
    ))

    game_id = cur.lastrowid

    conn.commit()
    conn.close()

    return game_id


def get_active_game(chat_id):
    conn = connect()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM games
        WHERE chat_id = ?
        AND status IN ('lobby', 'active')
        ORDER BY game_id DESC
        LIMIT 1
    """, (chat_id,))

    row = cur.fetchone()
    conn.close()

    return row


def add_game_player(game_id, user_id):
    conn = connect()
    cur = conn.cursor()

    cur.execute("""
        INSERT OR IGNORE INTO game_players
        (game_id, user_id)
        VALUES (?, ?)
    """, (
        game_id,
        user_id
    ))

    conn.commit()
    conn.close()


def get_game_players(game_id):
    conn = connect()
    cur = conn.cursor()

    cur.execute("""
        SELECT gp.*, u.username, u.first_name
        FROM game_players gp
        JOIN users u ON u.user_id = gp.user_id
        WHERE gp.game_id = ?
    """, (game_id,))

    rows = cur.fetchall()
    conn.close()

    return rows


def update_game(game_id, status=None, round_number=None):
    conn = connect()
    cur = conn.cursor()

    if status is not None:
        cur.execute("""
            UPDATE games
            SET status = ?
            WHERE game_id = ?
        """, (status, game_id))

    if round_number is not None:
        cur.execute("""
            UPDATE games
            SET round = ?
            WHERE game_id = ?
        """, (round_number, game_id))

    conn.commit()
    conn.close()
