"""SQLite persistence and atomic economy operations."""
import sqlite3, time, threading, os
from config import DATABASE_PATH, STARTING_BALANCE

_LOCK = threading.RLock()

def connect():
    os.makedirs(os.path.dirname(os.path.abspath(DATABASE_PATH)), exist_ok=True)
    con = sqlite3.connect(DATABASE_PATH, timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con

def init_db():
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
            balance INTEGER NOT NULL DEFAULT 0, bank INTEGER NOT NULL DEFAULT 0,
            xp INTEGER NOT NULL DEFAULT 0, level INTEGER NOT NULL DEFAULT 1,
            vip INTEGER NOT NULL DEFAULT 0, banned INTEGER NOT NULL DEFAULT 0,
            muted_until INTEGER NOT NULL DEFAULT 0, warnings INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS transactions(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            kind TEXT NOT NULL, amount INTEGER NOT NULL, note TEXT,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cooldowns(
            user_id INTEGER NOT NULL, name TEXT NOT NULL, until_ts INTEGER NOT NULL,
            PRIMARY KEY(user_id,name)
        );
        CREATE TABLE IF NOT EXISTS games(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, game TEXT,
            bet INTEGER, result TEXT, net INTEGER, created_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS inventory(
            user_id INTEGER NOT NULL, item TEXT NOT NULL, qty INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id,item)
        );
        CREATE TABLE IF NOT EXISTS achievements(
            user_id INTEGER NOT NULL, achievement TEXT NOT NULL,
            created_at INTEGER NOT NULL, PRIMARY KEY(user_id,achievement)
        );
        CREATE TABLE IF NOT EXISTS promo_codes(
            code TEXT PRIMARY KEY, amount INTEGER NOT NULL,
            max_uses INTEGER NOT NULL DEFAULT 1, uses INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS promo_claims(
            user_id INTEGER NOT NULL, code TEXT NOT NULL,
            PRIMARY KEY(user_id,code)
        );
        CREATE TABLE IF NOT EXISTS audit(
            id INTEGER PRIMARY KEY AUTOINCREMENT, actor INTEGER, action TEXT,
            target INTEGER, details TEXT, created_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
        CREATE INDEX IF NOT EXISTS idx_tx_user ON transactions(user_id);
        CREATE INDEX IF NOT EXISTS idx_games_user ON games(user_id);
        """)
        c.commit()

def ensure_user(user_id, username="", first_name=""):
    with _LOCK, connect() as c:
        row=c.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not row:
            c.execute("""INSERT INTO users(user_id,username,first_name,balance,created_at)
                         VALUES(?,?,?,?,?)""",
                      (user_id,username or "",first_name or "",STARTING_BALANCE,int(time.time())))
        else:
            c.execute("UPDATE users SET username=?,first_name=? WHERE user_id=?",
                      (username or "",first_name or "",user_id))
        c.commit()

def user(user_id):
    ensure_user(user_id)
    with connect() as c:
        return c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()

def all_users():
    with connect() as c:
        return c.execute("SELECT user_id FROM users ORDER BY user_id").fetchall()

def change_balance(user_id, delta, kind="adjust", note=""):
    with _LOCK, connect() as c:
        c.execute("BEGIN IMMEDIATE")
        ensure_user(user_id)
        row=c.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row["balance"] + delta < 0:
            c.rollback()
            return False
        c.execute("UPDATE users SET balance=balance+?, xp=xp+? WHERE user_id=?",
                  (delta, max(0, abs(delta)//100), user_id))
        c.execute("INSERT INTO transactions(user_id,kind,amount,note,created_at) VALUES(?,?,?,?,?)",
                  (user_id,kind,delta,note,int(time.time())))
        c.commit()
        update_level(user_id)
        return True

def transfer(sender, receiver, amount):
    if amount <= 0 or sender == receiver:
        return False
    with _LOCK, connect() as c:
        c.execute("BEGIN IMMEDIATE")
        ensure_user(sender); ensure_user(receiver)
        s=c.execute("SELECT balance FROM users WHERE user_id=?", (sender,)).fetchone()
        if s["balance"] < amount:
            c.rollback(); return False
        c.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (amount,sender))
        c.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amount,receiver))
        now=int(time.time())
        c.execute("INSERT INTO transactions(user_id,kind,amount,note,created_at) VALUES(?,?,?,?,?)",
                  (sender,"pay",-amount,f"to {receiver}",now))
        c.execute("INSERT INTO transactions(user_id,kind,amount,note,created_at) VALUES(?,?,?,?,?)",
                  (receiver,"pay",amount,f"from {sender}",now))
        c.commit()
        return True

def bank_move(user_id, amount, deposit=True):
    if amount <= 0: return False
    with _LOCK, connect() as c:
        c.execute("BEGIN IMMEDIATE")
        ensure_user(user_id)
        r=c.execute("SELECT balance,bank FROM users WHERE user_id=?", (user_id,)).fetchone()
        if deposit:
            if r["balance"] < amount: c.rollback(); return False
            c.execute("UPDATE users SET balance=balance-?,bank=bank+? WHERE user_id=?",(amount,amount,user_id))
            kind="deposit"
        else:
            if r["bank"] < amount: c.rollback(); return False
            c.execute("UPDATE users SET balance=balance+?,bank=bank-? WHERE user_id=?",(amount,amount,user_id))
            kind="withdraw"
        c.execute("INSERT INTO transactions(user_id,kind,amount,note,created_at) VALUES(?,?,?,?,?)",
                  (user_id,kind,amount if not deposit else -amount,"bank",int(time.time())))
        c.commit(); return True

def cooldown_ready(user_id, name, seconds):
    now=int(time.time())
    with _LOCK, connect() as c:
        r=c.execute("SELECT until_ts FROM cooldowns WHERE user_id=? AND name=?",(user_id,name)).fetchone()
        if r and r["until_ts"] > now:
            return False, r["until_ts"]-now
        c.execute("INSERT INTO cooldowns(user_id,name,until_ts) VALUES(?,?,?) ON CONFLICT(user_id,name) DO UPDATE SET until_ts=excluded.until_ts",
                  (user_id,name,now+seconds)); c.commit()
        return True, 0

def update_level(user_id):
    with _LOCK, connect() as c:
        r=c.execute("SELECT xp FROM users WHERE user_id=?",(user_id,)).fetchone()
        if r:
            level=max(1, r["xp"]//1000+1)
            c.execute("UPDATE users SET level=? WHERE user_id=?",(level,user_id)); c.commit()

def log_game(user_id, game, bet, result, net):
    with connect() as c:
        c.execute("INSERT INTO games(user_id,game,bet,result,net,created_at) VALUES(?,?,?,?,?,?)",
                  (user_id,game,bet,result,net,int(time.time()))); c.commit()

def audit(actor, action, target=None, details=""):
    with connect() as c:
        c.execute("INSERT INTO audit(actor,action,target,details,created_at) VALUES(?,?,?,?,?)",
                  (actor,action,target,details,int(time.time()))); c.commit()

def top_users(limit=10):
    with connect() as c:
        return c.execute("SELECT * FROM users ORDER BY balance DESC LIMIT ?",(limit,)).fetchall()

def recent_transactions(user_id, limit=10):
    with connect() as c:
        return c.execute("SELECT * FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT ?",(user_id,limit)).fetchall()

def set_balance(user_id, amount):
    if amount < 0: return False
    with _LOCK, connect() as c:
        c.execute("BEGIN IMMEDIATE"); ensure_user(user_id)
        old=c.execute("SELECT balance FROM users WHERE user_id=?",(user_id,)).fetchone()["balance"]
        c.execute("UPDATE users SET balance=? WHERE user_id=?",(amount,user_id))
        c.execute("INSERT INTO transactions(user_id,kind,amount,note,created_at) VALUES(?,?,?,?,?)",
                  (user_id,"setbalance",amount-old,"admin",int(time.time())))
        c.commit(); return True

def set_bank(user_id, amount):
    if amount < 0: return False
    with connect() as c:
        ensure_user(user_id); c.execute("UPDATE users SET bank=? WHERE user_id=?",(amount,user_id)); c.commit(); return True
