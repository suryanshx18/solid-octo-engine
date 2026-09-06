import os
import asyncio
import random
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
    arcade_multiplier
)


BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))


# =========================================================
# IN-MEMORY GAME STATE
# =========================================================

parchi_games = {}

# chat_id -> fly state
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


def remember_user(user):
    add_user(
        user.id,
        user.username,
        user.first_name
    )


def player_name(player):
    return (
        player["first_name"]
        or player["username"]
        or "Player"
    )


def mention_player(player):
    return (
        f'<a href="tg://user?id={player["user_id"]}">'
        f'{player_name(player)}'
        f'</a>'
    )


# =========================================================
# /START
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    remember_user(update.effective_user)

    await update.message.reply_text(
        "🏏 <b>Welcome to 16 Parchi!</b>\n\n"
        "Your private connection is ready.\n\n"
        "Use /help to see all commands.",
        parse_mode="HTML"
    )


# =========================================================
# /HELP
# =========================================================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    remember_user(update.effective_user)

    text = (
        "📖 <b>16 PARCHI — HELP</b>\n\n"

        "🏏 <b>Parchi</b>\n"
        "/startgame — Create a game\n"
        "/begin — Begin the game\n"
        "/endgame — End current game\n\n"

        "💰 <b>Account</b>\n"
        "/bal — Check coins\n"
        "/leaderboard — Top players\n\n"

        "🚀 <b>Free Fly</b>\n"
        "/fly — Start free arcade Fly\n"
        "/stopfly — Owner-only emergency stop\n\n"

        "👑 <b>Owner</b>\n"
        "/give 1000 — Add coins by reply\n"
        "/add 1000 — Add coins by reply\n"
        "/removec 1000 — Remove coins by reply\n"
        "/admin — Add admin by reply\n"
        "/unadmin — Remove admin by reply\n\n"

        "🎴 <b>Parchi Values</b>\n"
        "Virat Kohli — 5,000\n"
        "MS Dhoni — 4,500\n"
        "Rohit Sharma — 4,000\n"
        "KL Rahul — 3,500\n\n"

        "🔒 Cards are private.\n"
        "The group only receives turn reminders."
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

    coins = get_balance(update.effective_user.id)

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

    for index, row in enumerate(rows, 1):
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
            "❌ Start the game inside a group."
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
        "👥 Exactly 4 players.\n"
        "🎴 Each player gets 4 random cards.\n"
        "🔄 One card is passed clockwise.\n"
        "🏆 Four identical cards wins.\n\n"
        "⚠️ Every player must first open the bot "
        "privately and send /start.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


# =========================================================
# LOBBY
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

    for index, player in enumerate(players, 1):
        text += (
            f"{index}. {player_name(player)}\n"
        )

    text += f"\n👥 <b>{len(players)}/4</b>\n"

    if len(players) < 4:
        text += (
            "\n⏳ Waiting for players..."
        )

        keyboard = [[
            InlineKeyboardButton(
                "🎟 Join Parchi Game",
                callback_data=f"join:{game_id}"
            )
        ]]

    else:
        text += (
            "\n\n✅ <b>4/4 PLAYERS</b>\n"
            "⏳ Private connection check running..."
        )

        keyboard = []

    try:
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
    except Exception:
        pass


# =========================================================
# JOIN
# =========================================================

async def join_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            "Game already started.",
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

    await update_lobby_message(
        query,
        game_id
    )

    players = get_game_players(game_id)

    if len(players) == 4:
        asyncio.create_task(
            private_access_check(
                context,
                game_id,
                game["chat_id"]
            )
        )


# =========================================================
# PRIVATE ACCESS CHECK
# =========================================================

async def private_access_check(
    context,
    game_id,
    chat_id
):
    await asyncio.sleep(30)

    game = get_game(game_id)

    if not game or game["status"] != "lobby":
        return

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "⚠️ <b>30 SECONDS LEFT!</b>\n\n"
            "All players must have opened the bot "
            "privately and sent /start."
        ),
        parse_mode="HTML"
    )

    await asyncio.sleep(30)

    game = get_game(game_id)

    if not game or game["status"] != "lobby":
        return

    players = get_game_players(game_id)

    removed = []

    for player in players:
        try:
            await context.bot.send_message(
                chat_id=player["user_id"],
                text=(
                    "✅ <b>Private connection confirmed!</b>\n\n"
                    "You can receive your secret cards."
                ),
                parse_mode="HTML"
            )

        except Exception:
            remove_game_player(
                game_id,
                player["user_id"]
            )

            removed.append(
                player_name(player)
            )

    remaining = get_game_players(game_id)

    if removed:
        removed_text = "\n".join(
            f"• {name}"
            for name in removed
        )

        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "⏰ <b>PRIVATE CHECK FINISHED</b>\n\n"
                "❌ Removed:\n"
                f"{removed_text}\n\n"
                f"👥 Remaining: {len(remaining)}/4\n\n"
                "Replacement players can use the Join button."
            ),
            parse_mode="HTML"
        )

    if len(remaining) == 4:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "✅ <b>All 4 players are ready!</b>\n\n"
                "The host can now use /begin."
            ),
            parse_mode="HTML"
        )

    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"👥 Need {4 - len(remaining)} "
                "more player(s)."
            )
        )


