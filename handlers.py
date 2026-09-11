import asyncio, html, time, re
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError
from telegram.ext import CommandHandler, MessageHandler, CallbackQueryHandler, ChatMemberHandler, ChatJoinRequestHandler, filters
import config, database, moderation

SETTING_GROUPS={
'🛡 Protection':['antiflood','antilink','antispam','antiforward','anti_raid','anti_join_spam','anti_username','anti_service'],
'🔒 Locks':['lock_links','lock_media','lock_stickers','lock_gifs','lock_polls','lock_files','lock_voice','lock_video','lock_audio','lock_forwards','lock_mentions','lock_bots','lock_contacts','lock_locations','lock_commands'],
'👋 Members':['welcome','goodbye','verification','join_captcha','leave_ban_enabled','tag_enabled','force_rules','clean_welcome','clean_goodbye'],
'📣 Channel':['channel_post_filter','channel_post_links','channel_post_media','channel_post_forward','channel_auto_delete','accept_requests'],
'⚙️ Automation':['auto_delete','auto_warn','auto_mute','auto_ban','auto_pin_rules','admin_only_media','mention_lock','caps_lock','emoji_lock']}
LABELS={k:k.replace('_',' ').title() for g in SETTING_GROUPS.values() for k in g}

def esc(x):return html.escape(str(x or ''))
def kb_home():
    return InlineKeyboardMarkup([[InlineKeyboardButton('⚙️ Settings',callback_data='settings:0'),InlineKeyboardButton('🛡 Moderation',callback_data='mod')],[InlineKeyboardButton('👋 Members',callback_data='members'),InlineKeyboardButton('📣 Channel',callback_data='channel')],[InlineKeyboardButton('📋 Logs',callback_data='logs'),InlineKeyboardButton('👮 Admins',callback_data='admins')],[InlineKeyboardButton('📊 Stats',callback_data='stats')]])
def kb_settings(row,page=0):
    groups=list(SETTING_GROUPS); name=list(SETTING_GROUPS)[page%len(groups)]; keys=SETTING_GROUPS[name]; rows=[]
    for i in range(0,len(keys),2):
        rows.append([InlineKeyboardButton(('✅ ' if row[k] else '❌ ')+LABELS[k],callback_data=f't:{k}') for k in keys[i:i+2]])
    nav=[]
    if page>0:nav.append(InlineKeyboardButton('◀️',callback_data=f'settings:{page-1}'))
    nav.append(InlineKeyboardButton(f'{page+1}/{len(groups)}',callback_data='noop'))
    if page<len(groups)-1:nav.append(InlineKeyboardButton('▶️',callback_data=f'settings:{page+1}'))
    rows.append(nav); rows.append([InlineKeyboardButton('🔙 Home',callback_data='home')]); return InlineKeyboardMarkup(rows)

async def start(update,context): await update.message.reply_text('🛡️ <b>GroupGuard V9999999 Ultra</b>\nAdd me as admin, then run /setup in your group or channel.',parse_mode=ParseMode.HTML)
async def setup(update,context):
    if update.effective_chat.type not in ('group','supergroup','channel'):return
    database.ensure_chat(update.effective_chat.id,update.effective_chat.title or '',update.effective_chat.type)
    await update.effective_message.reply_text('🛡️ <b>GroupGuard Ultra is ready.</b>\nOpen the control panel to configure everything.',parse_mode=ParseMode.HTML,reply_markup=kb_home())
async def panel(update,context):
    if await moderation.actor_is_mod(update,context): await update.effective_message.reply_text('🛡️ <b>Control Panel</b>',parse_mode=ParseMode.HTML,reply_markup=kb_home())

