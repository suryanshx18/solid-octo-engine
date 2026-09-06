import logging
import os

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
OWNER_ID = int(
    os.getenv("OWNER_ID", "0")
)

database.init_db()


def mention_user(user):

    if user.username:
        return f"@{user.username}"

    return (
        user.first_name
        or str(user.id)
    )


def mention_row(row):

    if row["username"]:
        return f"@{row['username']}"

    return (
        row["first_name"]
        or str(row["user_id"])
    )


def is_owner(user_id):
    return user_id == OWNER_ID


def is_admin_or_owner(user_id):
    return (
        is_owner(user_id)
        or database.is_admin(user_id)
    )


# =========================
# START
# =========================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    database.ensure_user(
        update.effective_user
    )

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

        if is_admin_or_owner(
            update.effective_user.id
        ):
            keyboard.append([
                InlineKeyboardButton(
                    "⚙️ Admin Panel",
                    callback_data="adminpanel"
                )
            ])

        await update.message.reply_text(
            "🕵️ MAFIA: HIDDEN CITY\n\n"

            f"Welcome, "
            f"{mention_user(update.effective_user)}!\n\n"

            "🔫 Mafia\n"
            "🔎 Detective\n"
            "💊 Doctor\n"
            "👥 Citizens\n\n"

            f"💰 Balance: "
            f"{balance:,} CHAOS\n\n"

            "Add me to a Telegram group "
            "to play multiplayer.",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            )
        )

    else:

        await update.message.reply_text(
            "🕵️ MAFIA: HIDDEN CITY\n\n"
            "Use /startgame to create a game."
        )


# =========================
# BALANCE
# =========================

