"""
bot.py
------
Main entry point for the Telegram Games Bot.

Responsibilities:
    - Bot / Dispatcher initialization
    - Command routing (general, game, admin, owner)
    - Callback-query routing
    - Global single-active-game-per-chat management
    - Aviator & Flip mini-games (self-contained, no lobby needed)
    - Error handling, startup/shutdown

Run with:
    BOT_TOKEN=xxx OWNER_ID=123456789 python bot.py

All "coins" in this bot are virtual, in-game currency only. They carry no
real-world monetary value and cannot be bought, sold, deposited, or withdrawn.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

import database as db
from game1 import BaseGame, RajaMantriGame, ImpostorGame, FourCardMatchGame, RULES_TEXT_G1
from game2 import AntakshariGame, CardsGame, MakeTheBoxGame, RULES_TEXT_G2
from game3 import LudoGame, PowerRangersGame, BusinessTycoonGame

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
_OWNER_ID_RAW = os.environ.get("OWNER_ID", "").strip()

if not BOT_TOKEN:
    print("ERROR: BOT_TOKEN environment variable is not set.", file=sys.stderr)
    sys.exit(1)

if not _OWNER_ID_RAW or not _OWNER_ID_RAW.lstrip("-").isdigit():
    print("ERROR: OWNER_ID environment variable is not set to a valid integer.", file=sys.stderr)
    sys.exit(1)

OWNER_ID = int(_OWNER_ID_RAW)

STARTING_COINS = 1000          # coins a brand-new player starts with
LEADERBOARD_SIZE = 10
RICHLIST_SIZE = 30

# Aviator / Flip config
AVIATOR_MIN_BET = 10
AVIATOR_PRESETS = [50, 100, 250, 500, 1000]
AVIATOR_TICK_SECONDS = 0.9
AVIATOR_MAX_MULTIPLIER = 50.0
AVIATOR_MAX_TICKS = 120

FLIP_MIN_BET = 10
FLIP_WIN_MULTIPLIER = 2.0
FLIP_LOSE_MULTIPLIER = 0.2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("games_bot")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

START_TIME = datetime.utcnow()

# --------------------------------------------------------------------------
# Global active-game registry: one active multiplayer game per chat
# --------------------------------------------------------------------------

active_games: Dict[int, Any] = {}


def on_game_finish(chat_id: int) -> None:
    """Called by a game instance once it's fully done - clears the slot."""
    active_games.pop(chat_id, None)


# --------------------------------------------------------------------------
# Permission helpers
# --------------------------------------------------------------------------

def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


def is_admin(user_id: int) -> bool:
    """True only for explicitly appointed bot admins (not the owner)."""
    return db.is_admin_db(user_id)


def is_owner_or_admin(user_id: int) -> bool:
    return is_owner(user_id) or is_admin(user_id)


# --------------------------------------------------------------------------
# Game catalog (drives /games, /help, and command routing)
# --------------------------------------------------------------------------

GAME_CATALOG: List[Dict[str, Any]] = [
    {"key": "raja", "cls": RajaMantriGame, "cmd": "/raja", "join": "/raja_join",
     "start": "/raja_start", "rules": "/raja_rules", "label": "👑 Raja Mantri", "section": "👑 RAJA MANTRI"},
    {"key": "impostor", "cls": ImpostorGame, "cmd": "/impostor", "join": "/impostor_join",
     "start": "/impostor_start", "rules": "/impostor_rules", "vote": "/impostor_vote",
     "label": "🕵️ Impostor", "section": "🕵️ IMPOSTOR"},
    {"key": "4card", "cls": FourCardMatchGame, "cmd": "/4card", "join": "/4card_join",
     "start": "/4card_start", "rules": "/4card_rules", "label": "🃏 4 Card Match", "section": "🃏 4 CARD MATCH"},
    {"key": "antakshari", "cls": AntakshariGame, "cmd": "/antakshari", "join": "/anti_join",
     "start": "/anti_start", "rules": "/anti_rules", "label": "🎵 Antakshari", "section": "🎵 ANTAKSHARI"},
    {"key": "cards", "cls": CardsGame, "cmd": "/cards", "join": "/card_join",
     "start": "/card_start", "rules": "/card_rules", "label": "🃏 Cards", "section": "🃏 CARDS"},
    {"key": "box", "cls": MakeTheBoxGame, "cmd": "/box", "join": "/box_join",
     "start": "/box_start", "rules": "/box_rules", "label": "📦 Make The Box", "section": "📦 MAKE THE BOX"},
    {"key": "ludo", "cls": LudoGame, "cmd": "/ludo", "join": "/ludo_join",
     "start": "/ludo_start", "rules": "/ludo_rules", "label": "🎲 Ludo", "section": "🎲 LUDO"},
    {"key": "rangers", "cls": PowerRangersGame, "cmd": "/rangers", "join": "/ranger_join",
     "start": "/ranger_start", "rules": "/ranger_rules", "label": "⚡ Power Rangers", "section": "⚡ POWER RANGERS"},
    {"key": "business", "cls": BusinessTycoonGame, "cmd": "/business", "join": "/business_join",
     "start": "/business_start", "rules": "/business_rules", "label": "🏦 Business Tycoon", "section": "🏦 BUSINESS"},
]
CATALOG_BY_KEY = {g["key"]: g for g in GAME_CATALOG}