async def callback(update,context):
    q=update.callback_query
    try:await q.answer()
    except BadRequest:pass
    if q.data=='noop':return
    chat_id=q.message.chat.id
    if not await moderation.actor_is_mod(update,context,q.from_user.id):return
    row=database.get_chat(chat_id)
    if not row:database.ensure_chat(chat_id,q.message.chat.title or '',q.message.chat.type);row=database.get_chat(chat_id)
    if q.data=='home':await q.edit_message_text('🛡️ <b>GroupGuard Ultra</b>',parse_mode=ParseMode.HTML,reply_markup=kb_home());return
    if q.data.startswith('settings:'):
        page=int(q.data.split(':')[1]);await q.edit_message_text('⚙️ <b>All Settings</b>\nToggle protection and automation modules.',parse_mode=ParseMode.HTML,reply_markup=kb_settings(row,page));return
    if q.data.startswith('t:'):
        key=q.data[2:];database.set_setting(chat_id,key,0 if row[key] else 1);row=database.get_chat(chat_id);await q.edit_message_reply_markup(reply_markup=kb_settings(row,0));return
    if q.data=='mod':text='🛡 <b>Moderation</b>\n/ban /unban /kick /mute /unmute /warn /unwarn /purge /pin /unpin /slowmode /lock /unlock';mark=kb_home()
    elif q.data=='members':text='👋 /welcome /setwelcome /goodbye /setgoodbye /verify /setrules /rules /whitelist';mark=kb_home()
    elif q.data=='channel':text='📣 /acceptreq CHAT /stopaccreq CHAT\n/linkleave GROUP CHANNEL\n/unlinkleave GROUP CHANNEL\n/channelstats';mark=kb_home()
    elif q.data=='logs':
        logs=database.recent_logs(chat_id,25);text='📋 <b>Recent Logs</b>\n'+('\n'.join(f"• {esc(x['action'])} → <code>{x['target_id']}</code> {esc(x['details'])}" for x in logs) or 'No logs yet.');mark=kb_home()
    elif q.data=='admins':
        try:a=await context.bot.get_chat_administrators(chat_id);text='👮 <b>Telegram Admins</b>\n'+'\n'.join(f'• {esc(x.user.first_name)} — <code>{x.user.id}</code>' for x in a)
        except Exception:text='Unable to read admins.'
        mark=kb_home()
    elif q.data=='stats':
        s=database.stats(chat_id);text=f"📊 <b>Stats</b>\nUsers seen: {s['users']}\nWarnings: {s['warnings']}\nFilters: {s['filters']}\nLogs: {s['logs']}\nCustom admins: {s['admins']}";mark=kb_home()
    else:return
    try:await q.edit_message_text(text,parse_mode=ParseMode.HTML,reply_markup=mark)
    except BadRequest:pass

async def remember(update,context):
    chat=update.effective_chat
    if not chat or chat.type not in ('group','supergroup','channel'):return
    database.ensure_chat(chat.id,chat.title or '',chat.type)
    if update.effective_user:database.upsert_user(chat.id,update.effective_user)

async def verification_cmd(update,context):
    if not context.args:await update.message.reply_text('Usage: /verify CODE');return
    if database.is_verified(update.effective_chat.id,update.effective_user.id) or len(context.args[0])<4:
        token=context.args[0].upper()
        with database.LOCK,database.connect() as c:
            r=c.execute('SELECT token,expires_at FROM verification WHERE chat_id=? AND user_id=?',(update.effective_chat.id,update.effective_user.id)).fetchone()
            if r and r['token']==token and r['expires_at']>int(time.time()):c.execute('UPDATE verification SET verified=1 WHERE chat_id=? AND user_id=?',(update.effective_chat.id,update.effective_user.id));c.commit()
            else:r=None
        if r:
            try:await context.bot.restrict_chat_member(update.effective_chat.id,update.effective_user.id,permissions=ChatPermissions(can_send_messages=True,can_send_audios=True,can_send_documents=True,can_send_photos=True,can_send_videos=True,can_send_video_notes=True,can_send_voice_notes=True,can_send_polls=True,can_send_other_messages=True,can_add_web_page_previews=True))
            except:pass
            await update.message.reply_text('✅ Verification complete.');return
    await update.message.reply_text('❌ Invalid or expired code.')