# =========================================================
# /BEGIN
# =========================================================

async def begin(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    players = get_game_players(game["id"])

    if len(players) != 4:
        await update.message.reply_text(
            f"❌ Need exactly 4 players.\n"
            f"Current: {len(players)}/4"
        )
        return

    await start_parchi_game(
        context,
        game["id"]
    )


# =========================================================
# START PARCHI
# =========================================================

async def start_parchi_game(context, game_id):
    game = get_game(game_id)

    if not game or game["status"] != "lobby":
        return

    players = get_game_players(game_id)

    if len(players) != 4:
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

    # PRIVATE CARD DELIVERY
    for player in players:
        cards = hands[player["user_id"]]

        card_text = "\n".join(
            f"🎴 {i + 1}. {card}"
            for i, card in enumerate(cards)
        )

        try:
            await context.bot.send_message(
                chat_id=player["user_id"],
                text=(
                    "🔒 <b>YOUR SECRET CARDS</b>\n\n"
                    f"{card_text}\n\n"
                    "Do not share your cards."
                ),
                parse_mode="HTML"
            )
        except Exception:
            pass

    await context.bot.send_message(
        chat_id=game["chat_id"],
        text=(
            "🔥 <b>16 PARCHI GAME STARTED!</b>\n\n"
            "🎴 Cards have been privately distributed.\n"
            "🔒 Card information is hidden from the group.\n\n"
            "The first player will receive a private "
            "card-selection menu."
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

async def show_turn(context, chat_id, game_id):
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

    # ONLY GROUP REMINDER
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"🎴 <b>{mention_player(current)}</b>\n\n"
            "📩 <b>Your turn!</b>\n"
            "Check your DM and send 1 card."
        ),
        parse_mode="HTML"
    )

    # PRIVATE MENU
    cards = state["hands"][current["user_id"]]

    keyboard = []

    for index, card in enumerate(cards):
        keyboard.append([
            InlineKeyboardButton(
                f"🎴 {card}",
                callback_data=f"card:{game_id}:{index}"
            )
        ])

    try:
        await context.bot.send_message(
            chat_id=current["user_id"],
            text=(
                "🎴 <b>YOUR TURN</b>\n\n"
                "Choose ONE card to pass "
                "to the next player."
            ),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )

    except Exception:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"⚠️ {mention_player(current)}, "
                "please open the bot privately and "
                "send /start."
            ),
            parse_mode="HTML"
        )


# =========================================================
# CARD SELECTION
# =========================================================

async def card_selected(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query

    await query.answer()

    parts = query.data.split(":")

    if len(parts) != 3:
        return

    game_id = int(parts[1])
    card_index = int(parts[2])

    game = get_game(game_id)

    if not game or game["status"] != "active":
        await query.edit_message_text(
            "❌ Game is no longer active."
        )
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
            "❌ It is not your turn.",
            show_alert=True
        )
        return

    sender_cards = state["hands"][sender["user_id"]]

    if card_index < 0 or card_index >= len(sender_cards):
        await query.answer(
            "Invalid card.",
            show_alert=True
        )
        return

    card = sender_cards.pop(card_index)

    receiver_index = (turn + 1) % 4
    receiver = players[receiver_index]

    receiver_cards = state["hands"][receiver["user_id"]]
    receiver_cards.append(card)

    # Remove old button menu.
    try:
        await query.edit_message_text(
            "✅ <b>Card sent!</b>\n\n"
            "Your card was privately passed "
            "to the next player.",
            parse_mode="HTML"
        )
    except Exception:
        pass

    # Receiver gets private cards.
    receiver_card_text = "\n".join(
        f"🎴 {i + 1}. {name}"
        for i, name in enumerate(receiver_cards)
    )

    try:
        await context.bot.send_message(
            chat_id=receiver["user_id"],
            text=(
                "📥 <b>CARD RECEIVED</b>\n\n"
                "Your current cards:\n\n"
                f"{receiver_card_text}\n\n"
                "🔒 These cards are private."
            ),
            parse_mode="HTML"
        )
    except Exception:
        pass

    # WINNER CHECK
    winner = check_winner(receiver_cards)

    if winner:
        winner_id = receiver["user_id"]
        amount = winner["amount"]

        state["winner"] = winner_id

        change_coins(
            winner_id,
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
                f"🏆 {mention_player(receiver)}\n"
                f"💰 Prize: <b>{amount:,} coins</b>\n\n"
                "🏏 Game finished!"
            ),
            parse_mode="HTML"
        )

        try:
            await context.bot.send_message(
                chat_id=winner_id,
                text=(
                    "🏆 <b>YOU WON!</b>\n\n"
                    f"🎴 {winner['player']} × 4\n"
                    f"💰 Prize: <b>{amount:,} coins</b>\n"
                    f"💳 Balance: "
                    f"{get_balance(winner_id):,}"
                ),
                parse_mode="HTML"
            )
        except Exception:
            pass

        parchi_games.pop(
            game_id,
            None
        )

        return

    # NEXT TURN
    state["turn"] += 1

    update_game(
        game_id,
        current_turn=state["turn"]
    )

    await show_turn(
        context,
        game["chat_id"],
        game_id
    )