# --------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------

def ensure_user(message: Message) -> None:
    u = message.from_user
    if u is None:
        return
    db.register_user(u.id, u.username, u.first_name)
    db.touch_activity(u.id)
    if message.chat:
        db.register_chat(message.chat.id, message.chat.type, message.chat.title)


def fmt_user(user_row: Dict[str, Any]) -> str:
    # sqlite3.Row supports mapping/index access, but not .get().
    try:
        name = user_row["first_name"] or "Player"
    except (KeyError, TypeError, IndexError):
        name = "Player"
    try:
        username = user_row["username"]
    except (KeyError, TypeError, IndexError):
        username = None
    return f"@{username}" if username else name


async def launch_lobby(chat_id: int, creator_id: int, creator_name: str, key: str) -> str:
    """Create and post a new lobby for the given game key. Returns an error message or ''."""
    if chat_id in active_games:
        return "❌ A game is already running in this chat."
    entry = CATALOG_BY_KEY[key]
    game = entry["cls"](bot, chat_id, creator_id, creator_name)
    if hasattr(game, "on_finish"):
        game.on_finish = on_game_finish
    active_games[chat_id] = game
    if creator_id not in getattr(game, "players", {}):
        ok, msg = await game.add_player(creator_id, creator_name)
        if not ok:
            active_games.pop(chat_id, None)
            return msg
    await game.send_lobby()
    return ""


async def join_lobby(chat_id: int, key: str, user_id: int, name: str) -> str:
    entry = CATALOG_BY_KEY[key]
    game = active_games.get(chat_id)
    if not game or not isinstance(game, entry["cls"]):
        return f"❌ No open {entry['label']} lobby here. Start one with {entry['cmd']}."
    ok, msg = await game.add_player(user_id, name)
    if ok:
        await game._refresh_lobby()
    return msg


async def start_lobby(chat_id: int, key: str, user_id: int) -> str:
    entry = CATALOG_BY_KEY[key]
    game = active_games.get(chat_id)
    if not game or not isinstance(game, entry["cls"]):
        return f"❌ No open {entry['label']} lobby here."
    ok, msg = await game.try_start(user_id)
    return msg


# --------------------------------------------------------------------------
# General commands
# --------------------------------------------------------------------------

async def cmd_start(message: Message, args: List[str]) -> None:
    u = message.from_user
    before = db.get_user(u.id)
    ensure_user(message)
    created = before is None
    text = (
        f"🎮 <b>Welcome to the Ultimate Games Bot, {u.first_name}!</b>\n\n"
        f"All coins here are 100% virtual and just for fun - no real money involved.\n\n"
        + (f"🎁 You've been given {STARTING_COINS} starting coins!\n\n" if created else "")
        + "Use /help to see everything I can do, or /games to jump straight into a game."
    )
    await message.reply(text)


async def cmd_help(message: Message, args: List[str]) -> None:
    ensure_user(message)
    uid = message.from_user.id
    lines = ["❤️ <b>ULTIMATE GAMES BOT</b>", "━━━━━━━━━━━━━━━━━━", "",
              "🎮 <b>GENERAL</b>",
              "/start", "/help", "/games", "/balance", "/profile", "/leaderboard",
              "/richpeople", "/join", "/cancel", "/give", "/aviator", "/flip", ""]
    for g in GAME_CATALOG:
        lines.append(f"<b>{g['section']}</b>")
        lines.append(g["cmd"])
        lines.append(g["join"])
        lines.append(g["start"])
        if "vote" in g:
            lines.append(g["vote"])
        lines.append(g["rules"])
        lines.append("")

    if is_owner_or_admin(uid):
        lines.append("🛡 <b>ADMIN</b>")
        lines.append("/adminpanels")
        lines.append("/endgame")
        lines.append("")

    if is_owner(uid):
        lines.append("👑 <b>OWNER</b>")
        lines.append("/admin USER_ID")
        lines.append("/unadmin USER_ID")
        lines.append("/add USER_ID AMOUNT")
        lines.append("/take USER_ID AMOUNT")
        lines.append("/broadcast (reply to a message)")
        lines.append("/info")
        lines.append("/banuser USER_ID")
        lines.append("/unbanuser USER_ID")

    await message.reply("\n".join(lines))