async def moderation_message(update,context):
    msg=update.effective_message;chat=update.effective_chat;user=update.effective_user
    if not msg or not user or chat.type not in ('group','supergroup','channel'):return
    database.ensure_chat(chat.id,chat.title or '',chat.type);database.upsert_user(chat.id,user)
    if await moderation.actor_is_mod(update,context,user.id) or database.is_whitelisted(chat.id,user.id):return
    row=database.get_chat(chat.id);text=msg.text or msg.caption or '';low=text.lower()
    if chat.type=='channel':
        if row['channel_post_links'] and moderation.URL_RE.search(text):
            try:await msg.delete()
            except:pass
            database.add_log(chat.id,user.id,'channel_delete_link',user.id,'channel post');return
        if row['channel_post_forward'] and msg.forward_origin:
            try:await msg.delete()
            except:pass
            return
    if row['verification'] and not database.is_verified(chat.id,user.id) and chat.type in ('group','supergroup'):
        try:await msg.delete()
        except:pass
        token=moderation.random_token();database.set_verification(chat.id,user.id,token,int(time.time())+row['verify_timeout'])
        try:
            await context.bot.restrict_chat_member(chat.id,user.id,permissions=ChatPermissions(can_send_messages=False))
            await chat.send_message(f'🧩 {moderation.mention(user)}\nVerify with <code>/verify {token}</code>',parse_mode=ParseMode.HTML)
        except:pass
        return
    if row['antilink'] and moderation.URL_RE.search(text):await moderation.punish(context,update,'delete',user.id,'link');return
    if row['antiforward'] and msg.forward_origin:await moderation.punish(context,update,'delete',user.id,'forward');return
    if row['antiflood'] and moderation.flood_state(context,chat.id,user.id,row['flood_window'])>row['flood_limit']:await moderation.punish(context,update,'mute',user.id,'flood');return
    if row['caps_lock'] and len(text)>15 and sum(1 for x in text if x.isalpha())>8 and sum(1 for x in text if x.isupper())/max(1,sum(1 for x in text if x.isalpha()))>.75:await moderation.punish(context,update,'delete',user.id,'caps');return
    if row['mention_lock'] and '@' in text:await moderation.punish(context,update,'delete',user.id,'mentions');return
    checks=[('lock_links',moderation.URL_RE.search(text)),('lock_media',bool(msg.effective_attachment)),('lock_stickers',bool(msg.sticker)),('lock_gifs',bool(msg.animation)),('lock_polls',bool(msg.poll or msg.poll_option_ids)),('lock_files',bool(msg.document)),('lock_voice',bool(msg.voice or msg.video_note)),('lock_video',bool(msg.video)),('lock_audio',bool(msg.audio)),('lock_forwards',bool(msg.forward_origin)),('lock_contacts',bool(msg.contact)),('lock_locations',bool(msg.location)),('lock_bots',bool(msg.via_bot))]
    for key,hit in checks:
        if row[key] and hit:await moderation.punish(context,update,'delete',user.id,key);return
    for f in database.filters(chat.id):
        if f['keyword'] in low:
            if f['delete_message']:
                try:await msg.delete()
                except:pass
            await chat.send_message(f['response'],reply_to_message_id=msg.id);database.add_log(chat.id,user.id,'filter',user.id,f['keyword']);return
    if any(w in low for w in database.words(chat.id)):await moderation.punish(context,update,'delete',user.id,'banned word');return

async def new_member(update,context):
    cm=update.chat_member;chat=cm.chat;u=cm.new_chat_member.user;database.ensure_chat(chat.id,chat.title or '',chat.type);database.upsert_user(chat.id,u);row=database.get_chat(chat.id)
    old,new=cm.old_chat_member.status,cm.new_chat_member.status
    if new in ('member','administrator') and old in ('left','kicked'):
        if row['anti_raid'] and moderation.raid_state(context,chat.id,row['raid_window'])>=row['raid_limit']:
            database.set_raid(chat.id,1)
            try:await context.bot.ban_chat_member(chat.id,u.id)
            except:pass
            return
        if row['welcome'] and chat.type in ('group','supergroup'):
            try:
                m=await chat.send_message(row['welcome_text'] or f'👋 Welcome {moderation.mention(u)}!',parse_mode=ParseMode.HTML)
                if row['clean_welcome']:context.job_queue.run_once(delete_job,row['delete_seconds'],data=(chat.id,m.message_id))
            except:pass
    if new in ('left','kicked') and old in ('member','administrator'):
        if row['goodbye'] and chat.type in ('group','supergroup'):
            try:await chat.send_message(row['goodbye_text'] or f'🚪 {esc(u.first_name)} left.',parse_mode=ParseMode.HTML)
            except:pass
        if row['leave_ban_enabled']:
            targets=[x['linked_chat_id'] for x in database.linked(chat.id,'leave_ban')]
            for target in targets:
                try:await context.bot.ban_chat_member(target,u.id);database.add_log(target,context.bot.id,'leave_ban',u.id,f'source={chat.id}')
                except:pass

