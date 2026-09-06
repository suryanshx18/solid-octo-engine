import os
import asyncio
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
    generate_crash_point,
    multiplier_at_time,
    calculate_payout,
    MIN_MULTIPLIER,
    MAX_MULTIPLIER
)


BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))


# =========================================================
# GLOBAL GAME MEMORY
# =========================================================

parchi_games = {}

fly_games = {}


# =========================================================
# HELPERS
# =========================================================

def mention(user):
    name = user.first_name or "Player"

    return f'<a href="tg://user?id={user.id}">{name}</a>'


def is_owner(user_id):
    return user_id == OWNER_ID


def is_privileged(user_id):
    return (
        is_owner(user_id)
        or is_admin(user_id)
    )


def get_parchi_game(game_id):
    return parchi_games.get(game_id)


def game_is_active(game_id):
    game = get_game(game_id)

    if not game:
        return False

    return game["status"] in ("lobby", "active")


# =========================================================
# /START
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    add_user(
        user.id,
        user.username,
        user.first_name
    )

    await update.message.reply_text(
        "🏏 <b>16 Parchi Game</b>\n\n"
        "You are registered successfully.\n\n"
        "Commands:\n"
        "/startgame - Start a Parchi game\n"
        "/bal - Check coins\n"
        "/leaderboard - Leaderboard\n"
        "/fly - Play Rocket Fly\n"
        "/endgame - End current game\n",
        parse_mode="HTML"
    )


# =========================================================
# BALANCE
# =========================================================

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    add_user(
        user.id,
        user.username,
        user.first_name
    )

    coins = get_balance(user.id)

    await update.message.reply_text(
        f"💰 <b>Your Coins:</b> {coins:,}",
        parse_mode="HTML"
    )


# =========================================================
# LEADERBOARD
# =========================================================

async def show_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):

    rows = leaderboard(10)

    if not rows:
        await update.message.reply_text(
            "No players yet."
        )
        return

    text = "🏆 <b>Leaderboard</b>\n\n"

    for index, row in enumerate(rows, start=1):

        name = row["first_name"] or row["username"] or "Player"

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

    user = update.effective_user

    add_user(
        user.id,
        user.username,
        user.first_name
    )

    existing = get_active_game(update.effective_chat.id)

    if existing:
        await update.message.reply_text(
            "❌ A game is already running in this group."
        )
        return

    game_id = create_game(
        update.effective_chat.id,
        user.id,
        "parchi"
    )

    parchi_games[game_id] = {
        "hands": {},
        "turn": 0,
        "started": False,
        "removed": set(),
        "winner": None
    }

    keyboard = [
        [
            InlineKeyboardButton(
                "🎟 Join Parchi Game",
                callback_data=f"join:{game_id}"
            )
        ]
    ]

    await update.message.reply_text(
        "🏏 <b>16 PARCHI GAME</b>\n\n"
        "🎴 16 total parchis\n"
        "👥 Exactly 4 players\n\n"
        "Cards:\n"
        "• Virat Kohli — 5,000 coins\n"
        "• MS Dhoni — 4,500 coins\n"
        "• Rohit Sharma — 4,000 coins\n"
        "• KL Rahul — 3,500 coins\n\n"
        "Each player gets 4 random cards.\n\n"
        "⚠️ After joining, you have <b>60 seconds</b> "
        "to open the bot privately and press /start.\n\n"
        "Press the button to join.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


# =========================================================
# JOIN
# =========================================================

async def join_game(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    await query.answer()

    game_id = int(query.data.split(":")[1])

    game = get_game(game_id)

    if not game:
        await query.answer(
            "Game no longer exists.",
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

    add_user(
        user.id,
        user.username,
        user.first_name
    )

    players = get_game_players(game_id)

    already = get_game_player(
        game_id,
        user.id
    )

    if already:
        await query.answer(
            "You already joined!",
            show_alert=True
        )
        return

    if len(players) >= 4:
        await query.answer(
            "Game is full!",
            show_alert=True
        )
        return

    position = len(players)

    add_game_player(
        game_id,
        user.id,
        position
    )

    players = get_game_players(game_id)

    text = (
        "🏏 <b>16 PARCHI GAME</b>\n\n"
        f"Game ID: <code>{game_id}</code>\n\n"
        "Players:\n"
    )

    for p in players:
        text += f"• {p['first_name'] or 'Player'}\n"

    text += (
        f"\n👥 {len(players)}/4 players\n\n"
    )

    if len(players) == 4:

        text += (
            "✅ <b>4 players joined!</b>\n\n"
            "The bot will now check private access.\n"
            "Every player must have opened the bot with /start.\n\n"
            "⏳ You have 60 seconds."
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    "▶️ Begin Game",
                    callback_data=f"begin:{game_id}"
                )
            ]
        ]

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )

        asyncio.create_task(
            private_access_check(
                context,
                game_id,
                update.effective_chat.id
            )
        )

    else:

        text += (
            "\nWaiting for more players..."
        )

        await query.edit_message_text(
            text,
            parse_mode="HTML"
        )


