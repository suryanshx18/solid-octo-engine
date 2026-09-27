#!/usr/bin/env python3

import asyncio
import html
import json
import logging
import os
import random
import string
from datetime import datetime
from typing import Any, Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.request import HTTPXRequest


# ============================================================
# CONFIG
# ============================================================

TOKEN = os.getenv("BOT_TOKEN", "").strip()
BOT_USERNAME = os.getenv("BOT_USERNAME").strip().lstrip("@")

try:
    OWNER_ID = int(os.getenv("OWNER_ID", "0"))
except ValueError:
    OWNER_ID = 0

DATA_FILE = os.getenv("DATA_FILE", "bot_data.json")


# ============================================================
# PREMIUM EMOJIS
# ============================================================

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


# ============================================================
# BUTTON STYLES
# ============================================================

BUTTON_STYLE_PRIMARY = "primary"
BUTTON_STYLE_SUCCESS = "success"
BUTTON_STYLE_DANGER = "danger"


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)


# ============================================================
# GLOBAL DATA
# ============================================================

giveaways: dict[str, dict[str, Any]] = {}
all_users: dict[str, dict[str, Any]] = {}
user_sessions: dict[int, dict[str, Any]] = {}
admin_sessions: dict[int, dict[str, Any]] = {}
channel_history: dict[str, dict[str, Any]] = {}

# Runtime-only message map.
# It is intentionally not saved in JSON because Telegram message IDs
# can become stale and this data is only needed while the process runs.
vote_messages: dict[str, dict[int, int]] = {}


# ============================================================
# HELPERS
# ============================================================

def now_iso() -> str:
    return datetime.now().isoformat()


def safe_html(value: Any) -> str:
    """Escape dynamic values before inserting them into Telegram HTML."""
    if value is None:
        return ""
    return html.escape(str(value), quote=False)


def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