async def bal(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    database.ensure_user(
        update.effective_user
    )

    balance = database.get_balance(
        update.effective_user.id
    )

    await update.message.reply_text(
        "💰 YOUR BALANCE\n\n"

        f"👤 {mention_user(update.effective_user)}\n"

        f"🪙 {balance:,} CHAOS"
    )


# =========================
# LEADERBOARD
# =========================

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

    text = "🏆 TOP 20 PLAYERS\n\n"

    medals = [
        "🥇",
        "🥈",
        "🥉"
    ]

    for index, row in enumerate(
        rows,
        start=1
    ):

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

    await update.message.reply_text(
        text
    )


# =========================
# ADD COINS
# =========================

async def add_coins(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_owner(
        update.effective_user.id
    ):

        await update.message.reply_text(
            "❌ Owner only."
        )

        return

    if not update.message.reply_to_message:

        await update.message.reply_text(
            "Reply to a player's message.\n\n"
            "/addc 500"
        )

        return

    if len(context.args) != 1:

        await update.message.reply_text(
            "Usage: /addc amount"
        )

        return

    try:

        amount = int(
            context.args[0]
        )

        if amount <= 0:
            raise ValueError

    except ValueError:

        await update.message.reply_text(
            "❌ Enter a valid positive amount."
        )

        return

    target = (
        update.message.reply_to_message.from_user
    )

    database.ensure_user(target)

    new_balance = database.change_coins(
        update.effective_user.id,
        target.id,
        amount,
        "add"
    )

    await update.message.reply_text(
        "💰 COINS ADDED\n\n"

        f"👤 Player: "
        f"{mention_user(target)}\n"

        f"➕ Added: "
        f"{amount:,}\n"

        f"💵 New Balance: "
        f"{new_balance:,}"
    )


# =========================
# REMOVE COINS
# =========================

async def remove_coins(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_owner(
        update.effective_user.id
    ):

        await update.message.reply_text(
            "❌ Owner only."
        )

        return

    if not update.message.reply_to_message:

        await update.message.reply_text(
            "Reply to a player's message.\n\n"
            "/removec 500"
        )

        return

    if len(context.args) != 1:

        await update.message.reply_text(
            "Usage: /removec amount"
        )

        return

    try:

        amount = int(
            context.args[0]
        )

        if amount <= 0:
            raise ValueError

    except ValueError:

        await update.message.reply_text(
            "❌ Enter a valid positive amount."
        )

        return

    target = (
        update.message.reply_to_message.from_user
    )

    database.ensure_user(target)

    old_balance = database.get_balance(
        target.id
    )

    new_balance = database.change_coins(
        update.effective_user.id,
        target.id,
        amount,
        "remove"
    )

    removed = (
        old_balance - new_balance
    )

    await update.message.reply_text(
        "💸 COINS REMOVED\n\n"

        f"👤 Player: "
        f"{mention_user(target)}\n"

        f"➖ Removed: "
        f"{removed:,}\n"

        f"💵 New Balance: "
        f"{new_balance:,}"
    )


# =========================
# ADMIN
# =========================

async def add_admin(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_owner(
        update.effective_user.id
    ):

        await update.message.reply_text(
            "❌ Owner only."
        )

        return

    if not update.message.reply_to_message:

        await update.message.reply_text(
            "Reply to a user's message with /admin."
        )

        return

    target = (
        update.message.reply_to_message.from_user
    )

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
        "🛡️ ADMIN ADDED\n\n"

        f"👤 {mention_user(target)} "
        "is now an admin."
    )


async def remove_admin(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_owner(
        update.effective_user.id
    ):

        await update.message.reply_text(
            "❌ Owner only."
        )

        return

    if not update.message.reply_to_message:

        await update.message.reply_text(
            "Reply to a user's message with /unadmin."
        )

        return

    target = (
        update.message.reply_to_message.from_user
    )

    database.remove_admin(
        target.id
    )

    await update.message.reply_text(
        "🛡️ ADMIN REMOVED\n\n"

        f"👤 {mention_user(target)} "
        "is no longer an admin."
    )


# =========================
# ADMIN PANEL
# =========================

async def adminpanel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin_or_owner(
        update.effective_user.id
    ):

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

    if is_owner(
        update.effective_user.id
    ):

        keyboard.append([
            InlineKeyboardButton(
                "🛡️ Admin Management",
                callback_data="admin_management"
            )
        ])

    await update.message.reply_text(
        "⚙️ MAFIA ADMIN PANEL\n\n"

        f"👥 Players: "
        f"{stats['users']}\n"

        f"🛡️ Admins: "
        f"{stats['admins']}\n"

        f"🎮 Active games: "
        f"{stats['games']}\n"

        f"🪙 Total coins: "
        f"{stats['coins']:,}",

        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


# =========================
# START GAME
# =========================

async def startgame(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if update.effective_chat.type == "private":

        await update.message.reply_text(
            "⚠️ Start games inside a group."
        )

        return

    database.ensure_user(
        update.effective_user
    )

    existing = database.get_active_game(
        update.effective_chat.id
    )

    if existing:

        await update.message.reply_text(
            "⚠️ A game is already running."
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
                "🎮 JOIN",
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
        "🕵️ MAFIA: HIDDEN CITY\n\n"

        "A new game lobby has opened!\n\n"

        "👥 Players: 1/12\n\n"

        "Press JOIN to enter.\n\n"

        "Host uses /begin when "
        "at least 4 players have joined.",

        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


# =========================
# BEGIN GAME
# =========================

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
            "❌ Only the host can begin."
        )

        return

    players = database.get_game_players(
        active["game_id"]
    )

    if len(players) < 4:

        await update.message.reply_text(
            f"❌ Need at least 4 players.\n"
            f"Current: {len(players)}"
        )

        return

    game.start_game(
        active["game_id"]
    )

    # Secret role DM
    for player in players:

        try:

            role_player = database.get_player(
                active["game_id"],
                player["user_id"]
            )

            await context.bot.send_message(
                chat_id=player["user_id"],
                text=(
                    "🔐 YOUR SECRET ROLE\n\n"

                    f"🎭 Role: "
                    f"{role_player['role']}\n\n"

                    f"🎯 Mission:\n"
                    f"{role_player['secret_mission']}\n\n"

                    "Keep your role secret."
                )
            )

        except Exception:
            pass

    await update.message.reply_text(
        "🌙 NIGHT 1 BEGINS!\n\n"

        "Secret roles have been assigned.\n"
        "Check your DM with the bot.\n\n"

        "Mafia, Doctor and Detective "
        "can make their choices."
    )

    await send_night_panel(
        update.effective_chat.id,
        active["game_id"],
        context
    )


# =========================
# NIGHT PANEL
# =========================

async def send_night_panel(
    chat_id,
    game_id,
    context
):

    players = database.get_game_players(
        game_id,
        alive_only=True
    )

    keyboard = []

    for player in players:

        keyboard.append([
            InlineKeyboardButton(
                mention_row(player),
                callback_data=(
                    f"night:"
                    f"{game_id}:"
                    f"{player['user_id']}"
                )
            )
        ])

    await context.bot.send_message(
        chat_id=chat_id,

        text=(
            "🌙 NIGHT PHASE\n\n"

            "Choose a player according "
            "to your role.\n\n"

            "🔫 Mafia → eliminate a target\n"
            "💊 Doctor → protect someone\n"
            "🔎 Detective → investigate someone"
        ),

        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


# =========================
# DAY PANEL
# =========================

async def send_day_panel(
    chat_id,
    game_id,
    context
):

    players = database.get_game_players(
        game_id,
        alive_only=True
    )

    keyboard = []

    for player in players:

        keyboard.append([
            InlineKeyboardButton(
                f"🗳️ {mention_row(player)}",
                callback_data=(
                    f"vote:"
                    f"{game_id}:"
                    f"{player['user_id']}"
                )
            )
        ])

    await context.bot.send_message(
        chat_id=chat_id,

        text=(
            "☀️ DAY PHASE\n\n"

            "Discuss in the group.\n\n"

            "Then vote for the player "
            "you believe is Mafia.\n\n"

            "Each player gets one vote."
        ),

        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


# =========================
# WIN CHECK
# =========================

async def check_winner(
    chat_id,
    game_id,
    context
):

    winner, players = game.get_winner(
        game_id
    )

    if winner is None:
        return False

    if winner == "mafia":

        text = (
            "🔫 MAFIA WINS!\n\n"
            "The Mafia controls the city.\n\n"
        )

    else:

        text = (
            "👥 CITIZENS WIN!\n\n"
            "The Mafia has been eliminated.\n\n"
        )

    text += "🎭 FINAL ROLES\n\n"

    for player in database.get_game_players(
        game_id
    ):

        status = (
            "❤️"
            if player["alive"]
            else "💀"
        )

        text += (
            f"{status} "
            f"{mention_row(player)} — "
            f"{player['role']}\n"
        )

    winners = [
        p["user_id"]
        for p in players
    ]

    database.increment_game_stats(
        game_id,
        winners
    )

    database.reward_players(
        game_id,
        winners
    )

    database.end_game(
        game_id
    )

    await context.bot.send_message(
        chat_id=chat_id,

        text=(
            text
            + "\n🏆 Winners received "
            "+250 CHAOS."
        )
    )

    return True


# =========================
# END GAME
# =========================

async def endgame(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if update.effective_chat.type == "private":

        await update.message.reply_text(
            "⚠️ /endgame can only be used "
            "inside a group."
        )

        return

    active = database.get_active_game(
        update.effective_chat.id
    )

    if not active:

        await update.message.reply_text(
            "❌ There is no active game."
        )

        return

    # Host OR owner can end the game.
    allowed = (
        active["host_id"]
        == update.effective_user.id
        or is_owner(
            update.effective_user.id
        )
    )

    if not allowed:

        await update.message.reply_text(
            "❌ Only the game host or bot owner "
            "can use /endgame."
        )

        return

    game_id = active["game_id"]

    players = database.get_game_players(
        game_id
    )

    # Reveal roles.
    text = (
        "🛑 GAME ENDED\n\n"
        "The game was manually ended.\n\n"
        "🎭 SECRET ROLES REVEALED\n\n"
    )

    for player in players:

        status = (
            "❤️"
            if player["alive"]
            else "💀"
        )

        role = (
            player["role"]
            or "Unassigned"
        )

        text += (
            f"{status} "
            f"{mention_row(player)} — "
            f"{role}\n"
        )

    database.end_game(
        game_id
    )

    await update.message.reply_text(
        text
    )


# =========================
# CALLBACKS
# =========================

async def callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    user = query.from_user

    database.ensure_user(user)

    data = query.data

    # -------------------------
    # BALANCE
    # -------------------------

    if data == "balance":

        balance = database.get_balance(
            user.id
        )

        await query.answer(
            f"Balance: {balance:,} CHAOS",
            show_alert=True
        )

        return

    # -------------------------
    # LEADERBOARD
    # -------------------------

    if data == "leaderboard":

        rows = database.leaderboard(20)

        text = "🏆 TOP PLAYERS\n\n"

        for i, row in enumerate(
            rows,
            1
        ):

            name = (
                f"@{row['username']}"
                if row["username"]
                else row["first_name"]
            )

            text += (
                f"{i}. {name} — "
                f"{row['coins']:,} 🪙\n"
            )

        await query.message.reply_text(
            text
        )

        await query.answer()

        return

    # -------------------------
    # HELP
    # -------------------------

    if data == "help":

        await query.answer()

        await query.message.reply_text(
            "📖 MAFIA: HIDDEN CITY\n\n"

            "👥 4–12 players\n\n"

            "🌙 NIGHT\n"
            "🔫 Mafia chooses a target.\n"
            "💊 Doctor protects someone.\n"
            "🔎 Detective investigates someone.\n\n"

            "☀️ DAY\n"
            "Players discuss and vote.\n\n"

            "🔫 Mafia wins when "
            "Mafia >= Citizens.\n\n"

            "👥 Citizens win when "
            "all Mafia are eliminated.\n\n"

            "Commands:\n"
            "/startgame\n"
            "/begin\n"
            "/endgame\n"
            "/bal\n"
            "/leaderboard"
        )

        return

    # -------------------------
    # ADMIN PANEL
    # -------------------------

    if data == "adminpanel":

        if not is_admin_or_owner(user.id):

            await query.answer(
                "❌ Permission denied.",
                show_alert=True
            )

            return

        stats = database.get_stats()

        await query.message.reply_text(
            "⚙️ ADMIN PANEL\n\n"

            f"👥 Players: "
            f"{stats['users']}\n"

            f"🛡️ Admins: "
            f"{stats['admins']}\n"

            f"🎮 Games: "
            f"{stats['games']}\n"

            f"🪙 Coins: "
            f"{stats['coins']:,}"
        )

        await query.answer()

        return

    # -------------------------
    # JOIN
    # -------------------------

    if data.startswith("join:"):

        game_id = int(
            data.split(":")[1]
        )

        active = database.get_active_game(
            query.message.chat.id
        )

        if (
            not active
            or active["game_id"] != game_id
            or active["status"] != "lobby"
        ):

            await query.answer(
                "❌ Game unavailable.",
                show_alert=True
            )

            return

        players = database.get_game_players(
            game_id
        )

        if len(players) >= 12:

            await query.answer(
                "❌ Game is full.",
                show_alert=True
            )

            return

        if any(
            p["user_id"] == user.id
            for p in players
        ):

            await query.answer(
                "You're already in.",
                show_alert=True
            )

            return

        database.add_game_player(
            game_id,
            user.id
        )

        players = database.get_game_players(
            game_id
        )

        await query.answer(
            "🎮 You joined!",
            show_alert=True
        )

        await query.message.reply_text(
            f"🎮 {mention_user(user)} joined!\n\n"
            f"👥 Players: {len(players)}/12"
        )

        return

    # -------------------------
    # NIGHT
    # -------------------------

    if data.startswith("night:"):

        parts = data.split(":")

        game_id = int(parts[1])
        target_id = int(parts[2])

        current_game = database.get_game(
            game_id
        )

        if not current_game:
            await query.answer()
            return

        if (
            current_game["status"] != "active"
            or current_game["phase"] != "night"
        ):

            await query.answer(
                "❌ Night is over.",
                show_alert=True
            )

            return

        player = database.get_player(
            game_id,
            user.id
        )

        target = database.get_player(
            game_id,
            target_id
        )

        if not player or not player["alive"]:

            await query.answer(
                "❌ You are not alive.",
                show_alert=True
            )

            return

        if not target or not target["alive"]:

            await query.answer(
                "❌ Invalid target.",
                show_alert=True
            )

            return

        role = player["role"]

        if role == "Mafia":

            if target_id == user.id:

                await query.answer(
                    "❌ You cannot target yourself.",
                    show_alert=True
                )

                return

            database.update_game(
                game_id,
                night_target=target_id
            )

            await query.answer(
                "🔫 Target selected.",
                show_alert=True
            )

        elif role == "Doctor":

            database.update_game(
                game_id,
                doctor_target=target_id
            )

            await query.answer(
                "💊 Protection selected.",
                show_alert=True
            )

        elif role == "Detective":

            database.update_game(
                game_id,
                detective_target=target_id
            )

            await context.bot.send_message(
                chat_id=user.id,

                text=(
                    "🔎 INVESTIGATION RESULT\n\n"

                    f"Player: "
                    f"{mention_row(target)}\n"

                    f"Role: "
                    f"{target['role']}"
                )
            )

            await query.answer(
                "🔎 Check your DM.",
                show_alert=True
            )

        else:

            await query.answer(
                "❌ Citizens have no night action.",
                show_alert=True
            )

            return

        # -------------------------
        # CHECK NIGHT READY
        # -------------------------

        players = database.get_game_players(
            game_id,
            alive_only=True
        )

        mafia = [
            p for p in players
            if p["role"] == "Mafia"
        ]

        doctors = [
            p for p in players
            if p["role"] == "Doctor"
        ]

        detectives = [
            p for p in players
            if p["role"] == "Detective"
        ]

        latest = database.get_game(
            game_id
        )

        mafia_ready = (
            len(mafia) == 0
            or latest["night_target"]
            is not None
        )

        doctor_ready = (
            len(doctors) == 0
            or latest["doctor_target"]
            is not None
        )

        detective_ready = (
            len(detectives) == 0
            or latest["detective_target"]
            is not None
        )

        if (
            mafia_ready
            and doctor_ready
            and detective_ready
        ):

            killed = game.resolve_night(
                game_id
            )

            if killed:

                await query.message.reply_text(
                    "🌅 MORNING\n\n"

                    f"💀 "
                    f"{mention_row(killed)} "
                    "was eliminated during "
                    "the night."
                )

            else:

                await query.message.reply_text(
                    "🌅 MORNING\n\n"
                    "✨ Nobody was eliminated."
                )

            if await check_winner(
                query.message.chat.id,
                game_id,
                context
            ):
                return

            database.update_game(
                game_id,
                phase="day"
            )

            await send_day_panel(
                query.message.chat.id,
                game_id,
                context
            )

        return

    # -------------------------
    # VOTE
    # -------------------------

    if data.startswith("vote:"):

        parts = data.split(":")

        game_id = int(parts[1])
        target_id = int(parts[2])

        current_game = database.get_game(
            game_id
        )

        if not current_game:
            await query.answer()
            return

        if (
            current_game["status"] != "active"
            or current_game["phase"] != "day"
        ):

            await query.answer(
                "❌ Voting isn't active.",
                show_alert=True
            )

            return

        voter = database.get_player(
            game_id,
            user.id
        )

        target = database.get_player(
            game_id,
            target_id
        )

        if not voter or not voter["alive"]:

            await query.answer(
                "❌ Dead players cannot vote.",
                show_alert=True
            )

            return

        if not target or not target["alive"]:

            await query.answer(
                "❌ Invalid target.",
                show_alert=True
            )

            return

        if target_id == user.id:

            await query.answer(
                "❌ You cannot vote yourself.",
                show_alert=True
            )

            return

        if database.has_voted(
            game_id,
            user.id,
            "day"
        ):

            await query.answer(
                "❌ You already voted.",
                show_alert=True
            )

            return

        database.add_vote(
            game_id,
            user.id,
            target_id,
            "day"
        )

        await query.answer(
            "🗳️ Vote recorded.",
            show_alert=True
        )

        alive_players = database.get_game_players(
            game_id,
            alive_only=True
        )

        votes = database.get_votes(
            game_id,
            "day"
        )

        # Everyone alive has voted.
        if len(votes) >= len(alive_players):

            eliminated, vote_count = (
                game.resolve_day(game_id)
            )

            if eliminated:

                await query.message.reply_text(
                    "⚖️ VOTE RESULT\n\n"

                    f"💀 "
                    f"{mention_row(eliminated)} "
                    f"was eliminated with "
                    f"{vote_count} vote(s).\n\n"

                    f"🎭 Role: "
                    f"{eliminated['role']}"
                )

            else:

                await query.message.reply_text(
                    "⚖️ VOTE RESULT\n\n"

                    "🤝 The vote ended in a tie.\n"
                    "Nobody was eliminated."
                )

            if await check_winner(
                query.message.chat.id,
                game_id,
                context
            ):
                return

            current = database.get_game(
                game_id
            )

            next_round = (
                current["round"] + 1
            )

            database.update_game(
                game_id,
                phase="night",
                round=next_round
            )

            await query.message.reply_text(
                f"🌙 NIGHT {next_round} BEGINS!"
            )

            await send_night_panel(
                query.message.chat.id,
                game_id,
                context
            )

        return

    # -------------------------
    # ADMIN
    # -------------------------

    if data.startswith("admin_"):

        if not is_admin_or_owner(user.id):

            await query.answer(
                "❌ Permission denied.",
                show_alert=True
            )

            return

        await query.answer()

        stats = database.get_stats()

        if data == "admin_stats":

            await query.message.reply_text(
                "📊 STATISTICS\n\n"

                f"👥 Players: "
                f"{stats['users']}\n"

                f"🛡️ Admins: "
                f"{stats['admins']}\n"

                f"🎮 Active games: "
                f"{stats['games']}\n"

                f"🪙 Total coins: "
                f"{stats['coins']:,}"
            )

        elif data == "admin_economy":

            await query.message.reply_text(
                "💰 ECONOMY\n\n"

                "Reply to a player's message:\n\n"

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


# =========================
# MAIN
# =========================

def main():

    if not TOKEN:

        raise RuntimeError(
            "BOT_TOKEN environment variable "
            "is missing."
        )

    if OWNER_ID == 0:

        raise RuntimeError(
            "OWNER_ID environment variable "
            "is missing."
        )

    application = (
        Application.builder()
        .token(TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    application.add_handler(
        CommandHandler(
            "bal",
            bal
        )
    )

    application.add_handler(
        CommandHandler(
            "leaderboard",
            leaderboard_cmd
        )
    )

    application.add_handler(
        CommandHandler(
            "addc",
            add_coins
        )
    )

    application.add_handler(
        CommandHandler(
            "removec",
            remove_coins
        )
    )

    application.add_handler(
        CommandHandler(
            "admin",
            add_admin
        )
    )

    application.add_handler(
        CommandHandler(
            "unadmin",
            remove_admin
        )
    )

    application.add_handler(
        CommandHandler(
            "adminpanel",
            adminpanel
        )
    )

    application.add_handler(
        CommandHandler(
            "startgame",
            startgame
        )
    )

    application.add_handler(
        CommandHandler(
            "begin",
            begin
        )
    )

    application.add_handler(
        CommandHandler(
            "endgame",
            endgame
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            callback
        )
    )

    print(
        "🕵️ MAFIA HIDDEN CITY BOT STARTED"
    )

    application.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