# =========================================================
# PRIVATE ACCESS CHECK
# =========================================================

async def private_access_check(context, game_id, chat_id):

    await asyncio.sleep(60)

    game = get_game(game_id)

    if not game:
        return

    if game["status"] != "lobby":
        return

    players = get_game_players(game_id)

    kicked = []

    for player in players:

        user_id = player["user_id"]

        try:

            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "🏏 Your Parchi game is ready!\n\n"
                    "You passed the private bot check."
                )
            )

        except Exception:

            remove_game_player(
                game_id,
                user_id
            )

            kicked.append(
                player["first_name"] or "Player"
            )

    remaining = get_game_players(game_id)

    if kicked:

        names = ", ".join(kicked)

        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "⏰ <b>60 seconds finished.</b>\n\n"
                f"❌ Removed: {names}\n\n"
                f"👥 Remaining players: {len(remaining)}/4\n\n"
                "A new player can join."
            ),
            parse_mode="HTML"
        )

    if len(remaining) == 4:

        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "✅ All 4 players passed the private check.\n\n"
                "The host can now press /begin."
            )
        )

    elif len(remaining) < 4:

        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "⚠️ The game needs exactly 4 players.\n"
                "Use the Join button for replacement players."
            )
        )


# =========================================================
# /BEGIN
# =========================================================

async def begin(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_chat.type == "private":
        await update.message.reply_text(
            "Use /begin inside the group."
        )
        return

    game = get_active_game(
        update.effective_chat.id
    )

    if not game:
        await update.message.reply_text(
            "❌ No active Parchi lobby."
        )
        return

    user_id = update.effective_user.id

    if (
        user_id != game["host_id"]
        and not is_privileged(user_id)
    ):
        await update.message.reply_text(
            "❌ Only the host/admin can begin the game."
        )
        return

    players = get_game_players(game["id"])

    if len(players) != 4:

        await update.message.reply_text(
            f"❌ Exactly 4 players are required.\n"
            f"Current players: {len(players)}"
        )
        return

    game_id = game["id"]

    player_ids = [
        p["user_id"]
        for p in players
    ]

    hands = deal_cards(player_ids)

    parchi_games[game_id]["hands"] = hands
    parchi_games[game_id]["turn"] = 0
    parchi_games[game_id]["started"] = True

    update_game(
        game_id,
        status="active",
        current_turn=0
    )

    # Send secret cards.
    for player in players:

        user_id = player["user_id"]
        cards = hands[user_id]

        try:

            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "🎴 <b>YOUR SECRET PARCHIS</b>\n\n"
                    f"{format_cards(cards)}\n\n"
                    "Keep these cards private!"
                ),
                parse_mode="HTML"
            )

        except Exception:

            remove_game_player(
                game_id,
                user_id
            )

    await update.message.reply_text(
        "🎴 <b>Cards have been distributed!</b>\n\n"
        "Each player has 4 secret parchis.\n\n"
        "The card passing round is starting.",
        parse_mode="HTML"
    )

    await show_turn(
        context,
        update.effective_chat.id,
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

    keyboard = [
        [
            InlineKeyboardButton(
                "🎴 Give 1 Card",
                callback_data=f"give:{game_id}"
            )
        ]
    ]

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"🎴 <b>{current['first_name'] or 'Player'}</b>'s turn\n\n"
            "Choose one card to give to the next player.\n\n"
            "Cards are transferred clockwise."
        ),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


# =========================================================
# GIVE CARD
# =========================================================

