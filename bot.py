#!/usr/bin/env python3
import logging
import random
import string
import json
import re
import time
from collections import defaultdict, deque
import os
import asyncio
from datetime import datetime
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from telegram.request import HTTPXRequest

# ================= CONFIG ================= #
TOKEN = os.getenv("BOT_TOKEN", "8471761138:AAFiaG6FiHZT0v_VjpNK_MC4q2NIr1siWVM")
BOT_USERNAME = "HuhVotingBot"
OWNER_ID = 8936019952

# ================= PREMIUM EMOJIS ================= #
EMOJI_VOTE = "5267095979097610740"
EMOJI_JOIN = "6237668294896131350"
EMOJI_CANCEL = "6240245571626475799"
EMOJI_MAIN_MENU = "6240245571626475799"
EMOJI_BACK = "6217402478825049695"
EMOJI_CREATE = "5208891329626521299"
EMOJI_CONNECT = "5244710862953941180"
EMOJI_MANAGE = "6237621548472081271"
EMOJI_ADD_VOTES = "6240003971126139705"
EMOJI_REMOVE_VOTES = "6240003971126139705"
EMOJI_LEADERBOARD = "6240027791014765668"
EMOJI_END_GIVEAWAY = "6240085923397114865"
EMOJI_ADMIN = "6237595159329113605"
EMOJI_BROADCAST = "6237668294896131350"
EMOJI_STATS = "6239790794719370356"
EMOJI_SETTINGS = "6237621548472081271"
EMOJI_USERS = "6237867138997034625"
EMOJI_BACKUP = "6237900592497302202"
EMOJI_CLEAR = "6240152061598504832"
EMOJI_CHANNEL = "6237510794150419802"
EMOJI_NOTIFICATION = "6240073270423462835"
EMOJI_CONFIRM = "6239815031219820750"
EMOJI_REFRESH = "6240085923397114865"
EMOJI_WELCOME = "6332080283176672910"
EMOJI_FIRE = "6334449730734529256"
EMOJI_ARROW = "6332591195306334733"
EMOJI_CHART = "6332186798365612896"
EMOJI_HEART = "6237558987978447573"
EMOJI_ROCKET = "5188481279963715781"
EMOJI_CROWN = "6332246180583447893"
EMOJI_ERROR = "6334723470475139278"
EMOJI_ENDED = "6237572882197650867"
EMOJI_STAR = "6239815031219820750"
EMOJI_ID = "6237547619200014867"
EMOJI_GIFT = "6239894475229895983"
EMOJI_WINE = "6237510794150419802"
EMOJI_SMILE = "6237867138997034625"
EMOJI_LOVE = "6334437167955188087"
EMOJI_LIGHTNING = "6240073270423462835"
EMOJI_POINTER = "6237732706520668707"
EMOJI_ALERT = "6240152061598504832"
EMOJI_CLOWN = "6237900592497302202"
EMOJI_SEARCH = "6239790794719370356"
EMOJI_SPEAKER = "5217968773071401144"
EMOJI_LINK = "5289511602393984968"
EMOJI_CONFETTI = "6240085923397114865"
EMOJI_LOCATION = "6240101054566897479"
EMOJI_RIGHT = "6240295371772271503"
EMOJI_DIAMOND = "6240003971126139705"
EMOJI_CALENDAR = "6240027791014765668"
EMOJI_WINNER = "6332435498446888848"
EMOJI_MONEY_BAG = "6332246180583447893"
EMOJI_CELEBRATE = "6237621707385871360"
EMOJI_INBOX = "6237973405077871246"
EMOJI_LOCK = "6332490478323243268"
EMOJI_SHIELD = "6237595159329113605"

# ================= COLOR STYLES ================= #
BUTTON_STYLE_PRIMARY = "primary"
BUTTON_STYLE_SUCCESS = "success"
BUTTON_STYLE_DANGER = "danger"

# ================= LOGGING ================= #
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================= JSON DATABASE ================= #
DATA_FILE = "bot_data.json"

def load_data():
    global giveaways, all_users, channel_history
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                giveaways = data.get("giveaways", {})
                all_users = data.get("all_users", {})
                channel_history = data.get("channel_history", {})
                # Restore runtime-only sets and integer user IDs after JSON load.
                for _gid, _g in giveaways.items():
                    _g["users"] = {int(k): v for k, v in _g.get("users", {}).items()}
                    _g["vote_counts"] = {int(k): int(v) for k, v in _g.get("vote_counts", {}).items()}
                    _g["voted_users"] = {int(k): set(v) for k, v in _g.get("voted_users", {}).items()}
                logger.info(f"Loaded: {len(giveaways)} giveaways, {len(all_users)} users")
        else:
            giveaways = {}
            all_users = {}
            channel_history = {}
    except Exception as e:
        logger.error(f"Error loading: {e}")
        giveaways = {}
        all_users = {}
        channel_history = {}