async def join_request(update,context):
    r=update.chat_join_request;database.ensure_chat(r.chat.id,r.chat.title or '',r.chat.type);database.add_request(r.chat.id,r.from_user)
    row=database.get_chat(r.chat.id)
    if row['accept_requests']:
        try:await context.bot.approve_chat_join_request(r.chat.id,r.from_user.id);database.remove_request(r.chat.id,r.from_user.id);database.add_log(r.chat.id,context.bot.id,'accept_request',r.from_user.id,'auto')
        except TelegramError:pass

async def scheduled_worker(context):
    for row in database.due_schedules():
        try:await context.bot.send_message(row['chat_id'],row['text']);database.reschedule_or_deactivate(row)
        except:database.reschedule_or_deactivate(row)
async def delete_job(context):
    chat_id,msg_id=context.job.data
    try:await context.bot.delete_message(chat_id,msg_id)
    except:pass

async def admin_cmd(update,context):
    if update.effective_user.id!=config.OWNER_ID and not await moderation.actor_is_mod(update,context):return
    if not context.args or not update.message:await update.message.reply_text('Usage: /admin USER_ID [role]');return
    try:uid=int(context.args[0]);role=context.args[1] if len(context.args)>1 else 'mod';database.add_admin(update.effective_chat.id,uid,role,update.effective_user.id);await update.message.reply_text(f'✅ Added {uid} as {role}.')
    except:await update.message.reply_text('❌ Invalid user ID.')
async def unadmin(update,context):
    if update.effective_user.id!=config.OWNER_ID:return
    if context.args:database.remove_admin(update.effective_chat.id,int(context.args[0]));await update.message.reply_text('✅ Removed.')
async def adminlist(update,context):
    rows=database.list_admins(update.effective_chat.id);await update.message.reply_text('👮\n'+('\n'.join(f"• {x['user_id']} — {x['role']}" for x in rows) or 'No custom admins.'))

def target_from(update,context):
    if update.message and update.message.reply_to_message:return update.message.reply_to_message.from_user
    if context.args:
        try:return type('U',(),{'id':int(context.args[0]),'first_name':str(context.args[0])})()
        except:return None
    return None

async def moderate_cmd(update,context):
    if not await moderation.actor_is_mod(update,context):return
    cmd=update.message.text.split()[0].split('@')[0][1:].lower();target=target_from(update,context)
    if not target:await update.message.reply_text('Reply to a user or give a numeric USER_ID.');return
    cid=update.effective_chat.id
    try:
        if cmd=='ban':await context.bot.ban_chat_member(cid,target.id);msg='banned'
        elif cmd=='unban':await context.bot.unban_chat_member(cid,target.id,only_if_banned=True);msg='unbanned'
        elif cmd=='kick':await context.bot.ban_chat_member(cid,target.id);await context.bot.unban_chat_member(cid,target.id);msg='kicked'
        elif cmd=='mute':
            mins=int(context.args[1]) if len(context.args)>1 and context.args[1].isdigit() else database.get_chat(cid)['mute_minutes'];await context.bot.restrict_chat_member(cid,target.id,permissions=ChatPermissions(can_send_messages=False),until_date=int(time.time())+mins*60);msg=f'muted {mins}m'
        elif cmd=='unmute':await context.bot.restrict_chat_member(cid,target.id,permissions=ChatPermissions(can_send_messages=True,can_send_audios=True,can_send_documents=True,can_send_photos=True,can_send_videos=True,can_send_video_notes=True,can_send_voice_notes=True,can_send_polls=True,can_send_other_messages=True,can_add_web_page_previews=True));msg='unmuted'
        elif cmd=='warn':
            n=database.warn(cid,target.id);limit=database.get_chat(cid)['warn_limit'];msg=f'warning {n}/{limit}';
            if n>=limit:await context.bot.ban_chat_member(cid,target.id);database.clear_warnings(cid,target.id);msg+=' — auto-banned'
        elif cmd=='unwarn':database.clear_warnings(cid,target.id);msg='warnings cleared'
        database.add_log(cid,update.effective_user.id,cmd,target.id,'manual');await update.message.reply_text(f'✅ {msg} — <code>{target.id}</code>',parse_mode=ParseMode.HTML)
    except TelegramError as e:await update.message.reply_text(f'❌ {e}')