async def give_card(update: Update, context: ContextTypes.DEFAULT_TYPE):

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

        await query.answer(
            "Game no longer has 4 players.",
            show_alert=True
        )
        return

    state = parchi_games[game_id]

    turn = state["turn"] % 4

    current_player = players[turn]

    if query.from_user.id != current_player["user_id"]:

        await query.answer(
            "It is not your turn.",
            show_alert=True
        )
        return

    cards = state["hands"][current_player["user_id"]]

    if not cards:

        await query.answer(
            "You have no cards.",
            show_alert=True
        )
        return

    keyboard = []

    for index, card in enumerate(cards):

        keyboard.append([
            InlineKeyboardButton(
                f"{index + 1}. {card}",
                callback_data=f"card:{game_id}:{index}"
            )
        ])

    await query.edit_message_text(
        "🎴 <b>Choose the card to give</b>\n\n"
        "The card will go to the next player.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


# =========================================================
# CARD SELECTED
# =========================================================

async def card_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):

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

    state = parchi_games[game_id]

    turn = state["turn"] % 4

    sender = players[turn]

    if query.from_user.id != sender["user_id"]:

        await query.answer(
            "It is not your turn.",
            show_alert=True
        )
        return

    sender_cards = state["hands"][sender["user_id"]]

    if card_index >= len(sender_cards):
        return

    card = sender_cards.pop(card_index)

    next_index = (turn + 1) % 4

    receiver = players[next_index]

    state["hands"][receiver["user_id"]].append(card)

    # Send updated private cards.
    try:

        await context.bot.send_message(
            chat_id=receiver["user_id"],
            text=(
                "🎴 <b>You received a card!</b>\n\n"
                f"Card: <b>{card}</b>\n\n"
                "Your current cards:\n"
                f"{format_cards(state['hands'][receiver['user_id']])}"
            ),
            parse_mode="HTML"
        )

    except Exception:
        pass

    # Check winner.
    winner = check_winner(
        state["hands"][receiver["user_id"]]
    )

    if winner:

        state["winner"] = receiver["user_id"]

        amount = winner["amount"]
        winner_name = receiver["first_name"] or "Player"

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
                f"🏆 {winner_name}\n"
                f"🎴 {winner['player']} × 4\n\n"
                f"💰 Prize: <b>{amount:,} coins</b>\n\n"
                "🏏 Game finished!"
            ),
            parse_mode="HTML"
        )

        return

    # Next player's turn.
    state["turn"] += 1

    update_game(
        game_id,
        current_turn=state["turn"]
    )

    await context.bot.send_message(
        chat_id=game["chat_id"],
        text=(
            f"🎴 {sender['first_name'] or 'Player'} "
            f"gave <b>{card}</b> to "
            f"{receiver['first_name'] or 'Player'}."
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

async def endgame(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_chat.type == "private":
        await update.message.reply_text(
            "❌ Use /endgame inside the group."
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
            "❌ Only the game host, owner or admin can use /endgame."
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
        "The current game has been cancelled by the host/admin.\n"
        "No further cards or Fly actions are allowed.",
        parse_mode="HTML"
    )


# =========================================================
# /FLY
# =========================================================

async def fly(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    add_user(
        user.id,
        user.username,
        user.first_name
    )

    chat_id = update.effective_chat.id

    if chat_id in fly_games:

        await update.message.reply_text(
            "🚀 A Fly round is already running."
        )
        return

    # Syntax:
    # /fly 100

    if not context.args:

        await update.message.reply_text(
            "🚀 <b>Fly</b>\n\n"
            "Use:\n"
            "<code>/fly 100</code>\n\n"
            "Minimum bet: 1 coin.",
            parse_mode="HTML"
        )
        return

    try:

        bet = int(context.args[0])

    except ValueError:

        await update.message.reply_text(
            "❌ Enter a valid number."
        )
        return

    if bet <= 0:

        await update.message.reply_text(
            "❌ Bet must be greater than 0."
        )
        return

    balance = get_balance(user.id)

    if balance < bet:

        await update.message.reply_text(
            f"❌ You only have {balance:,} coins."
        )
        return

    change_coins(
        user.id,
        -bet,
        "Fly bet"
    )

    fly_games[chat_id] = {
        "crash": generate_crash_point(),
        "players": {
            user.id: {
                "bet": bet,
                "cashed_out": False,
                "cashout_multiplier": None,
                "payout": 0
            }
        },
        "started": True
    }

    game = fly_games[chat_id]

    await update.message.reply_text(
        "🚀 <b>ROCKET FLY STARTED!</b>\n\n"
        f"💰 Bet: {bet:,}\n"
        f"📈 Starting multiplier: {MIN_MULTIPLIER}x\n"
        f"📉 Maximum multiplier: {MAX_MULTIPLIER}x\n\n"
        "Press CASH OUT before the rocket crashes!",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "💰 CASH OUT",
                    callback_data=f"cashout:{chat_id}"
                )
            ]
        ]),
        parse_mode="HTML"
    )

    asyncio.create_task(
        run_fly(
            context,
            chat_id
        )
    )


# =========================================================
# FLY ENGINE
# =========================================================