async def cmd_games(message: Message, args: List[str]) -> None:
    ensure_user(message)
    b = InlineKeyboardBuilder()
    for g in GAME_CATALOG:
        b.button(text=g["label"], callback_data=f"launch:{g['key']}")
    b.adjust(2)
    await message.reply("🎮 <b>CHOOSE YOUR GAME</b>\n\nTap a game to open its lobby!", reply_markup=b.as_markup())


async def cmd_balance(message: Message, args: List[str]) -> None:
    ensure_user(message)
    coins = db.get_balance(message.from_user.id)
    await message.reply(f"💰 Your balance: <b>{coins}</b> coins")


async def cmd_profile(message: Message, args: List[str]) -> None:
    ensure_user(message)
    user = db.get_user(message.from_user.id)
    rank = db.get_rank(message.from_user.id)
    games = user["games_played"]
    winrate = f"{(user['wins'] / games * 100):.1f}%" if games else "N/A"
    text = (
        f"👤 <b>PROFILE - {message.from_user.first_name}</b>\n\n"
        f"💰 Coins: {user['coins']}\n"
        f"🎮 Games played: {games}\n"
        f"🏆 Wins: {user['wins']}\n"
        f"💀 Losses: {user['losses']}\n"
        f"📈 Win rate: {winrate}\n"
        f"🏅 Rank: #{rank}"
    )
    await message.reply(text)


def _medal(i: int) -> str:
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")


async def cmd_leaderboard(message: Message, args: List[str]) -> None:
    ensure_user(message)
    top = db.get_leaderboard(LEADERBOARD_SIZE)
    if not top:
        await message.reply("No players yet!")
        return
    lines = ["🏆 <b>LEADERBOARD - TOP PLAYERS</b>\n"]
    for i, u in enumerate(top, 1):
        lines.append(f"{_medal(i)} {fmt_user(u)} - {u['coins']} coins")
    await message.reply("\n".join(lines))


async def cmd_richpeople(message: Message, args: List[str]) -> None:
    ensure_user(message)
    top = db.get_leaderboard(RICHLIST_SIZE)
    if not top:
        await message.reply("No players yet!")
        return
    lines = ["💎 <b>TOP 30 RICHEST PLAYERS</b>\n"]
    for i, u in enumerate(top, 1):
        lines.append(f"{_medal(i)} {fmt_user(u)} - {u['coins']} coins")
    await message.reply("\n".join(lines))


async def cmd_join(message: Message, args: List[str]) -> None:
    ensure_user(message)
    chat_id = message.chat.id
    game = active_games.get(chat_id)
    if not game:
        await message.reply("❌ No active lobby here. Use /games to start one!")
        return
    ok, msg = await game.add_player(message.from_user.id, message.from_user.first_name)
    if ok:
        await game._refresh_lobby()
    await message.reply(msg)


async def cmd_cancel(message: Message, args: List[str]) -> None:
    ensure_user(message)
    chat_id = message.chat.id
    game = active_games.get(chat_id)
    if not game:
        await message.reply("❌ No active game to cancel.")
        return
    uid = message.from_user.id
    if uid != getattr(game, "creator_id", None) and not is_owner_or_admin(uid):
        await message.reply("❌ Only the game creator, an admin, or the owner can cancel this.")
        return
    if game.status != "lobby":
        await message.reply("❌ Game already started - ask an admin/owner to use /endgame instead.")
        return
    await game.force_end("Cancelled.")


# --------------------------------------------------------------------------
# Per-game commands (create / join / start / rules / vote)
# --------------------------------------------------------------------------

def make_game_commands(key: str):
    entry = CATALOG_BY_KEY[key]

    async def _create(message: Message, args: List[str]) -> None:
        ensure_user(message)
        err = await launch_lobby(message.chat.id, message.from_user.id, message.from_user.first_name, key)
        if err:
            await message.reply(err)

    async def _join(message: Message, args: List[str]) -> None:
        ensure_user(message)
        msg = await join_lobby(message.chat.id, key, message.from_user.id, message.from_user.first_name)
        await message.reply(msg)

    async def _start(message: Message, args: List[str]) -> None:
        ensure_user(message)
        msg = await start_lobby(message.chat.id, key, message.from_user.id)
        await message.reply(msg)

    async def _rules(message: Message, args: List[str]) -> None:
        rules = getattr(entry["cls"], "RULES_TEXT", None)
        if rules is None:
            rules = RULES_TEXT_G1.get(key) or RULES_TEXT_G2.get(key) or "Rules unavailable."
        await message.reply(rules)

    return _create, _join, _start, _rules


