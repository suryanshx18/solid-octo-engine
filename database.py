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
            claimed_free INTEGER DEFAULT 0,
            created_at TEXT  
        )  
    """)  

    # Safe migration: ensure claimed_free column exists if DB was already created
    try:
        cur.execute("ALTER TABLE users ADD COLUMN claimed_free INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    cur.execute("""  
        CREATE TABLE IF NOT EXISTS admins (  
            user_id INTEGER PRIMARY KEY,  
            added_at TEXT  
        )  
    """)  

    cur.execute("""  
        CREATE TABLE IF NOT EXISTS coin_transactions (  
            id INTEGER PRIMARY KEY AUTOINCREMENT,  
            user_id INTEGER NOT NULL,  
            amount INTEGER NOT NULL,  
            reason TEXT,  
            created_at TEXT  
        )  
    """)  

    cur.execute("""  
        CREATE TABLE IF NOT EXISTS games (  
            id INTEGER PRIMARY KEY AUTOINCREMENT,  
            chat_id INTEGER NOT NULL,  
            host_id INTEGER NOT NULL,  
            game_type TEXT NOT NULL,  
            status TEXT NOT NULL,  
            current_turn INTEGER DEFAULT 0,  
            created_at TEXT,  
            ended_at TEXT  
        )  
    """)  

    cur.execute("""  
        CREATE TABLE IF NOT EXISTS game_players (  
            game_id INTEGER NOT NULL,  
            user_id INTEGER NOT NULL,  
            position INTEGER NOT NULL,  
            joined_at TEXT,  
            PRIMARY KEY (game_id, user_id)  
        )  
    """)  

    conn.commit()  
    conn.close()

# =========================================================
# USERS
# =========================================================

def add_user(user_id, username=None, first_name=None):
    conn = get_db()

    conn.execute("""  
        INSERT OR IGNORE INTO users  
        (user_id, username, first_name, coins, claimed_free, created_at)  
        VALUES (?, ?, ?, 0, 0, ?)  
    """, (  
        user_id,  
        username,  
        first_name,  
        now()  
    ))  

    conn.execute("""  
        UPDATE users  
        SET username = ?,  
            first_name = ?  
        WHERE user_id = ?  
    """, (  
        username,  
        first_name,  
        user_id  
    ))  

    conn.commit()  
    conn.close()

def get_user(user_id):
    conn = get_db()

    row = conn.execute("""  
        SELECT *  
        FROM users  
        WHERE user_id = ?  
    """, (user_id,)).fetchone()  

    conn.close()  

    return row

def get_balance(user_id):
    row = get_user(user_id)
    return row["coins"] if row else 0

def claim_free_coins(user_id, amount=10000):
    user = get_user(user_id)
    if not user or user["claimed_free"] == 1:
        return False, 0
    
    conn = get_db()
    conn.execute("""
        UPDATE users
        SET coins = coins + ?,
            claimed_free = 1
        WHERE user_id = ?
    """, (amount, user_id))
    
    conn.execute("""  
        INSERT INTO coin_transactions  
        (user_id, amount, reason, created_at)  
        VALUES (?, ?, ?, ?)  
    """, (  
        user_id,  
        amount,  
        "Claimed /free bonus",  
        now()  
    ))
    
    conn.commit()
    conn.close()
    return True, amount

def change_coins(user_id, amount, reason=""):
    conn = get_db()

    conn.execute("""  
        UPDATE users  
        SET coins = coins + ?  
        WHERE user_id = ?  
    """, (  
        amount,  
        user_id  
    ))  

    conn.execute("""  
        INSERT INTO coin_transactions  
        (user_id, amount, reason, created_at)  
        VALUES (?, ?, ?, ?)  
    """, (  
        user_id,  
        amount,  
        reason,  
        now()  
    ))  

    conn.commit()  
    conn.close()

# =========================================================
# ADMINS
# =========================================================

def is_admin(user_id):
    conn = get_db()

    row = conn.execute("""  
        SELECT user_id  
        FROM admins  
        WHERE user_id = ?  
    """, (user_id,)).fetchone()  

    conn.close()  

    return row is not None

def add_admin(user_id):
    conn = get_db()

    conn.execute("""  
        INSERT OR IGNORE INTO admins  
        (user_id, added_at)  
        VALUES (?, ?)  
    """, (  
        user_id,  
        now()  
    ))  

    conn.commit()  
    conn.close()

def remove_admin(user_id):
    conn = get_db()

    conn.execute("""  
        DELETE FROM admins  
        WHERE user_id = ?  
    """, (user_id,))  

    conn.commit()  
    conn.close()

# =========================================================
# LEADERBOARD
# =========================================================

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

# =========================================================
# GAMES
# =========================================================

def create_game(chat_id, host_id, game_type="parchi"):
    conn = get_db()

    cur = conn.cursor()  

    cur.execute("""  
        INSERT INTO games  
        (  
            chat_id,  
            host_id,  
            game_type,  
            status,  
            current_turn,  
            created_at  
        )  
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
            SET status = ?,  
                current_turn = ?  
            WHERE id = ?  
        """, (  
            status,  
            current_turn,  
            game_id  
        ))  

    elif status is not None:  
        conn.execute("""  
            UPDATE games  
            SET status = ?  
            WHERE id = ?  
        """, (  
            status,  
            game_id  
        ))  

    elif current_turn is not None:  
        conn.execute("""  
            UPDATE games  
            SET current_turn = ?  
            WHERE id = ?  
        """, (  
            current_turn,  
            game_id  
        ))  

    conn.commit()  
    conn.close()

def end_game(game_id):
    conn = get_db()

    conn.execute("""  
        UPDATE games  
        SET status = 'ended',  
            ended_at = ?  
        WHERE id = ?  
    """, (  
        now(),  
        game_id  
    ))  

    conn.commit()  
    conn.close()

# =========================================================
# GAME PLAYERS
# =========================================================

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
    """, (  
        game_id,  
        user_id  
    ))  

    conn.commit()  
    conn.close()

def get_game_players(game_id):
    conn = get_db()

    rows = conn.execute("""  
        SELECT  
            gp.game_id,  
            gp.user_id,  
            gp.position,  
            gp.joined_at,  
            u.username,  
            u.first_name  
        FROM game_players gp  
        JOIN users u  
        ON gp.user_id = u.user_id  
        WHERE gp.game_id = ?  
        ORDER BY gp.position ASC  
    """, (game_id,)).fetchall()  

    conn.close()  

    return rows

def get_game_player(game_id, user_id):
    conn = get_db()

    row = conn.execute("""  
        SELECT  
            gp.*,  
            u.username,  
            u.first_name  
        FROM game_players gp  
        JOIN users u  
        ON gp.user_id = u.user_id  
        WHERE gp.game_id = ?  
        AND gp.user_id = ?  
    """, (  
        game_id,  
        user_id  
    )).fetchone()  

    conn.close()  

    return row