async def purge(update,context):
    if not await moderation.actor_is_mod(update,context):return
    n=int(context.args[0]) if context.args and context.args[0].isdigit() else 10;start=update.message.message_id
    deleted=0
    for mid in range(start,max(0,start-n),-1):
        try:await context.bot.delete_message(update.effective_chat.id,mid);deleted+=1
        except:pass
    await update.message.reply_text(f'🧹 Deleted {deleted} messages.')
async def pin(update,context):
    if not await moderation.actor_is_mod(update,context):return
    m=update.message.reply_to_message
    if not m:return await update.message.reply_text('Reply to a message.')
    try:await m.pin();await update.message.reply_text('📌 Pinned.')
    except TelegramError as e:await update.message.reply_text(f'❌ {e}')
async def unpin(update,context):
    if not await moderation.actor_is_mod(update,context):return
    try:await context.bot.unpin_chat_message(update.effective_chat.id);await update.message.reply_text('📍 Unpinned.')
    except TelegramError as e:await update.message.reply_text(f'❌ {e}')
async def slowmode(update,context):
    if not await moderation.actor_is_mod(update,context):return
    sec=int(context.args[0]) if context.args and context.args[0].isdigit() else 0
    try:await context.bot.set_chat_permissions(update.effective_chat.id,ChatPermissions(can_send_messages=True,can_send_audios=True,can_send_documents=True,can_send_photos=True,can_send_videos=True,can_send_video_notes=True,can_send_voice_notes=True,can_send_polls=True,can_send_other_messages=True,can_add_web_page_previews=True));await update.message.reply_text(f'🐢 Slowmode command received: {sec}s (Telegram clients may expose slow mode separately).')
    except TelegramError as e:await update.message.reply_text(f'❌ {e}')
async def lock_cmd(update,context):
    if not await moderation.actor_is_mod(update,context):return
    key=context.args[0].lower() if context.args else 'links';mapping={'links':'lock_links','media':'lock_media','stickers':'lock_stickers','gifs':'lock_gifs','polls':'lock_polls','files':'lock_files','voice':'lock_voice','video':'lock_video','audio':'lock_audio','forwards':'lock_forwards','mentions':'lock_mentions','bots':'lock_bots','commands':'lock_commands'}
    if key not in mapping:return await update.message.reply_text('Usage: /lock links|media|stickers|gifs|polls|files|voice|video|audio|forwards|mentions|bots|commands')
    database.set_setting(update.effective_chat.id,mapping[key],1);await update.message.reply_text(f'🔒 {key} locked.')
async def unlock_cmd(update,context):
    if not await moderation.actor_is_mod(update,context):return
    key=context.args[0].lower() if context.args else 'links';mapping={'links':'lock_links','media':'lock_media','stickers':'lock_stickers','gifs':'lock_gifs','polls':'lock_polls','files':'lock_files','voice':'lock_voice','video':'lock_video','audio':'lock_audio','forwards':'lock_forwards','mentions':'lock_mentions','bots':'lock_bots','commands':'lock_commands'}
    if key in mapping:database.set_setting(update.effective_chat.id,mapping[key],0);await update.message.reply_text(f'🔓 {key} unlocked.')

async def toggle(update,context):
    if not await moderation.actor_is_mod(update,context):return
    cmd=update.message.text.split()[0].split('@')[0][1:].lower();mapping={'welcome':'welcome','goodbye':'goodbye','verify':'verification','verification':'verification','antilink':'antilink','antiflood':'antiflood','antiforward':'antiforward','antispam':'antispam','antiraid':'anti_raid','leaveban':'leave_ban_enabled','acceptreq':'accept_requests','tagging':'tag_enabled'}
    if cmd not in mapping:return
    if not context.args:return await update.message.reply_text(f'Usage: /{cmd} on|off')
    database.set_setting(update.effective_chat.id,mapping[cmd],int(context.args[0].lower() in ('on','yes','1','true')));await update.message.reply_text('✅ Updated.')
async def set_text(update,context):
    if not await moderation.actor_is_mod(update,context):return
    cmd=update.message.text.split()[0].split('@')[0][1:];text=update.message.text.partition(' ')[2].strip();key={'setwelcome':'welcome_text','setgoodbye':'goodbye_text','setrules':'rules'}[cmd]
    if not text:return await update.message.reply_text(f'Usage: /{cmd} TEXT')
    database.set_setting(update.effective_chat.id,key,text);await update.message.reply_text('✅ Saved.')