async def cmd_impostor_vote(message: Message, args: List[str]) -> None:
    ensure_user(message)
    game = active_games.get(message.chat.id)
    if not isinstance(game, ImpostorGame):
        await message.reply("❌ No Impostor game is currently running here.")
        return
    await game.resend_voting_keyboard(message)


# --------------------------------------------------------------------------
# Owner / admin commands
# --------------------------------------------------------------------------

async def cmd_add(message: Message, args: List[str]) -> None:
    ensure_user(message)
    if not is_owner(message.from_user.id):
        await message.reply("❌ Owner-only command.")
        return
    if len(args) != 2 or not args[0].lstrip("-").isdigit() or not args[1].isdigit():
        await message.reply("Usage: /add USER_ID AMOUNT")
        return
    target, amount = int(args[0]), int(args[1])
    if amount <= 0:
        await message.reply("❌ Amount must be a positive integer.")
        return
    if not db.user_exists(target):
        await message.reply("❌ That user hasn't started the bot yet.")
        return
    new_balance = db.add_coins(target, amount)
    await message.reply(f"✅ Added {amount} coins to user {target}. New balance: {new_balance}")


async def cmd_take(message: Message, args: List[str]) -> None:
    ensure_user(message)
    if not is_owner(message.from_user.id):
        await message.reply("❌ Owner-only command.")
        return
    if len(args) != 2 or not args[0].lstrip("-").isdigit() or not args[1].isdigit():
        await message.reply("Usage: /take USER_ID AMOUNT")
        return
    target, amount = int(args[0]), int(args[1])
    if amount <= 0:
        await message.reply("❌ Amount must be a positive integer.")
        return
    if not db.user_exists(target):
        await message.reply("❌ That user hasn't started the bot yet.")
        return
    if not db.take_coins(target, amount):
        await message.reply("❌ User does not have enough coins.")
        return
    new_balance = db.get_balance(target)
    await message.reply(f"✅ Took {amount} coins from user {target}. New balance: {new_balance}")


async def cmd_endgame(message: Message, args: List[str]) -> None:
    ensure_user(message)
    uid = message.from_user.id
    if not is_owner_or_admin(uid):
        await message.reply("❌ You must be an admin or the owner to use this.")
        return
    game = active_games.get(message.chat.id)
    if not game:
        await message.reply("No active game.")
        return
    await game.force_end("The current game was ended by an administrator.")


async def cmd_admin(message: Message, args: List[str]) -> None:
    ensure_user(message)
    uid = message.from_user.id
    if not is_owner(uid):
        await message.reply("❌ Only the owner can appoint bot admins.")
        return
    if len(args) != 1 or not args[0].lstrip("-").isdigit():
        await message.reply("Usage: /admin USER_ID")
        return
    target = int(args[0])
    if target == OWNER_ID:
        await message.reply("❌ The owner already has full permissions.")
        return
    if db.add_admin(target, uid):
        await message.reply(f"✅ User {target} is now a bot admin.")
    else:
        await message.reply("❌ That user is already an admin.")


async def cmd_unadmin(message: Message, args: List[str]) -> None:
    ensure_user(message)
    uid = message.from_user.id
    if not is_owner(uid):
        await message.reply("❌ Only the owner can remove bot admins.")
        return
    if len(args) != 1 or not args[0].lstrip("-").isdigit():
        await message.reply("Usage: /unadmin USER_ID")
        return
    target = int(args[0])
    if target == OWNER_ID:
        await message.reply("❌ You cannot remove the owner.")
        return
    if db.remove_admin(target):
        await message.reply(f"✅ User {target} is no longer a bot admin.")
    else:
        await message.reply("❌ That user is not an admin.")


async def cmd_adminpanels(message: Message, args: List[str]) -> None:
    ensure_user(message)
    admins = db.list_admins()
    owner_row = db.get_user(OWNER_ID)
    owner_username = owner_row["username"] if owner_row is not None else None
    owner_display = f"@{owner_username}" if owner_username else str(OWNER_ID)

    lines = ["👑 <b>BOT ADMINS</b>\n", "Owner:", f"• {owner_display}", ""]
    if admins:
        lines.append("Admins:")
        for i, a in enumerate(admins, 1):
            username = a["username"]
            first_name = a["first_name"]
            display = f"@{username}" if username else (first_name or str(a["user_id"]))
            lines.append(f"{i}. {display}")
    else:
        lines.append("No additional admins have been added.")
    await message.reply("\n".join(lines))