def save_data():
    try:
        data = {
            "giveaways": giveaways,
            "all_users": all_users,
            "channel_history": channel_history,
            "last_saved": datetime.now().isoformat()
        }
        def json_safe(obj):
            if isinstance(obj, set):
                return list(obj)
            if isinstance(obj, dict):
                return {str(k): json_safe(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [json_safe(v) for v in obj]
            return obj
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(json_safe(data), f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error saving: {e}")

def save_user(user_id, username, first_name, last_name=None, source=None):
    if str(user_id) not in all_users:
        all_users[str(user_id)] = {
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "joined_at": datetime.now().isoformat(),
            "last_active": datetime.now().isoformat(),
            "source": source or "unknown",
            "total_votes_given": 0,
            "total_giveaways_joined": 0
        }
        save_data()
    else:
        all_users[str(user_id)]["last_active"] = datetime.now().isoformat()
        if username:
            all_users[str(user_id)]["username"] = username
        save_data()
    return True

def update_user_stats(user_id, action):
    user_id_str = str(user_id)
    if user_id_str in all_users:
        if action == "vote":
            all_users[user_id_str]["total_votes_given"] = all_users[user_id_str].get("total_votes_given", 0) + 1
        elif action == "join":
            all_users[user_id_str]["total_giveaways_joined"] = all_users[user_id_str].get("total_giveaways_joined", 0) + 1
        save_data()

def update_channel_history(channel_identifier, channel_display, channel_id, user_id, user_name, action, giveaway_id=None):
    channel_key = str(channel_identifier)
    
    if channel_key not in channel_history:
        channel_history[channel_key] = {
            "channel_identifier": channel_identifier,
            "channel_display": channel_display,
            "channel_id": channel_id,
            "type": "private" if str(channel_id).startswith('-100') or str(channel_id).startswith('-') else "public",
            "total_giveaways": 0,
            "giveaways": [],
            "created_by": user_id,
            "created_by_name": user_name,
            "first_created": datetime.now().isoformat()
        }
    
    if action == "create":
        channel_history[channel_key]["total_giveaways"] += 1
        channel_history[channel_key]["giveaways"].append({
            "giveaway_id": giveaway_id,
            "created_at": datetime.now().isoformat(),
            "status": "active",
            "participants": 0
        })
        channel_history[channel_key]["last_giveaway"] = datetime.now().isoformat()
    elif action == "end" and giveaway_id:
        for g in channel_history[channel_key]["giveaways"]:
            if g.get("giveaway_id") == giveaway_id:
                g["status"] = "ended"
                g["ended_at"] = datetime.now().isoformat()
                break
    
    save_data()

# ================= INITIALIZE ================= #
giveaways = {}
all_users = {}
user_sessions = {}
admin_sessions = {}
channel_history = {}
vote_messages = {}

# ================= SECURITY / ANTI-ABUSE ================= #
SECURITY_ENABLED = True
AUTO_BAN_ON_ABUSE = True
PROFILE_ABUSE_CHECK_ENABLED = True
AUTO_BAN_ON_PROFILE_ABUSE = True

# Vote anti-abuse thresholds.
VOTE_WINDOW_SECONDS = 30
MAX_VOTES_IN_WINDOW = 8
MAX_TARGETS_IN_WINDOW = 6
SUSPICIOUS_SCORE_LIMIT = 3

# Common abusive/profane terms. Matching is normalized and supports simple obfuscation.
ABUSE_WORDS = {
    "fuck", "fucking", "fucker", "motherfucker", "shit", "bitch", "bastard",
    "asshole", "dick", "piss", "cunt", "whore", "slut", "idiot", "stupid",
    "gaand", "gand", "chutiya", "chutiye", "madarchod", "madharchod",
    "bhosdike", "bhosdi", "bc", "mc", "behenchod", "bhenchod", "randi",
    "harami", "kamina", "kamine", "kutte", "kutta"
}

# Terms indicating explicit/adult content.
ADULT_WORDS = {
    "porn", "porno", "pornography", "xxx", "nsfw", "nudes", "nude",
    "sexcam", "sexvideo", "onlyfans"
}

banned_users = set()
suspicious_scores = defaultdict(int)
vote_activity = defaultdict(deque)


def normalize_security_text(text):
    text = (text or "").lower()
    replacements = {
        "@": "a", "4": "a", "3": "e", "1": "i", "!": "i",
        "0": "o", "$": "s", "5": "s"
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def contains_banned_content(text):
    normalized = normalize_security_text(text)
    words = set(normalized.split())
    compact = normalized.replace(" ", "")

    if words & ABUSE_WORDS:
        return True, "abusive/profane language"
    if words & ADULT_WORDS:
        return True, "18+ / adult content"

    # Catch simple letter/symbol/space obfuscation for longer terms.
    for term in (ABUSE_WORDS | ADULT_WORDS):
        if len(term) >= 5 and term in compact:
            return True, "abusive/profane or prohibited content"

    return False, ""


def check_profile_for_abuse(user):
    """Check username and display-name fields before allowing bot access."""
    if not PROFILE_ABUSE_CHECK_ENABLED or not user:
        return False, ""

    profile_fields = (
        ("username", user.username or ""),
        ("first name", user.first_name or ""),
        ("last name", user.last_name or ""),
    )

    for field_name, value in profile_fields:
        if value:
            found, _reason = contains_banned_content(value)
            if found:
                return True, f"{field_name} contains a banned word"

    return False, ""


def is_security_banned(user_id):
    return int(user_id) in banned_users


def security_ban_user(user_id, reason):
    uid = int(user_id)
    banned_users.add(uid)
    all_users.setdefault(str(uid), {})
    all_users[str(uid)]["security_banned"] = True
    all_users[str(uid)]["security_ban_reason"] = reason
    all_users[str(uid)]["security_banned_at"] = datetime.now().isoformat()
    save_data()


def register_vote_activity(voter_id, target_id):
    now = time.monotonic()
    q = vote_activity[int(voter_id)]
    q.append((now, int(target_id)))
    while q and now - q[0][0] > VOTE_WINDOW_SECONDS:
        q.popleft()
    votes = len(q)
    targets = len({target for _, target in q})
    suspicious = votes > MAX_VOTES_IN_WINDOW or targets > MAX_TARGETS_IN_WINDOW
    return suspicious, votes, targets


def load_security_state():
    for uid, data in all_users.items():
        if data.get("security_banned"):
            banned_users.add(int(uid))

load_data()
load_security_state()

request = HTTPXRequest(connect_timeout=30, read_timeout=30, write_timeout=30, pool_timeout=30)

def premium_button(text, callback_data=None, url=None, emoji_id=None, style=None):
    if url:
        return InlineKeyboardButton(text=text, url=url, icon_custom_emoji_id=emoji_id, style=style)
    return InlineKeyboardButton(text=text, callback_data=callback_data, icon_custom_emoji_id=emoji_id, style=style)

def is_owner(user_id):
    return user_id == OWNER_ID

async def send_notification_to_owner(context, title, message):
    try:
        await context.bot.send_message(
            chat_id=OWNER_ID,
            text=f"<b>{title}</b>\n\n{message}",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to send: {e}")

async def update_vote_button_in_channel(context, giveaway_id, user_id, new_votes):
    try:
        giveaway = giveaways.get(giveaway_id)
        if not giveaway:
            return False
        
        if giveaway_id in vote_messages and user_id in vote_messages[giveaway_id]:
            message_id = vote_messages[giveaway_id][user_id]
            try:
                new_keyboard = [[
                    premium_button(f"Vote - {new_votes}", callback_data=f"vote_{giveaway_id}_{user_id}", emoji_id=EMOJI_VOTE, style=BUTTON_STYLE_SUCCESS)
                ]]
                await context.bot.edit_message_reply_markup(
                    chat_id=giveaway['channel_id'],
                    message_id=message_id,
                    reply_markup=InlineKeyboardMarkup(new_keyboard)
                )
                return True
            except Exception as e:
                logger.error(f"Failed to edit: {e}")
                return False
        return False
    except Exception as e:
        logger.error(f"Error updating: {e}")
        return False

# ================= START COMMAND ================= #
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if SECURITY_ENABLED and user and user.id != OWNER_ID:
        if is_security_banned(user.id):
            await update.message.reply_text("🚫 You are banned from using this bot.")
            return

        profile_found, profile_reason = check_profile_for_abuse(user)
        if profile_found and AUTO_BAN_ON_PROFILE_ABUSE:
            security_ban_user(user.id, profile_reason)
            await send_notification_to_owner(
                context,
                "🚨 PROFILE SECURITY AUTO-BAN",
                f"👤 {user.full_name or 'Unknown'}\\n"
                f"🔹 Username: @{user.username or 'N/A'}\\n"
                f"🆔 <code>{user.id}</code>\\n"
                f"⚠️ Reason: {profile_reason}"
            )
            await update.message.reply_text(
                "🚫 Your name/username contains a banned word. You have been banned."
            )
            return

    save_user(user.id, user.username, user.first_name, user.last_name, source="/start")
    
    if context.args and len(context.args) > 0:
        giveaway_id = context.args[0]
        await handle_giveaway_link(update, giveaway_id)
        return

    keyboard = [
        [premium_button("CONNECT", url=f"https://t.me/{BOT_USERNAME}?startchannel=true&admin=post_messages", emoji_id=EMOJI_CONNECT, style=BUTTON_STYLE_SUCCESS)],
        [premium_button("CREATE", callback_data="create_giveaway", emoji_id=EMOJI_CREATE, style=BUTTON_STYLE_PRIMARY),
         premium_button("MANAGE", callback_data="my_giveaways", emoji_id=EMOJI_MANAGE, style=BUTTON_STYLE_PRIMARY)]
    ]

    welcome_text = (
        f"<b><tg-emoji emoji-id='{EMOJI_WELCOME}'>🙂</tg-emoji> WELCOME TO HUH VOTE GIVEAWAY BOT</b>\n\n"
        f"<i><tg-emoji emoji-id='{EMOJI_FIRE}'>☄️</tg-emoji> Create Powerful Vote Giveaways</i>\n"
        f"<i><tg-emoji emoji-id='{EMOJI_ARROW}'>🔜</tg-emoji> Real Time Vote System</i>\n"
        f"<i><tg-emoji emoji-id='{EMOJI_CHART}'>📈</tg-emoji> Advanced Management Tools</i>\n"
        f"<i><tg-emoji emoji-id='{EMOJI_HEART}'>❤️‍🔥</tg-emoji> Leaderboard & Analytics</i>\n\n"
        f"<b><tg-emoji emoji-id='{EMOJI_ROCKET}'>🚀</tg-emoji> START CREATING NOW!</b>"
    )

    await update.message.reply_text(text=welcome_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_giveaway_link(update: Update, giveaway_id: str):
    if giveaway_id not in giveaways:
        await update.message.reply_text(
            f"<tg-emoji emoji-id='{EMOJI_ERROR}'>❌</tg-emoji> <b>INVALID LINK</b>",
            parse_mode="HTML"
        )
        return

    giveaway = giveaways[giveaway_id]
    user_id = update.effective_user.id
    
    if giveaway.get("ended", False):
        await update.message.reply_text(
            f"<tg-emoji emoji-id='{EMOJI_ENDED}'>❌</tg-emoji> <b>GIVEAWAY ENDED</b>",
            parse_mode="HTML"
        )
        return

    if user_id in giveaway.get("users", {}):
        await update.message.reply_text(
            f"<tg-emoji emoji-id='{EMOJI_STAR}'>🌟</tg-emoji> <b>ALREADY PARTICIPATED!</b>\n\n"
            f"<tg-emoji emoji-id='{EMOJI_ID}'>💌</tg-emoji> <b>Your ID:</b> <code>{user_id}</code>",
            parse_mode="HTML"
        )
        return

    # Check if user is a member of the channel
    channel_id = giveaway.get('channel_id')
    is_member = False
    
    if channel_id:
        try:
            member = await context.bot.get_chat_member(chat_id=channel_id, user_id=user_id)
            if member.status in ['member', 'administrator', 'creator']:
                is_member = True
            elif member.status == 'restricted' and getattr(member, 'is_member', False):
                is_member = True
        except Exception as e:
            logger.error(f"Error checking membership: {e}")
    
    if is_member:
        # User is a member - show join button
        keyboard = [[
            premium_button("JOIN GIVEAWAY", callback_data=f"join_{giveaway_id}", emoji_id=EMOJI_JOIN, style=BUTTON_STYLE_SUCCESS)
        ]]
        channel_display = giveaway.get("channel_display", giveaway.get("channel", "Channel"))
        
        await update.message.reply_text(
            f"<tg-emoji emoji-id='{EMOJI_GIFT}'>🎁</tg-emoji> <b>EXCLUSIVE GIVEAWAY</b>\n\n"
            f"<tg-emoji emoji-id='{EMOJI_WINE}'>🍷</tg-emoji> <b>Hosted By:</b> {channel_display}\n"
            f"<tg-emoji emoji-id='{EMOJI_SMILE}'>😎</tg-emoji> <b>Participants:</b> {len(giveaway['users'])}\n\n"
            f"<tg-emoji emoji-id='{EMOJI_CONFIRM}'>✅</tg-emoji> <b>You are a member of the channel!</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        # User is NOT a member - show channel join options
        channel_display = giveaway.get("channel_display", giveaway.get("channel", "Channel"))
        channel_identifier = giveaway.get("channel", "")
        
        # Get channel link
        channel_link = None
        try:
            if channel_identifier.startswith('@'):
                channel_link = f"https://t.me/{channel_identifier[1:]}"
            else:
                # Try to get invite link or use chat link
                chat = await context.bot.get_chat(channel_id)
                if chat.invite_link:
                    channel_link = chat.invite_link
                else:
                    channel_link = f"https://t.me/{BOT_USERNAME}?startchannel=true"
        except:
            channel_link = f"https://t.me/{BOT_USERNAME}?startchannel=true"
        
        keyboard = [
            [premium_button("JOIN CHANNEL", url=channel_link, emoji_id=EMOJI_CHANNEL, style=BUTTON_STYLE_SUCCESS)],
            [premium_button("TRY AGAIN", callback_data=f"retry_join_{giveaway_id}", emoji_id=EMOJI_REFRESH, style=BUTTON_STYLE_PRIMARY)]
        ]
        
        await update.message.reply_text(
            f"<tg-emoji emoji-id='{EMOJI_ALERT}'>⚠️</tg-emoji> <b>CHANNEL MEMBERSHIP REQUIRED</b>\n\n"
            f"<tg-emoji emoji-id='{EMOJI_GIFT}'>🎁</tg-emoji> <b>Giveaway Host:</b> {channel_display}\n\n"
            f"<i>You need to join the channel first to participate in this giveaway!</i>\n\n"
            f"<b>Steps to join:</b>\n"
            f"1️⃣ Click <b>JOIN CHANNEL</b> below\n"
            f"2️⃣ Join the channel\n"
            f"3️⃣ Click <b>TRY AGAIN</b> to verify membership",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def retry_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle retry join callback - checks membership again and opens the join link"""
    query = update.callback_query
    await query.answer()
    
    giveaway_id = query.data.split("_")[2]
    user_id = query.from_user.id
    
    if giveaway_id not in giveaways:
        await query.edit_message_text(
            f"<tg-emoji emoji-id='{EMOJI_ERROR}'>❌</tg-emoji> <b>Giveaway not found!</b>",
            parse_mode="HTML"
        )
        return
    
    giveaway = giveaways[giveaway_id]
    channel_id = giveaway.get('channel_id')
    channel_display = giveaway.get("channel_display", giveaway.get("channel", "Channel"))
    
    # Check membership again
    is_member = False
    if channel_id:
        try:
            member = await context.bot.get_chat_member(chat_id=channel_id, user_id=user_id)
            if member.status in ['member', 'administrator', 'creator']:
                is_member = True
            elif member.status == 'restricted' and getattr(member, 'is_member', False):
                is_member = True
        except Exception as e:
            logger.error(f"Error checking membership on retry: {e}")
    
    if is_member:
        # Now user is a member - show join button
        keyboard = [[
            premium_button("JOIN GIVEAWAY", callback_data=f"join_{giveaway_id}", emoji_id=EMOJI_JOIN, style=BUTTON_STYLE_SUCCESS)
        ]]
        
        await query.edit_message_text(
            f"<tg-emoji emoji-id='{EMOJI_GIFT}'>🎁</tg-emoji> <b>EXCLUSIVE GIVEAWAY</b>\n\n"
            f"<tg-emoji emoji-id='{EMOJI_WINE}'>🍷</tg-emoji> <b>Hosted By:</b> {channel_display}\n"
            f"<tg-emoji emoji-id='{EMOJI_SMILE}'>😎</tg-emoji> <b>Participants:</b> {len(giveaway['users'])}\n\n"
            f"<tg-emoji emoji-id='{EMOJI_CONFIRM}'>✅</tg-emoji> <b>Membership verified! You can now join.</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        # Still not a member - show the channel join options again
        channel_identifier = giveaway.get("channel", "")
        channel_link = None
        
        try:
            if channel_identifier.startswith('@'):
                channel_link = f"https://t.me/{channel_identifier[1:]}"
            else:
                chat = await context.bot.get_chat(channel_id)
                if chat.invite_link:
                    channel_link = chat.invite_link
                else:
                    channel_link = f"https://t.me/{BOT_USERNAME}?startchannel=true"
        except:
            channel_link = f"https://t.me/{BOT_USERNAME}?startchannel=true"
        
        keyboard = [
            [premium_button("JOIN CHANNEL", url=channel_link, emoji_id=EMOJI_CHANNEL, style=BUTTON_STYLE_SUCCESS)],
            [premium_button("TRY AGAIN", callback_data=f"retry_join_{giveaway_id}", emoji_id=EMOJI_REFRESH, style=BUTTON_STYLE_PRIMARY)]
        ]
        
        await query.edit_message_text(
            f"<tg-emoji emoji-id='{EMOJI_ALERT}'>⚠️</tg-emoji> <b>STILL NOT A MEMBER</b>\n\n"
            f"<tg-emoji emoji-id='{EMOJI_GIFT}'>🎁</tg-emoji> <b>Giveaway Host:</b> {channel_display}\n\n"
            f"<i>Please join the channel first!</i>\n\n"
            f"<b>Steps to join:</b>\n"
            f"1️⃣ Click <b>JOIN CHANNEL</b> below\n"
            f"2️⃣ Join the channel\n"
            f"3️⃣ Click <b>TRY AGAIN</b> to verify membership",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# ================= CREATE GIVEAWAY ================= #
async def create_giveaway_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_sessions[user_id] = {"step": "waiting_channel"}
    keyboard = [[premium_button("CANCEL", callback_data="cancel_creation", emoji_id=EMOJI_CANCEL, style=BUTTON_STYLE_DANGER)]]
    await query.edit_message_text(
        text=f"<b><tg-emoji emoji-id='{EMOJI_LIGHTNING}'>⚡</tg-emoji> CREATE GIVEAWAY</b>\n\n"
             f"<i><tg-emoji emoji-id='{EMOJI_POINTER}'>👈</tg-emoji> Send your channel information:</i>\n\n"
             f"<b>Public:</b> <code>@username</code>\n<b>Private:</b> <code>-1001234567890</code>",
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def cancel_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id in user_sessions:
        del user_sessions[user_id]
    
    keyboard = [
        [premium_button("CONNECT", url=f"https://t.me/{BOT_USERNAME}?startchannel=true&admin=post_messages", emoji_id=EMOJI_CONNECT, style=BUTTON_STYLE_SUCCESS)],
        [premium_button("CREATE", callback_data="create_giveaway", emoji_id=EMOJI_CREATE, style=BUTTON_STYLE_PRIMARY),
         premium_button("MANAGE", callback_data="my_giveaways", emoji_id=EMOJI_MANAGE, style=BUTTON_STYLE_PRIMARY)]
    ]
    
    await query.edit_message_text(
        text="✅ <b>Cancelled!</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def process_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    
    if user_id not in user_sessions or user_sessions[user_id].get("step") != "waiting_channel":
        return
    
    channel_input = update.message.text.strip()
    loading_msg = await update.message.reply_text(
        f"<tg-emoji emoji-id='{EMOJI_LIGHTNING}'>⚡</tg-emoji> <b>Verifying...</b>",
        parse_mode="HTML"
    )
    
    try:
        if channel_input.startswith('@'):
            chat = await context.bot.get_chat(chat_id=channel_input)
            channel_info = {"identifier": channel_input, "display_name": channel_input, "chat_id": chat.id, "type": "public"}
        else:
            chat = await context.bot.get_chat(chat_id=int(channel_input))
            channel_info = {"identifier": str(channel_input), "display_name": chat.title or f"Channel {channel_input}", "chat_id": chat.id, "type": "private"}
    except Exception as e:
        await loading_msg.delete()
        error = str(e).lower()
        if "bot is not a member" in error or "not enough rights" in error:
            await update.message.reply_text(
                f"🤖 <b>Bot is not admin!</b>\n\nPlease add @{BOT_USERNAME} as an admin in the channel first.",
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text(
                f"<tg-emoji emoji-id='{EMOJI_ERROR}'>❌</tg-emoji> <b>Invalid channel!</b>",
                parse_mode="HTML"
            )
        del user_sessions[user_id]
        return
    
    for gid, gdata in giveaways.items():
        if gdata.get("channel") == channel_info["identifier"] and not gdata.get("ended", False):
            await loading_msg.delete()
            existing_link = f"https://t.me/{BOT_USERNAME}?start={gid}"
            await update.message.reply_text(
                f"<tg-emoji emoji-id='{EMOJI_ALERT}'>🚨</tg-emoji> <b>GIVEAWAY ALREADY ACTIVE!</b>\n\n"
                f"<b>Channel:</b> {channel_info['display_name']}\n\n"
                f"<b>Active Link:</b>\n<code>{existing_link}</code>",
                parse_mode="HTML"
            )
            del user_sessions[user_id]
            return
    
    try:
        test_msg = await context.bot.send_message(chat_id=channel_info["chat_id"], text="✅ Bot connected!")
        await test_msg.delete()
    except:
        await loading_msg.delete()
        await update.message.reply_text(
            f"🤖 <b>Bot is not admin!</b>\n\nPlease add @{BOT_USERNAME} as an admin in the channel first.",
            parse_mode="HTML"
        )
        del user_sessions[user_id]
        return
    
    giveaway_id = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    link = f"https://t.me/{BOT_USERNAME}?start={giveaway_id}"
    
    giveaways[giveaway_id] = {
        "channel": channel_info["identifier"], "channel_display": channel_info["display_name"],
        "channel_id": channel_info["chat_id"], "users": {}, "vote_counts": {}, "voted_users": {},
        "creator": user_id, "creator_name": user_name, "ended": False, "created_at": datetime.now().isoformat()
    }
    
    update_channel_history(
        channel_identifier=channel_info["identifier"],
        channel_display=channel_info["display_name"],
        channel_id=channel_info["chat_id"],
        user_id=user_id,
        user_name=user_name,
        action="create",
        giveaway_id=giveaway_id
    )
    
    vote_messages[giveaway_id] = {}
    save_data()
    
    if user_id != OWNER_ID:
        await send_notification_to_owner(context, "🔔 NEW GIVEAWAY CREATED!",
            f"👤 {user_name}\n🆔 <code>{user_id}</code>\n📢 {channel_info['display_name']}\n🔗 <code>{link}</code>")
    
    try:
        await context.bot.send_message(
            chat_id=channel_info["chat_id"],
            text=f"<b><tg-emoji emoji-id='{EMOJI_CONFETTI}'>🎉</tg-emoji> NEW GIVEAWAY STARTED!</b>\n\n"
                 f"<b><tg-emoji emoji-id='{EMOJI_RIGHT}'>➡️</tg-emoji> JOIN HERE:</b>\n{link}",
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    except: pass
    
    await loading_msg.delete()
    
    success_text = (
        f"<b><tg-emoji emoji-id='{EMOJI_CLOWN}'>✅</tg-emoji> GIVEAWAY CREATED!</b>\n\n"
        f"<b><tg-emoji emoji-id='{EMOJI_SEARCH}'>🔍</tg-emoji> ID:</b> <code>{giveaway_id}</code>\n"
        f"<b><tg-emoji emoji-id='{EMOJI_SPEAKER}'>📢</tg-emoji> Channel:</b> {channel_info['display_name']}\n\n"
        f"<b><tg-emoji emoji-id='{EMOJI_LINK}'>🔗</tg-emoji> LINK:</b>\n<code>{link}</code>"
    )
    
    keyboard = [[
        premium_button("MANAGE", callback_data=f"manage_{giveaway_id}", emoji_id=EMOJI_MANAGE, style=BUTTON_STYLE_PRIMARY),
        premium_button("MAIN MENU", callback_data="main_menu", emoji_id=EMOJI_MAIN_MENU, style=BUTTON_STYLE_PRIMARY)
    ]]
    
    await update.message.reply_text(success_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    del user_sessions[user_id]

# ================= MANAGE ================= #
async def my_giveaways(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    text = f"<b><tg-emoji emoji-id='{EMOJI_CROWN}'>💰</tg-emoji> YOUR GIVEAWAYS</b>\n\n"
    keyboard = []
    found = False
    
    for gid, gdata in giveaways.items():
        if gdata.get("creator") == user_id and not gdata.get("ended", False):
            found = True
            keyboard.append([premium_button(
                text=f"📢 {gdata.get('channel_display', gdata.get('channel'))}",
                callback_data=f"manage_{gid}",
                emoji_id=EMOJI_MANAGE,
                style=BUTTON_STYLE_PRIMARY
            )])
    
    if not found:
        text = f"<tg-emoji emoji-id='{EMOJI_ERROR}'>❌</tg-emoji> <b>No active giveaways!</b>"
        keyboard.append([premium_button("CREATE NEW", callback_data="create_giveaway", emoji_id=EMOJI_CREATE, style=BUTTON_STYLE_PRIMARY)])
    
    keyboard.append([premium_button("MAIN MENU", callback_data="main_menu", emoji_id=EMOJI_MAIN_MENU, style=BUTTON_STYLE_PRIMARY)])
    
    await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def manage_giveaway(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    giveaway_id = query.data.split("_")[1]
    if giveaway_id not in giveaways:
        await query.edit_message_text(f"<tg-emoji emoji-id='{EMOJI_ERROR}'>❌</tg-emoji> Not found!", parse_mode="HTML")
        return
    
    giveaway = giveaways[giveaway_id]
    status = "🟢 ACTIVE" if not giveaway.get("ended") else "🔴 ENDED"
    
    keyboard = [
        [
            premium_button("ADD VOTES", callback_data=f"addvotes_{giveaway_id}", emoji_id=EMOJI_ADD_VOTES, style=BUTTON_STYLE_PRIMARY),
            premium_button("REMOVE VOTES", callback_data=f"removevotes_{giveaway_id}", emoji_id=EMOJI_REMOVE_VOTES, style=BUTTON_STYLE_DANGER)
        ],
        [
            premium_button("LEADERBOARD", callback_data=f"leaderboard_{giveaway_id}", emoji_id=EMOJI_LEADERBOARD, style=BUTTON_STYLE_PRIMARY)
        ],
        [
            premium_button("END GIVEAWAY", callback_data=f"endgiveaway_{giveaway_id}", emoji_id=EMOJI_END_GIVEAWAY, style=BUTTON_STYLE_DANGER)
        ],
        [
            premium_button("BACK", callback_data="my_giveaways", emoji_id=EMOJI_BACK, style=BUTTON_STYLE_PRIMARY)
        ]
    ]
    
    await query.edit_message_text(
        text=f"<b><tg-emoji emoji-id='{EMOJI_ARROW}'>➡️</tg-emoji> MANAGEMENT PANEL</b>\n\n"
             f"<b>Status:</b> {status}\n"
             f"<b>Channel:</b> {giveaway.get('channel_display', giveaway.get('channel'))}\n"
             f"<b>Joined:</b> {len(giveaway.get('users', {}))}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ================= VOTE MANAGEMENT ================= #
async def add_votes_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    giveaway_id = query.data.split("_")[1]
    context.user_data["vote_giveaway"] = giveaway_id
    context.user_data["vote_action"] = "add"
    await query.edit_message_text(
        text=f"<b><tg-emoji emoji-id='{EMOJI_DIAMOND}'>💎</tg-emoji> ADD VOTES</b>\n\nSend: <code>USER_ID VOTES</code>\nExample: <code>12345678 10</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[premium_button("BACK", callback_data=f"manage_{giveaway_id}", emoji_id=EMOJI_BACK, style=BUTTON_STYLE_PRIMARY)]])
    )

async def remove_votes_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    giveaway_id = query.data.split("_")[1]
    context.user_data["vote_giveaway"] = giveaway_id
    context.user_data["vote_action"] = "remove"
    await query.edit_message_text(
        text=f"<b><tg-emoji emoji-id='{EMOJI_DIAMOND}'>💎</tg-emoji> REMOVE VOTES</b>\n\nSend: <code>USER_ID VOTES</code>\nExample: <code>12345678 5</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[premium_button("BACK", callback_data=f"manage_{giveaway_id}", emoji_id=EMOJI_BACK, style=BUTTON_STYLE_PRIMARY)]])
    )

async def process_vote_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    giveaway_id = context.user_data.get("vote_giveaway")
    action = context.user_data.get("vote_action")
    if not giveaway_id or giveaway_id not in giveaways:
        return
    
    try:
        parts = update.message.text.strip().split()
        target_uid = int(parts[0])
        votes = int(parts[1])
    except:
        await update.message.reply_text(f"<tg-emoji emoji-id='{EMOJI_ALERT}'>🚨</tg-emoji> Invalid! Send <code>USER_ID VOTES</code>.", parse_mode="HTML")
        return
    
    giveaway = giveaways[giveaway_id]
    if target_uid not in giveaway['users']:
        await update.message.reply_text(f"<tg-emoji emoji-id='{EMOJI_ERROR}'>❌</tg-emoji> User not found!", parse_mode="HTML")
        return
    
    old_votes = giveaway['vote_counts'].get(target_uid, 0)
    
    if action == "add":
        giveaway['vote_counts'][target_uid] = old_votes + votes
        msg = f"<tg-emoji emoji-id='{EMOJI_DIAMOND}'>💎</tg-emoji> Added +{votes} votes!"
    else:
        giveaway['vote_counts'][target_uid] = max(0, old_votes - votes)
        msg = f"<tg-emoji emoji-id='{EMOJI_DIAMOND}'>💎</tg-emoji> Removed {votes} votes!"
    
    new_votes = giveaway['vote_counts'][target_uid]
    save_data()
    
    await update_vote_button_in_channel(context, giveaway_id, target_uid, new_votes)
    
    await update.message.reply_text(
        f"{msg}\n<b>New Total:</b> {new_votes} votes",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[premium_button("BACK", callback_data=f"manage_{giveaway_id}", emoji_id=EMOJI_BACK, style=BUTTON_STYLE_PRIMARY)]])
    )
    
    del context.user_data["vote_giveaway"]
    del context.user_data["vote_action"]

async def show_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    giveaway_id = query.data.split("_")[1]
    giveaway = giveaways[giveaway_id]
    
    sorted_users = sorted(giveaway['vote_counts'].items(), key=lambda x: x[1], reverse=True)[:10]
    
    text = f"<b><tg-emoji emoji-id='{EMOJI_CALENDAR}'>🗓</tg-emoji> LEADERBOARD</b>\n\n"
    if not sorted_users:
        text += "<i>No votes yet.</i>"
    else:
        for idx, (uid, votes) in enumerate(sorted_users, 1):
            name = giveaway['users'].get(uid, f"User {uid}")
            text += f"<b>{idx}.</b> {name} - <b>{votes} votes</b>\n"
    
    await query.edit_message_text(
        text=text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[premium_button("BACK", callback_data=f"manage_{giveaway_id}", emoji_id=EMOJI_BACK, style=BUTTON_STYLE_PRIMARY)]])
    )

async def end_giveaway(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    giveaway_id = query.data.split("_")[1]
    await query.edit_message_text(
        text=f"<b><tg-emoji emoji-id='{EMOJI_LOCK}'>⚠️</tg-emoji> End this giveaway?</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [premium_button("CONFIRM", callback_data=f"confirm_end_{giveaway_id}", emoji_id=EMOJI_CONFIRM, style=BUTTON_STYLE_DANGER)],
            [premium_button("CANCEL", callback_data=f"manage_{giveaway_id}", emoji_id=EMOJI_CANCEL, style=BUTTON_STYLE_PRIMARY)]
        ])
    )

async def confirm_end_giveaway(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    giveaway_id = query.data.split("_")[2]
    giveaway = giveaways[giveaway_id]
    
    giveaway["ended"] = True
    
    sorted_users = sorted(giveaway['vote_counts'].items(), key=lambda x: x[1], reverse=True)
    winner_text = "No participants."
    if sorted_users:
        w_uid, w_votes = sorted_users[0]
        winner_text = f"🏆 <b>WINNER:</b> {giveaway['users'][w_uid]} with {w_votes} votes!"
    
    update_channel_history(
        channel_identifier=giveaway.get("channel"),
        channel_display=giveaway.get("channel_display"),
        channel_id=giveaway.get("channel_id"),
        user_id=giveaway.get("creator"),
        user_name=giveaway.get("creator_name", "Unknown"),
        action="end",
        giveaway_id=giveaway_id
    )
    
    save_data()
    
    if giveaway_id in vote_messages:
        del vote_messages[giveaway_id]
    
    try:
        await context.bot.send_message(
            chat_id=giveaway['channel_id'],
            text=f"💰 <b>GIVEAWAY ENDED!</b>\n\n{winner_text}",
            parse_mode="HTML"
        )
    except: pass
    
    await query.edit_message_text(
        text=f"✅ <b>Giveaway ended!</b>\n\n{winner_text}",
        parse_mode="HTML"
    )

# ================= JOIN HANDLER (WITH CHANNEL CHECK) ================= #
async def handle_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    giveaway_id = query.data.split("_")[1]
    user = query.from_user

    if is_security_banned(user.id):
        await query.answer("🚫 You are banned from this bot.", show_alert=True)
        return
    
    save_user(user.id, user.username, user.first_name, user.last_name, source="join")
    update_user_stats(user.id, "join")
    
    if giveaway_id not in giveaways:
        await query.answer("Giveaway not found!", show_alert=True)
        return

    giveaway = giveaways[giveaway_id]
    
    if giveaway.get("ended"):
        await query.answer("❌ This giveaway has already ended!", show_alert=True)
        return
        
    if user.id in giveaway["users"]:
        await query.answer("⚠️ Already Joined!", show_alert=True)
        return
    
    # Double-check membership before allowing join
    channel_id = giveaway.get('channel_id')
    is_member = False
    
    if channel_id:
        try:
            member = await context.bot.get_chat_member(chat_id=channel_id, user_id=user.id)
            if member.status in ['member', 'administrator', 'creator']:
                is_member = True
            elif member.status == 'restricted' and getattr(member, 'is_member', False):
                is_member = True
        except Exception as e:
            logger.error(f"Error checking membership: {e}")
    
    if not is_member:
        # User is not a member - redirect to membership flow
        channel_display = giveaway.get("channel_display", giveaway.get("channel", "Channel"))
        channel_identifier = giveaway.get("channel", "")
        
        channel_link = None
        try:
            if channel_identifier.startswith('@'):
                channel_link = f"https://t.me/{channel_identifier[1:]}"
            else:
                chat = await context.bot.get_chat(channel_id)
                if chat.invite_link:
                    channel_link = chat.invite_link
                else:
                    channel_link = f"https://t.me/{BOT_USERNAME}?startchannel=true"
        except:
            channel_link = f"https://t.me/{BOT_USERNAME}?startchannel=true"
        
        keyboard = [
            [premium_button("JOIN CHANNEL", url=channel_link, emoji_id=EMOJI_CHANNEL, style=BUTTON_STYLE_SUCCESS)],
            [premium_button("TRY AGAIN", callback_data=f"retry_join_{giveaway_id}", emoji_id=EMOJI_REFRESH, style=BUTTON_STYLE_PRIMARY)]
        ]
        
        await query.edit_message_text(
            f"<tg-emoji emoji-id='{EMOJI_ALERT}'>⚠️</tg-emoji> <b>CHANNEL MEMBERSHIP REQUIRED</b>\n\n"
            f"<tg-emoji emoji-id='{EMOJI_GIFT}'>🎁</tg-emoji> <b>Giveaway Host:</b> {channel_display}\n\n"
            f"<i>You need to join the channel first to participate!</i>\n\n"
            f"<b>Steps to join:</b>\n"
            f"1️⃣ Click <b>JOIN CHANNEL</b> below\n"
            f"2️⃣ Join the channel\n"
            f"3️⃣ Click <b>TRY AGAIN</b> to verify membership",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
        
    # User is a member - proceed with joining
    giveaway["users"][user.id] = user.full_name or user.first_name
    giveaway["vote_counts"][user.id] = 0
    giveaway["voted_users"][user.id] = set()
    save_data()
    
    await query.answer("✅ Registration Successful!", show_alert=True)
    
    channel_text = (
        f"<tg-emoji emoji-id='{EMOJI_SMILE}'>😎</tg-emoji> <b>Name:</b> {user.full_name or user.first_name}\n"
        f"<tg-emoji emoji-id='{EMOJI_ID}'>💌</tg-emoji> <b>ID:</b> <code>{user.id}</code>"
    )
    
    vote_keyboard = [[
        premium_button(f"Vote - 0", callback_data=f"vote_{giveaway_id}_{user.id}", emoji_id=EMOJI_VOTE, style=BUTTON_STYLE_SUCCESS)
    ]]
    
    try:
        sent_msg = await context.bot.send_message(
            chat_id=giveaway['channel_id'],
            text=channel_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(vote_keyboard)
        )
        if giveaway_id not in vote_messages:
            vote_messages[giveaway_id] = {}
        vote_messages[giveaway_id][user.id] = sent_msg.message_id
    except Exception as e:
        logger.error(f"Error: {e}")
    
    await query.edit_message_text(
        text=f"✅ <b>Registration Successful!</b>\n\n"
             f"😎 {user.full_name or user.first_name}\n"
             f"💌 <code>{user.id}</code>\n\n"
             f"📥 Profile shared in channel!",
        parse_mode="HTML"
    )

# ================= VOTE HANDLER (WITH POPUP) ================= #
async def handle_vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split("_")
    giveaway_id = parts[1]
    target_user_id = int(parts[2])
    voter_id = query.from_user.id

    if is_security_banned(voter_id):
        await query.answer("🚫 You are banned from this bot.", show_alert=True)
        return
    
    voter = query.from_user
    save_user(voter.id, voter.username, voter.first_name, voter.last_name, source="vote")
    update_user_stats(voter.id, "vote")
    
    if giveaway_id not in giveaways:
        await query.answer("❌ Giveaway not active!", show_alert=True)
        return
        
    giveaway = giveaways[giveaway_id]
    
    if giveaway.get("ended"):
        await query.answer("❌ This giveaway has ended!", show_alert=True)
        return

    try:
        member = await context.bot.get_chat_member(chat_id=giveaway['channel_id'], user_id=voter_id)
        if member.status in ['left', 'kicked']:
            await query.answer("⚠️ Only channel members can vote! Please join the channel first.", show_alert=True)
            return
        if member.status == 'restricted' and not getattr(member, 'is_member', False):
            await query.answer("⚠️ Only channel members can vote! Please join the channel first.", show_alert=True)
            return
    except:
        await query.answer("⚠️ Please join the channel first to vote!", show_alert=True)
        return

    suspicious, vote_count, target_count = register_vote_activity(voter_id, target_user_id)
    if suspicious:
        suspicious_scores[voter_id] += 1
        if suspicious_scores[voter_id] >= SUSPICIOUS_SCORE_LIMIT:
            security_ban_user(voter_id, "suspicious multi/fake voting activity")
            await send_notification_to_owner(
                context,
                "🚨 SECURITY AUTO-BAN",
                f"👤 {voter.full_name or 'Unknown'}\n🆔 <code>{voter_id}</code>\n⚠️ Reason: suspicious voting ({vote_count} votes / {target_count} targets in {VOTE_WINDOW_SECONDS}s)"
            )
            await query.answer("🚫 Suspicious voting detected. You are banned.", show_alert=True)
            return
        await query.answer("⚠️ Voting too quickly. Please slow down.", show_alert=True)
        return

    if target_user_id not in giveaway["voted_users"]:
        giveaway["voted_users"][target_user_id] = set()

    if voter_id in giveaway["voted_users"][target_user_id]:
        await query.answer("⚠️ You have already voted for this user!", show_alert=True)
        return

    giveaway["voted_users"][target_user_id].add(voter_id)
    giveaway['vote_counts'][target_user_id] = giveaway['vote_counts'].get(target_user_id, 0) + 1
    new_votes = giveaway['vote_counts'][target_user_id]
    save_data()
    
    await update_vote_button_in_channel(context, giveaway_id, target_user_id, new_votes)
    
    await query.answer("🎉 Vote recorded!", show_alert=False)

# ================= ADMIN COMMANDS ================= #
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/admin - Show all admin commands"""
    user_id = update.effective_user.id
    if not is_owner(user_id):
        await update.message.reply_text("❌ You are not the owner!")
        return
    
    text = """
<b>👑 ADMIN COMMANDS</b>

<code>/admin</code> - Show this help menu
<code>/broadcast &lt;msg&gt;</code> - Send message to all users
<code>/bc &lt;msg&gt;</code> - Send message to all channels
<code>/ball &lt;msg&gt;</code> - Send to all users + all channels
<code>/stats</code> - Bot statistics
<code>/users</code> - Recent users list
<code>/channels</code> - Channel history
<code>/backup</code> - Manual backup
<code>/settings</code> - Bot settings
<code>/testnotify</code> - Test notification
<code>/clear</code> - Delete all data

<code>/g_management &lt;giveaway_id&gt;</code> - Open giveaway management panel
<code>/add_vote &lt;giveaway_id&gt; &lt;user_id&gt; &lt;votes&gt;</code> - Add votes to user
<code>/remove_vote &lt;giveaway_id&gt; &lt;user_id&gt; &lt;votes&gt;</code> - Remove votes from user

<b>📌 Note:</b> Owner can manage any giveaway secretly
"""
    await update.message.reply_text(text, parse_mode="HTML")

async def bc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/bc {msg} - Send message to all channels where bot has active giveaways"""
    user_id = update.effective_user.id
    if not is_owner(user_id):
        await update.message.reply_text("❌ You are not the owner!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Usage: /bc <message>")
        return
    
    msg = ' '.join(context.args)
    await update.message.reply_text(f"🚀 <b>Sending to all channels...</b>\n\nMessage: {msg[:100]}...", parse_mode="HTML")
    
    success = 0
    fail = 0
    channels_sent = set()
    
    for gid, gdata in giveaways.items():
        channel_id = gdata.get('channel_id')
        if channel_id and channel_id not in channels_sent and not gdata.get('ended', False):
            channels_sent.add(channel_id)
            try:
                await context.bot.send_message(chat_id=channel_id, text=msg, parse_mode="HTML", disable_web_page_preview=True)
                success += 1
            except Exception as e:
                logger.error(f"Failed to send to channel {channel_id}: {e}")
                fail += 1
            await asyncio.sleep(0.5)
    
    await update.message.reply_text(
        f"<b>✅ BROADCAST TO CHANNELS COMPLETED!</b>\n\n"
        f"<b>✅ Sent:</b> <code>{success}</code>\n"
        f"<b>❌ Failed:</b> <code>{fail}</code>\n"
        f"<b>📊 Total Channels:</b> <code>{len(channels_sent)}</code>",
        parse_mode="HTML"
    )

async def ball_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/ball {msg} - Send message to all users AND all channels"""
    user_id = update.effective_user.id
    if not is_owner(user_id):
        await update.message.reply_text("❌ You are not the owner!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Usage: /ball <message>")
        return
    
    msg = ' '.join(context.args)
    await update.message.reply_text(f"🚀 <b>Sending to ALL USERS + ALL CHANNELS...</b>\n\nMessage: {msg[:100]}...", parse_mode="HTML")
    
    # Send to all users
    user_success = 0
    user_fail = 0
    for uid in all_users.keys():
        try:
            await context.bot.send_message(chat_id=int(uid), text=msg, parse_mode="HTML", disable_web_page_preview=True)
            user_success += 1
        except:
            user_fail += 1
        await asyncio.sleep(0.05)
    
    # Send to all channels
    channel_success = 0
    channel_fail = 0
    channels_sent = set()
    
    for gid, gdata in giveaways.items():
        channel_id = gdata.get('channel_id')
        if channel_id and channel_id not in channels_sent and not gdata.get('ended', False):
            channels_sent.add(channel_id)
            try:
                await context.bot.send_message(chat_id=channel_id, text=msg, parse_mode="HTML", disable_web_page_preview=True)
                channel_success += 1
            except Exception as e:
                logger.error(f"Failed to send to channel {channel_id}: {e}")
                channel_fail += 1
            await asyncio.sleep(0.5)
    
    await update.message.reply_text(
        f"<b>✅ BALL BROADCAST COMPLETED!</b>\n\n"
        f"<b>📱 USERS:</b>\n"
        f"   ✅ Sent: <code>{user_success}</code>\n"
        f"   ❌ Failed: <code>{user_fail}</code>\n"
        f"   📊 Total: <code>{len(all_users)}</code>\n\n"
        f"<b>📺 CHANNELS:</b>\n"
        f"   ✅ Sent: <code>{channel_success}</code>\n"
        f"   ❌ Failed: <code>{channel_fail}</code>\n"
        f"   📊 Total: <code>{len(channels_sent)}</code>",
        parse_mode="HTML"
    )

async def g_management_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/g_management {giveaway_id} - Open management panel for any giveaway (owner only)"""
    user_id = update.effective_user.id
    if not is_owner(user_id):
        await update.message.reply_text("❌ You are not the owner!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Usage: /g_management <giveaway_id>")
        return
    
    giveaway_id = context.args[0]
    if giveaway_id not in giveaways:
        await update.message.reply_text(f"❌ Giveaway '{giveaway_id}' not found!")
        return
    
    giveaway = giveaways[giveaway_id]
    status = "🟢 ACTIVE" if not giveaway.get("ended") else "🔴 ENDED"
    
    keyboard = [
        [
            premium_button("ADD VOTES", callback_data=f"addvotes_{giveaway_id}", emoji_id=EMOJI_ADD_VOTES, style=BUTTON_STYLE_PRIMARY),
            premium_button("REMOVE VOTES", callback_data=f"removevotes_{giveaway_id}", emoji_id=EMOJI_REMOVE_VOTES, style=BUTTON_STYLE_DANGER)
        ],
        [
            premium_button("LEADERBOARD", callback_data=f"leaderboard_{giveaway_id}", emoji_id=EMOJI_LEADERBOARD, style=BUTTON_STYLE_PRIMARY)
        ],
        [
            premium_button("END GIVEAWAY", callback_data=f"endgiveaway_{giveaway_id}", emoji_id=EMOJI_END_GIVEAWAY, style=BUTTON_STYLE_DANGER)
        ]
    ]
    
    await update.message.reply_text(
        text=f"<b><tg-emoji emoji-id='{EMOJI_ARROW}'>➡️</tg-emoji> MANAGEMENT PANEL (ADMIN)</b>\n\n"
             f"<b>Giveaway ID:</b> <code>{giveaway_id}</code>\n"
             f"<b>Status:</b> {status}\n"
             f"<b>Channel:</b> {giveaway.get('channel_display', giveaway.get('channel'))}\n"
             f"<b>Creator:</b> {giveaway.get('creator_name', 'Unknown')}\n"
             f"<b>Joined:</b> {len(giveaway.get('users', {}))}\n"
             f"<b>Total Votes:</b> {sum(giveaway.get('vote_counts', {}).values())}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def add_vote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/add_vote {giveaway_id} {user_id} {votes}"""
    user_id = update.effective_user.id
    if not is_owner(user_id):
        await update.message.reply_text("❌ You are not the owner!")
        return
    
    if len(context.args) != 3:
        await update.message.reply_text("❌ Usage: /add_vote <giveaway_id> <user_id> <votes>")
        return
    
    giveaway_id = context.args[0]
    target_uid = int(context.args[1])
    votes = int(context.args[2])
    
    if giveaway_id not in giveaways:
        await update.message.reply_text(f"❌ Giveaway '{giveaway_id}' not found!")
        return
    
    giveaway = giveaways[giveaway_id]
    if target_uid not in giveaway['users']:
        await update.message.reply_text(f"❌ User {target_uid} not found in this giveaway!")
        return
    
    old_votes = giveaway['vote_counts'].get(target_uid, 0)
    giveaway['vote_counts'][target_uid] = old_votes + votes
    new_votes = giveaway['vote_counts'][target_uid]
    save_data()
    
    await update_vote_button_in_channel(context, giveaway_id, target_uid, new_votes)
    
    await update.message.reply_text(
        f"✅ <b>Votes Added!</b>\n\n"
        f"<b>Giveaway:</b> <code>{giveaway_id}</code>\n"
        f"<b>User:</b> <code>{target_uid}</code> ({giveaway['users'][target_uid]})\n"
        f"<b>Added:</b> +{votes} votes\n"
        f"<b>New Total:</b> {new_votes} votes",
        parse_mode="HTML"
    )

async def remove_vote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/remove_vote {giveaway_id} {user_id} {votes}"""
    user_id = update.effective_user.id
    if not is_owner(user_id):
        await update.message.reply_text("❌ You are not the owner!")
        return
    
    if len(context.args) != 3:
        await update.message.reply_text("❌ Usage: /remove_vote <giveaway_id> <user_id> <votes>")
        return
    
    giveaway_id = context.args[0]
    target_uid = int(context.args[1])
    votes = int(context.args[2])
    
    if giveaway_id not in giveaways:
        await update.message.reply_text(f"❌ Giveaway '{giveaway_id}' not found!")
        return
    
    giveaway = giveaways[giveaway_id]
    if target_uid not in giveaway['users']:
        await update.message.reply_text(f"❌ User {target_uid} not found in this giveaway!")
        return
    
    old_votes = giveaway['vote_counts'].get(target_uid, 0)
    giveaway['vote_counts'][target_uid] = max(0, old_votes - votes)
    new_votes = giveaway['vote_counts'][target_uid]
    save_data()
    
    await update_vote_button_in_channel(context, giveaway_id, target_uid, new_votes)
    
    await update.message.reply_text(
        f"✅ <b>Votes Removed!</b>\n\n"
        f"<b>Giveaway:</b> <code>{giveaway_id}</code>\n"
        f"<b>User:</b> <code>{target_uid}</code> ({giveaway['users'][target_uid]})\n"
        f"<b>Removed:</b> -{votes} votes\n"
        f"<b>New Total:</b> {new_votes} votes",
        parse_mode="HTML"
    )

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        await update.message.reply_text("❌ You are not the owner!")
        return
    
    if not context.args:
        admin_sessions[OWNER_ID] = {"step": "waiting_broadcast"}
        await update.message.reply_text(
            "<b>📢 BROADCAST SYSTEM</b>\n\n"
            "Send your message below.\n\n"
            "<b>Supported HTML Tags:</b>\n"
            "<code>&lt;b&gt;bold&lt;/b&gt;</code>\n"
            "<code>&lt;i&gt;italic&lt;/i&gt;</code>\n"
            "<code>&lt;u&gt;underline&lt;/u&gt;</code>\n"
            "<code>&lt;s&gt;strikethrough&lt;/s&gt;</code>\n"
            "<code>&lt;a href='URL'&gt;link&lt;/a&gt;</code>\n"
            "<code>&lt;tg-emoji emoji-id='ID'&gt;🎁&lt;/tg-emoji&gt;</code>\n\n"
            f"<b>Total Users:</b> <code>{len(all_users)}</code>\n\n"
            "Send /cancel to abort.",
            parse_mode="HTML"
        )
        return
    
    msg = ' '.join(context.args)
    await update.message.reply_text(f"🚀 <b>Broadcast started!</b>\n\nTotal users: <code>{len(all_users)}</code>\nThis may take some time...", parse_mode="HTML")
    
    success = 0
    fail = 0
    for uid in all_users.keys():
        try:
            await context.bot.send_message(chat_id=int(uid), text=msg, parse_mode="HTML", disable_web_page_preview=True)
            success += 1
        except:
            fail += 1
        await asyncio.sleep(0.05)
    
    await update.message.reply_text(
        f"<b>✅ BROADCAST COMPLETED!</b>\n\n"
        f"<b>✅ Sent:</b> <code>{success}</code>\n"
        f"<b>❌ Failed:</b> <code>{fail}</code>\n"
        f"<b>📊 Total:</b> <code>{len(all_users)}</code>",
        parse_mode="HTML"
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        await update.message.reply_text("❌ You are not the owner!")
        return
    
    active = sum(1 for g in giveaways.values() if not g.get("ended", False))
    participants = sum(len(g.get("users", {})) for g in giveaways.values())
    votes = sum(sum(g.get("vote_counts", {}).values()) for g in giveaways.values())
    
    text = (
        f"<b><tg-emoji emoji-id='{EMOJI_STATS}'>📊</tg-emoji> BOT STATISTICS</b>\n\n"
        f"<b>👥 Users:</b> <code>{len(all_users)}</code>\n"
        f"<b>🎁 Giveaways:</b> <code>{len(giveaways)}</code>\n"
        f"<b>🟢 Active:</b> <code>{active}</code>\n"
        f"<b>📺 Channels:</b> <code>{len(channel_history)}</code>\n"
        f"<b>👤 Participants:</b> <code>{participants}</code>\n"
        f"<b>🗳️ Votes:</b> <code>{votes}</code>"
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        await update.message.reply_text("❌ You are not the owner!")
        return
    
    users_list = list(all_users.values())[-15:]
    users_list.reverse()
    text = f"<b><tg-emoji emoji-id='{EMOJI_USERS}'>👥</tg-emoji> RECENT USERS</b>\n\n"
    for u in users_list:
        text += f"<b>👤 {u.get('first_name', 'Unknown')}</b>\n   🆔 <code>{u.get('user_id')}</code>\n   📝 @{u.get('username', 'no')}\n   📍 {u.get('source', '?')}\n\n"
    text += f"\n<b>Total Users:</b> <code>{len(all_users)}</code>"
    await update.message.reply_text(text, parse_mode="HTML")

async def channels_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        await update.message.reply_text("❌ You are not the owner!")
        return
    
    text = f"<b><tg-emoji emoji-id='{EMOJI_CHANNEL}'>📺</tg-emoji> CHANNEL GIVEAWAY HISTORY</b>\n\n"
    
    text += "<b>🟢 ACTIVE GIVEAWAYS</b>\n"
    text += "<code>─────────────────</code>\n"
    active_found = False
    
    for ch_key, ch_data in channel_history.items():
        active_giveaways = [g for g in ch_data.get("giveaways", []) if g.get("status") == "active"]
        if active_giveaways:
            active_found = True
            text += f"\n<b>📢 {ch_data.get('channel_display', 'Unknown')}</b>\n"
            text += f"   🔍 Type: <code>{ch_data.get('type', 'unknown').upper()}</code>\n"
            text += f"   🆔 ID: <code>{ch_data.get('channel_id', 'N/A')}</code>\n"
            text += f"   👤 Owner: {ch_data.get('created_by_name', 'Unknown')}\n"
            for g in active_giveaways:
                text += f"      • ID: <code>{g.get('giveaway_id', 'N/A')}</code>\n"
                text += f"        📅 Created: {g.get('created_at', '')[:10]}\n"
    
    if not active_found:
        text += "<i>No active giveaways</i>\n"
    
    text += "\n<b>🔴 GIVEAWAY HISTORY</b>\n"
    text += "<code>─────────────────</code>\n"
    ended_found = False
    
    for ch_key, ch_data in list(channel_history.items())[-10:]:
        ended_giveaways = [g for g in ch_data.get("giveaways", []) if g.get("status") == "ended"]
        if ended_giveaways:
            ended_found = True
            text += f"\n<b>📢 {ch_data.get('channel_display', 'Unknown')}</b>\n"
            text += f"   🔍 Type: <code>{ch_data.get('type', 'unknown').upper()}</code>\n"
            text += f"   🆔 ID: <code>{ch_data.get('channel_id', 'N/A')}</code>\n"
            text += f"   👤 Owner: {ch_data.get('created_by_name', 'Unknown')}\n"
            text += f"   🎁 Total: <code>{ch_data.get('total_giveaways', 0)}</code> giveaways\n"
    
    if not ended_found:
        text += "<i>No giveaway history yet</i>\n"
    
    await update.message.reply_text(text, parse_mode="HTML")

async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        await update.message.reply_text("❌ You are not the owner!")
        return
    
    save_data()
    await update.message.reply_text(
        f"<b>✅ BACKUP CREATED!</b>\n\n"
        f"<b>💾 File:</b> <code>{DATA_FILE}</code>\n"
        f"<b>👥 Users:</b> <code>{len(all_users)}</code>\n"
        f"<b>🎁 Giveaways:</b> <code>{len(giveaways)}</code>\n"
        f"<b>📺 Channels:</b> <code>{len(channel_history)}</code>\n\n"
        "<i>Data is automatically saved on every change.</i>",
        parse_mode="HTML"
    )

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        await update.message.reply_text("❌ You are not the owner!")
        return
    
    await update.message.reply_text(
        f"<b><tg-emoji emoji-id='{EMOJI_SETTINGS}'>⚙️</tg-emoji> SETTINGS</b>\n\n"
        f"<b>Bot Username:</b> @{BOT_USERNAME}\n"
        f"<b>Owner ID:</b> <code>{OWNER_ID}</code>\n"
        f"<b>Data File:</b> <code>{DATA_FILE}</code>\n"
        f"<b>Auto Save:</b> ✅ Enabled\n"
        f"<b>User Tracking:</b> ✅ Enabled\n"
        f"<b>Channel History:</b> ✅ Enabled\n"
        f"<b>Auto Vote Update:</b> ✅ Enabled\n\n"
        "<i>Settings are managed via bot configuration.</i>",
        parse_mode="HTML"
    )

async def testnotify_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        await update.message.reply_text("❌ You are not the owner!")
        return
    
    await send_notification_to_owner(context, "🔔 TEST NOTIFICATION", "This is a test notification from your bot!\n\nAll systems working fine.")
    await update.message.reply_text("✅ Test notification sent to owner!", parse_mode="HTML")

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        await update.message.reply_text("❌ You are not the owner!")
        return
    
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ CONFIRM CLEAR", callback_data="confirm_clear", style=BUTTON_STYLE_DANGER),
        InlineKeyboardButton("❌ CANCEL", callback_data="main_menu", style=BUTTON_STYLE_PRIMARY)
    ]])
    
    await update.message.reply_text(
        f"<b><tg-emoji emoji-id='{EMOJI_ALERT}'>⚠️</tg-emoji> DANGER ZONE</b>\n\n"
        f"Are you sure you want to clear ALL data?\n\n"
        f"This will delete:\n"
        f"• <code>{len(all_users)}</code> users\n"
        f"• <code>{len(giveaways)}</code> giveaways\n"
        f"• <code>{len(channel_history)}</code> channel histories\n\n"
        f"<b>This action cannot be undone!</b>",
        parse_mode="HTML",
        reply_markup=keyboard
    )

async def confirm_clear_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if not is_owner(user_id):
        await query.edit_message_text("❌ You are not the owner!", parse_mode="HTML")
        return
    
    global giveaways, all_users, channel_history, vote_messages, banned_users, suspicious_scores, vote_activity
    giveaways = {}
    all_users = {}
    channel_history = {}
    vote_messages = {}
    banned_users.clear()
    suspicious_scores.clear()
    vote_activity.clear()
    save_data()
    
    await query.edit_message_text(
        "✅ <b>All data cleared successfully!</b>\n\nBot data has been reset.",
        parse_mode="HTML"
    )

async def process_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID or admin_sessions.get(OWNER_ID, {}).get("step") != "waiting_broadcast":
        return
    
    if update.message.text == "/cancel":
        del admin_sessions[OWNER_ID]
        await update.message.reply_text("❌ Broadcast cancelled!", parse_mode="HTML")
        return
    
    msg = update.message.text
    await update.message.reply_text(f"🚀 <b>Broadcast started!</b>\n\nTotal users: <code>{len(all_users)}</code>\nThis may take some time...", parse_mode="HTML")
    
    success = 0
    fail = 0
    for uid in all_users.keys():
        try:
            await context.bot.send_message(chat_id=int(uid), text=msg, parse_mode="HTML", disable_web_page_preview=True)
            success += 1
        except:
            fail += 1
        await asyncio.sleep(0.05)
    
    del admin_sessions[OWNER_ID]
    
    await update.message.reply_text(
        f"<b>✅ BROADCAST COMPLETED!</b>\n\n"
        f"<b>✅ Sent:</b> <code>{success}</code>\n"
        f"<b>❌ Failed:</b> <code>{fail}</code>\n"
        f"<b>📊 Total:</b> <code>{len(all_users)}</code>",
        parse_mode="HTML"
    )


async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner-only manual security ban."""
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ You are not the owner!")
        return

    if not context.args:
        await update.message.reply_text("❌ Usage: /ban <user_id> [reason]")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")
        return

    reason = " ".join(context.args[1:]).strip() or "manual owner ban"
    security_ban_user(target_id, reason)
    await update.message.reply_text(
        f"🚫 <b>User banned.</b>\n\n🆔 <code>{target_id}</code>\n⚠️ {reason}",
        parse_mode="HTML"
    )


async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner-only manual security unban."""
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ You are not the owner!")
        return

    if not context.args:
        await update.message.reply_text("❌ Usage: /unban <user_id>")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")
        return

    banned_users.discard(target_id)
    if str(target_id) in all_users:
        all_users[str(target_id)]["security_banned"] = False
        all_users[str(target_id)]["security_unbanned_at"] = datetime.now().isoformat()
    save_data()

    await update.message.reply_text(
        f"✅ <b>User unbanned.</b>\n\n🆔 <code>{target_id}</code>",
        parse_mode="HTML"
    )


async def security_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ You are not the owner!")
        return
    active_bans = len(banned_users)
    suspicious = sum(suspicious_scores.values())
    await update.message.reply_text(
        f"<b>🛡 SECURITY STATUS</b>\n\n"
        f"<b>Auto-ban:</b> {'ON' if AUTO_BAN_ON_ABUSE else 'OFF'}\n"
        f"<b>Banned users:</b> <code>{active_bans}</code>\n"
        f"<b>Suspicious score:</b> <code>{suspicious}</code>\n"
        f"<b>Vote window:</b> <code>{VOTE_WINDOW_SECONDS}s</code>\n"
        f"<b>Max votes/window:</b> <code>{MAX_VOTES_IN_WINDOW}</code>",
        parse_mode="HTML"
    )

# ================= MAIN MENU ================= #
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [premium_button("CONNECT", url=f"https://t.me/{BOT_USERNAME}?startchannel=true&admin=post_messages", emoji_id=EMOJI_CONNECT, style=BUTTON_STYLE_SUCCESS)],
        [premium_button("CREATE", callback_data="create_giveaway", emoji_id=EMOJI_CREATE, style=BUTTON_STYLE_PRIMARY),
         premium_button("MANAGE", callback_data="my_giveaways", emoji_id=EMOJI_MANAGE, style=BUTTON_STYLE_PRIMARY)]
    ]
    
    await query.edit_message_text(text="<b>🌐 MAIN MENU</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

# ================= BUTTON ROUTER ================= #
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user = query.from_user
    logger.info(f"Button: {data}")

    if SECURITY_ENABLED and user and user.id != OWNER_ID:
        if is_security_banned(user.id):
            await query.answer("🚫 You are banned from this bot.", show_alert=True)
            return

        profile_found, profile_reason = check_profile_for_abuse(user)
        if profile_found and AUTO_BAN_ON_PROFILE_ABUSE:
            security_ban_user(user.id, profile_reason)
            await send_notification_to_owner(
                context,
                "🚨 PROFILE SECURITY AUTO-BAN",
                f"👤 {user.full_name or 'Unknown'}\\n"
                f"🔹 Username: @{user.username or 'N/A'}\\n"
                f"🆔 <code>{user.id}</code>\\n"
                f"⚠️ Reason: {profile_reason}"
            )
            await query.answer(
                "🚫 Your name/username contains a banned word. You are banned.",
                show_alert=True
            )
            return

    if data == "confirm_clear":
        await confirm_clear_callback(update, context)
    elif data == "create_giveaway":
        await create_giveaway_flow(update, context)
    elif data == "cancel_creation":
        await cancel_creation(update, context)
    elif data == "my_giveaways":
        await my_giveaways(update, context)
    elif data == "main_menu":
        await main_menu(update, context)
    elif data.startswith("retry_join_"):
        await retry_join(update, context)
    elif data.startswith("manage_"):
        await manage_giveaway(update, context)
    elif data.startswith("addvotes_"):
        await add_votes_flow(update, context)
    elif data.startswith("removevotes_"):
        await remove_votes_flow(update, context)
    elif data.startswith("leaderboard_"):
        await show_leaderboard(update, context)
    elif data.startswith("endgiveaway_"):
        await end_giveaway(update, context)
    elif data.startswith("confirm_end_"):
        await confirm_end_giveaway(update, context)
    elif data.startswith("join_"):
        await handle_join(update, context)
    elif data.startswith("vote_"):
        await handle_vote(update, context)

async def security_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not SECURITY_ENABLED or not update.effective_user or not update.message:
        return False

    user = update.effective_user
    user_id = user.id

    if user_id == OWNER_ID:
        return False

    if is_security_banned(user_id):
        try:
            await update.message.reply_text("🚫 You are banned from using this bot.")
        except Exception:
            pass
        return True

    profile_found, profile_reason = check_profile_for_abuse(user)
    if profile_found and AUTO_BAN_ON_PROFILE_ABUSE:
        security_ban_user(user_id, profile_reason)
        await send_notification_to_owner(
            context,
            "🚨 PROFILE SECURITY AUTO-BAN",
            f"👤 {user.full_name or 'Unknown'}\\n"
            f"🔹 Username: @{user.username or 'N/A'}\\n"
            f"🆔 <code>{user_id}</code>\\n"
            f"⚠️ Reason: {profile_reason}"
        )
        await update.message.reply_text(
            "🚫 Your name/username contains a banned word. You have been banned."
        )
        return True

    text = update.message.text or ""
    found, reason = contains_banned_content(text)
    if found and AUTO_BAN_ON_ABUSE:
        security_ban_user(user_id, reason)
        await send_notification_to_owner(
            context,
            "🚨 SECURITY AUTO-BAN",
            f"👤 {user.full_name or 'Unknown'}\n"
            f"🆔 <code>{user_id}</code>\n"
            f"⚠️ Reason: {reason}"
        )
        await update.message.reply_text(
            "🚫 Your message contained prohibited content. You have been banned from using this bot."
        )
        return True
    return False


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await security_message_handler(update, context):
        return

    user_id = update.effective_user.id
    
    if user_id == OWNER_ID and admin_sessions.get(OWNER_ID, {}).get("step") == "waiting_broadcast":
        await process_broadcast(update, context)
        return
    
    if user_id in user_sessions and user_sessions[user_id].get("step") == "waiting_channel":
        await process_channel(update, context)
        return
    
    if "vote_giveaway" in context.user_data:
        await process_vote_change(update, context)
        return

def main():
    app = Application.builder().token(TOKEN).request(request).build()
    
    # User commands
    app.add_handler(CommandHandler("start", start))
    
    # Admin commands
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("bc", bc_command))
    app.add_handler(CommandHandler("ball", ball_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("users", users_command))
    app.add_handler(CommandHandler("channels", channels_command))
    app.add_handler(CommandHandler("backup", backup_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("security", security_command))
    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("unban", unban_command))
    app.add_handler(CommandHandler("testnotify", testnotify_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("g_management", g_management_command))
    app.add_handler(CommandHandler("add_vote", add_vote_command))
    app.add_handler(CommandHandler("remove_vote", remove_vote_command))
    
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("=" * 60)
    print("🤖 PREMIUM VOTE-GIVEAWAY BOT IS ACTIVE!")
    print(f"📌 Bot Username: @{BOT_USERNAME}")
    print(f"👑 Owner ID: {OWNER_ID}")
    print(f"💾 Data File: {DATA_FILE}")
    print("=" * 60)
    print("\n✅ ADMIN COMMANDS:")
    print("   /admin - Show all admin commands")
    print("   /broadcast <msg> - Send to all users")
    print("   /bc <msg> - Send to all channels")
    print("   /ball <msg> - Send to all users + all channels")
    print("   /stats - Bot statistics")
    print("   /users - Recent users list")
    print("   /channels - Channel history")
    print("   /backup - Manual backup")
    print("   /settings - Bot settings")
    print("   /security - Security status")
    print("   /ban <user_id> [reason] - Manual ban")
    print("   /unban <user_id> - Remove security ban")
    print("   /testnotify - Test notification")
    print("   /clear - Delete all data")
    print("   /g_management <id> - Open giveaway panel")
    print("   /add_vote <id> <user_id> <votes> - Add votes")
    print("   /remove_vote <id> <user_id> <votes> - Remove votes")
    print("=" * 60)
    print("\n✅ CHANNEL MEMBERSHIP SYSTEM ADDED:")
    print("   • Checks if user is a channel member before joining")
    print("   • Shows JOIN CHANNEL button if not a member")
    print("   • Shows TRY AGAIN button to re-check membership")
    print("=" * 60)
    
    app.run_polling(allowed_updates=["message", "callback_query"])

if __name__ == "__main__":
    main()