async def run_fly(context, chat_id):

    game = fly_games.get(chat_id)

    if not game:
        return

    crash = game["crash"]

    elapsed = 0

    while True:

        await asyncio.sleep(1)

        elapsed += 1

        multiplier = multiplier_at_time(
            elapsed
        )

        # Crash.
        if multiplier >= crash:

            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "💥 <b>ROCKET CRASHED!</b>\n\n"
                    f"📉 Crash: <b>{crash:.2f}x</b>"
                ),
                parse_mode="HTML"
            )

            # Players who did not cash out lose their bet.
            results = []

            for user_id, player in game["players"].items():

                if player["cashed_out"]:

                    results.append(
                        f"💰 {user_id}: "
                        f"+{player['payout']:,} coins"
                    )

                else:

                    results.append(
                        f"❌ {user_id}: "
                        f"Lost {player['bet']:,} coins"
                    )

            if results:

                await context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        "📊 <b>Fly Results</b>\n\n"
                        + "\n".join(results)
                    ),
                    parse_mode="HTML"
                )

            fly_games.pop(
                chat_id,
                None
            )

            return

        # Maximum reached.
        if multiplier >= MAX_MULTIPLIER:

            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "🚀 <b>100x MAXIMUM REACHED!</b>\n\n"
                    "The rocket has reached the maximum multiplier."
                ),
                parse_mode="HTML"
            )

            fly_games.pop(
                chat_id,
                None
            )

            return

        # Update public multiplier.
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🚀 <b>{multiplier:.2f}x</b>",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        f"💰 CASH OUT @ {multiplier:.2f}x",
                        callback_data=f"cashout:{chat_id}"
                    )
                ]
            ]),
            parse_mode="HTML"
        )


# =========================================================
# CASH OUT
# =========================================================

async def cashout(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    await query.answer()

    chat_id = int(
        query.data.split(":")[1]
    )

    game = fly_games.get(chat_id)

    if not game:

        await query.answer(
            "Rocket has already crashed.",
            show_alert=True
        )
        return

    user_id = query.from_user.id

    player = game["players"].get(user_id)

    if not player:

        await query.answer(
            "You don't have a bet in this round.",
            show_alert=True
        )
        return

    if player["cashed_out"]:

        await query.answer(
            "You already cashed out.",
            show_alert=True
        )
        return

    # Approximate current multiplier from elapsed time
    # based on game start timestamp stored by task.
    # We calculate using task start marker.
    if "start_time" not in game:
        game["start_time"] = asyncio.get_running_loop().time()

    elapsed = (
        asyncio.get_running_loop().time()
        - game["start_time"]
    )

    multiplier = multiplier_at_time(
        elapsed
    )

    if multiplier < MIN_MULTIPLIER:
        multiplier = MIN_MULTIPLIER

    multiplier = min(
        multiplier,
        MAX_MULTIPLIER
    )

    # If multiplier has already crossed crash point,
    # cashout is invalid.
    if multiplier >= game["crash"]:

        await query.answer(
            "💥 Too late! Rocket crashed.",
            show_alert=True
        )
        return

    payout = calculate_payout(
        player["bet"],
        multiplier
    )

    player["cashed_out"] = True
    player["cashout_multiplier"] = multiplier
    player["payout"] = payout

    change_coins(
        user_id,
        payout,
        f"Fly cashout at {multiplier:.2f}x"
    )

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"💰 <b>{query.from_user.first_name}</b> "
            f"cashed out!\n\n"
            f"📈 Multiplier: <b>{multiplier:.2f}x</b>\n"
            f"💵 Bet: {player['bet']:,}\n"
            f"🏆 Won: <b>{payout:,} coins</b>"
        ),
        parse_mode="HTML"
    )


# =========================================================
# ADMIN COMMANDS
# =========================================================

async def add_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_owner(update.effective_user.id):

        await update.message.reply_text(
            "❌ Owner only."
        )
        return

    if not update.message.reply_to_message:

        await update.message.reply_text(
            "Reply to a user's message:\n"
            "/addc 1000"
        )
        return

    if not context.args:

        await update.message.reply_text(
            "Usage: /addc 1000"
        )
        return

    try:
        amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text(
            "Invalid amount."
        )
        return

    target = update.message.reply_to_message.from_user

    add_user(
        target.id,
        target.username,
        target.first_name
    )

    change_coins(
        target.id,
        amount,
        "Owner added coins"
    )

    await update.message.reply_text(
        f"✅ Added {amount:,} coins to "
        f"{target.first_name}."
    )


