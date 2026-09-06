import os
import logging
import random

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)

import database
import game


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)


TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))


database.init_db()


def mention_user(user):
    if user.username:
        return f"@{user.username}"

    return user.first_name or str(user.id)


def is_owner(user_id):
    return user_id == OWNER_ID


def is_admin_or_owner(user_id):
    return is_owner(user_id) or database.is_admin(user_id)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    database.ensure_user(update.effective_user)

    if update.effective_chat.type == "private":

        balance = database.get_balance(
            update.effective_user.id
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    "📖 How To Play",
                    callback_data="help"
                )
            ],
            [
                InlineKeyboardButton(
                    "💰 Balance",
                    callback_data="balance"
                ),
                InlineKeyboardButton(
                    "🏆 Leaderboard",
                    callback_data="leaderboard"
                )
            ]
        ]

        if is_admin_or_owner(update.effective_user.id):
            keyboard.append([
                InlineKeyboardButton(
                    "⚙️ Admin Panel",
                    callback_data="adminpanel"
                )
            ])

        await update.message.reply_text(
            f"🔥 CHAOSCORE\n\n"
            f"Welcome, {mention_user(update.effective_user)}!\n\n"
            f"🎲 Risk\n"
            f"🤖 Battle the AI\n"
            f"🃏 Betray your opponents\n\n"
            f"💰 Balance: {balance:,} CHAOS\n\n"
            f"Add me to a Telegram group to play multiplayer.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    else:

        await update.message.reply_text(
            "🔥 CHAOSCORE\n\n"
            "Multiplayer game bot.\n\n"
            "Use /startgame to create a game."
        )


async def bal(update: Update, context: ContextTypes.DEFAULT_TYPE):

    database.ensure_user(update.effective_user)

    balance = database.get_balance(
        update.effective_user.id
    )

    await update.message.reply_text(
        f"💰 YOUR BALANCE\n\n"
        f"👤 {mention_user(update.effective_user)}\n"
        f"🪙 {balance:,} CHAOS"
    )


async def leaderboard_cmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    rows = database.leaderboard(20)

    if not rows:
        await update.message.reply_text(
            "🏆 Leaderboard is empty."
        )
        return

    text = "🏆 CHAOSCORE LEADERBOARD\n\n"

    medals = ["🥇", "🥈", "🥉"]

    for index, row in enumerate(rows, start=1):

        name = (
            f"@{row['username']}"
            if row["username"]
            else row["first_name"]
        )

        prefix = (
            medals[index - 1]
            if index <= 3
            else f"{index}."
        )

        text += (
            f"{prefix} {name} — "
            f"{row['coins']:,} 🪙\n"
        )

    await update.message.reply_text(text)


async def add_coins(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_owner(update.effective_user.id):
        await update.message.reply_text(
            "❌ Owner only."
        )
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "Reply to a user's message.\n\n"
            "Example:\n"
            "/addc 500"
        )
        return

    if len(context.args) != 1:
        await update.message.reply_text(
            "Usage: /addc amount"
        )
        return

    try:
        amount = int(context.args[0])

        if amount <= 0:
            raise ValueError

    except ValueError:

        await update.message.reply_text(
            "❌ Enter a valid positive amount."
        )
        return

    target = update.message.reply_to_message.from_user

    database.ensure_user(target)

    new_balance = database.change_coins(
        update.effective_user.id,
        target.id,
        amount,
        "add"
    )

    await update.message.reply_text(
        f"💰 COINS ADDED\n\n"
        f"👤 Player: {mention_user(target)}\n"
        f"➕ Added: {amount:,}\n"
        f"💵 New Balance: {new_balance:,}"
    )


async def remove_coins(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_owner(update.effective_user.id):
        await update.message.reply_text(
            "❌ Owner only."
        )
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "Reply to a user's message.\n\n"
            "Example:\n"
            "/removec 500"
        )
        return

    if len(context.args) != 1:
        await update.message.reply_text(
            "Usage: /removec amount"
        )
        return

    try:
        amount = int(context.args[0])

        if amount <= 0:
            raise ValueError

    except ValueError:

        await update.message.reply_text(
            "❌ Enter a valid positive amount."
        )
        return

    target = update.message.reply_to_message.from_user

    database.ensure_user(target)

    old_balance = database.get_balance(target.id)

    new_balance = database.change_coins(
        update.effective_user.id,
        target.id,
        amount,
        "remove"
    )

    removed = old_balance - new_balance

    await update.message.reply_text(
        f"💸 COINS REMOVED\n\n"
        f"👤 Player: {mention_user(target)}\n"
        f"➖ Removed: {removed:,}\n"
        f"💵 New Balance: {new_balance:,}"
    )


async def add_admin(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_owner(update.effective_user.id):
        await update.message.reply_text(
            "❌ Owner only."
        )
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "Reply to the user's message with /admin."
        )
        return

    target = update.message.reply_to_message.from_user

    if target.id == OWNER_ID:
        await update.message.reply_text(
            "👑 Owner is already above admin."
        )
        return

    database.ensure_user(target)
    database.add_admin(
        target.id,
        update.effective_user.id
    )

    await update.message.reply_text(
        f"🛡️ ADMIN ADDED\n\n"
        f"👤 {mention_user(target)} is now a bot admin."
    )


async def remove_admin(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_owner(update.effective_user.id):
        await update.message.reply_text(
            "❌ Owner only."
        )
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "Reply to the user's message with /unadmin."
        )
        return

    target = update.message.reply_to_message.from_user

    database.remove_admin(target.id)

    await update.message.reply_text(
        f"🛡️ ADMIN REMOVED\n\n"
        f"👤 {mention_user(target)} is no longer an admin."
    )


async def adminpanel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin_or_owner(update.effective_user.id):

        await update.message.reply_text(
            "❌ You don't have permission."
        )
        return

    stats = database.get_stats()

    keyboard = [
        [
            InlineKeyboardButton(
                "👥 Players",
                callback_data="admin_players"
            )
        ],
        [
            InlineKeyboardButton(
                "💰 Economy",
                callback_data="admin_economy"
            )
        ],
        [
            InlineKeyboardButton(
                "🎮 Active Games",
                callback_data="admin_games"
            )
        ],
        [
            InlineKeyboardButton(
                "📊 Statistics",
                callback_data="admin_stats"
            )
        ]
    ]

    if is_owner(update.effective_user.id):
        keyboard.append([
            InlineKeyboardButton(
                "🛡️ Admin Management",
                callback_data="admin_management"
            )
        ])

    await update.message.reply_text(
        "⚙️ CHAOSCORE ADMIN PANEL\n\n"
        f"👥 Players: {stats['users']}\n"
        f"🛡️ Admins: {stats['admins']}\n"
        f"🎮 Active games: {stats['games']}\n"
        f"🪙 Total coins: {stats['coins']:,}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def startgame(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if update.effective_chat.type == "private":

        await update.message.reply_text(
            "⚠️ Multiplayer games must be "
            "started inside a group."
        )
        return

    database.ensure_user(update.effective_user)

    existing = database.get_active_game(
        update.effective_chat.id
    )

    if existing:

        await update.message.reply_text(
            "⚠️ A game is already running in this group."
        )
        return

    game_id = database.create_game(
        update.effective_chat.id,
        update.effective_user.id
    )

    database.add_game_player(
        game_id,
        update.effective_user.id
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "🎮 JOIN GAME",
                callback_data=f"join:{game_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "📖 RULES",
                callback_data="help"
            )
        ]
    ]

    await update.message.reply_text(
        "🔥 CHAOSCORE GAME\n\n"
        "A new game is forming!\n\n"
        "Players: 1/12\n\n"
        "Press JOIN GAME to enter.\n\n"
        "Host can use /begin when ready.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def begin(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if update.effective_chat.type == "private":
        return

    active = database.get_active_game(
        update.effective_chat.id
    )

    if not active:
        await update.message.reply_text(
            "❌ No game lobby exists."
        )
        return

    if active["host_id"] != update.effective_user.id:
        await update.message.reply_text(
            "❌ Only the game host can begin."
        )
        return

    players = database.get_game_players(
        active["game_id"]
    )

    if len(players) < 4:

        await update.message.reply_text(
            f"❌ Need at least 4 players.\n"
            f"Current players: {len(players)}"
        )
        return

    game.start_game_engine(
        active["game_id"]
    )

    # Send secret roles
    for player in players:

        try:

            role = None
            mission = None

            for p in database.get_game_players(
                active["game_id"]
            ):

                if p["user_id"] == player["user_id"]:
                    role = p["role"]
                    mission = p["secret_mission"]

            await context.bot.send_message(
                chat_id=player["user_id"],
                text=(
                    "🔐 YOUR SECRET CHAOSCORE ROLE\n\n"
                    f"🎭 Role: {role}\n\n"
                    f"🎯 Mission:\n{mission}\n\n"
                    "Keep this secret."
                )
            )

        except Exception:

            # User hasn't started the bot in DM.
            pass

    await update.message.reply_text(
        "🔥 GAME STARTED!\n\n"
        f"Players: {len(players)}\n"
        "Round: 1\n\n"
        "🤖 The AI is preparing...\n\n"
        "Players will receive their actions below."
    )

    await send_round(
        update.effective_chat.id,
        active["game_id"],
        context
    )


async def send_round(
    chat_id,
    game_id,
    context
):

    event_name, event_description = game.random_event()

    ai_power = game.calculate_ai_power()

    keyboard = [
        [
            InlineKeyboardButton(
                "⚔️ ATTACK",
                callback_data=f"act:{game_id}:attack"
            ),
            InlineKeyboardButton(
                "🛡️ DEFEND",
                callback_data=f"act:{game_id}:defend"
            )
        ],
        [
            InlineKeyboardButton(
                "🎲 GAMBLE",
                callback_data=f"act:{game_id}:gamble"
            ),
            InlineKeyboardButton(
                "🕵️ SABOTAGE",
                callback_data=f"act:{game_id}:sabotage"
            )
        ]
    ]

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"⚡ ROUND\n\n"
            f"🌪️ {event_name}\n"
            f"{event_description}\n\n"
            f"🤖 AI POWER: {ai_power}\n\n"
            "Choose your action:"
        ),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    user = query.from_user

    database.ensure_user(user)

    data = query.data

    if data == "balance":

        balance = database.get_balance(user.id)

        await query.answer(
            f"Balance: {balance:,} CHAOS",
            show_alert=True
        )

        return

    if data == "leaderboard":

        rows = database.leaderboard(20)

        text = "🏆 TOP PLAYERS\n\n"

        for i, row in enumerate(rows, 1):

            name = (
                f"@{row['username']}"
                if row["username"]
                else row["first_name"]
            )

            text += (
                f"{i}. {name} — "
                f"{row['coins']:,} 🪙\n"
            )

        await query.message.reply_text(text)

        return

    if data == "help":

        await query.message.reply_text(
            "📖 CHAOSCORE\n\n"
            "🎲 Risk your coins.\n"
            "🤖 Fight the AI.\n"
            "🃏 Secret roles create betrayal.\n"
            "🤝 Form alliances.\n"
            "🏆 Finish with the highest score.\n\n"
            "Group:\n"
            "/startgame\n"
            "/begin\n\n"
            "DM:\n"
            "/bal\n"
            "/leaderboard"
        )

        return

    if data == "adminpanel":

        if not is_admin_or_owner(user.id):
            await query.answer(
                "❌ No permission.",
                show_alert=True
            )
            return

        stats = database.get_stats()

        await query.message.reply_text(
            "⚙️ ADMIN PANEL\n\n"
            f"👥 Players: {stats['users']}\n"
            f"🛡️ Admins: {stats['admins']}\n"
            f"🎮 Active games: {stats['games']}\n"
            f"🪙 Coins: {stats['coins']:,}"
        )

        return

    if data.startswith("join:"):

        game_id = int(data.split(":")[1])

        active = database.get_active_game(
            query.message.chat.id
        )

        if not active or active["game_id"] != game_id:

            await query.answer(
                "❌ Game no longer available.",
                show_alert=True
            )
            return

        players = database.get_game_players(game_id)

        if len(players) >= 12:

            await query.answer(
                "❌ Game is full.",
                show_alert=True
            )
            return

        database.add_game_player(
            game_id,
            user.id
        )

        players = database.get_game_players(game_id)

        await query.answer(
            "🎮 You joined!",
            show_alert=True
        )

        await query.message.reply_text(
            f"🎮 {mention_user(user)} joined!\n\n"
            f"Players: {len(players)}/12"
        )

        return

    if data.startswith("act:"):

        parts = data.split(":")

        game_id = int(parts[1])
        action = parts[2]

        players = database.get_game_players(game_id)

        player_ids = [
            p["user_id"]
            for p in players
        ]

        if user.id not in player_ids:

            await query.answer(
                "❌ You're not in this game.",
                show_alert=True
            )
            return

        points = game.resolve_action(action)

        conn = database.connect()
        cur = conn.cursor()

        cur.execute("""
            UPDATE game_players
            SET score = score + ?
            WHERE game_id = ?
            AND user_id = ?
        """, (
            points,
            game_id,
            user.id
        ))

        conn.commit()
        conn.close()

        await query.answer(
            f"{action.upper()}: {points:+d} points",
            show_alert=True
        )

        return

    if data.startswith("admin_"):

        if not is_admin_or_owner(user.id):

            await query.answer(
                "❌ Permission denied.",
                show_alert=True
            )
            return

        stats = database.get_stats()

        if data == "admin_stats":

            await query.message.reply_text(
                "📊 STATISTICS\n\n"
                f"👥 Players: {stats['users']}\n"
                f"🛡️ Admins: {stats['admins']}\n"
                f"🎮 Active games: {stats['games']}\n"
                f"🪙 Total coins: {stats['coins']:,}"
            )

        elif data == "admin_economy":

            await query.message.reply_text(
                "💰 ECONOMY\n\n"
                "Use coin commands by replying "
                "to a player's message:\n\n"
                "/addc amount\n"
                "/removec amount"
            )

        elif data == "admin_players":

            await query.message.reply_text(
                f"👥 Registered players: "
                f"{stats['users']}"
            )

        elif data == "admin_games":

            await query.message.reply_text(
                f"🎮 Active games: "
                f"{stats['games']}"
            )

        elif data == "admin_management":

            if not is_owner(user.id):

                await query.answer(
                    "❌ Owner only.",
                    show_alert=True
                )
                return

            await query.message.reply_text(
                "🛡️ ADMIN MANAGEMENT\n\n"
                "Reply to a user's message:\n\n"
                "/admin\n"
                "/unadmin"
            )

        return


def main():

    if not TOKEN:
        raise RuntimeError(
            "BOT_TOKEN environment variable is missing."
        )

    if OWNER_ID == 0:
        raise RuntimeError(
            "OWNER_ID environment variable is missing."
        )

    application = (
        Application.builder()
        .token(TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("bal", bal)
    )

    application.add_handler(
        CommandHandler("leaderboard", leaderboard_cmd)
    )

    application.add_handler(
        CommandHandler("addc", add_coins)
    )

    application.add_handler(
        CommandHandler("removec", remove_coins)
    )

    application.add_handler(
        CommandHandler("admin", add_admin)
    )

    application.add_handler(
        CommandHandler("unadmin", remove_admin)
    )

    application.add_handler(
        CommandHandler("adminpanel", adminpanel)
    )

    application.add_handler(
        CommandHandler("startgame", startgame)
    )

    application.add_handler(
        CommandHandler("begin", begin)
    )

    application.add_handler(
        CallbackQueryHandler(callback)
    )

    print("🔥 CHAOSCORE BOT STARTED")

    application.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