async def cmd_give(message: Message, args: List[str]) -> None:
    """Peer-to-peer coin transfer: reply to the recipient's message with /give AMOUNT."""
    ensure_user(message)
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply("❌ Reply to the user's message you want to give coins to, e.g. `/give 100`.")
        return
    if len(args) != 1 or not args[0].isdigit():
        await message.reply("Usage: reply to a user's message with /give AMOUNT")
        return
    amount = int(args[0])
    if amount <= 0:
        await message.reply("❌ Amount must be a positive integer.")
        return
    sender = message.from_user
    recipient = message.reply_to_message.from_user
    if recipient.id == sender.id:
        await message.reply("❌ You can't give coins to yourself.")
        return
    if recipient.is_bot:
        await message.reply("❌ You can't give coins to a bot.")
        return
    db.register_user(recipient.id, recipient.username, recipient.first_name)
    if db.get_balance(sender.id) < amount:
        await message.reply("❌ You don't have enough coins.")
        return
    if db.transfer_coins(sender.id, recipient.id, amount):
        await message.reply(f"✅ Sent {amount} coins to {recipient.first_name}!")
    else:
        await message.reply("❌ Transfer failed.")


async def cmd_broadcast(message: Message, args: List[str]) -> None:
    ensure_user(message)
    if not is_owner(message.from_user.id):
        await message.reply("❌ Owner-only command.")
        return
    if not message.reply_to_message:
        await message.reply("❌ Reply to the message you want to broadcast with /broadcast.")
        return

    targets = set(db.get_all_user_ids()) | set(db.get_all_group_chat_ids())
    sent, failed = 0, 0
    status = await message.reply(f"📡 Broadcasting to {len(targets)} chats...")
    for chat_id in targets:
        try:
            await bot.copy_message(
                chat_id=chat_id,
                from_chat_id=message.chat.id,
                message_id=message.reply_to_message.message_id,
            )
            sent += 1
        except (TelegramForbiddenError, TelegramBadRequest):
            failed += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)
    await status.edit_text(f"📡 Broadcast complete!\n✅ Sent: {sent}\n❌ Failed: {failed}")


async def cmd_info(message: Message, args: List[str]) -> None:
    ensure_user(message)
    if not is_owner(message.from_user.id):
        await message.reply("❌ Owner-only command.")
        return
    stats = db.get_bot_stats()
    uptime = datetime.utcnow() - START_TIME
    hours, rem = divmod(int(uptime.total_seconds()), 3600)
    minutes, _ = divmod(rem, 60)
    text = (
        "📊 <b>BOT INFO</b>\n\n"
        f"👥 Total users started: {stats['total_users']}\n"
        f"🟢 Active in last 24h: {stats['active_24h']}\n"
        f"🟢 Active in last 7d: {stats['active_7d']}\n"
        f"🚫 Banned users: {stats['banned_users']}\n"
        f"💬 Groups: {stats['groups']}\n"
        f"🎮 Games played (all time): {stats['total_games']}\n"
        f"⚡ Active games right now: {len(active_games)}\n"
        f"⏱ Uptime: {hours}h {minutes}m"
    )
    await message.reply(text)


async def cmd_banuser(message: Message, args: List[str]) -> None:
    ensure_user(message)
    if not is_owner(message.from_user.id):
        await message.reply("❌ Owner-only command.")
        return
    if len(args) != 1 or not args[0].lstrip("-").isdigit():
        await message.reply("Usage: /banuser USER_ID")
        return
    target = int(args[0])
    if target == OWNER_ID:
        await message.reply("❌ You cannot ban the owner.")
        return
    if db.ban_user(target):
        await message.reply(f"🚫 User {target} has been banned.")
    else:
        await message.reply("❌ That user hasn't started the bot.")


async def cmd_unbanuser(message: Message, args: List[str]) -> None:
    ensure_user(message)
    if not is_owner(message.from_user.id):
        await message.reply("❌ Owner-only command.")
        return
    if len(args) != 1 or not args[0].lstrip("-").isdigit():
        await message.reply("Usage: /unbanuser USER_ID")
        return
    target = int(args[0])
    if db.unban_user(target):
        await message.reply(f"✅ User {target} has been unbanned.")
    else:
        await message.reply("❌ That user hasn't started the bot.")