async def remove_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_owner(update.effective_user.id):

        await update.message.reply_text(
            "❌ Owner only."
        )
        return

    if not update.message.reply_to_message:

        await update.message.reply_text(
            "Reply to a user's message:\n"
            "/removec 1000"
        )
        return

    if not context.args:

        await update.message.reply_text(
            "Usage: /removec 1000"
        )
        return

    try:
        amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text(
            "Invalid amount."
        )
        return

    target = update.message.reply_to_message.from_user

    add_user(
        target.id,
        target.username,
        target.first_name
    )

    change_coins(
        target.id,
        -abs(amount),
        "Owner removed coins"
    )

    await update.message.reply_text(
        f"✅ Removed {amount:,} coins from "
        f"{target.first_name}."
    )


async def make_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_owner(update.effective_user.id):

        await update.message.reply_text(
            "❌ Owner only."
        )
        return

    if not update.message.reply_to_message:

        await update.message.reply_text(
            "Reply to a user with /admin"
        )
        return

    target = update.message.reply_to_message.from_user

    add_admin(target.id)

    await update.message.reply_text(
        f"✅ {target.first_name} is now an admin."
    )


async def remove_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_owner(update.effective_user.id):

        await update.message.reply_text(
            "❌ Owner only."
        )
        return

    if not update.message.reply_to_message:

        await update.message.reply_text(
            "Reply to a user with /unadmin"
        )
        return

    target = update.message.reply_to_message.from_user

    remove_admin(target.id)

    await update.message.reply_text(
        f"✅ {target.first_name} removed from admins."
    )


# =========================================================
# CALLBACK ROUTER
# =========================================================

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    data = query.data

    if data.startswith("join:"):
        await join_game(
            update,
            context
        )

    elif data.startswith("begin:"):
        await query.answer()

        await begin_from_callback(
            update,
            context
        )

    elif data.startswith("give:"):
        await give_card(
            update,
            context
        )

    elif data.startswith("card:"):
        await card_selected(
            update,
            context
        )

    elif data.startswith("cashout:"):
        await cashout(
            update,
            context
        )


# =========================================================
# BEGIN BUTTON
# =========================================================

async def begin_from_callback(update, context):

    query = update.callback_query

    game_id = int(
        query.data.split(":")[1]
    )

    game = get_game(game_id)

    if not game:
        return

    if game["status"] != "lobby":

        await query.answer(
            "Game already started.",
            show_alert=True
        )
        return

    user_id = query.from_user.id

    if (
        user_id != game["host_id"]
        and not is_privileged(user_id)
    ):

        await query.answer(
            "Only the host/admin can begin.",
            show_alert=True
        )
        return

    players = get_game_players(game_id)

    if len(players) != 4:

        await query.answer(
            "Exactly 4 players are required.",
            show_alert=True
        )
        return

    # Reuse begin logic.
    update.message = None

    await start_game_direct(
        update,
        context,
        game_id
    )


async def start_game_direct(update, context, game_id):

    game = get_game(game_id)

    players = get_game_players(game_id)

    if len(players) != 4:
        return

    player_ids = [
        p["user_id"]
        for p in players
    ]

    hands = deal_cards(
        player_ids
    )

    parchi_games[game_id] = {
        "hands": hands,
        "turn": 0,
        "started": True,
        "removed": set(),
        "winner": None
    }

    update_game(
        game_id,
        status="active",
        current_turn=0
    )

    for player in players:

        try:

            await context.bot.send_message(
                chat_id=player["user_id"],
                text=(
                    "🎴 <b>YOUR SECRET PARCHIS</b>\n\n"
                    f"{format_cards(hands[player['user_id']])}\n\n"
                    "Don't show your cards to other players."
                ),
                parse_mode="HTML"
            )

        except Exception:
            pass

    await context.bot.send_message(
        chat_id=game["chat_id"],
        text=(
            "🔥 <b>GAME STARTED!</b>\n\n"
            "All 16 parchis have been distributed.\n"
            "Each player has 4 cards.\n\n"
            "Pass one card clockwise each turn.\n\n"
            "First player to collect 4 identical cards wins!"
        ),
        parse_mode="HTML"
    )

    await show_turn(
        context,
        game["chat_id"],
        game_id
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

    # General commands.
    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    application.add_handler(
        CommandHandler(
            "bal",
            balance
        )
    )

    application.add_handler(
        CommandHandler(
            "leaderboard",
            show_leaderboard
        )
    )

    # Parchi.
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

    # Fly.
    application.add_handler(
        CommandHandler(
            "fly",
            fly
        )
    )

    # Owner/admin.
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
            make_admin
        )
    )

    application.add_handler(
        CommandHandler(
            "unadmin",
            remove_admin_command
        )

    )

    application.add_handler(
        CallbackQueryHandler(
            callbacks
        )
    )

    print("🏏 16 Parchi Bot started...")

    application.run_polling()


if __name__ == "__main__":
    main()