async def rules(update,context):
    r=database.get_chat(update.effective_chat.id);await update.message.reply_text(r['rules'] or '📜 No rules configured.',parse_mode=ParseMode.HTML)
async def filter_cmd(update,context):
    if not await moderation.actor_is_mod(update,context) or len(context.args)<2:return await update.message.reply_text('Usage: /filter KEYWORD RESPONSE')
    database.add_filter(update.effective_chat.id,context.args[0],' '.join(context.args[1:]));await update.message.reply_text('✅ Filter saved.')
async def delfilter(update,context):
    if not await moderation.actor_is_mod(update,context) or not context.args:return
    await update.message.reply_text('✅ Deleted.' if database.del_filter(update.effective_chat.id,context.args[0]) else '❌ Not found.')
async def badword(update,context):
    if not await moderation.actor_is_mod(update,context) or len(context.args)<2:return await update.message.reply_text('Usage: /badword add|del WORD')
    op,w=context.args[0].lower(),context.args[1];ok=False
    if op=='add':database.add_word(update.effective_chat.id,w,update.effective_user.id);ok=True
    elif op=='del':ok=database.del_word(update.effective_chat.id,w)
    await update.message.reply_text('✅ Done.' if ok else '❌ Not found.')
async def linkleave(update,context):
    if not await moderation.actor_is_mod(update,context) or len(context.args)<2:return await update.message.reply_text('Usage: /linkleave GROUP_ID CHANNEL_ID')
    try:
        group=moderation.parse_target(context.args[0]);channel=moderation.parse_target(context.args[1]);g=await context.bot.get_chat(group);c=await context.bot.get_chat(channel);database.ensure_chat(g.id,g.title or '',g.type);database.ensure_chat(c.id,c.title or '',c.type);database.add_link(c.id,g.id,'leave_ban');database.set_setting(c.id,'leave_ban_enabled',1);await update.message.reply_text(f'🔗 If a user leaves {c.title}, the bot will ban them from {g.title}.')
    except TelegramError as e:await update.message.reply_text(f'❌ {e}')
async def unlinkleave(update,context):
    if not await moderation.actor_is_mod(update,context) or len(context.args)<2:return await update.message.reply_text('Usage: /unlinkleave GROUP_ID CHANNEL_ID')
    try:
        g=moderation.parse_target(context.args[0]);c=moderation.parse_target(context.args[1]);g=await context.bot.get_chat(g);c=await context.bot.get_chat(c);database.del_link(c.id,g.id,'leave_ban');await update.message.reply_text('✅ Leave-ban link removed.')
    except:pass
async def acceptreq(update,context):
    if not await moderation.actor_is_mod(update,context) or not context.args:return await update.message.reply_text('Usage: /acceptreq CHANNEL_LINK_OR_ID')
    try:
        target=await context.bot.get_chat(moderation.parse_target(context.args[0]));database.ensure_chat(target.id,target.title or '',target.type);database.set_setting(target.id,'accept_requests',1);await update.message.reply_text(f'✅ Auto-accept enabled for {target.title}.')
    except TelegramError as e:await update.message.reply_text(f'❌ {e}')
async def stopaccreq(update,context):
    if not await moderation.actor_is_mod(update,context) or not context.args:return await update.message.reply_text('Usage: /stopaccreq CHANNEL_LINK_OR_ID')
    try:
        target=await context.bot.get_chat(moderation.parse_target(context.args[0]));database.ensure_chat(target.id,target.title or '',target.type);database.set_setting(target.id,'accept_requests',0);await update.message.reply_text(f'🛑 Auto-accept disabled for {target.title}.')
    except TelegramError as e:await update.message.reply_text(f'❌ {e}')
async def all_tag(update,context):
    if not await moderation.actor_is_mod(update,context):return
    users=database.known_users(update.effective_chat.id)
    if not users:return await update.message.reply_text('No observed members yet.')
    parts=[];cur='📣 <b>Everyone:</b> '
    for u in users:
        item=f'<a href="tg://user?id={u["user_id"]}">{esc(u["first_name"] or u["username"] or u["user_id"])}</a> '
        if len(cur)+len(item)>3500:parts.append(cur);cur=item
        else:cur+=item
    parts.append(cur)
    for p in parts:await update.message.reply_text(p,parse_mode=ParseMode.HTML);await asyncio.sleep(config.TAG_DELAY)