# --------------------------------------------------------------------------
# AVIATOR mini-game
# --------------------------------------------------------------------------

@dataclass
class AviatorRound:
    round_id: int
    chat_id: int
    user_id: int
    name: str
    bet: int
    crash_point: float
    multiplier: float = 1.0
    message_id: Optional[int] = None
    finished: bool = False
    task: Optional[asyncio.Task] = None


_aviator_rounds: Dict[int, AviatorRound] = {}
_aviator_counter = 0


def _generate_crash_point() -> float:
    # Keep the game visibly moving before a crash; never crash at 1.00x.
    r = random.random()
    val = 1.20 + (r ** 2) * 8.80
    return round(min(val, AVIATOR_MAX_MULTIPLIER), 2)


def _aviator_keyboard(round_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="💰 CASH OUT", callback_data=f"av:cashout:{round_id}")
    return b.as_markup()


def _aviator_presets_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for amt in AVIATOR_PRESETS:
        b.button(text=f"{amt} coins", callback_data=f"av:bet:{amt}")
    b.button(text="✏️ Custom Amount", callback_data="av:custom")
    b.adjust(len(AVIATOR_PRESETS))
    return b.as_markup()


async def cmd_aviator(message: Message, args: List[str]) -> None:
    ensure_user(message)
    if args and args[0].isdigit():
        await start_aviator_round(message.chat.id, message.from_user.id, message.from_user.first_name, int(args[0]))
        return
    await message.reply(
        "✈️ <b>AVIATOR</b>\nPick a bet amount (virtual coins only):",
        reply_markup=_aviator_presets_keyboard(),
    )


async def start_aviator_round(chat_id: int, user_id: int, name: str, bet: int) -> None:
    if bet < AVIATOR_MIN_BET:
        await bot.send_message(chat_id, f"❌ Minimum bet is {AVIATOR_MIN_BET} coins.")
        return
    if db.get_balance(user_id) < bet:
        await bot.send_message(chat_id, "❌ You don't have enough coins for that bet.")
        return
    db.take_coins(user_id, bet)

    global _aviator_counter
    _aviator_counter += 1
    round_id = _aviator_counter
    crash_point = _generate_crash_point()
    rnd = AviatorRound(round_id=round_id, chat_id=chat_id, user_id=user_id, name=name,
                        bet=bet, crash_point=crash_point)
    _aviator_rounds[round_id] = rnd

    msg = await bot.send_message(
        chat_id,
        f"✈️ <b>Aviator</b> - {name}\n💵 Bet: {bet}\n📈 Multiplier: <b>1.00x</b>\n\nCash out before it crashes!",
        reply_markup=_aviator_keyboard(round_id),
    )
    rnd.message_id = msg.message_id
    rnd.task = asyncio.create_task(_aviator_tick(round_id))


async def _aviator_tick(round_id: int) -> None:
    rnd = _aviator_rounds.get(round_id)
    if not rnd:
        return
    try:
        for _ in range(AVIATOR_MAX_TICKS):
            await asyncio.sleep(AVIATOR_TICK_SECONDS)
            if rnd.finished:
                return

            # Increase every tick, then immediately edit the SAME Telegram message.
            next_multiplier = round(
                rnd.multiplier + 0.05 + rnd.multiplier * 0.06, 2
            )
            if next_multiplier >= rnd.crash_point:
                rnd.multiplier = rnd.crash_point
                await _aviator_crash(rnd)
                return

            rnd.multiplier = next_multiplier
            if rnd.message_id is not None:
                try:
                    await bot.edit_message_text(
                        chat_id=rnd.chat_id,
                        message_id=rnd.message_id,
                        text=(
                            f"✈️ <b>Aviator</b> - {rnd.name}\n"
                            f"💵 Bet: {rnd.bet}\n"
                            f"📈 Multiplier: <b>{rnd.multiplier:.2f}x</b>\n\n"
                            "Cash out before it crashes!"
                        ),
                        reply_markup=_aviator_keyboard(round_id),
                    )
                except Exception as exc:
                    # Do not kill the background task if Telegram temporarily rejects an edit.
                    logger.warning("Aviator message edit failed (round %s): %s", round_id, exc)

        if not rnd.finished:
            await _aviator_crash(rnd)
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("Aviator tick task failed for round %s", round_id)
        if not rnd.finished:
            await _aviator_crash(rnd)


