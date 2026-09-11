import sqlite3, threading, time
from config import DB_PATH, DEFAULT_WARN_LIMIT

LOCK = threading.RLock()

CHAT_COLUMNS = {
    'enabled','welcome','goodbye','verification','antiflood','flood_limit','flood_window',
    'antilink','antispam','antiforward','anti_raid','raid_limit','raid_window','media_lock',
    'sticker_lock','gif_lock','photo_lock','video_lock','file_lock','audio_lock','voice_lock',
    'bot_lock','mention_lock','caps_lock','emoji_lock','command_lock','warn_limit','mute_minutes',
    'log_chat_id','rules','welcome_text','goodbye_text','verify_timeout','leave_ban_enabled',
    'leave_ban_target','accept_requests','tag_enabled','auto_delete','delete_seconds',
    'filter_delete','auto_warn','auto_mute','auto_ban','admin_only_media','lock_status','slowmode',
    'lock_links','lock_media','lock_stickers','lock_gifs','lock_polls','lock_files','lock_voice',
    'lock_video','lock_audio','lock_commands','lock_forwards','lock_mentions','lock_bots',
    'lock_contacts','lock_locations','anti_service','anti_username','anti_join_spam','join_captcha',
    'join_captcha_timeout','clean_welcome','clean_goodbye','auto_pin_rules','channel_post_filter',
    'channel_post_links','channel_post_media','channel_post_forward','channel_auto_delete','force_rules'
}

def connect():
    c = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('PRAGMA synchronous=NORMAL')
    c.execute('PRAGMA foreign_keys=ON')
    return c

