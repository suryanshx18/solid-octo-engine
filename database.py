import os, sqlite3, threading, time
from config import DATABASE_PATH, STARTING_BALANCE

_LOCK = threading.RLock()

def connect():
    os.makedirs(os.path.dirname(os.path.abspath(DATABASE_PATH)), exist_ok=True)
    c = sqlite3.connect(DATABASE_PATH, timeout=30, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('PRAGMA busy_timeout=30000')
    c.execute('PRAGMA foreign_keys=ON')
    return c

def _ensure(c, uid, username='', first_name=''):
    row = c.execute('SELECT user_id FROM users WHERE user_id=?', (uid,)).fetchone()
    if row:
        c.execute('UPDATE users SET username=?,first_name=? WHERE user_id=?', (username or '', first_name or '', uid))
    else:
        c.execute('INSERT INTO users(user_id,username,first_name,balance,created_at) VALUES(?,?,?,?,?)', (uid, username or '', first_name or '', STARTING_BALANCE, int(time.time())))

def init_db():
    with _LOCK, connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY,username TEXT,first_name TEXT,balance INTEGER NOT NULL DEFAULT 0,bank INTEGER NOT NULL DEFAULT 0,xp INTEGER NOT NULL DEFAULT 0,level INTEGER NOT NULL DEFAULT 1,vip INTEGER NOT NULL DEFAULT 0,banned INTEGER NOT NULL DEFAULT 0,muted_until INTEGER NOT NULL DEFAULT 0,warnings INTEGER NOT NULL DEFAULT 0,created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS transactions(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,kind TEXT NOT NULL,amount INTEGER NOT NULL,note TEXT,created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS cooldowns(user_id INTEGER NOT NULL,name TEXT NOT NULL,until_ts INTEGER NOT NULL,PRIMARY KEY(user_id,name));
        CREATE TABLE IF NOT EXISTS games(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,game TEXT,bet INTEGER,result TEXT,net INTEGER,created_at INTEGER);
        CREATE TABLE IF NOT EXISTS inventory(user_id INTEGER NOT NULL,item TEXT NOT NULL,qty INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(user_id,item));
        CREATE TABLE IF NOT EXISTS achievements(user_id INTEGER NOT NULL,achievement TEXT NOT NULL,created_at INTEGER NOT NULL,PRIMARY KEY(user_id,achievement));
        CREATE TABLE IF NOT EXISTS promo_codes(code TEXT PRIMARY KEY,amount INTEGER NOT NULL,max_uses INTEGER NOT NULL DEFAULT 1,uses INTEGER NOT NULL DEFAULT 0,active INTEGER NOT NULL DEFAULT 1,expires_at INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS promo_claims(user_id INTEGER NOT NULL,code TEXT NOT NULL,created_at INTEGER NOT NULL,PRIMARY KEY(user_id,code));
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,actor INTEGER,action TEXT,target INTEGER,details TEXT,created_at INTEGER);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
        CREATE INDEX IF NOT EXISTS idx_tx_user ON transactions(user_id);
        CREATE INDEX IF NOT EXISTS idx_games_user ON games(user_id);
        ''')

def ensure_user(uid, username='', first_name=''):
    with _LOCK, connect() as c:
        _ensure(c, uid, username, first_name); c.commit()

def user(uid):
    with _LOCK, connect() as c:
        _ensure(c, uid); c.commit()
        return c.execute('SELECT * FROM users WHERE user_id=?', (uid,)).fetchone()

def all_users():
    with connect() as c: return c.execute('SELECT user_id FROM users ORDER BY user_id').fetchall()

def change_balance(uid, delta, kind='adjust', note=''):
    with _LOCK, connect() as c:
        c.execute('BEGIN IMMEDIATE'); _ensure(c, uid)
        r=c.execute('SELECT balance,xp FROM users WHERE user_id=?',(uid,)).fetchone()
        if r['balance'] + delta < 0: c.rollback(); return False
        xp=max(0,abs(delta)//100)
        c.execute('UPDATE users SET balance=balance+?,xp=xp+?,level=? WHERE user_id=?',(delta,xp,max(1,(r['xp']+xp)//1000+1),uid))
        c.execute('INSERT INTO transactions(user_id,kind,amount,note,created_at) VALUES(?,?,?,?,?)',(uid,kind,delta,note,int(time.time())))
        c.commit(); return True

def transfer(sender, receiver, amount):
    if amount<=0 or sender==receiver: return False
    with _LOCK, connect() as c:
        c.execute('BEGIN IMMEDIATE'); _ensure(c,sender); _ensure(c,receiver)
        s=c.execute('SELECT balance FROM users WHERE user_id=?',(sender,)).fetchone()
        if s['balance']<amount: c.rollback(); return False
        now=int(time.time())
        c.execute('UPDATE users SET balance=balance-? WHERE user_id=?',(amount,sender)); c.execute('UPDATE users SET balance=balance+? WHERE user_id=?',(amount,receiver))
        c.execute('INSERT INTO transactions(user_id,kind,amount,note,created_at) VALUES(?,?,?,?,?)',(sender,'transfer',-amount,f'to {receiver}',now)); c.execute('INSERT INTO transactions(user_id,kind,amount,note,created_at) VALUES(?,?,?,?,?)',(receiver,'transfer',amount,f'from {sender}',now)); c.commit(); return True

def bank_move(uid, amount, deposit=True):
    if amount<=0:return False
    with _LOCK, connect() as c:
        c.execute('BEGIN IMMEDIATE'); _ensure(c,uid); r=c.execute('SELECT balance,bank FROM users WHERE user_id=?',(uid,)).fetchone()
        if deposit and r['balance']<amount: c.rollback(); return False
        if not deposit and r['bank']<amount: c.rollback(); return False
        if deposit: c.execute('UPDATE users SET balance=balance-?,bank=bank+? WHERE user_id=?',(amount,amount,uid)); tx=-amount
        else: c.execute('UPDATE users SET balance=balance+?,bank=bank-? WHERE user_id=?',(amount,amount,uid)); tx=amount
        c.execute('INSERT INTO transactions(user_id,kind,amount,note,created_at) VALUES(?,?,?,?,?)',(uid,'deposit' if deposit else 'withdraw',tx,'bank',int(time.time()))); c.commit(); return True

def cooldown_ready(uid,name,seconds):
    now=int(time.time())
    with _LOCK, connect() as c:
        r=c.execute('SELECT until_ts FROM cooldowns WHERE user_id=? AND name=?',(uid,name)).fetchone()
        if r and r['until_ts']>now:return False,r['until_ts']-now
        c.execute('INSERT INTO cooldowns(user_id,name,until_ts) VALUES(?,?,?) ON CONFLICT(user_id,name) DO UPDATE SET until_ts=excluded.until_ts',(uid,name,now+seconds)); c.commit(); return True,0

def log_game(uid,game,bet,result,net):
    with _LOCK, connect() as c: c.execute('INSERT INTO games(user_id,game,bet,result,net,created_at) VALUES(?,?,?,?,?,?)',(uid,game,bet,result,net,int(time.time()))); c.commit()

def audit(actor,action,target=None,details=''):
    with _LOCK, connect() as c: c.execute('INSERT INTO audit(actor,action,target,details,created_at) VALUES(?,?,?,?,?)',(actor,action,target,details,int(time.time()))); c.commit()

def top_users(limit=10):
    with connect() as c:return c.execute('SELECT * FROM users WHERE banned=0 ORDER BY (balance+bank) DESC LIMIT ?',(limit,)).fetchall()

def recent_transactions(uid,limit=10):
    with connect() as c:return c.execute('SELECT * FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT ?',(uid,limit)).fetchall()

def set_balance(uid,amount):
    if amount<0:return False
    with _LOCK, connect() as c:
        c.execute('BEGIN IMMEDIATE'); _ensure(c,uid); old=c.execute('SELECT balance FROM users WHERE user_id=?',(uid,)).fetchone()['balance']; c.execute('UPDATE users SET balance=? WHERE user_id=?',(amount,uid)); c.execute('INSERT INTO transactions(user_id,kind,amount,note,created_at) VALUES(?,?,?,?,?)',(uid,'setbalance',amount-old,'admin',int(time.time()))); c.commit(); return True

def set_bank(uid,amount):
    if amount<0:return False
    with _LOCK, connect() as c:c.execute('BEGIN IMMEDIATE'); _ensure(c,uid); c.execute('UPDATE users SET bank=? WHERE user_id=?',(amount,uid)); c.commit(); return True

def add_item(uid,item,qty=1):
    if qty<=0:return False
    with _LOCK,connect() as c:c.execute('INSERT INTO inventory(user_id,item,qty) VALUES(?,?,?) ON CONFLICT(user_id,item) DO UPDATE SET qty=qty+excluded.qty',(uid,item,qty));c.commit();return True

def inventory(uid):
    with connect() as c:return c.execute('SELECT item,qty FROM inventory WHERE user_id=? AND qty>0 ORDER BY item',(uid,)).fetchall()

def unlock(uid,name):
    with _LOCK,connect() as c:
        c.execute('INSERT OR IGNORE INTO achievements(user_id,achievement,created_at) VALUES(?,?,?)',(uid,name,int(time.time())));c.commit()

def achievements(uid):
    with connect() as c:return c.execute('SELECT achievement FROM achievements WHERE user_id=? ORDER BY created_at',(uid,)).fetchall()

def create_promo(code,amount,max_uses,expires_at=0):
    code=code.strip().upper()
    if not code or amount<=0 or max_uses<=0:return False
    with _LOCK,connect() as c:
        try:c.execute('INSERT INTO promo_codes(code,amount,max_uses,expires_at) VALUES(?,?,?,?)',(code,amount,max_uses,expires_at));c.commit();return True
        except sqlite3.IntegrityError:return False

def redeem_promo(uid,code):
    code=code.strip().upper(); now=int(time.time())
    with _LOCK,connect() as c:
        c.execute('BEGIN IMMEDIATE'); _ensure(c,uid); p=c.execute('SELECT * FROM promo_codes WHERE code=? AND active=1',(code,)).fetchone()
        if not p or p['uses']>=p['max_uses'] or (p['expires_at'] and p['expires_at']<now):c.rollback();return None
        if c.execute('SELECT 1 FROM promo_claims WHERE user_id=? AND code=?',(uid,code)).fetchone():c.rollback();return None
        c.execute('INSERT INTO promo_claims(user_id,code,created_at) VALUES(?,?,?)',(uid,code,now));c.execute('UPDATE promo_codes SET uses=uses+1,active=CASE WHEN uses+1>=max_uses THEN 0 ELSE active END WHERE code=?',(code,));c.execute('UPDATE users SET balance=balance+?,xp=xp+?,level=? WHERE user_id=?',(p['amount'],p['amount']//100,max(1,(c.execute('SELECT xp FROM users WHERE user_id=?',(uid,)).fetchone()['xp']+p['amount']//100)//1000+1),uid));c.execute('INSERT INTO transactions(user_id,kind,amount,note,created_at) VALUES(?,?,?,?,?)',(uid,'promo',p['amount'],code,now));c.commit();return p['amount']

def promos():
    with connect() as c:return c.execute('SELECT * FROM promo_codes ORDER BY code').fetchall()

def delete_promo(code):
    with _LOCK,connect() as c:c.execute('DELETE FROM promo_codes WHERE code=?',(code.strip().upper(),));ok=c.rowcount>0;c.commit();return ok

def stats():
    with connect() as c:return (c.execute('SELECT COUNT(*) n FROM users').fetchone()['n'],c.execute('SELECT COALESCE(SUM(balance+bank),0) n FROM users').fetchone()['n'],c.execute('SELECT COUNT(*) n FROM games').fetchone()['n'])