async def _aviator_crash(rnd: AviatorRound) -> None:
    rnd.finished = True
    try:
        if rnd.message_id is not None:
            await bot.edit_message_text(
                chat_id=rnd.chat_id,
                message_id=rnd.message_id,
                text=(
                    f"✈️ <b>Aviator</b> - {rnd.name}\n💵 Bet: {rnd.bet}\n"
                    f"💥 <b>CRASHED AT {rnd.crash_point:.2f}x</b>\n"
                    f"❌ {rnd.name} lost {rnd.bet} coins."
                ),
            )
    except Exception:
        pass
    db.update_stats(rnd.user_id, won=False)
    _aviator_rounds.pop(rnd.round_id, None)


async def handle_aviator_callback(callback: CallbackQuery) -> None:
    data = callback.data or ""
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "bet":
        amount = int(parts[2])
        ensure_user_from_callback(callback)
        await callback.answer()
        await start_aviator_round(callback.message.chat.id, callback.from_user.id,
                                   callback.from_user.first_name, amount)
    elif action == "custom":
        await callback.answer("Type: /aviator AMOUNT to bet a custom amount.", show_alert=True)
    elif action == "cashout":
        round_id = int(parts[2])
        rnd = _aviator_rounds.get(round_id)
        if not rnd or rnd.finished:
            await callback.answer("This round already ended.", show_alert=True)
            return
        if callback.from_user.id != rnd.user_id:
            await callback.answer("❌ This isn't your bet!", show_alert=True)
            return
        rnd.finished = True
        winnings = int(rnd.bet * rnd.multiplier)
        db.add_coins(rnd.user_id, winnings)
        db.update_stats(rnd.user_id, won=True)
        await callback.answer(f"Cashed out at {rnd.multiplier:.2f}x!")
        try:
            await bot.edit_message_text(
                f"💰 <b>CASHED OUT at {rnd.multiplier:.2f}x!</b>\n{rnd.name} won {winnings} coins!",
                rnd.chat_id, rnd.message_id,
            )
        except Exception:
            pass
        _aviator_rounds.pop(round_id, None)


def ensure_user_from_callback(callback: CallbackQuery) -> None:
    u = callback.from_user
    db.register_user(u.id, u.username, u.first_name)
    db.touch_activity(u.id)


# --------------------------------------------------------------------------
# FLIP mini-game
# --------------------------------------------------------------------------

async def cmd_flip(message: Message, args: List[str]) -> None:
    ensure_user(message)
    if len(args) != 2:
        await message.reply("Usage: /flip h AMOUNT  or  /flip t AMOUNT")
        return
    choice_raw, amount_raw = args[0].lower(), args[1]
    if choice_raw in ("h", "heads"):
        choice = "heads"
    elif choice_raw in ("t", "tails"):
        choice = "tails"
    else:
        await message.reply("❌ Prediction must be 'h' (heads) or 't' (tails).")
        return
    if not amount_raw.isdigit():
        await message.reply("❌ Amount must be a positive whole number.")
        return
    amount = int(amount_raw)
    if amount < FLIP_MIN_BET:
        await message.reply(f"❌ Minimum bet is {FLIP_MIN_BET} coins.")
        return
    uid = message.from_user.id
    if db.get_balance(uid) < amount:
        await message.reply("❌ You don't have enough coins.")
        return

    db.take_coins(uid, amount)
    result = random.choice(["heads", "tails"])
    won = result == choice

    if won:
        payout = int(amount * FLIP_WIN_MULTIPLIER)
        db.add_coins(uid, payout)
        text = (f"🪙 The coin landed on <b>{result}</b>! You guessed right!\n"
                f"🎉 You won {payout} coins ({FLIP_WIN_MULTIPLIER}x your bet)!")
    else:
        payout = int(amount * FLIP_LOSE_MULTIPLIER)
        db.add_coins(uid, payout)
        text = (f"🪙 The coin landed on <b>{result}</b>. You guessed {choice} - wrong!\n"
                f"💸 You got back {payout} coins ({FLIP_LOSE_MULTIPLIER}x your bet).")
    db.update_stats(uid, won=won)
    await message.reply(text)


# --------------------------------------------------------------------------
# Command routing table
# --------------------------------------------------------------------------

COMMANDS: Dict[str, Callable[[Message, List[str]], Any]] = {
    "/start": cmd_start,
    "/help": cmd_help,
    "/games": cmd_games,
    "/balance": cmd_balance,
    "/profile": cmd_profile,
    "/leaderboard": cmd_leaderboard,
    "/richpeople": cmd_richpeople,
    "/join": cmd_join,
    "/cancel": cmd_cancel,
    "/give": cmd_give,
    "/aviator": cmd_aviator,
    "/flip": cmd_flip,
    "/add": cmd_add,
    "/take": cmd_take,
    "/endgame": cmd_endgame,
    "/admin": cmd_admin,
    "/unadmin": cmd_unadmin,
    "/adminpanels": cmd_adminpanels,
    "/broadcast": cmd_broadcast,
    "/info": cmd_info,
    "/banuser": cmd_banuser,
    "/unbanuser": cmd_unbanuser,
    "/impostor_vote": cmd_impostor_vote,
}