# =========================================================
# /ENDGAME
# =========================================================

async def endgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            "❌ No active game."
        )
        return

    if (
        update.effective_user.id != game["host_id"]
        and not is_privileged(update.effective_user.id)
    ):
        await update.message.reply_text(
            "❌ Only the host, owner or admin can end it."
        )
        return

    end_game(game["id"])

    parchi_games.pop(
        game["id"],
        None
    )

    await update.message.reply_text(
        "🛑 <b>GAME ENDED</b>\n\n"
        "The current Parchi game has been stopped.",
        parse_mode="HTML"
    )


# =========================================================
# FREE FLY
# =========================================================

async def fly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    remember_user(update.effective_user)

    chat_id = update.effective_chat.id

    if chat_id in fly_games:
        await update.message.reply_text(
            "🚀 A Fly round is already running."
        )
        return

    fly_games[chat_id] = {
        "started_at": time.monotonic(),
        "message_id": None,
        "owner_user_id": update.effective_user.id,
        "cashed_out": False,
        "stopped": False
    }

    keyboard = [[
        InlineKeyboardButton(
            "💰 CASH OUT",
            callback_data=f"flycash:{chat_id}"
        )
    ]]

    sent = await update.message.reply_text(
        "🚀 <b>FLY STARTED</b>\n\n"
        "📈 Multiplier: <b>1.10x</b>\n\n"
        "This is free arcade mode.\n"
        "No coins are wagered.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

    fly_games[chat_id]["message_id"] = sent.message_id

    asyncio.create_task(
        fly_loop(
            context,
            chat_id
        )
    )


# =========================================================
# ONE-MESSAGE FLY LOOP
# =========================================================

async def fly_loop(context, chat_id):
    state = fly_games.get(chat_id)

    if not state:
        return

    started_at = state["started_at"]

    # Random crash point.
    crash = round(
        min(
            100.0,
            max(
                1.25,
                1.10 / random.random()
            )
        ),
        2
    )

    last_multiplier = 1.10

    while True:
        await asyncio.sleep(1)

        state = fly_games.get(chat_id)

        if not state:
            return

        if state["stopped"]:
            return

        if state["cashed_out"]:
            return

        elapsed = (
            time.monotonic()
            - started_at
        )

        multiplier = arcade_multiplier(
            elapsed
        )

        # Crash.
        if multiplier >= crash:
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=state["message_id"],
                    text=(
                        "💥 <b>FLY CRASHED!</b>\n\n"
                        f"📉 Final multiplier: "
                        f"<b>{crash:.2f}x</b>\n\n"
                        "No coins were wagered."
                    ),
                    parse_mode="HTML"
                )
            except Exception:
                pass

            fly_games.pop(
                chat_id,
                None
            )

            return

        # Update the SAME message.
        if multiplier > last_multiplier:
            try:
                keyboard = [[
                    InlineKeyboardButton(
                        "💰 CASH OUT",
                        callback_data=f"flycash:{chat_id}"
                    )
                ]]

                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=state["message_id"],
                    text=(
                        "🚀 <b>FLY</b>\n\n"
                        f"📈 Current multiplier: "
                        f"<b>{multiplier:.2f}x</b>\n\n"
                        "Press CASH OUT to finish this "
                        "free arcade round."
                    ),
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="HTML"
                )

            except Exception:
                pass

            last_multiplier = multiplier


# =========================================================
# FLY CASH OUT
# =========================================================

