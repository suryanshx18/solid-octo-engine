"""Owner/admin management. Admins are stored in SQLite, not hard-coded."""
import time, database, config

def is_owner(uid): return uid == config.OWNER_ID

def is_admin(uid):
    if is_owner(uid): return True
    r=database.user(uid)
    return bool(r and r["vip"] == -999)  # reserved flag is not used for VIP; admin IDs live in settings

def admin_ids():
    with database.connect() as c:
        r=c.execute("SELECT value FROM settings WHERE key='admins'").fetchone()
        return {int(x) for x in (r["value"].split(",") if r and r["value"] else []) if x.strip().isdigit()}

def has_power(uid):
    return is_owner(uid) or uid in admin_ids()

def set_admin(actor,target,enabled):
    if not is_owner(actor): return False
    ids=admin_ids()
    if enabled: ids.add(target)
    else: ids.discard(target)
    with database.connect() as c:
        value=",".join(map(str,sorted(ids)))
        c.execute("INSERT INTO settings(key,value) VALUES('admins',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(value,))
        c.commit()
    database.audit(actor,"admin" if enabled else "unadmin",target)
    return True

def maintenance(on=None):
    with database.connect() as c:
        if on is not None:
            c.execute("INSERT INTO settings(key,value) VALUES('maintenance',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",("1" if on else "0",))
            c.commit()
        r=c.execute("SELECT value FROM settings WHERE key='maintenance'").fetchone()
        return bool(r and r["value"]=="1")

def ban(actor,target,enabled=True):
    if not has_power(actor): return False
    with database.connect() as c:
        c.execute("UPDATE users SET banned=? WHERE user_id=?",(1 if enabled else 0,target)); c.commit()
    database.audit(actor,"ban" if enabled else "unban",target); return True

def warn(actor,target):
    if not has_power(actor): return False
    with database.connect() as c:
        c.execute("UPDATE users SET warnings=warnings+1 WHERE user_id=?",(target,)); c.commit()
    database.audit(actor,"warn",target); return True

def set_balance(actor,target,amount):
    if not has_power(actor): return False
    ok=database.set_balance(target,amount)
    if ok: database.audit(actor,"setbalance",target,str(amount))
    return ok

def give(actor,target,amount):
    if not has_power(actor) or amount<=0:return False
    ok=database.change_balance(target,amount,"admin_give","admin")
    if ok: database.audit(actor,"give",target,str(amount))
    return ok

def remove(actor,target,amount):
    if not has_power(actor) or amount<=0:return False
    ok=database.change_balance(target,-amount,"admin_remove","admin")
    if ok: database.audit(actor,"remove",target,str(amount))
    return ok
