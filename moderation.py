import re, time, random, string, html
from telegram import ChatPermissions
from telegram.error import TelegramError
import database, config

URL_RE=re.compile(r'(https?://|t\.me/|www\.|discord\.gg/|bit\.ly/)',re.I)

def mention(user):
    name=html.escape(user.first_name or user.username or 'User')
    return f'<a href="tg://user?id={user.id}">{name}</a>'

def parse_target(text):
    m=re.search(r'(?:https?://)?t\.me/([A-Za-z0-9_]+)',text or '')
    if m:return '@'+m.group(1)
    try:return int(str(text).strip())
    except:return str(text).strip()

def is_admin(member): return member.status in ('administrator','creator')

async def actor_is_mod(update,context,user_id=None):
    uid=user_id or update.effective_user.id
    if uid==config.OWNER_ID:return True
    if not update.effective_chat or update.effective_chat.type not in ('group','supergroup','channel'):return False
    row=database.get_admin(update.effective_chat.id,uid)
    if row:return True
    try:return is_admin(await context.bot.get_chat_member(update.effective_chat.id,uid))
    except TelegramError:return False

async def bot_can(context,chat_id,perm):
    try:
        m=await context.bot.get_chat_member(chat_id,context.bot.id)
        return m.status=='creator' or bool(getattr(m,perm,False))
    except TelegramError:return False

def random_token():return ''.join(random.choices(string.ascii_uppercase+string.digits,k=6))

def flood_state(context,chat_id,user_id,window=8):
    store=context.application.bot_data.setdefault('flood',{}); key=(chat_id,user_id); now=time.time(); arr=[x for x in store.get(key,[]) if now-x<window]; arr.append(now); store[key]=arr; return len(arr)

def raid_state(context,chat_id,window=15):
    store=context.application.bot_data.setdefault('raid',{}); now=time.time(); arr=[x for x in store.get(chat_id,[]) if now-x<window]; arr.append(now); store[chat_id]=arr; return len(arr)

async def punish(context,update,action,user_id,reason=''):
    chat_id=update.effective_chat.id
    try:
        if action=='delete': await update.effective_message.delete()
        elif action=='mute': await context.bot.restrict_chat_member(chat_id,user_id,permissions=ChatPermissions(can_send_messages=False),until_date=int(time.time())+600)
        elif action=='ban': await context.bot.ban_chat_member(chat_id,user_id)
    except TelegramError: pass
    database.add_log(chat_id,update.effective_user.id,action,user_id,reason)

