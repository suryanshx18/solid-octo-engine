import os
import asyncio
import time

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

from database import (
    init_db,
    add_user,
    get_balance,
    change_coins,
    is_admin,
    add_admin,
    remove_admin,
    leaderboard,
    create_game,
    get_game,
    get_active_game,
    update_game,
    end_game,
    add_game_player,
    remove_game_player,
    get_game_players,
    get_game_player
)

from game import (
    PARCHI_VALUES,
    deal_cards,
    check_winner,
    format_cards,
    arcade_multiplier
)


BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# In-memory state for currently running games.
parchi_games = {}
fly_games = {}


# =========================================================
# HELPERS
# =========================================================

def is_owner(user_id):
    return user_id == OWNER_ID


def is_privileged(user_id):
    return (
        is_owner(user_id)
        or is_admin(user_id)
    )


def player_name(row):
    return (
        row["first_name"]
        or row["username"]
        or "Player"
    )


def remember_user(user):
    add_user(
        user.id,
        user.username,
        user.first_name
    )


# =========================================================
# /START
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    remember_user(update.effective_user)

    await update.message.reply_text(
        "🏏 <b>Welcome to 16 Parchi!</b>\n\n"
        "Your account is ready.\n\n"
        "Use /help to see all commands.",
        parse_mode="HTML"
    )


# =========================================================
# /HELP
# =========================================================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    remember_user(update.effective_user)

    text = (
        "📖 <b>16 PARCHI BOT — HELP</b>\n\n"

        "🏏 <b>Parchi Game</b>\n"
        "/startgame — Create a new game\n"
        "/begin — Begin the 4-player game\n"
        "/endgame — End the current game\n\n"

        "💰 <b>Coins</b>\n"
        "/bal — Check your balance\n"
        "/leaderboard — Top 10 players\n\n"

        "🚀 <b>Free Fly</b>\n"
        "/fly — Start the free arcade multiplier\n\n"

        "👑 <b>Owner Commands</b>\n"
        "/give 1000 — Give coins by replying to a user\n"
        "/add 1000 — Same as /give\n"
        "/removec 1000 — Remove coins by reply\n"
        "/admin — Make a replied user admin\n"
        "/unadmin — Remove admin from a replied user\n\n"

        "🎴 <b>Parchi Values</b>\n"
        "Virat Kohli — 5,000 coins\n"
        "MS Dhoni — 4,500 coins\n"
        "Rohit Sharma — 4,000 coins\n"
        "KL Rahul — 3,500 coins\n\n"

        "ℹ️ The Parchi game requires exactly 4 players."
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML"
    )


# =========================================================
# /BAL
# =========================================================

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    remember_user(update.effective_user)

    coins = get_balance(
        update.effective_user.id
    )

    await update.message.reply_text(
        f"💰 <b>Your balance:</b> {coins:,} coins",
        parse_mode="HTML"
    )


# =========================================================
# /LEADERBOARD
# =========================================================

