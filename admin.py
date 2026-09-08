import database, config

def is_owner(uid): return uid==config.OWNER_ID

def admin_ids():
    with database.connect() as c:
        r=c.execute("SELECT value FROM settings WHERE key='admins'").fetchone()
        return {int(x) for x in (r['value'].split(',') if r and r['value'] else []) if x.strip().isdigit()}

def has_power(uid): return is_owner(uid) or uid in admin_ids()

def set_admin(actor,target,enabled):
    if not is_owner(actor) or target==config.OWNER_ID:return False
    ids=admin_ids(); ids.add(target) if enabled else ids.discard(target)
    with database.connect() as c:c.execute("INSERT INTO settings(key,value) VALUES('admins',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(','.join(map(str,sorted(ids))),));c.commit()
    database.audit(actor,'admin' if enabled else 'unadmin',target);return True

def maintenance(on=None):
    with database.connect() as c:
        if on is not None:c.execute("INSERT INTO settings(key,value) VALUES('maintenance',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",('1' if on else '0',));c.commit()
        r=c.execute("SELECT value FROM settings WHERE key='maintenance'").fetchone();return bool(r and r['value']=='1')

def ban(actor,target,enabled=True):
    if not has_power(actor):return False
    with database.connect() as c:database._ensure(c,target);c.execute('UPDATE users SET banned=? WHERE user_id=?',(int(enabled),target));c.commit()
    database.audit(actor,'ban' if enabled else 'unban',target);return True

def warn(actor,target):
    if not has_power(actor):return False
    with database.connect() as c:database._ensure(c,target);c.execute('UPDATE users SET warnings=warnings+1 WHERE user_id=?',(target,));c.commit()
    database.audit(actor,'warn',target);return True

def give(actor,target,amount):
    if not has_power(actor) or amount<=0:return False
    ok=database.change_balance(target,amount,'admin_give','admin');ok and database.audit(actor,'give',target,str(amount));return ok

def remove(actor,target,amount):
    if not has_power(actor) or amount<=0:return False
    ok=database.change_balance(target,-amount,'admin_remove','admin');ok and database.audit(actor,'remove',target,str(amount));return ok

def set_balance(actor,target,amount):
    if not has_power(actor):return False
    ok=database.set_balance(target,amount);ok and database.audit(actor,'setbalance',target,str(amount));return ok