def normalize_user_id(value: Any) -> Optional[int]:
    """Convert a JSON-loaded ID into an integer."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def member_is_present(member: Any) -> bool:
    """
    Telegram can return:
      member
      administrator
      creator
      restricted

    A restricted user can still be a member when is_member=True.
    """
    status = getattr(member, "status", None)

    if status in ("member", "administrator", "creator"):
        return True

    if status == "restricted":
        return bool(getattr(member, "is_member", False))

    return False


def premium_button(
    text: str,
    callback_data: Optional[str] = None,
    url: Optional[str] = None,
    emoji_id: Optional[str] = None,
    style: Optional[str] = None,
) -> InlineKeyboardButton:

    kwargs: dict[str, Any] = {
        "text": text,
    }

    if callback_data is not None:
        kwargs["callback_data"] = callback_data

    if url is not None:
        kwargs["url"] = url

    if style:
        kwargs["style"] = style

    return InlineKeyboardButton(**kwargs)


def main_menu_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            premium_button(
                "CONNECT",
                url=(
                    f"https://t.me/{BOT_USERNAME}"
                    "?startchannel=true&admin=post_messages"
                ),
                emoji_id=EMOJI_CONNECT,
                style=BUTTON_STYLE_SUCCESS,
            )
        ],
        [
            premium_button(
                "CREATE",
                callback_data="create_giveaway",
                emoji_id=EMOJI_CREATE,
                style=BUTTON_STYLE_PRIMARY,
            ),
            premium_button(
                "MANAGE",
                callback_data="my_giveaways",
                emoji_id=EMOJI_MANAGE,
                style=BUTTON_STYLE_PRIMARY,
            ),
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


def generate_giveaway_id() -> str:
    """Generate an 8-character giveaway ID."""
    while True:
        giveaway_id = "".join(
            random.choices(
                string.ascii_letters + string.digits,
                k=8,
            )
        )

        if giveaway_id not in giveaways:
            return giveaway_id


# ============================================================
# JSON DATABASE
# ============================================================

def load_data() -> None:
    """
    Load JSON database and normalize numeric dictionary keys.

    JSON always converts dictionary keys to strings. Telegram user IDs
    are numeric, so we convert relevant keys back to int after loading.
    """

    global giveaways, all_users, channel_history

    if not os.path.exists(DATA_FILE):
        giveaways = {}
        all_users = {}
        channel_history = {}
        return

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        giveaways = data.get("giveaways", {}) or {}
        all_users = data.get("all_users", {}) or {}
        channel_history = data.get("channel_history", {}) or {}

        # --------------------------------------------------------
        # Normalize giveaway dictionaries
        # --------------------------------------------------------

        for giveaway_id, giveaway in giveaways.items():

            giveaway.setdefault("users", {})
            giveaway.setdefault("vote_counts", {})
            giveaway.setdefault("voted_users", {})
            giveaway.setdefault("ended", False)

            # users
            normalized_users = {}

            for uid, name in giveaway["users"].items():
                normalized_uid = normalize_user_id(uid)

                if normalized_uid is not None:
                    normalized_users[normalized_uid] = name

            giveaway["users"] = normalized_users

            # vote_counts
            normalized_votes = {}

            for uid, votes in giveaway["vote_counts"].items():
                normalized_uid = normalize_user_id(uid)

                if normalized_uid is not None:
                    try:
                        normalized_votes[normalized_uid] = max(0, int(votes))
                    except (TypeError, ValueError):
                        normalized_votes[normalized_uid] = 0

            giveaway["vote_counts"] = normalized_votes

            # voted_users
            normalized_voters = {}

            for target_uid, voters in giveaway["voted_users"].items():

                normalized_target = normalize_user_id(target_uid)

                if normalized_target is None:
                    continue

                # Older versions could have stored lists.
                if isinstance(voters, list):
                    voter_set = set()

                    for voter in voters:
                        normalized_voter = normalize_user_id(voter)

                        if normalized_voter is not None:
                            voter_set.add(normalized_voter)

                    normalized_voters[normalized_target] = voter_set

                elif isinstance(voters, set):
                    normalized_voters[normalized_target] = {
                        int(v)
                        for v in voters
                        if normalize_user_id(v) is not None
                    }

                else:
                    normalized_voters[normalized_target] = set()

            giveaway["voted_users"] = normalized_voters

        logger.info(
            "Loaded: %s giveaways, %s users, %s channels",
            len(giveaways),
            len(all_users),
            len(channel_history),
        )

    except Exception as e:
        logger.exception("Error loading database: %s", e)

        # Do not destroy an existing file on a temporary read failure.
        giveaways = {}
        all_users = {}
        channel_history = {}


def make_json_safe(value: Any) -> Any:
    """
    Recursively convert sets and non-string dictionary keys into JSON-safe
    values while keeping the runtime dictionaries untouched.
    """

    if isinstance(value, dict):
        result = {}

        for key, item in value.items():

            if isinstance(key, int):
                json_key = str(key)
            else:
                json_key = str(key)

            result[json_key] = make_json_safe(item)

        return result

    if isinstance(value, set):
        return [
            make_json_safe(item)
            for item in sorted(
                value,
                key=lambda x: str(x),
            )
        ]

    if isinstance(value, list):
        return [make_json_safe(item) for item in value]

    if isinstance(value, tuple):
        return [make_json_safe(item) for item in value]

    return value


def save_data() -> bool:
    """
    Atomically save the database.

    The temporary file + os.replace approach prevents a process crash from
    leaving bot_data.json half-written.
    """

    temp_file = f"{DATA_FILE}.tmp"

    try:
        data = {
            "giveaways": make_json_safe(giveaways),
            "all_users": make_json_safe(all_users),
            "channel_history": make_json_safe(channel_history),
            "last_saved": now_iso(),
        }

        with open(
            temp_file,
            "w",
            encoding="utf-8",
        ) as f:

            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=2,
            )

            f.flush()
            os.fsync(f.fileno())

        os.replace(temp_file, DATA_FILE)

        return True

    except Exception as e:
        logger.exception("Error saving database: %s", e)

        try:
            if os.path.exists(temp_file):
                os.remove(temp_file)
        except Exception:
            pass

        return False


# ============================================================
# USER DATABASE
# ============================================================

def save_user(
    user_id: int,
    username: Optional[str],
    first_name: str,
    last_name: Optional[str] = None,
    source: Optional[str] = None,
) -> bool:

    user_key = str(user_id)

    if user_key not in all_users:

        all_users[user_key] = {
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "joined_at": now_iso(),
            "last_active": now_iso(),
            "source": source or "unknown",
            "total_votes_given": 0,
            "total_giveaways_joined": 0,
        }

    else:

        user_data = all_users[user_key]

        user_data["last_active"] = now_iso()

        if username:
            user_data["username"] = username

        if first_name:
            user_data["first_name"] = first_name

        if last_name is not None:
            user_data["last_name"] = last_name

        if source:
            user_data["source"] = source

    return save_data()


def update_user_stats(
    user_id: int,
    action: str,
) -> None:

    user_key = str(user_id)

    if user_key not in all_users:
        return

    if action == "vote":

        all_users[user_key]["total_votes_given"] = (
            all_users[user_key].get("total_votes_given", 0) + 1
        )

    elif action == "join":

        all_users[user_key]["total_giveaways_joined"] = (
            all_users[user_key].get(
                "total_giveaways_joined",
                0,
            ) + 1
        )

    save_data()


# ============================================================
# CHANNEL HISTORY
# ============================================================

def update_channel_history(
    channel_identifier: str,
    channel_display: str,
    channel_id: int,
    user_id: int,
    user_name: str,
    action: str,
    giveaway_id: Optional[str] = None,
) -> None:

    channel_key = str(channel_identifier)

    if channel_key not in channel_history:

        channel_type = (
            "public"
            if str(channel_identifier).startswith("@")
            else "private"
        )

        channel_history[channel_key] = {
            "channel_identifier": channel_identifier,
            "channel_display": channel_display,
            "channel_id": channel_id,
            "type": channel_type,
            "total_giveaways": 0,
            "giveaways": [],
            "created_by": user_id,
            "created_by_name": user_name,
            "first_created": now_iso(),
        }

    channel_data = channel_history[channel_key]

    if action == "create":

        channel_data["total_giveaways"] = (
            channel_data.get("total_giveaways", 0) + 1
        )

        channel_data.setdefault("giveaways", []).append(
            {
                "giveaway_id": giveaway_id,
                "created_at": now_iso(),
                "status": "active",
                "participants": 0,
            }
        )

        channel_data["last_giveaway"] = now_iso()

    elif action == "end" and giveaway_id:

        for giveaway_data in channel_data.get(
            "giveaways",
            [],
        ):

            if giveaway_data.get("giveaway_id") == giveaway_id:

                giveaway_data["status"] = "ended"
                giveaway_data["ended_at"] = now_iso()

                break

    save_data()


# ============================================================
# CHANNEL HELPERS
# ============================================================

async def get_channel_link(
    context: ContextTypes.DEFAULT_TYPE,
    channel_id: Any,
    channel_identifier: str,
) -> str:

    identifier = str(channel_identifier or "")

    # Public channel
    if identifier.startswith("@"):
        return f"https://t.me/{identifier[1:]}"

    try:

        chat = await context.bot.get_chat(channel_id)

        # Existing invite link
        if getattr(chat, "invite_link", None):
            return chat.invite_link

        # Try creating an invite link.
        # This works only when the bot has the appropriate admin rights.
        try:

            invite = await context.bot.create_chat_invite_link(
                chat_id=channel_id,
                name="Giveaway Bot Invite",
            )

            if invite and invite.invite_link:
                return invite.invite_link

        except Exception as invite_error:
            logger.warning(
                "Could not create invite link for %s: %s",
                channel_id,
                invite_error,
            )

    except Exception as e:
        logger.warning(
            "Could not obtain channel link: %s",
            e,
        )

    # Preserve the original fallback.
    return f"https://t.me/{BOT_USERNAME}?startchannel=true"


async def check_channel_membership(
    context: ContextTypes.DEFAULT_TYPE,
    channel_id: Any,
    user_id: int,
) -> bool:

    if not channel_id:
        return False

    try:

        member = await context.bot.get_chat_member(
            chat_id=channel_id,
            user_id=user_id,
        )

        return member_is_present(member)

    except Exception as e:

        logger.warning(
            "Membership check failed. Channel=%s User=%s Error=%s",
            channel_id,
            user_id,
            e,
        )

        return False


# ============================================================
# OWNER NOTIFICATION
# ============================================================

async def send_notification_to_owner(
    context: ContextTypes.DEFAULT_TYPE,
    title: str,
    message: str,
) -> None:

    if not OWNER_ID:
        return

    try:

        await context.bot.send_message(
            chat_id=OWNER_ID,
            text=(
                f"<b>{title}</b>\n\n"
                f"{message}"
            ),
            parse_mode="HTML",
        )

    except Exception as e:

        logger.error(
            "Failed to send owner notification: %s",
            e,
        )


# ============================================================
# VOTE BUTTON UPDATE
# ============================================================

async def update_vote_button_in_channel(
    context: ContextTypes.DEFAULT_TYPE,
    giveaway_id: str,
    user_id: int,
    new_votes: int,
) -> bool:

    try:

        giveaway = giveaways.get(giveaway_id)

        if not giveaway:
            return False

        message_map = vote_messages.get(
            giveaway_id,
            {},
        )

        message_id = message_map.get(user_id)

        if not message_id:
            return False

        new_keyboard = [
            [
                premium_button(
                    f"Vote - {new_votes}",
                    callback_data=(
                        f"vote_{giveaway_id}_{user_id}"
                    ),
                    emoji_id=EMOJI_VOTE,
                    style=BUTTON_STYLE_SUCCESS,
                )
            ]
        ]

        await context.bot.edit_message_reply_markup(
            chat_id=giveaway["channel_id"],
            message_id=message_id,
            reply_markup=InlineKeyboardMarkup(
                new_keyboard
            ),
        )

        return True

    except Exception as e:

        logger.warning(
            "Failed to update vote button: %s",
            e,
        )

        return False


# ============================================================
# START COMMAND
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    if not update.effective_user or not update.message:
        return

    user = update.effective_user

    save_user(
        user.id,
        user.username,
        user.first_name,
        user.last_name,
        source="/start",
    )

    if context.args:

        giveaway_id = context.args[0].strip()

        await handle_giveaway_link(
            update,
            context,
            giveaway_id,
        )

        return

    await update.message.reply_text(
        text=(
            f"<b><tg-emoji emoji-id='{EMOJI_WELCOME}'>🙂</tg-emoji> "
            f"WELCOME TO NURROSUL VOTE GIVEAWAY BOT</b>\n\n"

            f"<i><tg-emoji emoji-id='{EMOJI_FIRE}'>☄️</tg-emoji> "
            f"Create Powerful Vote Giveaways</i>\n"

            f"<i><tg-emoji emoji-id='{EMOJI_ARROW}'>🔜</tg-emoji> "
            f"Real Time Vote System</i>\n"

            f"<i><tg-emoji emoji-id='{EMOJI_CHART}'>📈</tg-emoji> "
            f"Advanced Management Tools</i>\n"

            f"<i><tg-emoji emoji-id='{EMOJI_HEART}'>❤️‍🔥</tg-emoji> "
            f"Leaderboard & Analytics</i>\n\n"

            f"<b><tg-emoji emoji-id='{EMOJI_ROCKET}'>🚀</tg-emoji> "
            f"START CREATING NOW!</b>"
        ),
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


# ============================================================
# GIVEAWAY DEEP LINK
# ============================================================

async def handle_giveaway_link(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    giveaway_id: str,
) -> None:

    if not update.message:
        return

    if giveaway_id not in giveaways:

        await update.message.reply_text(
            (
                f"<tg-emoji emoji-id='{EMOJI_ERROR}'>❌</tg-emoji> "
                f"<b>INVALID LINK</b>"
            ),
            parse_mode="HTML",
        )

        return

    giveaway = giveaways[giveaway_id]
    user_id = update.effective_user.id

    if giveaway.get("ended", False):

        await update.message.reply_text(
            (
                f"<tg-emoji emoji-id='{EMOJI_ENDED}'>❌</tg-emoji> "
                f"<b>GIVEAWAY ENDED</b>"
            ),
            parse_mode="HTML",
        )

        return

    if user_id in giveaway.get("users", {}):

        await update.message.reply_text(
            (
                f"<tg-emoji emoji-id='{EMOJI_STAR}'>🌟</tg-emoji> "
                f"<b>ALREADY PARTICIPATED!</b>\n\n"

                f"<tg-emoji emoji-id='{EMOJI_ID}'>💌</tg-emoji> "
                f"<b>Your ID:</b> "
                f"<code>{user_id}</code>"
            ),
            parse_mode="HTML",
        )

        return

    channel_id = giveaway.get("channel_id")

    is_member = await check_channel_membership(
        context,
        channel_id,
        user_id,
    )

    channel_display = giveaway.get(
        "channel_display",
        giveaway.get("channel", "Channel"),
    )

    if is_member:

        keyboard = [
            [
                premium_button(
                    "JOIN GIVEAWAY",
                    callback_data=f"join_{giveaway_id}",
                    emoji_id=EMOJI_JOIN,
                    style=BUTTON_STYLE_SUCCESS,
                )
            ]
        ]

        await update.message.reply_text(
            (
                f"<tg-emoji emoji-id='{EMOJI_GIFT}'>🎁</tg-emoji> "
                f"<b>EXCLUSIVE GIVEAWAY</b>\n\n"

                f"<tg-emoji emoji-id='{EMOJI_WINE}'>🍷</tg-emoji> "
                f"<b>Hosted By:</b> "
                f"{safe_html(channel_display)}\n"

                f"<tg-emoji emoji-id='{EMOJI_SMILE}'>😎</tg-emoji> "
                f"<b>Participants:</b> "
                f"{len(giveaway.get('users', {}))}\n\n"

                f"<tg-emoji emoji-id='{EMOJI_CONFIRM}'>✅</tg-emoji> "
                f"<b>You are a member of the channel!</b>"
            ),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
        )

        return

    channel_identifier = giveaway.get(
        "channel",
        "",
    )

    channel_link = await get_channel_link(
        context,
        channel_id,
        channel_identifier,
    )

    keyboard = [
        [
            premium_button(
                "JOIN CHANNEL",
                url=channel_link,
                emoji_id=EMOJI_CHANNEL,
                style=BUTTON_STYLE_SUCCESS,
            )
        ],
        [
            premium_button(
                "TRY AGAIN",
                callback_data=f"retry_join_{giveaway_id}",
                emoji_id=EMOJI_REFRESH,
                style=BUTTON_STYLE_PRIMARY,
            )
        ],
    ]

    await update.message.reply_text(
        (
            f"<tg-emoji emoji-id='{EMOJI_ALERT}'>⚠️</tg-emoji> "
            f"<b>CHANNEL MEMBERSHIP REQUIRED</b>\n\n"

            f"<tg-emoji emoji-id='{EMOJI_GIFT}'>🎁</tg-emoji> "
            f"<b>Giveaway Host:</b> "
            f"{safe_html(channel_display)}\n\n"

            f"<i>You need to join the channel first to "
            f"participate in this giveaway!</i>\n\n"

            f"<b>Steps to join:</b>\n"
            f"1️⃣ Click <b>JOIN CHANNEL</b> below\n"
            f"2️⃣ Join the channel\n"
            f"3️⃣ Click <b>TRY AGAIN</b> to verify membership"
        ),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


# ============================================================
# RETRY JOIN
# ============================================================

async def retry_join(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    query = update.callback_query

    await query.answer()

    parts = query.data.split("_", 2)

    if len(parts) != 3:
        await query.answer(
            "Invalid giveaway link!",
            show_alert=True,
        )
        return

    giveaway_id = parts[2]
    user_id = query.from_user.id

    if giveaway_id not in giveaways:

        await query.edit_message_text(
            (
                f"<tg-emoji emoji-id='{EMOJI_ERROR}'>❌</tg-emoji> "
                f"<b>Giveaway not found!</b>"
            ),
            parse_mode="HTML",
        )

        return

    giveaway = giveaways[giveaway_id]

    if giveaway.get("ended"):

        await query.edit_message_text(
            (
                f"<tg-emoji emoji-id='{EMOJI_ENDED}'>❌</tg-emoji> "
                f"<b>GIVEAWAY ENDED</b>"
            ),
            parse_mode="HTML",
        )

        return

    channel_id = giveaway.get("channel_id")

    is_member = await check_channel_membership(
        context,
        channel_id,
        user_id,
    )

    channel_display = giveaway.get(
        "channel_display",
        giveaway.get("channel", "Channel"),
    )

    if is_member:

        keyboard = [
            [
                premium_button(
                    "JOIN GIVEAWAY",
                    callback_data=f"join_{giveaway_id}",
                    emoji_id=EMOJI_JOIN,
                    style=BUTTON_STYLE_SUCCESS,
                )
            ]
        ]

        await query.edit_message_text(
            (
                f"<tg-emoji emoji-id='{EMOJI_GIFT}'>🎁</tg-emoji> "
                f"<b>EXCLUSIVE GIVEAWAY</b>\n\n"

                f"<tg-emoji emoji-id='{EMOJI_WINE}'>🍷</tg-emoji> "
                f"<b>Hosted By:</b> "
                f"{safe_html(channel_display)}\n"

                f"<tg-emoji emoji-id='{EMOJI_SMILE}'>😎</tg-emoji> "
                f"<b>Participants:</b> "
                f"{len(giveaway.get('users', {}))}\n\n"

                f"<tg-emoji emoji-id='{EMOJI_CONFIRM}'>✅</tg-emoji> "
                f"<b>Membership verified! You can now join.</b>"
            ),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
        )

        return

    channel_identifier = giveaway.get(
        "channel",
        "",
    )

    channel_link = await get_channel_link(
        context,
        channel_id,
        channel_identifier,
    )

    keyboard = [
        [
            premium_button(
                "JOIN CHANNEL",
                url=channel_link,
                emoji_id=EMOJI_CHANNEL,
                style=BUTTON_STYLE_SUCCESS,
            )
        ],
        [
            premium_button(
                "TRY AGAIN",
                callback_data=f"retry_join_{giveaway_id}",
                emoji_id=EMOJI_REFRESH,
                style=BUTTON_STYLE_PRIMARY,
            )
        ],
    ]

    await query.edit_message_text(
        (
            f"<tg-emoji emoji-id='{EMOJI_ALERT}'>⚠️</tg-emoji> "
            f"<b>STILL NOT A MEMBER</b>\n\n"

            f"<tg-emoji emoji-id='{EMOJI_GIFT}'>🎁</tg-emoji> "
            f"<b>Giveaway Host:</b> "
            f"{safe_html(channel_display)}\n\n"

            f"<i>Please join the channel first!</i>\n\n"

            f"<b>Steps to join:</b>\n"
            f"1️⃣ Click <b>JOIN CHANNEL</b> below\n"
            f"2️⃣ Join the channel\n"
            f"3️⃣ Click <b>TRY AGAIN</b> to verify membership"
        ),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


# ============================================================
# CREATE GIVEAWAY
# ============================================================

async def create_giveaway_flow(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    query = update.callback_query

    await query.answer()

    user_id = query.from_user.id

    user_sessions[user_id] = {
        "step": "waiting_channel"
    }

    keyboard = [
        [
            premium_button(
                "CANCEL",
                callback_data="cancel_creation",
                emoji_id=EMOJI_CANCEL,
                style=BUTTON_STYLE_DANGER,
            )
        ]
    ]

    await query.edit_message_text(
        text=(
            f"<b><tg-emoji emoji-id='{EMOJI_LIGHTNING}'>⚡</tg-emoji> "
            f"CREATE GIVEAWAY</b>\n\n"

            f"<i><tg-emoji emoji-id='{EMOJI_POINTER}'>👈</tg-emoji> "
            f"Send your channel information:</i>\n\n"

            f"<b>Public:</b> "
            f"<code>@username</code>\n"

            f"<b>Private:</b> "
            f"<code>-1001234567890</code>"
        ),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


async def cancel_creation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    query = update.callback_query

    await query.answer()

    user_id = query.from_user.id

    user_sessions.pop(
        user_id,
        None,
    )

    await query.edit_message_text(
        text="✅ <b>Cancelled!</b>",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


async def process_channel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    if not update.message or not update.effective_user:
        return

    user_id = update.effective_user.id
    user_name = update.effective_user.first_name

    session = user_sessions.get(user_id)

    if not session:
        return

    if session.get("step") != "waiting_channel":
        return

    channel_input = update.message.text.strip()

    loading_msg = await update.message.reply_text(
        (
            f"<tg-emoji emoji-id='{EMOJI_LIGHTNING}'>⚡</tg-emoji> "
            f"<b>Verifying...</b>"
        ),
        parse_mode="HTML",
    )

    try:

        if channel_input.startswith("@"):

            chat = await context.bot.get_chat(
                chat_id=channel_input
            )

            channel_info = {
                "identifier": channel_input,
                "display_name": (
                    chat.title
                    or channel_input
                ),
                "chat_id": chat.id,
                "type": "public",
            }

        else:

            try:
                numeric_channel_id = int(channel_input)
            except ValueError:
                raise ValueError("Invalid channel ID")

            chat = await context.bot.get_chat(
                chat_id=numeric_channel_id
            )

            channel_info = {
                "identifier": str(channel_input),
                "display_name": (
                    chat.title
                    or f"Channel {channel_input}"
                ),
                "chat_id": chat.id,
                "type": "private",
            }

    except Exception as e:

        logger.warning(
            "Channel verification failed: %s",
            e,
        )

        try:
            await loading_msg.delete()
        except Exception:
            pass

        error = str(e).lower()

        if (
            "bot is not a member" in error
            or "not enough rights" in error
            or "administrator" in error
            or "forbidden" in error
        ):

            await update.message.reply_text(
                (
                    f"🤖 <b>Bot is not admin!</b>\n\n"
                    f"Please add @{BOT_USERNAME} as an admin "
                    f"in the channel first."
                ),
                parse_mode="HTML",
            )

        else:

            await update.message.reply_text(
                (
                    f"<tg-emoji emoji-id='{EMOJI_ERROR}'>❌</tg-emoji> "
                    f"<b>Invalid channel!</b>"
                ),
                parse_mode="HTML",
            )

        user_sessions.pop(
            user_id,
            None,
        )

        return

    # --------------------------------------------------------
    # Check duplicate active giveaway
    # --------------------------------------------------------

    for gid, gdata in giveaways.items():

        if (
            gdata.get("channel")
            == channel_info["identifier"]
            and not gdata.get("ended", False)
        ):

            await loading_msg.delete()

            existing_link = (
                f"https://t.me/{BOT_USERNAME}"
                f"?start={gid}"
            )

            await update.message.reply_text(
                (
                    f"<tg-emoji emoji-id='{EMOJI_ALERT}'>🚨</tg-emoji> "
                    f"<b>GIVEAWAY ALREADY ACTIVE!</b>\n\n"

                    f"<b>Channel:</b> "
                    f"{safe_html(channel_info['display_name'])}\n\n"

                    f"<b>Active Link:</b>\n"
                    f"<code>{existing_link}</code>"
                ),
                parse_mode="HTML",
            )

            user_sessions.pop(
                user_id,
                None,
            )

            return

    # --------------------------------------------------------
    # Test bot permissions
    # --------------------------------------------------------

    try:

        test_msg = await context.bot.send_message(
            chat_id=channel_info["chat_id"],
            text="✅ Bot connected!",
        )

        try:
            await test_msg.delete()
        except Exception:
            pass

    except Exception as e:

        logger.warning(
            "Bot permission test failed: %s",
            e,
        )

        try:
            await loading_msg.delete()
        except Exception:
            pass

        await update.message.reply_text(
            (
                f"🤖 <b>Bot is not admin!</b>\n\n"
                f"Please add @{BOT_USERNAME} as an admin "
                f"in the channel first."
            ),
            parse_mode="HTML",
        )

        user_sessions.pop(
            user_id,
            None,
        )

        return

    # --------------------------------------------------------
    # Create giveaway
    # --------------------------------------------------------

    giveaway_id = generate_giveaway_id()

    link = (
        f"https://t.me/{BOT_USERNAME}"
        f"?start={giveaway_id}"
    )

    giveaways[giveaway_id] = {
        "channel": channel_info["identifier"],
        "channel_display": channel_info["display_name"],
        "channel_id": channel_info["chat_id"],
        "users": {},
        "vote_counts": {},
        "voted_users": {},
        "creator": user_id,
        "creator_name": user_name,
        "ended": False,
        "created_at": now_iso(),
    }

    update_channel_history(
        channel_identifier=channel_info["identifier"],
        channel_display=channel_info["display_name"],
        channel_id=channel_info["chat_id"],
        user_id=user_id,
        user_name=user_name,
        action="create",
        giveaway_id=giveaway_id,
    )

    vote_messages[giveaway_id] = {}

    save_data()

    # --------------------------------------------------------
    # Notify owner
    # --------------------------------------------------------

    if user_id != OWNER_ID:

        await send_notification_to_owner(
            context,
            "🔔 NEW GIVEAWAY CREATED!",
            (
                f"👤 {safe_html(user_name)}\n"
                f"🆔 <code>{user_id}</code>\n"
                f"📢 {safe_html(channel_info['display_name'])}\n"
                f"🔗 <code>{link}</code>"
            ),
        )

    # --------------------------------------------------------
    # Send channel announcement
    # --------------------------------------------------------

    try:

        await context.bot.send_message(
            chat_id=channel_info["chat_id"],
            text=(
                f"<b><tg-emoji emoji-id='{EMOJI_CONFETTI}'>🎉</tg-emoji> "
                f"NEW GIVEAWAY STARTED!</b>\n\n"

                f"<b><tg-emoji emoji-id='{EMOJI_RIGHT}'>➡️</tg-emoji> "
                f"JOIN HERE:</b>\n"
                f"{link}"
            ),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )

    except Exception as e:

        logger.warning(
            "Could not send giveaway announcement: %s",
            e,
        )

    try:
        await loading_msg.delete()
    except Exception:
        pass

    success_text = (
        f"<b><tg-emoji emoji-id='{EMOJI_CLOWN}'>✅</tg-emoji> "
        f"GIVEAWAY CREATED!</b>\n\n"

        f"<b><tg-emoji emoji-id='{EMOJI_SEARCH}'>🔍</tg-emoji> "
        f"ID:</b> <code>{giveaway_id}</code>\n"

        f"<b><tg-emoji emoji-id='{EMOJI_SPEAKER}'>📢</tg-emoji> "
        f"Channel:</b> "
        f"{safe_html(channel_info['display_name'])}\n\n"

        f"<b><tg-emoji emoji-id='{EMOJI_LINK}'>🔗</tg-emoji> "
        f"LINK:</b>\n"
        f"<code>{link}</code>"
    )

    keyboard = [
        [
            premium_button(
                "MANAGE",
                callback_data=f"manage_{giveaway_id}",
                emoji_id=EMOJI_MANAGE,
                style=BUTTON_STYLE_PRIMARY,
            ),
            premium_button(
                "MAIN MENU",
                callback_data="main_menu",
                emoji_id=EMOJI_MAIN_MENU,
                style=BUTTON_STYLE_PRIMARY,
            ),
        ]
    ]

    await update.message.reply_text(
        success_text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )

    user_sessions.pop(
        user_id,
        None,
    )


# ============================================================
# MANAGE GIVEAWAYS
# ============================================================

async def my_giveaways(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    query = update.callback_query

    await query.answer()

    user_id = query.from_user.id

    text = (
        f"<b><tg-emoji emoji-id='{EMOJI_CROWN}'>💰</tg-emoji> "
        f"YOUR GIVEAWAYS</b>\n\n"
    )

    keyboard = []
    found = False

    for gid, gdata in giveaways.items():

        if (
            gdata.get("creator") == user_id
            and not gdata.get("ended", False)
        ):

            found = True

            keyboard.append(
                [
                    premium_button(
                        text=(
                            f"📢 "
                            f"{gdata.get('channel_display', gdata.get('channel'))}"
                        ),
                        callback_data=f"manage_{gid}",
                        emoji_id=EMOJI_MANAGE,
                        style=BUTTON_STYLE_PRIMARY,
                    )
                ]
            )

    if not found:

        text = (
            f"<tg-emoji emoji-id='{EMOJI_ERROR}'>❌</tg-emoji> "
            f"<b>No active giveaways!</b>"
        )

        keyboard.append(
            [
                premium_button(
                    "CREATE NEW",
                    callback_data="create_giveaway",
                    emoji_id=EMOJI_CREATE,
                    style=BUTTON_STYLE_PRIMARY,
                )
            ]
        )

    keyboard.append(
        [
            premium_button(
                "MAIN MENU",
                callback_data="main_menu",
                emoji_id=EMOJI_MAIN_MENU,
                style=BUTTON_STYLE_PRIMARY,
            )
        ]
    )

    await query.edit_message_text(
        text=text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


async def manage_giveaway(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    query = update.callback_query

    await query.answer()

    giveaway_id = query.data.split("_", 1)[1]

    if giveaway_id not in giveaways:

        await query.edit_message_text(
            (
                f"<tg-emoji emoji-id='{EMOJI_ERROR}'>❌</tg-emoji> "
                f"Not found!"
            ),
            parse_mode="HTML",
        )

        return

    giveaway = giveaways[giveaway_id]

    # Only creator or owner can manage.
    if (
        query.from_user.id != giveaway.get("creator")
        and not is_owner(query.from_user.id)
    ):

        await query.answer(
            "You don't have permission to manage this giveaway.",
            show_alert=True,
        )

        return

    status = (
        "🟢 ACTIVE"
        if not giveaway.get("ended")
        else "🔴 ENDED"
    )

    keyboard = [
        [
            premium_button(
                "ADD VOTES",
                callback_data=f"addvotes_{giveaway_id}",
                emoji_id=EMOJI_ADD_VOTES,
                style=BUTTON_STYLE_PRIMARY,
            ),
            premium_button(
                "REMOVE VOTES",
                callback_data=f"removevotes_{giveaway_id}",
                emoji_id=EMOJI_REMOVE_VOTES,
                style=BUTTON_STYLE_DANGER,
            ),
        ],
        [
            premium_button(
                "LEADERBOARD",
                callback_data=f"leaderboard_{giveaway_id}",
                emoji_id=EMOJI_LEADERBOARD,
                style=BUTTON_STYLE_PRIMARY,
            )
        ],
        [
            premium_button(
                "END GIVEAWAY",
                callback_data=f"endgiveaway_{giveaway_id}",
                emoji_id=EMOJI_END_GIVEAWAY,
                style=BUTTON_STYLE_DANGER,
            )
        ],
        [
            premium_button(
                "BACK",
                callback_data="my_giveaways",
                emoji_id=EMOJI_BACK,
                style=BUTTON_STYLE_PRIMARY,
            )
        ],
    ]

    await query.edit_message_text(
        text=(
            f"<b><tg-emoji emoji-id='{EMOJI_ARROW}'>➡️</tg-emoji> "
            f"MANAGEMENT PANEL</b>\n\n"

            f"<b>Status:</b> {status}\n"

            f"<b>Channel:</b> "
            f"{safe_html(giveaway.get('channel_display', giveaway.get('channel')))}\n"

            f"<b>Joined:</b> "
            f"{len(giveaway.get('users', {}))}"
        ),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


# ============================================================
# VOTE MANAGEMENT
# ============================================================

async def add_votes_flow(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    query = update.callback_query

    await query.answer()

    giveaway_id = query.data.split("_", 1)[1]

    if giveaway_id not in giveaways:
        await query.answer(
            "Giveaway not found!",
            show_alert=True,
        )
        return

    context.user_data["vote_giveaway"] = giveaway_id
    context.user_data["vote_action"] = "add"

    await query.edit_message_text(
        text=(
            f"<b><tg-emoji emoji-id='{EMOJI_DIAMOND}'>💎</tg-emoji> "
            f"ADD VOTES</b>\n\n"

            f"Send: <code>USER_ID VOTES</code>\n"
            f"Example: <code>12345678 10</code>"
        ),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    premium_button(
                        "BACK",
                        callback_data=f"manage_{giveaway_id}",
                        emoji_id=EMOJI_BACK,
                        style=BUTTON_STYLE_PRIMARY,
                    )
                ]
            ]
        ),
    )


async def remove_votes_flow(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    query = update.callback_query

    await query.answer()

    giveaway_id = query.data.split("_", 1)[1]

    if giveaway_id not in giveaways:
        await query.answer(
            "Giveaway not found!",
            show_alert=True,
        )
        return

    context.user_data["vote_giveaway"] = giveaway_id
    context.user_data["vote_action"] = "remove"

    await query.edit_message_text(
        text=(
            f"<b><tg-emoji emoji-id='{EMOJI_DIAMOND}'>💎</tg-emoji> "
            f"REMOVE VOTES</b>\n\n"

            f"Send: <code>USER_ID VOTES</code>\n"
            f"Example: <code>12345678 5</code>"
        ),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    premium_button(
                        "BACK",
                        callback_data=f"manage_{giveaway_id}",
                        emoji_id=EMOJI_BACK,
                        style=BUTTON_STYLE_PRIMARY,
                    )
                ]
            ]
        ),
    )


async def process_vote_change(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    if not update.message:
        return

    giveaway_id = context.user_data.get(
        "vote_giveaway"
    )

    action = context.user_data.get(
        "vote_action"
    )

    if not giveaway_id or giveaway_id not in giveaways:
        return

    try:

        parts = update.message.text.strip().split()

        if len(parts) != 2:
            raise ValueError

        target_uid = int(parts[0])
        votes = int(parts[1])

        if votes <= 0:
            raise ValueError

    except (ValueError, TypeError):

        await update.message.reply_text(
            (
                f"<tg-emoji emoji-id='{EMOJI_ALERT}'>🚨</tg-emoji> "
                f"Invalid! Send "
                f"<code>USER_ID VOTES</code>."
            ),
            parse_mode="HTML",
        )

        return

    giveaway = giveaways[giveaway_id]

    if target_uid not in giveaway.get("users", {}):

        await update.message.reply_text(
            (
                f"<tg-emoji emoji-id='{EMOJI_ERROR}'>❌</tg-emoji> "
                f"User not found!"
            ),
            parse_mode="HTML",
        )

        return

    if giveaway.get("ended"):

        await update.message.reply_text(
            "❌ This giveaway has already ended.",
            parse_mode="HTML",
        )

        return

    old_votes = int(
        giveaway.get(
            "vote_counts",
            {},
        ).get(
            target_uid,
            0,
        )
    )

    if action == "add":

        giveaway["vote_counts"][target_uid] = (
            old_votes + votes
        )

        msg = (
            f"<tg-emoji emoji-id='{EMOJI_DIAMOND}'>💎</tg-emoji> "
            f"Added +{votes} votes!"
        )

    else:

        giveaway["vote_counts"][target_uid] = max(
            0,
            old_votes - votes,
        )

        msg = (
            f"<tg-emoji emoji-id='{EMOJI_DIAMOND}'>💎</tg-emoji> "
            f"Removed {votes} votes!"
        )

    new_votes = giveaway["vote_counts"][target_uid]

    save_data()

    await update_vote_button_in_channel(
        context,
        giveaway_id,
        target_uid,
        new_votes,
    )

    await update.message.reply_text(
        (
            f"{msg}\n"
            f"<b>New Total:</b> {new_votes} votes"
        ),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    premium_button(
                        "BACK",
                        callback_data=f"manage_{giveaway_id}",
                        emoji_id=EMOJI_BACK,
                        style=BUTTON_STYLE_PRIMARY,
                    )
                ]
            ]
        ),
    )

    context.user_data.pop(
        "vote_giveaway",
        None,
    )

    context.user_data.pop(
        "vote_action",
        None,
    )


async def show_leaderboard(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    query = update.callback_query

    await query.answer()

    giveaway_id = query.data.split("_", 1)[1]

    if giveaway_id not in giveaways:
        await query.answer(
            "Giveaway not found!",
            show_alert=True,
        )
        return

    giveaway = giveaways[giveaway_id]

    sorted_users = sorted(
        giveaway.get(
            "vote_counts",
            {},
        ).items(),
        key=lambda x: x[1],
        reverse=True,
    )[:10]

    text = (
        f"<b><tg-emoji emoji-id='{EMOJI_CALENDAR}'>🗓</tg-emoji> "
        f"LEADERBOARD</b>\n\n"
    )

    if not sorted_users:

        text += "<i>No votes yet.</i>"

    else:

        for idx, (uid, votes) in enumerate(
            sorted_users,
            1,
        ):

            name = giveaway.get(
                "users",
                {},
            ).get(
                uid,
                f"User {uid}",
            )

            text += (
                f"<b>{idx}.</b> "
                f"{safe_html(name)} - "
                f"<b>{votes} votes</b>\n"
            )

    await query.edit_message_text(
        text=text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    premium_button(
                        "BACK",
                        callback_data=f"manage_{giveaway_id}",
                        emoji_id=EMOJI_BACK,
                        style=BUTTON_STYLE_PRIMARY,
                    )
                ]
            ]
        ),
    )


# ============================================================
# END GIVEAWAY
# ============================================================

async def end_giveaway(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    query = update.callback_query

    await query.answer()

    giveaway_id = query.data.split("_", 1)[1]

    if giveaway_id not in giveaways:
        await query.answer(
            "Giveaway not found!",
            show_alert=True,
        )
        return

    await query.edit_message_text(
        text=(
            f"<b><tg-emoji emoji-id='{EMOJI_LOCK}'>⚠️</tg-emoji> "
            f"End this giveaway?</b>"
        ),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    premium_button(
                        "CONFIRM",
                        callback_data=f"confirm_end_{giveaway_id}",
                        emoji_id=EMOJI_CONFIRM,
                        style=BUTTON_STYLE_DANGER,
                    )
                ],
                [
                    premium_button(
                        "CANCEL",
                        callback_data=f"manage_{giveaway_id}",
                        emoji_id=EMOJI_CANCEL,
                        style=BUTTON_STYLE_PRIMARY,
                    )
                ],
            ]
        ),
    )


async def confirm_end_giveaway(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    query = update.callback_query

    await query.answer()

    giveaway_id = query.data.split("_", 2)[2]

    if giveaway_id not in giveaways:
        await query.answer(
            "Giveaway not found!",
            show_alert=True,
        )
        return

    giveaway = giveaways[giveaway_id]

    if (
        query.from_user.id != giveaway.get("creator")
        and not is_owner(query.from_user.id)
    ):

        await query.answer(
            "You don't have permission.",
            show_alert=True,
        )

        return

    if giveaway.get("ended"):

        await query.edit_message_text(
            "⚠️ Giveaway is already ended.",
            parse_mode="HTML",
        )

        return

    giveaway["ended"] = True

    sorted_users = sorted(
        giveaway.get(
            "vote_counts",
            {},
        ).items(),
        key=lambda x: x[1],
        reverse=True,
    )

    winner_text = "No participants."

    if sorted_users:

        w_uid, w_votes = sorted_users[0]

        winner_name = giveaway.get(
            "users",
            {},
        ).get(
            w_uid,
            f"User {w_uid}",
        )

        winner_text = (
            f"🏆 <b>WINNER:</b> "
            f"{safe_html(winner_name)} "
            f"with {w_votes} votes!"
        )

    update_channel_history(
        channel_identifier=giveaway.get("channel"),
        channel_display=giveaway.get("channel_display"),
        channel_id=giveaway.get("channel_id"),
        user_id=giveaway.get("creator"),
        user_name=giveaway.get(
            "creator_name",
            "Unknown",
        ),
        action="end",
        giveaway_id=giveaway_id,
    )

    save_data()

    vote_messages.pop(
        giveaway_id,
        None,
    )

    try:

        await context.bot.send_message(
            chat_id=giveaway["channel_id"],
            text=(
                f"💰 <b>GIVEAWAY ENDED!</b>\n\n"
                f"{winner_text}"
            ),
            parse_mode="HTML",
        )

    except Exception as e:

        logger.warning(
            "Failed to send ending announcement: %s",
            e,
        )

    await query.edit_message_text(
        text=(
            f"✅ <b>Giveaway ended!</b>\n\n"
            f"{winner_text}"
        ),
        parse_mode="HTML",
    )


# ============================================================
# JOIN HANDLER
# ============================================================

async def handle_join(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    query = update.callback_query

    await query.answer()

    giveaway_id = query.data.split("_", 1)[1]
    user = query.from_user

    if giveaway_id not in giveaways:

        await query.answer(
            "Giveaway not found!",
            show_alert=True,
        )

        return

    giveaway = giveaways[giveaway_id]

    if giveaway.get("ended"):

        await query.answer(
            "❌ This giveaway has already ended!",
            show_alert=True,
        )

        return

    # --------------------------------------------------------
    # Prevent duplicate registration
    # --------------------------------------------------------

    if user.id in giveaway.get("users", {}):

        await query.answer(
            "⚠️ Already Joined!",
            show_alert=True,
        )

        return

    save_user(
        user.id,
        user.username,
        user.first_name,
        user.last_name,
        source="join",
    )

    # --------------------------------------------------------
    # Membership check FIRST
    # --------------------------------------------------------

    is_member = await check_channel_membership(
        context,
        giveaway.get("channel_id"),
        user.id,
    )

    if not is_member:

        channel_display = giveaway.get(
            "channel_display",
            giveaway.get(
                "channel",
                "Channel",
            ),
        )

        channel_identifier = giveaway.get(
            "channel",
            "",
        )

        channel_link = await get_channel_link(
            context,
            giveaway.get("channel_id"),
            channel_identifier,
        )

        keyboard = [
            [
                premium_button(
                    "JOIN CHANNEL",
                    url=channel_link,
                    emoji_id=EMOJI_CHANNEL,
                    style=BUTTON_STYLE_SUCCESS,
                )
            ],
            [
                premium_button(
                    "TRY AGAIN",
                    callback_data=f"retry_join_{giveaway_id}",
                    emoji_id=EMOJI_REFRESH,
                    style=BUTTON_STYLE_PRIMARY,
                )
            ],
        ]

        await query.edit_message_text(
            (
                f"<tg-emoji emoji-id='{EMOJI_ALERT}'>⚠️</tg-emoji> "
                f"<b>CHANNEL MEMBERSHIP REQUIRED</b>\n\n"

                f"<tg-emoji emoji-id='{EMOJI_GIFT}'>🎁</tg-emoji> "
                f"<b>Giveaway Host:</b> "
                f"{safe_html(channel_display)}\n\n"

                f"<i>You need to join the channel first "
                f"to participate!</i>\n\n"

                f"<b>Steps to join:</b>\n"
                f"1️⃣ Click <b>JOIN CHANNEL</b> below\n"
                f"2️⃣ Join the channel\n"
                f"3️⃣ Click <b>TRY AGAIN</b> to verify membership"
            ),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
        )

        return

    # --------------------------------------------------------
    # Register participant
    # --------------------------------------------------------

    user_name = (
        user.full_name
        or user.first_name
        or f"User {user.id}"
    )

    giveaway.setdefault(
        "users",
        {}
    )

    giveaway.setdefault(
        "vote_counts",
        {}
    )

    giveaway.setdefault(
        "voted_users",
        {}
    )

    giveaway["users"][user.id] = user_name
    giveaway["vote_counts"][user.id] = 0
    giveaway["voted_users"][user.id] = set()

    update_user_stats(
        user.id,
        "join",
    )

    save_data()

    await query.answer(
        "✅ Registration Successful!",
        show_alert=True,
    )

    channel_text = (
        f"<tg-emoji emoji-id='{EMOJI_SMILE}'>😎</tg-emoji> "
        f"<b>Name:</b> {safe_html(user_name)}\n"

        f"<tg-emoji emoji-id='{EMOJI_ID}'>💌</tg-emoji> "
        f"<b>ID:</b> <code>{user.id}</code>"
    )

    vote_keyboard = [
        [
            premium_button(
                "Vote - 0",
                callback_data=(
                    f"vote_{giveaway_id}_{user.id}"
                ),
                emoji_id=EMOJI_VOTE,
                style=BUTTON_STYLE_SUCCESS,
            )
        ]
    ]

    try:

        sent_msg = await context.bot.send_message(
            chat_id=giveaway["channel_id"],
            text=channel_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                vote_keyboard
            ),
        )

        vote_messages.setdefault(
            giveaway_id,
            {},
        )

        vote_messages[giveaway_id][user.id] = (
            sent_msg.message_id
        )

    except Exception as e:

        logger.error(
            "Error sending participant to channel: %s",
            e,
        )

    await query.edit_message_text(
        text=(
            f"✅ <b>Registration Successful!</b>\n\n"

            f"😎 {safe_html(user_name)}\n"
            f"💌 <code>{user.id}</code>\n\n"

            f"📥 Profile shared in channel!"
        ),
        parse_mode="HTML",
    )


# ============================================================
# VOTE HANDLER
# ============================================================

async def handle_vote(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    query = update.callback_query

    # Parse callback safely.
    parts = query.data.split("_")

    if len(parts) != 3:

        await query.answer(
            "Invalid vote button.",
            show_alert=True,
        )

        return

    giveaway_id = parts[1]

    try:
        target_user_id = int(parts[2])
    except ValueError:

        await query.answer(
            "Invalid user ID.",
            show_alert=True,
        )

        return

    voter_id = query.from_user.id

    if giveaway_id not in giveaways:

        await query.answer(
            "❌ Giveaway not active!",
            show_alert=True,
        )

        return

    giveaway = giveaways[giveaway_id]

    if giveaway.get("ended"):

        await query.answer(
            "❌ This giveaway has ended!",
            show_alert=True,
        )

        return

    # Make sure target is an actual participant.
    if target_user_id not in giveaway.get("users", {}):

        await query.answer(
            "❌ User is not participating.",
            show_alert=True,
        )

        return

    # --------------------------------------------------------
    # Check voter membership
    # --------------------------------------------------------

    is_member = await check_channel_membership(
        context,
        giveaway.get("channel_id"),
        voter_id,
    )

    if not is_member:

        await query.answer(
            "⚠️ Only channel members can vote! "
            "Please join the channel first.",
            show_alert=True,
        )

        return

    # --------------------------------------------------------
    # Make sure voter is registered in all_users
    # --------------------------------------------------------

    voter = query.from_user

    save_user(
        voter.id,
        voter.username,
        voter.first_name,
        voter.last_name,
        source="vote",
    )

    # --------------------------------------------------------
    # Duplicate vote check
    # --------------------------------------------------------

    giveaway.setdefault(
        "voted_users",
        {}
    )

    giveaway["voted_users"].setdefault(
        target_user_id,
        set(),
    )

    voted_by = giveaway["voted_users"][
        target_user_id
    ]

    # Convert legacy list to set if needed.
    if isinstance(voted_by, list):

        voted_by = {
            int(v)
            for v in voted_by
            if normalize_user_id(v) is not None
        }

        giveaway["voted_users"][
            target_user_id
        ] = voted_by

    if voter_id in voted_by:

        await query.answer(
            "⚠️ You have already voted for this user!",
            show_alert=True,
        )

        return

    # --------------------------------------------------------
    # Record vote
    # --------------------------------------------------------

    voted_by.add(voter_id)

    giveaway.setdefault(
        "vote_counts",
        {}
    )

    giveaway["vote_counts"][target_user_id] = (
        giveaway["vote_counts"].get(
            target_user_id,
            0,
        ) + 1
    )

    new_votes = giveaway["vote_counts"][
        target_user_id
    ]

    # Only count the vote after all validation succeeded.
    update_user_stats(
        voter_id,
        "vote",
    )

    save_data()

    await update_vote_button_in_channel(
        context,
        giveaway_id,
        target_user_id,
        new_votes,
    )

    await query.answer(
        "🎉 Vote recorded!",
        show_alert=False,
    )


# ============================================================
# ADMIN COMMANDS
# ============================================================

async def admin_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    user_id = update.effective_user.id

    if not is_owner(user_id):

        await update.message.reply_text(
            "❌ You are not the owner!"
        )

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

    await update.message.reply_text(
        text,
        parse_mode="HTML",
    )


async def bc_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    user_id = update.effective_user.id

    if not is_owner(user_id):

        await update.message.reply_text(
            "❌ You are not the owner!"
        )

        return

    if not context.args:

        await update.message.reply_text(
            "❌ Usage: /bc <message>"
        )

        return

    msg = " ".join(context.args)

    await update.message.reply_text(
        (
            f"🚀 <b>Sending to all channels...</b>\n\n"
            f"Message: {safe_html(msg[:100])}..."
        ),
        parse_mode="HTML",
    )

    success = 0
    fail = 0
    channels_sent = set()

    for gid, gdata in giveaways.items():

        channel_id = gdata.get(
            "channel_id"
        )

        if (
            channel_id
            and channel_id not in channels_sent
            and not gdata.get("ended", False)
        ):

            channels_sent.add(channel_id)

            try:

                await context.bot.send_message(
                    chat_id=channel_id,
                    text=msg,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )

                success += 1

            except Exception as e:

                logger.error(
                    "Failed to send to channel %s: %s",
                    channel_id,
                    e,
                )

                fail += 1

            await asyncio.sleep(0.5)

    await update.message.reply_text(
        (
            f"<b>✅ BROADCAST TO CHANNELS COMPLETED!</b>\n\n"

            f"<b>✅ Sent:</b> <code>{success}</code>\n"
            f"<b>❌ Failed:</b> <code>{fail}</code>\n"
            f"<b>📊 Total Channels:</b> "
            f"<code>{len(channels_sent)}</code>"
        ),
        parse_mode="HTML",
    )


async def ball_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    user_id = update.effective_user.id

    if not is_owner(user_id):

        await update.message.reply_text(
            "❌ You are not the owner!"
        )

        return

    if not context.args:

        await update.message.reply_text(
            "❌ Usage: /ball <message>"
        )

        return

    msg = " ".join(context.args)

    await update.message.reply_text(
        (
            f"🚀 <b>Sending to ALL USERS + ALL CHANNELS...</b>\n\n"
            f"Message: {safe_html(msg[:100])}..."
        ),
        parse_mode="HTML",
    )

    user_success = 0
    user_fail = 0

    for uid in list(all_users.keys()):

        try:

            await context.bot.send_message(
                chat_id=int(uid),
                text=msg,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )

            user_success += 1

        except Exception:

            user_fail += 1

        await asyncio.sleep(0.05)

    channel_success = 0
    channel_fail = 0
    channels_sent = set()

    for gid, gdata in giveaways.items():

        channel_id = gdata.get(
            "channel_id"
        )

        if (
            channel_id
            and channel_id not in channels_sent
            and not gdata.get("ended", False)
        ):

            channels_sent.add(channel_id)

            try:

                await context.bot.send_message(
                    chat_id=channel_id,
                    text=msg,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )

                channel_success += 1

            except Exception as e:

                logger.error(
                    "Failed to send to channel %s: %s",
                    channel_id,
                    e,
                )

                channel_fail += 1

            await asyncio.sleep(0.5)

    await update.message.reply_text(
        (
            f"<b>✅ BALL BROADCAST COMPLETED!</b>\n\n"

            f"<b>📱 USERS:</b>\n"
            f"   ✅ Sent: <code>{user_success}</code>\n"
            f"   ❌ Failed: <code>{user_fail}</code>\n"
            f"   📊 Total: <code>{len(all_users)}</code>\n\n"

            f"<b>📺 CHANNELS:</b>\n"
            f"   ✅ Sent: <code>{channel_success}</code>\n"
            f"   ❌ Failed: <code>{channel_fail}</code>\n"
            f"   📊 Total: <code>{len(channels_sent)}</code>"
        ),
        parse_mode="HTML",
    )


async def g_management_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    user_id = update.effective_user.id

    if not is_owner(user_id):

        await update.message.reply_text(
            "❌ You are not the owner!"
        )

        return

    if not context.args:

        await update.message.reply_text(
            "❌ Usage: /g_management <giveaway_id>"
        )

        return

    giveaway_id = context.args[0]

    if giveaway_id not in giveaways:

        await update.message.reply_text(
            f"❌ Giveaway '{safe_html(giveaway_id)}' not found!",
            parse_mode="HTML",
        )

        return

    giveaway = giveaways[giveaway_id]

    status = (
        "🟢 ACTIVE"
        if not giveaway.get("ended")
        else "🔴 ENDED"
    )

    keyboard = [
        [
            premium_button(
                "ADD VOTES",
                callback_data=f"addvotes_{giveaway_id}",
                emoji_id=EMOJI_ADD_VOTES,
                style=BUTTON_STYLE_PRIMARY,
            ),
            premium_button(
                "REMOVE VOTES",
                callback_data=f"removevotes_{giveaway_id}",
                emoji_id=EMOJI_REMOVE_VOTES,
                style=BUTTON_STYLE_DANGER,
            ),
        ],
        [
            premium_button(
                "LEADERBOARD",
                callback_data=f"leaderboard_{giveaway_id}",
                emoji_id=EMOJI_LEADERBOARD,
                style=BUTTON_STYLE_PRIMARY,
            )
        ],
        [
            premium_button(
                "END GIVEAWAY",
                callback_data=f"endgiveaway_{giveaway_id}",
                emoji_id=EMOJI_END_GIVEAWAY,
                style=BUTTON_STYLE_DANGER,
            )
        ],
    ]

    total_votes = sum(
        giveaway.get(
            "vote_counts",
            {},
        ).values()
    )

    await update.message.reply_text(
        text=(
            f"<b><tg-emoji emoji-id='{EMOJI_ARROW}'>➡️</tg-emoji> "
            f"MANAGEMENT PANEL (ADMIN)</b>\n\n"

            f"<b>Giveaway ID:</b> "
            f"<code>{safe_html(giveaway_id)}</code>\n"

            f"<b>Status:</b> {status}\n"

            f"<b>Channel:</b> "
            f"{safe_html(giveaway.get('channel_display', giveaway.get('channel')))}\n"

            f"<b>Creator:</b> "
            f"{safe_html(giveaway.get('creator_name', 'Unknown'))}\n"

            f"<b>Joined:</b> "
            f"{len(giveaway.get('users', {}))}\n"

            f"<b>Total Votes:</b> {total_votes}"
        ),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


# ============================================================
# ADD VOTE COMMAND
# ============================================================

async def add_vote_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    user_id = update.effective_user.id

    if not is_owner(user_id):

        await update.message.reply_text(
            "❌ You are not the owner!"
        )

        return

    if len(context.args) != 3:

        await update.message.reply_text(
            "❌ Usage: /add_vote <giveaway_id> <user_id> <votes>"
        )

        return

    giveaway_id = context.args[0]

    try:

        target_uid = int(context.args[1])
        votes = int(context.args[2])

        if votes <= 0:
            raise ValueError

    except ValueError:

        await update.message.reply_text(
            "❌ User ID and votes must be positive numbers."
        )

        return

    if giveaway_id not in giveaways:

        await update.message.reply_text(
            f"❌ Giveaway '{giveaway_id}' not found!"
        )

        return

    giveaway = giveaways[giveaway_id]

    if target_uid not in giveaway.get("users", {}):

        await update.message.reply_text(
            f"❌ User {target_uid} not found in this giveaway!"
        )

        return

    old_votes = giveaway.get(
        "vote_counts",
        {},
    ).get(
        target_uid,
        0,
    )

    giveaway["vote_counts"][target_uid] = (
        old_votes + votes
    )

    new_votes = giveaway["vote_counts"][target_uid]

    save_data()

    await update_vote_button_in_channel(
        context,
        giveaway_id,
        target_uid,
        new_votes,
    )

    await update.message.reply_text(
        (
            f"✅ <b>Votes Added!</b>\n\n"

            f"<b>Giveaway:</b> "
            f"<code>{giveaway_id}</code>\n"

            f"<b>User:</b> "
            f"<code>{target_uid}</code> "
            f"({safe_html(giveaway['users'][target_uid])})\n"

            f"<b>Added:</b> +{votes} votes\n"
            f"<b>New Total:</b> {new_votes} votes"
        ),
        parse_mode="HTML",
    )


# ============================================================
# REMOVE VOTE COMMAND
# ============================================================

async def remove_vote_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    user_id = update.effective_user.id

    if not is_owner(user_id):

        await update.message.reply_text(
            "❌ You are not the owner!"
        )

        return

    if len(context.args) != 3:

        await update.message.reply_text(
            "❌ Usage: /remove_vote <giveaway_id> <user_id> <votes>"
        )

        return

    giveaway_id = context.args[0]

    try:

        target_uid = int(context.args[1])
        votes = int(context.args[2])

        if votes <= 0:
            raise ValueError

    except ValueError:

        await update.message.reply_text(
            "❌ User ID and votes must be positive numbers."
        )

        return

    if giveaway_id not in giveaways:

        await update.message.reply_text(
            f"❌ Giveaway '{giveaway_id}' not found!"
        )

        return

    giveaway = giveaways[giveaway_id]

    if target_uid not in giveaway.get("users", {}):

        await update.message.reply_text(
            f"❌ User {target_uid} not found in this giveaway!"
        )

        return

    old_votes = giveaway.get(
        "vote_counts",
        {},
    ).get(
        target_uid,
        0,
    )

    giveaway["vote_counts"][target_uid] = max(
        0,
        old_votes - votes,
    )

    new_votes = giveaway["vote_counts"][target_uid]

    save_data()

    await update_vote_button_in_channel(
        context,
        giveaway_id,
        target_uid,
        new_votes,
    )

    await update.message.reply_text(
        (
            f"✅ <b>Votes Removed!</b>\n\n"

            f"<b>Giveaway:</b> "
            f"<code>{giveaway_id}</code>\n"

            f"<b>User:</b> "
            f"<code>{target_uid}</code> "
            f"({safe_html(giveaway['users'][target_uid])})\n"

            f"<b>Removed:</b> -{votes} votes\n"
            f"<b>New Total:</b> {new_votes} votes"
        ),
        parse_mode="HTML",
    )


# ============================================================
# BROADCAST
# ============================================================

async def broadcast_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    user_id = update.effective_user.id

    if not is_owner(user_id):

        await update.message.reply_text(
            "❌ You are not the owner!"
        )

        return

    if not context.args:

        admin_sessions[OWNER_ID] = {
            "step": "waiting_broadcast"
        }

        await update.message.reply_text(
            (
                "<b>📢 BROADCAST SYSTEM</b>\n\n"

                "Send your message below.\n\n"

                "<b>Supported HTML Tags:</b>\n"
                "<code>&lt;b&gt;bold&lt;/b&gt;</code>\n"
                "<code>&lt;i&gt;italic&lt;/i&gt;</code>\n"
                "<code>&lt;u&gt;underline&lt;/u&gt;</code>\n"
                "<code>&lt;s&gt;strikethrough&lt;/s&gt;</code>\n"
                "<code>&lt;a href='URL'&gt;link&lt;/a&gt;</code>\n"
                "<code>&lt;tg-emoji emoji-id='ID'&gt;🎁&lt;/tg-emoji&gt;</code>\n\n"

                f"<b>Total Users:</b> "
                f"<code>{len(all_users)}</code>\n\n"

                "Send /cancel to abort."
            ),
            parse_mode="HTML",
        )

        return

    msg = " ".join(context.args)

    await update.message.reply_text(
        (
            f"🚀 <b>Broadcast started!</b>\n\n"
            f"Total users: <code>{len(all_users)}</code>\n"
            f"This may take some time..."
        ),
        parse_mode="HTML",
    )

    success = 0
    fail = 0

    for uid in list(all_users.keys()):

        try:

            await context.bot.send_message(
                chat_id=int(uid),
                text=msg,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )

            success += 1

        except Exception:

            fail += 1

        await asyncio.sleep(0.05)

    await update.message.reply_text(
        (
            f"<b>✅ BROADCAST COMPLETED!</b>\n\n"

            f"<b>✅ Sent:</b> "
            f"<code>{success}</code>\n"

            f"<b>❌ Failed:</b> "
            f"<code>{fail}</code>\n"

            f"<b>📊 Total:</b> "
            f"<code>{len(all_users)}</code>"
        ),
        parse_mode="HTML",
    )


# ============================================================
# STATISTICS
# ============================================================

async def stats_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    user_id = update.effective_user.id

    if not is_owner(user_id):

        await update.message.reply_text(
            "❌ You are not the owner!"
        )

        return

    active = sum(
        1
        for g in giveaways.values()
        if not g.get("ended", False)
    )

    participants = sum(
        len(g.get("users", {}))
        for g in giveaways.values()
    )

    votes = sum(
        sum(
            g.get(
                "vote_counts",
                {},
            ).values()
        )
        for g in giveaways.values()
    )

    text = (
        f"<b><tg-emoji emoji-id='{EMOJI_STATS}'>📊</tg-emoji> "
        f"BOT STATISTICS</b>\n\n"

        f"<b>👥 Users:</b> "
        f"<code>{len(all_users)}</code>\n"

        f"<b>🎁 Giveaways:</b> "
        f"<code>{len(giveaways)}</code>\n"

        f"<b>🟢 Active:</b> "
        f"<code>{active}</code>\n"

        f"<b>📺 Channels:</b> "
        f"<code>{len(channel_history)}</code>\n"

        f"<b>👤 Participants:</b> "
        f"<code>{participants}</code>\n"

        f"<b>🗳️ Votes:</b> "
        f"<code>{votes}</code>"
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
    )


# ============================================================
# USERS
# ============================================================

async def users_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    user_id = update.effective_user.id

    if not is_owner(user_id):

        await update.message.reply_text(
            "❌ You are not the owner!"
        )

        return

    users_list = list(
        all_users.values()
    )[-15:]

    users_list.reverse()

    text = (
        f"<b><tg-emoji emoji-id='{EMOJI_USERS}'>👥</tg-emoji> "
        f"RECENT USERS</b>\n\n"
    )

    for u in users_list:

        username = u.get(
            "username"
        )

        username_display = (
            f"@{username}"
            if username
            else "@no"
        )

        text += (
            f"<b>👤 "
            f"{safe_html(u.get('first_name', 'Unknown'))}</b>\n"

            f"   🆔 "
            f"<code>{u.get('user_id')}</code>\n"

            f"   📝 "
            f"{safe_html(username_display)}\n"

            f"   📍 "
            f"{safe_html(u.get('source', '?'))}\n\n"
        )

    text += (
        f"\n<b>Total Users:</b> "
        f"<code>{len(all_users)}</code>"
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
    )


# ============================================================
# CHANNEL HISTORY
# ============================================================

async def channels_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    user_id = update.effective_user.id

    if not is_owner(user_id):

        await update.message.reply_text(
            "❌ You are not the owner!"
        )

        return

    text = (
        f"<b><tg-emoji emoji-id='{EMOJI_CHANNEL}'>📺</tg-emoji> "
        f"CHANNEL GIVEAWAY HISTORY</b>\n\n"
    )

    text += (
        "<b>🟢 ACTIVE GIVEAWAYS</b>\n"
        "<code>─────────────────</code>\n"
    )

    active_found = False

    for ch_key, ch_data in channel_history.items():

        active_giveaways = [
            g
            for g in ch_data.get(
                "giveaways",
                [],
            )
            if g.get("status") == "active"
        ]

        if active_giveaways:

            active_found = True

            text += (
                f"\n<b>📢 "
                f"{safe_html(ch_data.get('channel_display', 'Unknown'))}"
                f"</b>\n"
            )

            text += (
                f"   🔍 Type: "
                f"<code>"
                f"{safe_html(ch_data.get('type', 'unknown')).upper()}"
                f"</code>\n"
            )

            text += (
                f"   🆔 ID: "
                f"<code>{ch_data.get('channel_id', 'N/A')}</code>\n"
            )

            text += (
                f"   👤 Owner: "
                f"{safe_html(ch_data.get('created_by_name', 'Unknown'))}\n"
            )

            for g in active_giveaways:

                text += (
                    f"      • ID: "
                    f"<code>{g.get('giveaway_id', 'N/A')}</code>\n"
                )

                text += (
                    f"        📅 Created: "
                    f"{g.get('created_at', '')[:10]}\n"
                )

    if not active_found:

        text += "<i>No active giveaways</i>\n"

    text += (
        "\n<b>🔴 GIVEAWAY HISTORY</b>\n"
        "<code>─────────────────</code>\n"
    )

    ended_found = False

    for ch_key, ch_data in list(
        channel_history.items()
    )[-10:]:

        ended_giveaways = [
            g
            for g in ch_data.get(
                "giveaways",
                [],
            )
            if g.get("status") == "ended"
        ]

        if ended_giveaways:

            ended_found = True

            text += (
                f"\n<b>📢 "
                f"{safe_html(ch_data.get('channel_display', 'Unknown'))}"
                f"</b>\n"
            )

            text += (
                f"   🔍 Type: "
                f"<code>"
                f"{safe_html(ch_data.get('type', 'unknown')).upper()}"
                f"</code>\n"
            )

            text += (
                f"   🆔 ID: "
                f"<code>{ch_data.get('channel_id', 'N/A')}</code>\n"
            )

            text += (
                f"   👤 Owner: "
                f"{safe_html(ch_data.get('created_by_name', 'Unknown'))}\n"
            )

            text += (
                f"   🎁 Total: "
                f"<code>{ch_data.get('total_giveaways', 0)}</code> "
                f"giveaways\n"
            )

    if not ended_found:

        text += (
            "<i>No giveaway history yet</i>\n"
        )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
    )


# ============================================================
# BACKUP
# ============================================================

async def backup_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    user_id = update.effective_user.id

    if not is_owner(user_id):

        await update.message.reply_text(
            "❌ You are not the owner!"
        )

        return

    success = save_data()

    if success:

        await update.message.reply_text(
            (
                f"<b>✅ BACKUP CREATED!</b>\n\n"

                f"<b>💾 File:</b> "
                f"<code>{safe_html(DATA_FILE)}</code>\n"

                f"<b>👥 Users:</b> "
                f"<code>{len(all_users)}</code>\n"

                f"<b>🎁 Giveaways:</b> "
                f"<code>{len(giveaways)}</code>\n"

                f"<b>📺 Channels:</b> "
                f"<code>{len(channel_history)}</code>\n\n"

                "<i>Data is automatically saved on every change.</i>"
            ),
            parse_mode="HTML",
        )

    else:

        await update.message.reply_text(
            "❌ Backup failed. Check the bot logs.",
            parse_mode="HTML",
        )


# ============================================================
# SETTINGS
# ============================================================

async def settings_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    user_id = update.effective_user.id

    if not is_owner(user_id):

        await update.message.reply_text(
            "❌ You are not the owner!"
        )

        return

    await update.message.reply_text(
        (
            f"<b><tg-emoji emoji-id='{EMOJI_SETTINGS}'>⚙️</tg-emoji> "
            f"SETTINGS</b>\n\n"

            f"<b>Bot Username:</b> "
            f"@{safe_html(BOT_USERNAME)}\n"

            f"<b>Owner ID:</b> "
            f"<code>{OWNER_ID}</code>\n"

            f"<b>Data File:</b> "
            f"<code>{safe_html(DATA_FILE)}</code>\n"

            f"<b>Auto Save:</b> ✅ Enabled\n"
            f"<b>User Tracking:</b> ✅ Enabled\n"
            f"<b>Channel History:</b> ✅ Enabled\n"
            f"<b>Auto Vote Update:</b> ✅ Enabled\n\n"

            "<i>Settings are managed via bot configuration.</i>"
        ),
        parse_mode="HTML",
    )


# ============================================================
# TEST NOTIFICATION
# ============================================================

async def testnotify_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    user_id = update.effective_user.id

    if not is_owner(user_id):

        await update.message.reply_text(
            "❌ You are not the owner!"
        )

        return

    await send_notification_to_owner(
        context,
        "🔔 TEST NOTIFICATION",
        (
            "This is a test notification from your bot!\n\n"
            "All systems working fine."
        ),
    )

    await update.message.reply_text(
        "✅ Test notification sent to owner!",
        parse_mode="HTML",
    )


# ============================================================
# CLEAR DATABASE
# ============================================================

async def clear_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    user_id = update.effective_user.id

    if not is_owner(user_id):

        await update.message.reply_text(
            "❌ You are not the owner!"
        )

        return

    keyboard = InlineKeyboardMarkup(
        [
            [
                premium_button(
                    "✅ CONFIRM CLEAR",
                    callback_data="confirm_clear",
                    emoji_id=EMOJI_CLEAR,
                    style=BUTTON_STYLE_DANGER,
                ),
                premium_button(
                    "❌ CANCEL",
                    callback_data="main_menu",
                    emoji_id=EMOJI_CANCEL,
                    style=BUTTON_STYLE_PRIMARY,
                ),
            ]
        ]
    )

    await update.message.reply_text(
        (
            f"<b><tg-emoji emoji-id='{EMOJI_ALERT}'>⚠️</tg-emoji> "
            f"DANGER ZONE</b>\n\n"

            f"Are you sure you want to clear ALL data?\n\n"

            f"This will delete:\n"
            f"• <code>{len(all_users)}</code> users\n"
            f"• <code>{len(giveaways)}</code> giveaways\n"
            f"• <code>{len(channel_history)}</code> channel histories\n\n"

            f"<b>This action cannot be undone!</b>"
        ),
        parse_mode="HTML",
        reply_markup=keyboard,
    )


async def confirm_clear_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    global giveaways
    global all_users
    global channel_history
    global vote_messages
    global user_sessions
    global admin_sessions

    query = update.callback_query

    await query.answer()

    user_id = query.from_user.id

    if not is_owner(user_id):

        await query.edit_message_text(
            "❌ You are not the owner!",
            parse_mode="HTML",
        )

        return

    giveaways = {}
    all_users = {}
    channel_history = {}

    vote_messages = {}
    user_sessions = {}
    admin_sessions = {}

    # Also clear the current Telegram context data.
    context.user_data.clear()

    save_data()

    await query.edit_message_text(
        (
            "✅ <b>All data cleared successfully!</b>\n\n"
            "Bot data has been reset."
        ),
        parse_mode="HTML",
    )


# ============================================================
# BROADCAST SESSION
# ============================================================

async def process_broadcast(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    if not update.message:
        return

    user_id = update.effective_user.id

    if (
        user_id != OWNER_ID
        or admin_sessions.get(
            OWNER_ID,
            {},
        ).get("step")
        != "waiting_broadcast"
    ):
        return

    if update.message.text.strip().lower() == "/cancel":

        admin_sessions.pop(
            OWNER_ID,
            None,
        )

        await update.message.reply_text(
            "❌ Broadcast cancelled!",
            parse_mode="HTML",
        )

        return

    msg = update.message.text

    await update.message.reply_text(
        (
            f"🚀 <b>Broadcast started!</b>\n\n"
            f"Total users: <code>{len(all_users)}</code>\n"
            f"This may take some time..."
        ),
        parse_mode="HTML",
    )

    success = 0
    fail = 0

    for uid in list(all_users.keys()):

        try:

            await context.bot.send_message(
                chat_id=int(uid),
                text=msg,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )

            success += 1

        except Exception:

            fail += 1

        await asyncio.sleep(0.05)

    admin_sessions.pop(
        OWNER_ID,
        None,
    )

    await update.message.reply_text(
        (
            f"<b>✅ BROADCAST COMPLETED!</b>\n\n"

            f"<b>✅ Sent:</b> "
            f"<code>{success}</code>\n"

            f"<b>❌ Failed:</b> "
            f"<code>{fail}</code>\n"

            f"<b>📊 Total:</b> "
            f"<code>{len(all_users)}</code>"
        ),
        parse_mode="HTML",
    )


# ============================================================
# MAIN MENU
# ============================================================

async def main_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    query = update.callback_query

    await query.answer()

    await query.edit_message_text(
        text="<b>🌐 MAIN MENU</b>",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


# ============================================================
# CALLBACK ROUTER
# ============================================================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    query = update.callback_query

    if not query:
        return

    data = query.data or ""

    logger.info(
        "Button pressed by %s: %s",
        query.from_user.id,
        data,
    )

    try:

        if data == "confirm_clear":

            await confirm_clear_callback(
                update,
                context,
            )

        elif data == "create_giveaway":

            await create_giveaway_flow(
                update,
                context,
            )

        elif data == "cancel_creation":

            await cancel_creation(
                update,
                context,
            )

        elif data == "my_giveaways":

            await my_giveaways(
                update,
                context,
            )

        elif data == "main_menu":

            await main_menu(
                update,
                context,
            )

        elif data.startswith("retry_join_"):

            await retry_join(
                update,
                context,
            )

        elif data.startswith("manage_"):

            await manage_giveaway(
                update,
                context,
            )

        elif data.startswith("addvotes_"):

            await add_votes_flow(
                update,
                context,
            )

        elif data.startswith("removevotes_"):

            await remove_votes_flow(
                update,
                context,
            )

        elif data.startswith("leaderboard_"):

            await show_leaderboard(
                update,
                context,
            )

        elif data.startswith("endgiveaway_"):

            await end_giveaway(
                update,
                context,
            )

        elif data.startswith("confirm_end_"):

            await confirm_end_giveaway(
                update,
                context,
            )

        elif data.startswith("join_"):

            await handle_join(
                update,
                context,
            )

        elif data.startswith("vote_"):

            await handle_vote(
                update,
                context,
            )

        else:

            await query.answer(
                "Unknown button.",
                show_alert=True,
            )

    except Exception as e:

        logger.exception(
            "Callback error for %s: %s",
            data,
            e,
        )

        try:

            await query.answer(
                "⚠️ Something went wrong.",
                show_alert=True,
            )

        except Exception:
            pass


# ============================================================
# TEXT MESSAGE ROUTER
# ============================================================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    # Owner broadcast session
    if (
        user_id == OWNER_ID
        and admin_sessions.get(
            OWNER_ID,
            {},
        ).get("step")
        == "waiting_broadcast"
    ):

        await process_broadcast(
            update,
            context,
        )

        return

    # Giveaway creation session
    if (
        user_id in user_sessions
        and user_sessions[user_id].get("step")
        == "waiting_channel"
    ):

        await process_channel(
            update,
            context,
        )

        return

    # Vote modification session
    if "vote_giveaway" in context.user_data:

        await process_vote_change(
            update,
            context,
        )

        return


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    logger.exception(
        "Unhandled bot error: %s",
        context.error,
    )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    if not TOKEN:

        raise RuntimeError(
            "BOT_TOKEN environment variable is missing."
        )

    if not OWNER_ID:

        raise RuntimeError(
            "OWNER_ID environment variable is missing or invalid."
        )

    load_data()

    request = HTTPXRequest(
        connect_timeout=30,
        read_timeout=30,
        write_timeout=30,
        pool_timeout=30,
    )

    app = (
        Application.builder()
        .token(TOKEN)
        .request(request)
        .build()
    )

    # --------------------------------------------------------
    # USER COMMANDS
    # --------------------------------------------------------

    app.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    # --------------------------------------------------------
    # ADMIN COMMANDS
    # --------------------------------------------------------

    app.add_handler(
        CommandHandler(
            "admin",
            admin_command,
        )
    )

    app.add_handler(
        CommandHandler(
            "broadcast",
            broadcast_command,
        )
    )

    app.add_handler(
        CommandHandler(
            "bc",
            bc_command,
        )
    )

    app.add_handler(
        CommandHandler(
            "ball",
            ball_command,
        )
    )

    app.add_handler(
        CommandHandler(
            "stats",
            stats_command,
        )
    )

    app.add_handler(
        CommandHandler(
            "users",
            users_command,
        )
    )

    app.add_handler(
        CommandHandler(
            "channels",
            channels_command,
        )
    )

    app.add_handler(
        CommandHandler(
            "backup",
            backup_command,
        )
    )

    app.add_handler(
        CommandHandler(
            "settings",
            settings_command,
        )
    )

    app.add_handler(
        CommandHandler(
            "testnotify",
            testnotify_command,
        )
    )

    app.add_handler(
        CommandHandler(
            "clear",
            clear_command,
        )
    )

    app.add_handler(
        CommandHandler(
            "g_management",
            g_management_command,
        )
    )

    app.add_handler(
        CommandHandler(
            "add_vote",
            add_vote_command,
        )
    )

    app.add_handler(
        CommandHandler(
            "remove_vote",
            remove_vote_command,
        )
    )

    # --------------------------------------------------------
    # CALLBACKS
    # --------------------------------------------------------

    app.add_handler(
        CallbackQueryHandler(
            button_handler
        )
    )

    # --------------------------------------------------------
    # TEXT
    # --------------------------------------------------------

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message,
        )
    )

    # --------------------------------------------------------
    # ERROR HANDLER
    # --------------------------------------------------------

    app.add_error_handler(
        error_handler
    )

    # --------------------------------------------------------
    # STARTUP LOG
    # --------------------------------------------------------

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
    print("   /testnotify - Test notification")
    print("   /clear - Delete all data")
    print("   /g_management <id> - Open giveaway panel")
    print("   /add_vote <id> <user_id> <votes> - Add votes")
    print("   /remove_vote <id> <user_id> <votes> - Remove votes")

    print("=" * 60)

    print("\n✅ CHANNEL MEMBERSHIP SYSTEM:")
    print("   • Checks membership before joining")
    print("   • Shows JOIN CHANNEL button if not a member")
    print("   • Shows TRY AGAIN button to re-check")
    print("   • Supports member/administrator/creator/restricted")

    print("=" * 60)

    app.run_polling(
        allowed_updates=[
            "message",
            "callback_query",
        ]
    )


if __name__ == "__main__":
    main()