async def show_leaderboard(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    remember_user(update.effective_user)

    rows = leaderboard(10)

    if not rows:
        await update.message.reply_text(
            "No players yet."
        )
        return

    text = "🏆 <b>LEADERBOARD</b>\n\n"

    for index, row in enumerate(rows, start=1):
        name = (
            row["first_name"]
            or row["username"]
            or "Player"
        )

        text += (
            f"{index}. {name} — "
            f"💰 {row['coins']:,}\n"
        )

    await update.message.reply_text(
        text,
        parse_mode="HTML"
    )


# =========================================================
# /STARTGAME
# =========================================================

async def startgame(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_chat.type == "private":
        await update.message.reply_text(
            "❌ Start the Parchi game in a group."
        )
        return

    remember_user(update.effective_user)

    chat_id = update.effective_chat.id

    existing = get_active_game(chat_id)

    if existing:
        await update.message.reply_text(
            "❌ A game is already running here."
        )
        return

    game_id = create_game(
        chat_id,
        update.effective_user.id,
        "parchi"
    )

    parchi_games[game_id] = {
        "hands": {},
        "turn": 0,
        "started": False,
        "winner": None
    }

    keyboard = [[
        InlineKeyboardButton(
            "🎟 Join Parchi Game",
            callback_data=f"join:{game_id}"
        )
    ]]

    await update.message.reply_text(
        "🏏 <b>16 PARCHI GAME</b>\n\n"
        f"Game ID: <code>{game_id}</code>\n\n"

        "🎴 16 total cards\n"
        "👥 Exactly 4 players\n\n"

        "Card values:\n"
        "• Virat Kohli — 5,000 coins\n"
        "• MS Dhoni — 4,500 coins\n"
        "• Rohit Sharma — 4,000 coins\n"
        "• KL Rahul — 3,500 coins\n\n"

        "Each player gets 4 random cards.\n"
        "Players pass one card clockwise.\n"
        "Four identical cards wins the corresponding prize.\n\n"

        "⚠️ After joining, each player must open "
        "the bot privately and send /start.\n"
        "You have 60 seconds for the private check.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


# =========================================================
# UPDATE LOBBY
# =========================================================

async def update_lobby_message(query, game_id):

    game = get_game(game_id)

    if not game or game["status"] != "lobby":
        return

    players = get_game_players(game_id)

    text = (
        "🏏 <b>16 PARCHI GAME</b>\n\n"
        f"Game ID: <code>{game_id}</code>\n\n"
        "Players:\n"
    )

    for index, player in enumerate(players, start=1):
        text += (
            f"{index}. {player_name(player)}\n"
        )

    text += (
        f"\n👥 <b>{len(players)}/4 players</b>\n"
    )

    if len(players) < 4:

        text += (
            "\n⏳ Waiting for more players...\n\n"
            "Anyone can press the button below."
        )

        keyboard = [[
            InlineKeyboardButton(
                "🎟 Join Parchi Game",
                callback_data=f"join:{game_id}"
            )
        ]]

    else:

        text += (
            "\n\n✅ <b>4/4 PLAYERS JOINED!</b>\n\n"
            "⚠️ All players must have opened the bot "
            "privately using /start.\n\n"
            "⏳ 60-second private check is running."
        )

        keyboard = [[
            InlineKeyboardButton(
                "▶️ Begin Game",
                callback_data=f"begin:{game_id}"
            )
        ]]

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


# =========================================================
# JOIN GAME
# =========================================================

async def join_game(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    game_id = int(
        query.data.split(":")[1]
    )

    game = get_game(game_id)

    if not game:
        await query.answer(
            "Game does not exist.",
            show_alert=True
        )
        return

    if game["status"] != "lobby":
        await query.answer(
            "Game has already started.",
            show_alert=True
        )
        return

    user = query.from_user

    remember_user(user)

    if get_game_player(game_id, user.id):
        await query.answer(
            "You already joined!",
            show_alert=True
        )
        return

    players = get_game_players(game_id)

    if len(players) >= 4:
        await query.answer(
            "Game is full!",
            show_alert=True
        )
        return

    add_game_player(
        game_id,
        user.id,
        len(players)
    )

    players = get_game_players(game_id)

    await update_lobby_message(
        query,
        game_id
    )

    # Start private access check exactly when 4 players join.
    if len(players) == 4:

        asyncio.create_task(
            private_access_check(
                context,
                game_id,
                game["chat_id"]
            )
        )


# =========================================================
# 60 SECOND PRIVATE CHECK
# =========================================================

async def private_access_check(
    context,
    game_id,
    chat_id
):

    # Warning after 30 seconds.
    await asyncio.sleep(30)

    game = get_game(game_id)

    if not game or game["status"] != "lobby":
        return

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "⚠️ <b>30 seconds remaining!</b>\n\n"
            "All 4 players must open the bot privately "
            "and send /start."
        ),
        parse_mode="HTML"
    )

    # Finish the 60-second period.
    await asyncio.sleep(30)

    game = get_game(game_id)

    if not game or game["status"] != "lobby":
        return

    players = get_game_players(game_id)

    removed_names = []

    for player in players:

        user_id = player["user_id"]

        try:
            # If this succeeds, the bot can DM them.
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "✅ Private connection confirmed.\n\n"
                    "You can receive your secret Parchi cards."
                )
            )

        except Exception:
            remove_game_player(
                game_id,
                user_id
            )

            removed_names.append(
                player_name(player)
            )

    remaining = get_game_players(game_id)

    if removed_names:

        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "⏰ <b>60-second check finished.</b>\n\n"
                "❌ Removed:\n"
                + "\n".join(
                    f"• {name}"
                    for name in removed_names
                )
                + f"\n\n👥 Remaining: {len(remaining)}/4\n\n"
                "New players can join using the Join button."
            ),
            parse_mode="HTML"
        )

    if len(remaining) == 4:

        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "✅ <b>All 4 players passed!</b>\n\n"
                "The host can now press /begin."
            ),
            parse_mode="HTML"
        )

    elif len(remaining) < 4:

        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "👥 The game needs 4 players again.\n\n"
                "Use the Join button to add replacement players."
            )
        )