async def gm(update,context):
    if not await moderation.actor_is_mod(update,context):return
    users=database.known_users(update.effective_chat.id)
    if not users:return await update.message.reply_text('No observed members yet.')
    text='🌅 <b>Good Morning!</b>\n'+' '.join(f'<a href="tg://user?id={u["user_id"]}">{esc(u["first_name"] or u["username"] or u["user_id"])}</a>' for u in users)
    for i in range(0,len(text),3500):await update.message.reply_text(text[i:i+3500],parse_mode=ParseMode.HTML);await asyncio.sleep(config.TAG_DELAY)
async def whitelist(update,context):
    if not await moderation.actor_is_mod(update,context) or not context.args:return await update.message.reply_text('Usage: /whitelist add|del USER_ID [reason]')
    op=context.args[0].lower();uid=int(context.args[1]);
    if op=='add':database.add_whitelist(update.effective_chat.id,uid,' '.join(context.args[2:]),update.effective_user.id);await update.message.reply_text('✅ Whitelisted.')
    elif op=='del':database.del_whitelist(update.effective_chat.id,uid);await update.message.reply_text('✅ Removed from whitelist.')
async def schedule(update,context):
    if not await moderation.actor_is_mod(update,context) or len(context.args)<2:return await update.message.reply_text('Usage: /schedule SECONDS MESSAGE')
    sec=int(context.args[0]);text=' '.join(context.args[1:]);sid=database.add_schedule(update.effective_chat.id,text,int(time.time())+sec);await update.message.reply_text(f'⏰ Scheduled #{sid} in {sec}s.')
async def unschedule(update,context):
    if not await moderation.actor_is_mod(update,context) or not context.args:return
    await update.message.reply_text('✅ Cancelled.' if database.cancel_schedule(update.effective_chat.id,int(context.args[0])) else '❌ Not found.')
async def stats(update,context):
    s=database.stats(update.effective_chat.id);await update.message.reply_text(f"📊 Users {s['users']} | Warnings {s['warnings']} | Filters {s['filters']} | Logs {s['logs']} | Admins {s['admins']}")
async def help_cmd(update,context):
    await update.message.reply_text('🛡️ <b>GroupGuard Ultra</b>\n\n<b>Moderation</b>: /ban /unban /kick /mute /unmute /warn /unwarn /purge /pin /unpin /slowmode /lock /unlock\n<b>Protection</b>: /filter /delfilter /badword /whitelist\n<b>Members</b>: /welcome /goodbye /verify /setwelcome /setgoodbye /setrules /rules /all /gm\n<b>Channel</b>: /acceptreq CHAT /stopaccreq CHAT /linkleave GROUP CHANNEL /unlinkleave GROUP CHANNEL\n<b>Automation</b>: /schedule SECONDS TEXT /unschedule ID\n<b>Panel</b>: /setup /panel /settings /stats /admin /unadmin /adminlist',parse_mode=ParseMode.HTML)

def register(app):
    for c,f in {'start':start,'help':help_cmd,'setup':setup,'panel':panel,'settings':panel,'verify':verification_cmd,'admin':admin_cmd,'unadmin':unadmin,'adminlist':adminlist,'purge':purge,'pin':pin,'unpin':unpin,'slowmode':slowmode,'lock':lock_cmd,'unlock':unlock_cmd,'filter':filter_cmd,'delfilter':delfilter,'badword':badword,'linkleave':linkleave,'unlinkleave':unlinkleave,'acceptreq':acceptreq,'stopaccreq':stopaccreq,'all':all_tag,'gm':gm,'whitelist':whitelist,'schedule':schedule,'unschedule':unschedule,'stats':stats,'rules':rules}.items():app.add_handler(CommandHandler(c,f))
    for c in ('ban','unban','kick','mute','unmute','warn','unwarn'):app.add_handler(CommandHandler(c,moderate_cmd))
    for c in ('welcome','goodbye','verification','verifyon','antilink','antiflood','antiforward','antispam','antiraid','leaveban','tagging'):app.add_handler(CommandHandler(c,toggle))
    for c in ('setwelcome','setgoodbye','setrules'):app.add_handler(CommandHandler(c,set_text))
    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(ChatMemberHandler(new_member,ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(ChatJoinRequestHandler(join_request))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND,moderation_message),group=10)
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND,remember),group=20)
    app.job_queue.run_repeating(scheduled_worker,interval=5,first=5)