async def fly_cashout(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query

    await query.answer()

    chat_id = int(
        query.data.split(":")[1]
    )

    state = fly_games.get(chat_id)

    if not state:
        await query.answer(
            "Fly round is already finished.",
            show_alert=True
        )
        return

    if state["cashed_out"]:
        return

    if state["stopped"]:
        return

    elapsed = (
        time.monotonic()
        - state["started_at"]
    )

    multiplier = arcade_multiplier(
        elapsed
    )

    state["cashed_out"] = True

    # Free arcade score.
    arcade_points = max(
        1,
        int(multiplier * 100)
    )

    try:
        await query.edit_message_text(
            "💰 <b>CASHED OUT!</b>\n\n"
            f"📈 Multiplier: <b>{multiplier:.2f}x</b>\n"
            f"🎮 Arcade points: <b>{arcade_points:,}</b>\n\n"
            "This was a free arcade round — "
            "no coins were wagered.",
            parse_mode="HTML"
        )
    except Exception:
        pass

    fly_games.pop(
        chat_id,
        None
    )


# =========================================================
# /STOPFLY — OWNER ONLY
# =========================================================

async def stopfly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(
        update.effective_user.id
    ):
        await update.message.reply_text(
            "❌ Owner only."
        )
        return

    chat_id = update.effective_chat.id

    state = fly_games.get(chat_id)

    if not state:
        await update.message.reply_text(
            "❌ No Fly round is running."
        )
        return

    state["stopped"] = True

    message_id = state["message_id"]

    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=(
                "🛑 <b>FLY STOPPED BY OWNER</b>\n\n"
                "The free arcade round has been stopped.\n"
                "No coins were wagered."
            ),
            parse_mode="HTML"
        )
    except Exception:
        pass

    fly_games.pop(
        chat_id,
        None
    )

    await update.message.reply_text(
        "✅ Fly round stopped."
    )


# =========================================================
# /GIVE + /ADD
# =========================================================

async def give_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(
        update.effective_user.id
    ):
        await update.message.reply_text(
            "❌ Owner only."
        )
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "❌ Reply to the user's message.\n\n"
            "Example:\n"
            "/give 5000"
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
        amount,
        f"Owner gave {amount} coins"
    )

    await update.message.reply_text(
        "✅ <b>COINS ADDED</b>\n\n"
        f"👤 {target.first_name}\n"
        f"💰 Added: {amount:,}\n"
        f"💳 Balance: {get_balance(target.id):,}",
        parse_mode="HTML"
    )


# =========================================================
# /REMOVEC
# =========================================================

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
            "❌ Reply to the user's message."
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

    current = get_balance(target.id)

    actual_remove = min(
        amount,
        current
    )

    change_coins(
        target.id,
        -actual_remove,
        f"Owner removed {actual_remove} coins"
    )

    await update.message.reply_text(
        "✅ <b>COINS REMOVED</b>\n\n"
        f"👤 {target.first_name}\n"
        f"💰 Removed: {actual_remove:,}\n"
        f"💳 Balance: {get_balance(target.id):,}",
        parse_mode="HTML"
    )


# =========================================================
# /ADMIN
# =========================================================

async def make_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(
        update.effective_user.id
    ):
        await update.message.reply_text(
            "❌ Owner only."
        )
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "❌ Reply to a user with /admin."
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
    if not is_owner(
        update.effective_user.id
    ):
        await update.message.reply_text(
            "❌ Owner only."
        )
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "❌ Reply to a user with /unadmin."
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

    elif query.data.startswith("card:"):
        await card_selected(
            update,
            context
        )

    elif query.data.startswith("flycash:"):
        await fly_cashout(
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

    if not OWNER_ID:
        raise RuntimeError(
            "OWNER_ID environment variable is missing."
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
        CommandHandler("leaderboard", show_leaderboard)
    )

    # Parchi
    application.add_handler(
        CommandHandler("startgame", startgame)
    )

    application.add_handler(
        CommandHandler("begin", begin)
    )

    application.add_handler(
        CommandHandler("endgame", endgame)
    )

    # Free Fly
    application.add_handler(
        CommandHandler("fly", fly)
    )

    application.add_handler(
        CommandHandler("stopfly", stopfly)
    )

    # Owner
    application.add_handler(
        CommandHandler("give", give_coins)
    )

    application.add_handler(
        CommandHandler("add", give_coins)
    )

    application.add_handler(
        CommandHandler("removec", remove_coins)
    )

    application.add_handler(
        CommandHandler("admin", make_admin)
    )

    application.add_handler(
        CommandHandler("unadmin", remove_admin_command)
    )

    # Buttons
    application.add_handler(
        CallbackQueryHandler(callbacks)
    )

    print("🏏 16 Parchi Bot started!")

    application.run_polling()


if __name__ == "__main__":
    main()