for _g in GAME_CATALOG:
    _create, _join, _start, _rules = make_game_commands(_g["key"])
    COMMANDS[_g["cmd"]] = _create
    COMMANDS[_g["join"]] = _join
    COMMANDS[_g["start"]] = _start
    COMMANDS[_g["rules"]] = _rules


# --------------------------------------------------------------------------
# Dispatcher-level handlers
# --------------------------------------------------------------------------

@dp.message(F.text.startswith("/"))
async def on_command(message: Message) -> None:
    try:
        parts = message.text.strip().split()
        cmd = parts[0].split("@")[0].lower()
        args = parts[1:]

        if message.from_user and db.is_banned(message.from_user.id) and cmd != "/start":
            await message.reply("🚫 You are banned from using this bot.")
            return

        handler = COMMANDS.get(cmd)
        if handler is None:
            return  # unknown command - stay silent to avoid spamming groups
        await handler(message, args)
    except Exception:
        logger.exception("Error handling command: %s", message.text)
        try:
            await message.reply("⚠️ Something went wrong processing that command. Please try again.")
        except Exception:
            pass


@dp.message(F.text)
async def on_plain_text(message: Message) -> None:
    """Routes plain (non-command) text to a running game that needs it (e.g. Antakshari)."""
    try:
        if message.from_user and db.is_banned(message.from_user.id):
            return
        ensure_user(message)
        game = active_games.get(message.chat.id)
        if game is not None and isinstance(game, AntakshariGame):
            await game.handle_message(message)
    except Exception:
        logger.exception("Error handling plain text message")


@dp.callback_query()
async def on_callback(callback: CallbackQuery) -> None:
    try:
        if callback.from_user and db.is_banned(callback.from_user.id):
            await callback.answer("🚫 You are banned from using this bot.", show_alert=True)
            return

        data = callback.data or ""
        chat_id = callback.message.chat.id if callback.message else None

        if data.startswith("launch:"):
            key = data.split(":", 1)[1]
            entry = CATALOG_BY_KEY.get(key)
            if not entry:
                await callback.answer("Unknown game.", show_alert=True)
                return
            ensure_user_from_callback(callback)
            err = await launch_lobby(chat_id, callback.from_user.id, callback.from_user.first_name, key)
            await callback.answer(err if err else f"{entry['label']} lobby created!")
            return

        if data.startswith("av:"):
            await handle_aviator_callback(callback)
            return

        game = active_games.get(chat_id) if chat_id is not None else None
        if game is not None and data.startswith(f"{game.PREFIX}:"):
            if isinstance(game, BaseGame):
                await game.handle_callback(callback, data.split(":")[1:])
            else:
                await game.handle_callback(callback)
            return

        await callback.answer()  # stale/unknown callback - no-op
    except Exception:
        logger.exception("Error handling callback: %s", callback.data)
        try:
            await callback.answer("⚠️ Something went wrong.", show_alert=True)
        except Exception:
            pass


# --------------------------------------------------------------------------
# Startup / shutdown
# --------------------------------------------------------------------------

async def on_startup() -> None:
    db.init_db()
    logger.info("Database initialized.")
    try:
        await bot.set_my_commands([
            {"command": "start", "description": "Start the bot / register"},
            {"command": "help", "description": "Show all commands"},
            {"command": "games", "description": "Browse all games"},
            {"command": "balance", "description": "Check your coin balance"},
            {"command": "profile", "description": "View your profile"},
            {"command": "leaderboard", "description": "Top players"},
            {"command": "richpeople", "description": "Top 30 richest players"},
            {"command": "aviator", "description": "Play Aviator"},
            {"command": "flip", "description": "Flip a coin and bet coins"},
        ])
    except Exception:
        logger.warning("Could not set bot commands (non-fatal).")
    logger.info("Bot started as configured. Owner ID: %s", OWNER_ID)


async def on_shutdown() -> None:
    logger.info("Shutting down - ending all active games gracefully...")
    for chat_id, game in list(active_games.items()):
        try:
            await game.force_end("The bot is restarting. Sorry for the interruption!")
        except Exception:
            pass
    active_games.clear()


async def main() -> None:
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
