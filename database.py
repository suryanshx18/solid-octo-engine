import sqlite3
from datetime import datetime

DB_NAME = "mafia.db"


def connect():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def now():
    return datetime.utcnow().isoformat()


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
            chat_id INTEGER NOT NULL,
            host_id INTEGER NOT NULL,
            status TEXT DEFAULT 'lobby',
            phase TEXT DEFAULT 'lobby',
            round INTEGER DEFAULT 0,
            night_target INTEGER,
            doctor_target INTEGER,
            detective_target INTEGER,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS game_players (
            game_id INTEGER,
            user_id INTEGER,
            role TEXT,
            alive INTEGER DEFAULT 1,
            score INTEGER DEFAULT 0,
            secret_mission TEXT,
            PRIMARY KEY(game_id, user_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS game_votes (
            game_id INTEGER,
            voter_id INTEGER,
            target_id INTEGER,
            phase TEXT,
            PRIMARY KEY(game_id, voter_id, phase)
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
            now()
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
        now()
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
        now()
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


# =========================
# GAME DATABASE
# =========================

def create_game(chat_id, host_id):
    conn = connect()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO games
        (chat_id, host_id, status, phase, round, created_at)
        VALUES (?, ?, 'lobby', 'lobby', 0, ?)
    """, (
        chat_id,
        host_id,
        now()
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


def get_game(game_id):
    conn = connect()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM games
        WHERE game_id = ?
    """, (game_id,))

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


def get_game_players(game_id, alive_only=False):
    conn = connect()
    cur = conn.cursor()

    if alive_only:
        cur.execute("""
            SELECT gp.*, u.username, u.first_name
            FROM game_players gp
            JOIN users u ON u.user_id = gp.user_id
            WHERE gp.game_id = ?
            AND gp.alive = 1
        """, (game_id,))
    else:
        cur.execute("""
            SELECT gp.*, u.username, u.first_name
            FROM game_players gp
            JOIN users u ON u.user_id = gp.user_id
            WHERE gp.game_id = ?
        """, (game_id,))

    rows = cur.fetchall()

    conn.close()

    return rows


def get_player(game_id, user_id):
    conn = connect()
    cur = conn.cursor()

    cur.execute("""
        SELECT gp.*, u.username, u.first_name
        FROM game_players gp
        JOIN users u ON u.user_id = gp.user_id
        WHERE gp.game_id = ?
        AND gp.user_id = ?
    """, (
        game_id,
        user_id
    ))

    row = cur.fetchone()

    conn.close()

    return row


def update_game(game_id, **fields):
    allowed = {
        "status",
        "phase",
        "round",
        "night_target",
        "doctor_target",
        "detective_target"
    }

    fields = {
        key: value
        for key, value in fields.items()
        if key in allowed
    }

    if not fields:
        return

    conn = connect()
    cur = conn.cursor()

    assignments = ", ".join(
        f"{key} = ?" for key in fields
    )

    values = list(fields.values())
    values.append(game_id)

    cur.execute(
        f"""
        UPDATE games
        SET {assignments}
        WHERE game_id = ?
        """,
        values
    )

    conn.commit()
    conn.close()


def assign_player_role(
    game_id,
    user_id,
    role,
    mission
):
    conn = connect()
    cur = conn.cursor()

    cur.execute("""
        UPDATE game_players
        SET role = ?, secret_mission = ?
        WHERE game_id = ?
        AND user_id = ?
    """, (
        role,
        mission,
        game_id,
        user_id
    ))

    conn.commit()
    conn.close()


def kill_player(game_id, user_id):
    conn = connect()
    cur = conn.cursor()

    cur.execute("""
        UPDATE game_players
        SET alive = 0
        WHERE game_id = ?
        AND user_id = ?
    """, (
        game_id,
        user_id
    ))

    conn.commit()
    conn.close()


def add_score(game_id, user_id, points):
    conn = connect()
    cur = conn.cursor()

    cur.execute("""
        UPDATE game_players
        SET score = score + ?
        WHERE game_id = ?
        AND user_id = ?
    """, (
        points,
        game_id,
        user_id
    ))

    conn.commit()
    conn.close()


def has_voted(game_id, voter_id, phase):
    conn = connect()
    cur = conn.cursor()

    cur.execute("""
        SELECT 1
        FROM game_votes
        WHERE game_id = ?
        AND voter_id = ?
        AND phase = ?
    """, (
        game_id,
        voter_id,
        phase
    ))

    result = cur.fetchone()

    conn.close()

    return result is not None


def add_vote(
    game_id,
    voter_id,
    target_id,
    phase
):
    conn = connect()
    cur = conn.cursor()

    cur.execute("""
        INSERT OR IGNORE INTO game_votes
        (game_id, voter_id, target_id, phase)
        VALUES (?, ?, ?, ?)
    """, (
        game_id,
        voter_id,
        target_id,
        phase
    ))

    conn.commit()
    conn.close()


def get_votes(game_id, phase):
    conn = connect()
    cur = conn.cursor()

    cur.execute("""
        SELECT voter_id, target_id
        FROM game_votes
        WHERE game_id = ?
        AND phase = ?
    """, (
        game_id,
        phase
    ))

    rows = cur.fetchall()

    conn.close()

    return rows


def clear_night_actions(game_id):
    update_game(
        game_id,
        night_target=None,
        doctor_target=None,
        detective_target=None
    )


def increment_game_stats(game_id, winners):
    conn = connect()
    cur = conn.cursor()

    players = get_game_players(game_id)

    for player in players:

        cur.execute("""
            UPDATE users
            SET games_played = games_played + 1
            WHERE user_id = ?
        """, (
            player["user_id"],
        ))

        if player["user_id"] in winners:

            cur.execute("""
                UPDATE users
                SET wins = wins + 1
                WHERE user_id = ?
            """, (
                player["user_id"],
            ))

    conn.commit()
    conn.close()


def reward_players(game_id, winners):
    conn = connect()
    cur = conn.cursor()

    for user_id in winners:

        cur.execute("""
            UPDATE users
            SET coins = coins + 250
            WHERE user_id = ?
        """, (
            user_id,
        ))

        cur.execute("""
            INSERT INTO coin_transactions
            (admin_id, target_user_id, amount, action, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            0,
            user_id,
            250,
            "game_win",
            now()
        ))

    conn.commit()
    conn.close()


def end_game(game_id):
    conn = connect()
    cur = conn.cursor()

    cur.execute("""
        UPDATE games
        SET status = 'finished',
            phase = 'finished'
        WHERE game_id = ?
    """, (
        game_id,
    ))

    conn.commit()
    conn.close()