# =========================================================
# /BEGIN
# =========================================================

async def begin(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if update.effective_chat.type == "private":
        await update.message.reply_text(
            "❌ Use /begin inside the group."
        )
        return

    remember_user(update.effective_user)

    game = get_active_game(
        update.effective_chat.id
    )

    if not game:
        await update.message.reply_text(
            "❌ No active game."
        )
        return

    if (
        update.effective_user.id != game["host_id"]
        and not is_privileged(update.effective_user.id)
    ):
        await update.message.reply_text(
            "❌ Only the host, owner or admin can begin."
        )
        return

    await start_parchi_game(
        context,
        game["id"]
    )


# =========================================================
# START PARCHI GAME
# =========================================================

async def start_parchi_game(
    context,
    game_id
):

    game = get_game(game_id)

    if not game or game["status"] != "lobby":
        return

    players = get_game_players(game_id)

    if len(players) != 4:
        await context.bot.send_message(
            chat_id=game["chat_id"],
            text=(
                f"❌ Exactly 4 players are required.\n"
                f"Current players: {len(players)}"
            )
        )
        return

    player_ids = [
        player["user_id"]
        for player in players
    ]

    hands = deal_cards(player_ids)

    parchi_games[game_id] = {
        "hands": hands,
        "turn": 0,
        "started": True,
        "winner": None
    }

    update_game(
        game_id,
        status="active",
        current_turn=0
    )

    # Send secret cards.
    for player in players:

        try:

            await context.bot.send_message(
                chat_id=player["user_id"],
                text=(
                    "🎴 <b>YOUR SECRET PARCHIS</b>\n\n"
                    f"{format_cards(hands[player['user_id']])}\n\n"
                    "🔒 Keep your cards secret!"
                ),
                parse_mode="HTML"
            )

        except Exception:
            pass

    await context.bot.send_message(
        chat_id=game["chat_id"],
        text=(
            "🔥 <b>PARCHI GAME STARTED!</b>\n\n"
            "🎴 All 16 cards have been distributed.\n\n"
            "➡️ Pass exactly one card clockwise.\n"
            "🏆 Get 4 identical cards to win!"
        ),
        parse_mode="HTML"
    )

    await show_turn(
        context,
        game["chat_id"],
        game_id
    )


# =========================================================
# SHOW TURN
# =========================================================

async def show_turn(
    context,
    chat_id,
    game_id
):

    game = get_game(game_id)

    if not game or game["status"] != "active":
        return

    players = get_game_players(game_id)

    if len(players) != 4:
        return

    state = parchi_games.get(game_id)

    if not state:
        return

    turn = state["turn"] % 4

    current = players[turn]

    keyboard = [[
        InlineKeyboardButton(
            "🎴 Give 1 Card",
            callback_data=f"give:{game_id}"
        )
    ]]

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"🎴 <b>{player_name(current)}</b>'s turn\n\n"
            "Press the button and choose one card "
            "to pass to the next player."
        ),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


# =========================================================
# GIVE CARD BUTTON
# =========================================================