def init_db():
    with LOCK, connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS chats(
          chat_id INTEGER PRIMARY KEY, title TEXT, kind TEXT, enabled INTEGER DEFAULT 1,
          welcome INTEGER DEFAULT 1, goodbye INTEGER DEFAULT 1, verification INTEGER DEFAULT 0,
          antiflood INTEGER DEFAULT 1, flood_limit INTEGER DEFAULT 6, flood_window INTEGER DEFAULT 8,
          antilink INTEGER DEFAULT 0, antispam INTEGER DEFAULT 1, antiforward INTEGER DEFAULT 0,
          anti_raid INTEGER DEFAULT 0, raid_limit INTEGER DEFAULT 8, raid_window INTEGER DEFAULT 15,
          media_lock INTEGER DEFAULT 0, sticker_lock INTEGER DEFAULT 0, gif_lock INTEGER DEFAULT 0,
          photo_lock INTEGER DEFAULT 0, video_lock INTEGER DEFAULT 0, file_lock INTEGER DEFAULT 0,
          audio_lock INTEGER DEFAULT 0, voice_lock INTEGER DEFAULT 0, bot_lock INTEGER DEFAULT 0,
          mention_lock INTEGER DEFAULT 0, caps_lock INTEGER DEFAULT 0, emoji_lock INTEGER DEFAULT 0,
          command_lock INTEGER DEFAULT 0, warn_limit INTEGER DEFAULT 3, mute_minutes INTEGER DEFAULT 10,
          log_chat_id INTEGER DEFAULT 0, rules TEXT DEFAULT '', welcome_text TEXT DEFAULT '',
          goodbye_text TEXT DEFAULT '', verify_timeout INTEGER DEFAULT 300,
          leave_ban_enabled INTEGER DEFAULT 0, leave_ban_target TEXT DEFAULT 'group',
          accept_requests INTEGER DEFAULT 0, tag_enabled INTEGER DEFAULT 1,
          auto_delete INTEGER DEFAULT 0, delete_seconds INTEGER DEFAULT 60, filter_delete INTEGER DEFAULT 1,
          auto_warn INTEGER DEFAULT 0, auto_mute INTEGER DEFAULT 0, auto_ban INTEGER DEFAULT 0,
          admin_only_media INTEGER DEFAULT 0, lock_status INTEGER DEFAULT 0, slowmode INTEGER DEFAULT 0,
          lock_links INTEGER DEFAULT 0, lock_media INTEGER DEFAULT 0, lock_stickers INTEGER DEFAULT 0,
          lock_gifs INTEGER DEFAULT 0, lock_polls INTEGER DEFAULT 0, lock_files INTEGER DEFAULT 0,
          lock_voice INTEGER DEFAULT 0, lock_video INTEGER DEFAULT 0, lock_audio INTEGER DEFAULT 0,
          lock_commands INTEGER DEFAULT 0, lock_forwards INTEGER DEFAULT 0, lock_mentions INTEGER DEFAULT 0,
          lock_bots INTEGER DEFAULT 0, lock_contacts INTEGER DEFAULT 0, lock_locations INTEGER DEFAULT 0,
          anti_service INTEGER DEFAULT 0, anti_username INTEGER DEFAULT 0, anti_join_spam INTEGER DEFAULT 0,
          join_captcha INTEGER DEFAULT 0, join_captcha_timeout INTEGER DEFAULT 300, clean_welcome INTEGER DEFAULT 1,
          clean_goodbye INTEGER DEFAULT 1, auto_pin_rules INTEGER DEFAULT 0, channel_post_filter INTEGER DEFAULT 1,
          channel_post_links INTEGER DEFAULT 0, channel_post_media INTEGER DEFAULT 0, channel_post_forward INTEGER DEFAULT 0,
          channel_auto_delete INTEGER DEFAULT 0, force_rules INTEGER DEFAULT 0, created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS admins(chat_id INTEGER,user_id INTEGER,role TEXT DEFAULT 'mod',added_by INTEGER,created_at INTEGER,PRIMARY KEY(chat_id,user_id));
        CREATE TABLE IF NOT EXISTS users(chat_id INTEGER,user_id INTEGER,username TEXT,first_name TEXT,last_seen INTEGER,is_bot INTEGER DEFAULT 0,PRIMARY KEY(chat_id,user_id));
        CREATE TABLE IF NOT EXISTS warnings(chat_id INTEGER,user_id INTEGER,count INTEGER DEFAULT 0,PRIMARY KEY(chat_id,user_id));
        CREATE TABLE IF NOT EXISTS filters(chat_id INTEGER,keyword TEXT,response TEXT,delete_message INTEGER DEFAULT 1,PRIMARY KEY(chat_id,keyword));
        CREATE TABLE IF NOT EXISTS banned_words(chat_id INTEGER,word TEXT,created_by INTEGER,PRIMARY KEY(chat_id,word));
        CREATE TABLE IF NOT EXISTS logs(id INTEGER PRIMARY KEY AUTOINCREMENT,chat_id INTEGER,actor_id INTEGER,action TEXT,target_id INTEGER DEFAULT 0,details TEXT,created_at INTEGER);
        CREATE TABLE IF NOT EXISTS verification(chat_id INTEGER,user_id INTEGER,token TEXT,expires_at INTEGER,verified INTEGER DEFAULT 0,PRIMARY KEY(chat_id,user_id));
        CREATE TABLE IF NOT EXISTS links(chat_id INTEGER,linked_chat_id INTEGER,relation TEXT,PRIMARY KEY(chat_id,linked_chat_id,relation));
        CREATE TABLE IF NOT EXISTS scheduled(id INTEGER PRIMARY KEY AUTOINCREMENT,chat_id INTEGER,text TEXT,run_at INTEGER,repeat_seconds INTEGER DEFAULT 0,active INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS join_requests(chat_id INTEGER,user_id INTEGER,username TEXT,first_name TEXT,requested_at INTEGER,PRIMARY KEY(chat_id,user_id));
        CREATE TABLE IF NOT EXISTS whitelist(chat_id INTEGER,user_id INTEGER,reason TEXT,added_by INTEGER,PRIMARY KEY(chat_id,user_id));
        CREATE TABLE IF NOT EXISTS raid_state(chat_id INTEGER PRIMARY KEY,started_at INTEGER,count INTEGER DEFAULT 0,active INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS settings_meta(chat_id INTEGER PRIMARY KEY,language TEXT DEFAULT 'en',timezone TEXT DEFAULT 'UTC');
        CREATE INDEX IF NOT EXISTS idx_logs_chat ON logs(chat_id,id DESC);
        CREATE INDEX IF NOT EXISTS idx_users_chat ON users(chat_id,last_seen DESC);
        CREATE INDEX IF NOT EXISTS idx_links_source ON links(chat_id,relation);
        ''')
        c.commit()

def ensure_chat(chat_id,title='',kind='group'):
    with LOCK, connect() as c:
        c.execute('INSERT OR IGNORE INTO chats(chat_id,title,kind,created_at) VALUES(?,?,?,?)',(chat_id,title,kind,int(time.time())))
        c.execute('UPDATE chats SET title=?,kind=? WHERE chat_id=?',(title,kind,chat_id)); c.commit()

def get_chat(chat_id):
    with LOCK, connect() as c: return c.execute('SELECT * FROM chats WHERE chat_id=?',(chat_id,)).fetchone()

def set_setting(chat_id,key,value):
    if key not in CHAT_COLUMNS: raise ValueError('invalid setting')
    with LOCK, connect() as c:
        c.execute(f'UPDATE chats SET {key}=? WHERE chat_id=?',(value,chat_id)); c.commit()

def upsert_user(chat_id,user):
    with LOCK, connect() as c:
        c.execute('''INSERT INTO users VALUES(?,?,?,?,?,?) ON CONFLICT(chat_id,user_id) DO UPDATE SET username=excluded.username,first_name=excluded.first_name,last_seen=excluded.last_seen,is_bot=excluded.is_bot''',(chat_id,user.id,user.username or '',user.first_name or '',int(time.time()),int(bool(user.is_bot)))); c.commit()

def known_users(chat_id,include_bots=False):
    with LOCK, connect() as c:
        q='SELECT * FROM users WHERE chat_id=?'+('' if include_bots else ' AND is_bot=0')+' ORDER BY first_name,user_id'; return c.execute(q,(chat_id,)).fetchall()

def add_admin(chat_id,user_id,role,added_by):
    with LOCK, connect() as c: c.execute('INSERT OR REPLACE INTO admins VALUES(?,?,?,?,?)',(chat_id,user_id,role,added_by,int(time.time()))); c.commit()

def remove_admin(chat_id,user_id):
    with LOCK, connect() as c: c.execute('DELETE FROM admins WHERE chat_id=? AND user_id=?',(chat_id,user_id)); c.commit()

def get_admin(chat_id,user_id):
    with LOCK, connect() as c: return c.execute('SELECT * FROM admins WHERE chat_id=? AND user_id=?',(chat_id,user_id)).fetchone()

def list_admins(chat_id):
    with LOCK, connect() as c: return c.execute('SELECT * FROM admins WHERE chat_id=? ORDER BY role,user_id',(chat_id,)).fetchall()

def warn(chat_id,user_id):
    with LOCK, connect() as c:
        c.execute('INSERT INTO warnings VALUES(?,?,1) ON CONFLICT(chat_id,user_id) DO UPDATE SET count=count+1',(chat_id,user_id)); r=c.execute('SELECT count FROM warnings WHERE chat_id=? AND user_id=?',(chat_id,user_id)).fetchone(); c.commit(); return r['count']

def clear_warnings(chat_id,user_id):
    with LOCK, connect() as c: c.execute('DELETE FROM warnings WHERE chat_id=? AND user_id=?',(chat_id,user_id)); c.commit()

def get_warning(chat_id,user_id):
    with LOCK, connect() as c: r=c.execute('SELECT count FROM warnings WHERE chat_id=? AND user_id=?',(chat_id,user_id)).fetchone(); return int(r['count']) if r else 0

def add_filter(chat_id,keyword,response,delete_message=True):
    with LOCK, connect() as c: c.execute('INSERT OR REPLACE INTO filters VALUES(?,?,?,?)',(chat_id,keyword.lower(),response,int(delete_message))); c.commit()

def del_filter(chat_id,keyword):
    with LOCK, connect() as c: c.execute('DELETE FROM filters WHERE chat_id=? AND keyword=?',(chat_id,keyword.lower())); ok=c.rowcount>0; c.commit(); return ok

def filters(chat_id):
    with LOCK, connect() as c: return c.execute('SELECT * FROM filters WHERE chat_id=? ORDER BY keyword',(chat_id,)).fetchall()

def add_word(chat_id,word,created_by):
    with LOCK, connect() as c: c.execute('INSERT OR REPLACE INTO banned_words VALUES(?,?,?)',(chat_id,word.lower(),created_by)); c.commit()

def del_word(chat_id,word):
    with LOCK, connect() as c: c.execute('DELETE FROM banned_words WHERE chat_id=? AND word=?',(chat_id,word.lower())); ok=c.rowcount>0; c.commit(); return ok

def words(chat_id):
    with LOCK, connect() as c: return [r['word'] for r in c.execute('SELECT word FROM banned_words WHERE chat_id=?',(chat_id,))]

def add_log(chat_id,actor,action,target=0,details=''):
    with LOCK, connect() as c: c.execute('INSERT INTO logs(chat_id,actor_id,action,target_id,details,created_at) VALUES(?,?,?,?,?,?)',(chat_id,actor,action,target,details,int(time.time()))); c.commit()

def recent_logs(chat_id,limit=40):
    with LOCK, connect() as c: return c.execute('SELECT * FROM logs WHERE chat_id=? ORDER BY id DESC LIMIT ?',(chat_id,limit)).fetchall()

def add_link(chat_id,linked_chat_id,relation):
    with LOCK, connect() as c: c.execute('INSERT OR REPLACE INTO links VALUES(?,?,?)',(chat_id,linked_chat_id,relation)); c.commit()

def del_link(chat_id,linked_chat_id,relation):
    with LOCK, connect() as c: c.execute('DELETE FROM links WHERE chat_id=? AND linked_chat_id=? AND relation=?',(chat_id,linked_chat_id,relation)); c.commit()

def linked(chat_id,relation):
    with LOCK, connect() as c: return c.execute('SELECT linked_chat_id FROM links WHERE chat_id=? AND relation=?',(chat_id,relation)).fetchall()

def reverse_links(source_chat_id,relation):
    with LOCK, connect() as c: return c.execute('SELECT chat_id FROM links WHERE linked_chat_id=? AND relation=?',(source_chat_id,relation)).fetchall()

def set_verification(chat_id,user_id,token,expires):
    with LOCK, connect() as c: c.execute('INSERT OR REPLACE INTO verification VALUES(?,?,?,?,0)',(chat_id,user_id,token,expires)); c.commit()

def verify(chat_id,user_id):
    with LOCK, connect() as c: c.execute('UPDATE verification SET verified=1 WHERE chat_id=? AND user_id=?',(chat_id,user_id)); c.commit()

def is_verified(chat_id,user_id):
    with LOCK, connect() as c:
        r=c.execute('SELECT verified,expires_at FROM verification WHERE chat_id=? AND user_id=?',(chat_id,user_id)).fetchone(); return bool(r and r['verified'] and r['expires_at']>int(time.time()))

def add_request(chat_id,user):
    with LOCK, connect() as c: c.execute('INSERT OR REPLACE INTO join_requests VALUES(?,?,?,?,?)',(chat_id,user.id,user.username or '',user.first_name or '',int(time.time()))); c.commit()

def remove_request(chat_id,user_id):
    with LOCK, connect() as c: c.execute('DELETE FROM join_requests WHERE chat_id=? AND user_id=?',(chat_id,user_id)); c.commit()

def add_whitelist(chat_id,user_id,reason,added_by):
    with LOCK, connect() as c: c.execute('INSERT OR REPLACE INTO whitelist VALUES(?,?,?,?)',(chat_id,user_id,reason,added_by)); c.commit()

def del_whitelist(chat_id,user_id):
    with LOCK, connect() as c: c.execute('DELETE FROM whitelist WHERE chat_id=? AND user_id=?',(chat_id,user_id)); c.commit()

def is_whitelisted(chat_id,user_id):
    with LOCK, connect() as c: return c.execute('SELECT 1 FROM whitelist WHERE chat_id=? AND user_id=?',(chat_id,user_id)).fetchone() is not None

def add_schedule(chat_id,text,run_at,repeat_seconds=0):
    with LOCK, connect() as c: cur=c.execute('INSERT INTO scheduled(chat_id,text,run_at,repeat_seconds,active) VALUES(?,?,?,?,1)',(chat_id,text,run_at,repeat_seconds)); c.commit(); return cur.lastrowid

def due_schedules(now=None):
    now=now or int(time.time())
    with LOCK, connect() as c: return c.execute('SELECT * FROM scheduled WHERE active=1 AND run_at<=? ORDER BY run_at',(now,)).fetchall()

def reschedule_or_deactivate(row):
    with LOCK, connect() as c:
        if row['repeat_seconds']>0: c.execute('UPDATE scheduled SET run_at=? WHERE id=?',(int(time.time())+row['repeat_seconds'],row['id']))
        else: c.execute('UPDATE scheduled SET active=0 WHERE id=?',(row['id'],))
        c.commit()

def cancel_schedule(chat_id,sid):
    with LOCK, connect() as c: c.execute('UPDATE scheduled SET active=0 WHERE id=? AND chat_id=?',(sid,chat_id)); ok=c.rowcount>0; c.commit(); return ok

def raid(chat_id,now,window):
    with LOCK, connect() as c:
        r=c.execute('SELECT * FROM raid_state WHERE chat_id=?',(chat_id,)).fetchone()
        if not r or now-r['started_at']>window: c.execute('INSERT OR REPLACE INTO raid_state VALUES(?,?,?,?)',(chat_id,now,1,0)); count=1
        else: count=r['count']+1; c.execute('UPDATE raid_state SET count=? WHERE chat_id=?',(count,chat_id))
        c.commit(); return count

def set_raid(chat_id,active):
    with LOCK, connect() as c: c.execute('UPDATE raid_state SET active=? WHERE chat_id=?',(int(active),chat_id)); c.commit()

def stats(chat_id):
    with LOCK, connect() as c:
        return {
          'users': c.execute('SELECT COUNT(*) n FROM users WHERE chat_id=? AND is_bot=0',(chat_id,)).fetchone()['n'],
          'warnings': c.execute('SELECT COALESCE(SUM(count),0) n FROM warnings WHERE chat_id=?',(chat_id,)).fetchone()['n'],
          'filters': c.execute('SELECT COUNT(*) n FROM filters WHERE chat_id=?',(chat_id,)).fetchone()['n'],
          'logs': c.execute('SELECT COUNT(*) n FROM logs WHERE chat_id=?',(chat_id,)).fetchone()['n'],
          'admins': c.execute('SELECT COUNT(*) n FROM admins WHERE chat_id=?',(chat_id,)).fetchone()['n']
        }