async def give_card(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    game_id = int(
        query.data.split(":")[1]
    )

    game = get_game(game_id)

    if not game or game["status"] != "active":
        await query.answer(
            "Game is not active.",
            show_alert=True
        )
        return

    players = get_game_players(game_id)

    if len(players) != 4:
        return

    state = parchi_games.get(game_id)

    if not state:
        return

    turn = state["turn"] % 4
    current = players[turn]

    if query.from_user.id != current["user_id"]:
        await query.answer(
            "It is not your turn.",
            show_alert=True
        )
        return

    cards = state["hands"][current["user_id"]]

    keyboard = []

    for index, card in enumerate(cards):
        keyboard.append([
            InlineKeyboardButton(
                f"{index + 1}. {card}",
                callback_data=f"card:{game_id}:{index}"
            )
        ])

    await query.edit_message_text(
        "🎴 <b>Choose one card</b>\n\n"
        "That card will be passed to the next player.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


# =========================================================
# CARD SELECTED
# =========================================================

async def card_selected(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")

    game_id = int(parts[1])
    card_index = int(parts[2])

    game = get_game(game_id)

    if not game or game["status"] != "active":
        return

    players = get_game_players(game_id)

    if len(players) != 4:
        return

    state = parchi_games.get(game_id)

    if not state:
        return

    turn = state["turn"] % 4

    sender = players[turn]

    if query.from_user.id != sender["user_id"]:
        await query.answer(
            "It is not your turn.",
            show_alert=True
        )
        return

    sender_cards = state["hands"][sender["user_id"]]

    if card_index < 0 or card_index >= len(sender_cards):
        return

    card = sender_cards.pop(card_index)

    receiver_index = (turn + 1) % 4
    receiver = players[receiver_index]

    state["hands"][receiver["user_id"]].append(card)

    # Secret notification.
    try:
        await context.bot.send_message(
            chat_id=receiver["user_id"],
            text=(
                "🎴 <b>You received a card!</b>\n\n"
                f"Received: <b>{card}</b>\n\n"
                "Your cards:\n"
                f"{format_cards(state['hands'][receiver['user_id']])}"
            ),
            parse_mode="HTML"
        )
    except Exception:
        pass

    # Check four-of-a-kind.
    winner = check_winner(
        state["hands"][receiver["user_id"]]
    )

    if winner:

        state["winner"] = receiver["user_id"]

        amount = winner["amount"]

        change_coins(
            receiver["user_id"],
            amount,
            f"Parchi win - {winner['player']}"
        )

        update_game(
            game_id,
            status="ended"
        )

        await context.bot.send_message(
            chat_id=game["chat_id"],
            text=(
                "🎉 <b>PARCHI WINNER!</b>\n\n"
                f"🏆 {player_name(receiver)}\n"
                f"🎴 {winner['player']} × 4\n\n"
                f"💰 Prize: <b>{amount:,} coins</b>\n\n"
                "🏏 Game finished!"
            ),
            parse_mode="HTML"
        )

        parchi_games.pop(
            game_id,
            None
        )

        return

    state["turn"] += 1

    update_game(
        game_id,
        current_turn=state["turn"]
    )

    await context.bot.send_message(
        chat_id=game["chat_id"],
        text=(
            f"🎴 {player_name(sender)} passed "
            f"<b>{card}</b> to "
            f"{player_name(receiver)}."
        ),
        parse_mode="HTML"
    )

    await show_turn(
        context,
        game["chat_id"],
        game_id
    )


# =========================================================
# /ENDGAME
# =========================================================

async def endgame(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if update.effective_chat.type == "private":
        await update.message.reply_text(
            "❌ Use /endgame in the group."
        )
        return

    game = get_active_game(
        update.effective_chat.id
    )

    if not game:
        await update.message.reply_text(
            "❌ There is no active game."
        )
        return

    user_id = update.effective_user.id

    if (
        user_id != game["host_id"]
        and not is_privileged(user_id)
    ):
        await update.message.reply_text(
            "❌ Only the host, owner or admin can end the game."
        )
        return

    end_game(game["id"])

    parchi_games.pop(
        game["id"],
        None
    )

    fly_games.pop(
        update.effective_chat.id,
        None
    )

    await update.message.reply_text(
        "🛑 <b>GAME ENDED</b>\n\n"
        "The current game has been ended.\n"
        "No further moves are allowed.",
        parse_mode="HTML"
    )


# =========================================================
# /FLY
# =========================================================

async def fly(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    remember_user(update.effective_user)

    chat_id = update.effective_chat.id

    if chat_id in fly_games:
        await update.message.reply_text(
            "🚀 A Fly round is already running."
        )
        return

    fly_games[chat_id] = {
        "started_at": time.monotonic(),
        "active": True
    }

    await update.message.reply_text(
        "🚀 <b>FREE FLY STARTED!</b>\n\n"
        "Multiplier starts at <b>1.10x</b>.\n"
        "Maximum: <b>100x</b>.\n\n"
        "This is an arcade mode — no coins are wagered.",
        parse_mode="HTML"
    )

    asyncio.create_task(
        run_fly(
            context,
            chat_id
        )
    )


# =========================================================
# FREE FLY ENGINE
# =========================================================

async def run_fly(
    context,
    chat_id
):

    game = fly_games.get(chat_id)

    if not game:
        return

    started_at = game["started_at"]

    # Random arcade ending between 1.10x and 100x.
    import random

    crash = round(
        min(
            100.0,
            max(
                1.10,
                1.10 / random.random()
            )
        ),
        2
    )

    last_multiplier = 1.10

    while True:

        await asyncio.sleep(1)

        if chat_id not in fly_games:
            return

        elapsed = time.monotonic() - started_at

        multiplier = arcade_multiplier(
            elapsed
        )

        if multiplier >= crash:

            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "💥 <b>ROCKET CRASHED!</b>\n\n"
                    f"📉 Crash point: <b>{crash:.2f}x</b>\n\n"
                    "🚀 Start another free round with /fly."
                ),
                parse_mode="HTML"
            )

            fly_games.pop(
                chat_id,
                None
            )

            return

        if multiplier > last_multiplier:

            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🚀 <b>{multiplier:.2f}x</b>",
                parse_mode="HTML"
            )

            last_multiplier = multiplier


# =========================================================
# OWNER / GIVE COINS
# =========================================================

async def give_coins(
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
            "❌ Reply to a user's message.\n\n"
            "Example:\n"
            "/give 5000"
        )
        return

    if not context.args:
        await update.message.reply_text(
            "❌ Enter an amount.\n\n"
            "Example:\n"
            "/give 5000"
        )
        return

    try:
        amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text(
            "❌ Amount must be a number."
        )
        return

    if amount <= 0:
        await update.message.reply_text(
            "❌ Amount must be greater than 0."
        )
        return

    target = update.message.reply_to_message.from_user

    remember_user(target)

    change_coins(
        target.id,
        amount,
        f"Owner gave {amount} coins"
    )

    new_balance = get_balance(target.id)

    await update.message.reply_text(
        "✅ <b>COINS ADDED</b>\n\n"
        f"👤 {target.first_name}\n"
        f"💰 Added: {amount:,}\n"
        f"💳 Balance: {new_balance:,}",
        parse_mode="HTML"
    )


# =========================================================
# OWNER / REMOVE COINS
# =========================================================

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
            "❌ Reply to a user's message.\n\n"
            "Example:\n"
            "/removec 1000"
        )
        return

    if not context.args:
        await update.message.reply_text(
            "❌ Enter an amount."
        )
        return

    try:
        amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text(
            "❌ Amount must be a number."
        )
        return

    if amount <= 0:
        await update.message.reply_text(
            "❌ Amount must be greater than 0."
        )
        return

    target = update.message.reply_to_message.from_user

    remember_user(target)

    change_coins(
        target.id,
        -amount,
        f"Owner removed {amount} coins"
    )

    await update.message.reply_text(
        f"✅ Removed {amount:,} coins from "
        f"{target.first_name}."
    )


# =========================================================
# /ADMIN
# =========================================================

async def make_admin(
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
            "❌ Reply to the user with /admin."
        )
        return

    target = update.message.reply_to_message.from_user

    remember_user(target)
    add_admin(target.id)

    await update.message.reply_text(
        f"✅ {target.first_name} is now an admin."
    )


# =========================================================
# /UNADMIN
# =========================================================

async def remove_admin_command(
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
            "❌ Reply to the user with /unadmin."
        )
        return

    target = update.message.reply_to_message.from_user

    remove_admin(target.id)

    await update.message.reply_text(
        f"✅ {target.first_name} is no longer an admin."
    )


# =========================================================
# CALLBACK ROUTER
# =========================================================

async def callbacks(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if query.data.startswith("join:"):
        await join_game(
            update,
            context
        )

    elif query.data.startswith("begin:"):
        await query.answer()

        game_id = int(
            query.data.split(":")[1]
        )

        game = get_game(game_id)

        if not game:
            return

        if (
            query.from_user.id != game["host_id"]
            and not is_privileged(query.from_user.id)
        ):
            await query.answer(
                "Only the host/admin can begin.",
                show_alert=True
            )
            return

        await start_parchi_game(
            context,
            game_id
        )

    elif query.data.startswith("give:"):
        await give_card(
            update,
            context
        )

    elif query.data.startswith("card:"):
        await card_selected(
            update,
            context
        )


# =========================================================
# MAIN
# =========================================================

def main():

    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN environment variable is missing."
        )

    init_db()

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    # Basic
    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("help", help_command)
    )

    application.add_handler(
        CommandHandler("bal", balance)
    )

    application.add_handler(
        CommandHandler(
            "leaderboard",
            show_leaderboard
        )
    )

    # Parchi
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

    # Free Fly
    application.add_handler(
        CommandHandler(
            "fly",
            fly
        )
    )

    # Owner
    application.add_handler(
        CommandHandler(
            "give",
            give_coins
        )
    )

    application.add_handler(
        CommandHandler(
            "add",
            give_coins
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
            make_admin
        )
    )

    application.add_handler(
        CommandHandler(
            "unadmin",
            remove_admin_command
        )
    )

    # Buttons
    application.add_handler(
        CallbackQueryHandler(
            callbacks
        )
    )

    print("🏏 16 Parchi Bot started!")

    application.run_polling()


if __name__ == "__main__":
    main()
