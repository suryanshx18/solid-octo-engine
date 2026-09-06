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
    claim_free_coins,
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
        player.get("first_name")
        or player.get("username")
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
        "Your private connection is ready.\n"  
        "Use /free to claim your 10,000 welcome bonus!\n\n"  
        "Use /help to see game rules and commands.",  
        parse_mode="HTML"  
    )

# =========================================================
# /HELP
# =========================================================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    remember_user(update.effective_user)

    text = (  
        "📖 <b>16 PARCHI — HELP & COMMANDS</b>\n\n"  

        "🏏 <b>WHAT IS 16 PARCHI?</b>\n"  
        "16 Parchi is a 4-player card game. There are 16 cards in total "  
        "(4 cards for 4 cricketers). Each player starts with 4 random cards. "  
        "Players pass 1 card clockwise every turn. The first player to collect "  
        "<b>4 identical cricket player cards</b> wins the round and earns coins!\n\n"  

        "🚀 <b>WHAT IS FLY MODE?</b>\n"  
        "Fly is an arcade crash-betting game. Place your wager during the 60s lobby. "  
        "Cash out before the rocket crashes to multiply your coins!\n\n"  

        "🏏 <b>Game Commands</b>\n"  
        "• /startgame — Create a game lobby\n"  
        "• /join — Join active lobby in group\n"  
        "• /begin — Host starts game manually\n"  
        "• /endgame — End active game\n\n"  

        "💰 <b>Economy & Bonus</b>\n"  
        "• /free — Claim 10,000 one-time bonus\n"  
        "• /bal — Check your coin balance\n"  
        "• /leaderboard — Top players\n\n"  

        "🚀 <b>Fly Mode Commands</b>\n"  
        "• /fly — Start a Fly betting round (60s lobby)\n"  
        "• /fly &lt;amount&gt; or /f &lt;amount&gt; — Bet custom coin amount\n"  
        "• /stopfly — Emergency stop (Owner only)\n\n"  

        "👑 <b>Owner Commands</b>\n"  
        "• /give &lt;amount&gt; — Add coins (by reply)\n"  
        "• /removec &lt;amount&gt; — Remove coins (by reply)\n"  
        "• /admin — Add admin (by reply)\n"  
        "• /unadmin — Remove admin (by reply)\n\n"  

        "🎴 <b>Card Values</b>\n"  
        "• Virat Kohli — 💰 5,000\n"  
        "• MS Dhoni — 💰 4,500\n"  
        "• Rohit Sharma — 💰 4,000\n"  
        "• KL Rahul — 💰 3,500\n\n"  

        "🔒 Cards are private. Group only receives turn reminders."  
    )  

    await update.message.reply_text(  
        text,  
        parse_mode="HTML"  
    )

# =========================================================
# /FREE
# =========================================================

async def free_coins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    remember_user(user)

    success, amount = claim_free_coins(user.id, 10000)

    if success:
        new_balance = get_balance(user.id)
        await update.message.reply_text(
            f"🎉 <b>CONGRATULATIONS!</b>\n\n"
            f"You claimed your one-time bonus of 💰 <b>{amount:,} coins</b>!\n"
            f"💳 Total Balance: <b>{new_balance:,} coins</b>",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text(
            "❌ You have already claimed your one-time <b>/free</b> bonus!",
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

async def show_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    remember_user(update.effective_user)

    rows = leaderboard(10)  

    if not rows:  
        await update.message.reply_text("No players yet.")  
        return  

    text = "🏆 <b>LEADERBOARD</b>\n\n"  

    for index, row in enumerate(rows, 1):  
        name = row["first_name"] or row["username"] or "Player"  
        text += f"{index}. {name} — 💰 {row['coins']:,}\n"  

    await update.message.reply_text(  
        text,  
        parse_mode="HTML"  
    )

# =========================================================
# /STARTGAME
# =========================================================

async def startgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("❌ Start the game inside a group.")
        return

    remember_user(update.effective_user)  
    chat_id = update.effective_chat.id  

    existing = get_active_game(chat_id)  

    if existing:  
        await update.message.reply_text("❌ A game is already running here.")  
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

    sent = await update.message.reply_text(  
        "🏏 <b>16 PARCHI GAME</b>\n\n"  
        f"Game ID: <code>{game_id}</code>\n\n"  
        "👥 <b>0/4 Players Joined</b>\n"  
        "⏳ Need 4 more players to start!\n\n"  
        "Click the button below or type <code>/join</code> to enter.\n\n"  
        "⚠️ Every player must first open the bot privately and send /start.",  
        reply_markup=InlineKeyboardMarkup(keyboard),  
        parse_mode="HTML"  
    )

# =========================================================
# LOBBY HELPER
# =========================================================

def build_lobby_text(game_id, players):
    needed = 4 - len(players)
    text = (  
        "🏏 <b>16 PARCHI GAME</b>\n\n"  
        f"Game ID: <code>{game_id}</code>\n\n"  
        "<b>Players Joined:</b>\n"  
    )  

    for index, player in enumerate(players, 1):  
        text += f"{index}. {player_name(player)}\n"  

    text += f"\n👥 <b>{len(players)}/4 Players</b>\n"  

    if needed > 0:  
        text += f"⏳ Need <b>{needed}</b> more player(s) to start!"  
    else:  
        text += "\n✅ <b>4/4 PLAYERS JOINED! Starting game now...</b>"  

    return text

async def update_lobby_message(context, game_id, message_id=None, query=None):
    game = get_game(game_id)
    if not game or game["status"] != "lobby":  
        return  

    players = get_game_players(game_id)  
    text = build_lobby_text(game_id, players)

    keyboard = []
    if len(players) < 4:
        keyboard = [[  
            InlineKeyboardButton(  
                "🎟 Join Parchi Game",  
                callback_data=f"join:{game_id}"  
            )  
        ]]  

    try:
        if query:
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML"
            )
        elif message_id:
            await context.bot.edit_message_text(
                chat_id=game["chat_id"],
                message_id=message_id,
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML"
            )
    except Exception:  
        pass

# =========================================================
# JOIN (BUTTON & /JOIN COMMAND)
# =========================================================

async def handle_join_logic(user, game, context, query=None):
    remember_user(user)
    game_id = game["id"]

    if game["status"] != "lobby":  
        if query:
            await query.answer("Game already started.", show_alert=True)
        return False, "Game already started."

    if get_game_player(game_id, user.id):  
        if query:
            await query.answer("You already joined!", show_alert=True)
        return False, "You have already joined!"

    players = get_game_players(game_id)  

    if len(players) >= 4:  
        if query:
            await query.answer("Game is full!", show_alert=True)
        return False, "Game is full!"

    add_game_player(game_id, user.id, len(players))  
    players = get_game_players(game_id)

    if query:
        await query.answer("Joined successfully!")
        await update_lobby_message(context, game_id, query=query)
    else:
        await update_lobby_message(context, game_id)

    # AUTOMATIC START WHEN 4 PLAYERS JOIN
    if len(players) == 4:
        asyncio.create_task(start_parchi_game(context, game_id))

    return True, f"Joined game! ({len(players)}/4)"

async def join_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  

    game_id = int(query.data.split(":")[1])  
    game = get_game(game_id)  

    if not game:  
        await query.answer("Game does not exist.", show_alert=True)  
        return  

    await handle_join_logic(query.from_user, game, context, query=query)

async def join_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("❌ Use /join in the group.")
        return

    game = get_active_game(update.effective_chat.id)
    if not game or game["status"] != "lobby":
        await update.message.reply_text("❌ No open lobby to join. Use /startgame first!")
        return

    success, msg = await handle_join_logic(update.effective_user, game, context)
    if not success:
        await update.message.reply_text(f"❌ {msg}")

# =========================================================
# /BEGIN
# =========================================================

async def begin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("❌ Use /begin inside the group.")
        return

    remember_user(update.effective_user)  
    game = get_active_game(update.effective_chat.id)  

    if not game:  
        await update.message.reply_text("❌ No active game.")  
        return  

    if (  
        update.effective_user.id != game["host_id"]  
        and not is_privileged(update.effective_user.id)  
    ):  
        await update.message.reply_text("❌ Only the host, owner or admin can begin.")  
        return  

    players = get_game_players(game["id"])  

    if len(players) != 4:  
        await update.message.reply_text(  
            f"❌ Need exactly 4 players to start.\n"  
            f"Current: {len(players)}/4"  
        )  
        return  

    await start_parchi_game(context, game["id"])

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

    player_ids = [player["user_id"] for player in players]  
    hands = deal_cards(player_ids)  

    parchi_games[game_id] = {  
        "hands": hands,  
        "turn": 0,  
        "started": True,  
        "winner": None  
    }  

    update_game(game_id, status="active", current_turn=0)  

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
                    "Do not share your cards with anyone."  
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
            "🔒 Card information is hidden from group.\n\n"  
            "The first player received their private card selection menu in DM."  
        ),  
        parse_mode="HTML"  
    )  

    await show_turn(context, game["chat_id"], game_id)

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

    # GROUP REMINDER  
    await context.bot.send_message(  
        chat_id=chat_id,  
        text=(  
            f"🎴 <b>{mention_player(current)}</b>\n\n"  
            "📩 <b>Your turn!</b> Check your DM and pick 1 card to pass."  
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
                "Choose ONE card to pass to the next player."  
            ),  
            reply_markup=InlineKeyboardMarkup(keyboard),  
            parse_mode="HTML"  
        )  

    except Exception:  
        await context.bot.send_message(  
            chat_id=chat_id,  
            text=(  
                f"⚠️ {mention_player(current)}, "  
                "please open the bot privately and send /start."  
            ),  
            parse_mode="HTML"  
        )

# =========================================================
# CARD SELECTION
# =========================================================

async def card_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  

    parts = query.data.split(":")  
    if len(parts) != 3:  
        return  

    game_id = int(parts[1])  
    card_index = int(parts[2])  

    game = get_game(game_id)  
    if not game or game["status"] != "active":  
        await query.edit_message_text("❌ Game is no longer active.")  
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
        await query.answer("❌ It is not your turn.", show_alert=True)  
        return  

    sender_cards = state["hands"][sender["user_id"]]  

    if card_index < 0 or card_index >= len(sender_cards):  
        await query.answer("Invalid card.", show_alert=True)  
        return  

    card = sender_cards.pop(card_index)  

    receiver_index = (turn + 1) % 4  
    receiver = players[receiver_index]  

    receiver_cards = state["hands"][receiver["user_id"]]  
    receiver_cards.append(card)  

    try:  
        await query.edit_message_text(  
            "✅ <b>Card sent!</b>\n\n"  
            "Your card was privately passed to the next player.",  
            parse_mode="HTML"  
        )  
    except Exception:  
        pass  

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

        update_game(game_id, status="ended")  

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
                    f"💳 Balance: {get_balance(winner_id):,}"  
                ),  
                parse_mode="HTML"  
            )  
        except Exception:  
            pass  

        parchi_games.pop(game_id, None)  
        return  

    # NEXT TURN  
    state["turn"] += 1  
    update_game(game_id, current_turn=state["turn"])  

    await show_turn(context, game["chat_id"], game_id)

# =========================================================
# /ENDGAME
# =========================================================

async def endgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("❌ Use /endgame in the group.")
        return

    game = get_active_game(update.effective_chat.id)  

    if not game:  
        await update.message.reply_text("❌ No active game.")  
        return  

    if (  
        update.effective_user.id != game["host_id"]  
        and not is_privileged(update.effective_user.id)  
    ):  
        await update.message.reply_text("❌ Only the host, owner or admin can end it.")  
        return  

    end_game(game["id"])  
    parchi_games.pop(game["id"], None)  

    await update.message.reply_text(  
        "🛑 <b>GAME ENDED</b>\n\n"  
        "The current Parchi game has been stopped.",  
        parse_mode="HTML"  
    )

# =========================================================
# FLY GAME LOBBY & ENGINE
# =========================================================

def build_fly_bet_keyboard(chat_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("100", callback_data=f"flybet:{chat_id}:100"),
            InlineKeyboardButton("200", callback_data=f"flybet:{chat_id}:200"),
            InlineKeyboardButton("500", callback_data=f"flybet:{chat_id}:500"),
        ],
        [
            InlineKeyboardButton("1000", callback_data=f"flybet:{chat_id}:1000"),
            InlineKeyboardButton("2500", callback_data=f"flybet:{chat_id}:2500"),
            InlineKeyboardButton("5000", callback_data=f"flybet:{chat_id}:5000"),
        ]
    ])

def build_fly_lobby_text(time_left, bets):
    text = (
        "🚀 <b>FLY ROUND STARTING SOON!</b>\n\n"
        f"⏳ Time remaining to place wagers: <b>{time_left}s</b>\n\n"
        "Select an amount below or use <code>/f <amount></code> or <code>/fly <amount></code> to set a custom wager.\n\n"
        "👥 <b>Current Bets:</b>\n"
    )

    if not bets:  
        text += "<i>No wagers placed yet.</i>\n"  
    else:  
        for user_id, info in bets.items():  
            name = info["first_name"] or info["username"] or "Player"  
            text += f"• {name}: 💰 <b>{info['amount']:,} coins</b>\n"  

    return text

async def fly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Route custom bet if arguments are supplied with /fly (e.g. /fly 89)
    if context.args:
        await fly_custom_bet(update, context)
        return

    remember_user(update.effective_user)
    chat_id = update.effective_chat.id  

    if chat_id in fly_games:  
        await update.message.reply_text("🚀 A Fly round is already active in this group.")  
        return  

    fly_games[chat_id] = {  
        "status": "lobby",  
        "message_id": None,  
        "owner_user_id": update.effective_user.id,  
        "bets": {},  
        "started_at": None,  
        "stopped": False  
    }  

    keyboard = build_fly_bet_keyboard(chat_id)  
    text = build_fly_lobby_text(60, {})  

    sent = await update.message.reply_text(  
        text,  
        reply_markup=keyboard,  
        parse_mode="HTML"  
    )  

    fly_games[chat_id]["message_id"] = sent.message_id  
    asyncio.create_task(fly_lobby_timer(context, chat_id))

async def fly_custom_bet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    remember_user(update.effective_user)
    chat_id = update.effective_chat.id  
    state = fly_games.get(chat_id)  

    if not state or state["status"] != "lobby":  
        await update.message.reply_text("❌ No Fly betting lobby is active right now.")  
        return  

    if not context.args:  
        await update.message.reply_text(  
            "❌ Please enter an amount. Example: <code>/f 1500</code>",  
            parse_mode="HTML"  
        )  
        return  

    try:  
        amount = int(context.args[0])  
    except ValueError:  
        await update.message.reply_text("❌ Amount must be a valid number.")  
        return  

    if amount <= 0:  
        await update.message.reply_text("❌ Amount must be greater than 0.")  
        return  

    user = update.effective_user  
    user_id = user.id  
    current_balance = get_balance(user_id)  
    existing_bet = state["bets"].get(user_id, {}).get("amount", 0)  

    if current_balance + existing_bet < amount:  
        await update.message.reply_text(  
            f"❌ Insufficient balance! Your total balance is {current_balance:,} coins."  
        )  
        return  

    if existing_bet > 0:  
        change_coins(user_id, existing_bet, "Fly bet update refund")  

    change_coins(user_id, -amount, "Fly bet placed")  

    state["bets"][user_id] = {  
        "amount": amount,  
        "first_name": user.first_name,  
        "username": user.username,  
        "cashed_out": False,  
        "cashout_mult": 0.0,  
        "win_amount": 0  
    }  

    await update.message.reply_text(  
        f"✅ <b>Wager set!</b> {user.first_name} bet 💰 <b>{amount:,} coins</b>.",  
        parse_mode="HTML"  
    )

async def fly_bet_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split(":")  
    chat_id = int(parts[1])  
    amount = int(parts[2])  

    state = fly_games.get(chat_id)  

    if not state or state["status"] != "lobby":  
        await query.answer("Lobby timer finished or round ended.", show_alert=True)  
        return  

    user = query.from_user  
    remember_user(user)  
    user_id = user.id  
    current_balance = get_balance(user_id)  
    existing_bet = state["bets"].get(user_id, {}).get("amount", 0)  

    if current_balance + existing_bet < amount:  
        await query.answer(  
            f"Insufficient balance! You have {current_balance:,} coins.",  
            show_alert=True  
        )  
        return  

    if existing_bet > 0:  
        change_coins(user_id, existing_bet, "Fly bet update refund")  

    change_coins(user_id, -amount, "Fly bet placed")  

    state["bets"][user_id] = {  
        "amount": amount,  
        "first_name": user.first_name,  
        "username": user.username,  
        "cashed_out": False,  
        "cashout_mult": 0.0,  
        "win_amount": 0  
    }  

    await query.answer(f"Wager set to {amount:,} coins!", show_alert=False)

async def fly_lobby_timer(context, chat_id):
    for time_left in range(60, 0, -5):
        await asyncio.sleep(5)
        state = fly_games.get(chat_id)  

        if not state or state["stopped"]:  
            return  

        keyboard = build_fly_bet_keyboard(chat_id)  
        text = build_fly_lobby_text(time_left, state["bets"])  

        try:  
            await context.bot.edit_message_text(  
                chat_id=chat_id,  
                message_id=state["message_id"],  
                text=text,  
                reply_markup=keyboard,  
                parse_mode="HTML"  
            )  
        except Exception:  
            pass  

    state = fly_games.get(chat_id)  

    if not state or state["stopped"]:  
        return  

    if not state["bets"]:  
        try:  
            await context.bot.edit_message_text(  
                chat_id=chat_id,  
                message_id=state["message_id"],  
                text="🚀 <b>FLY CANCELLED</b>\n\nNo wagers were placed.",  
                parse_mode="HTML"  
            )  
        except Exception:  
            pass  

        fly_games.pop(chat_id, None)  
        return  

    state["status"] = "flying"  
    state["started_at"] = time.monotonic()  

    asyncio.create_task(fly_flight_loop(context, chat_id))

async def fly_flight_loop(context, chat_id):
    state = fly_games.get(chat_id)
    if not state:  
        return  

    started_at = state["started_at"]  
    crash = round(min(100.0, max(1.25, 1.10 / random.random())), 2)  
    last_multiplier = 1.10  

    while True:  
        await asyncio.sleep(1)  
        state = fly_games.get(chat_id)  

        if not state or state["stopped"]:  
            return  

        elapsed = time.monotonic() - started_at  
        multiplier = arcade_multiplier(elapsed)  

        all_cashed_out = all(b["cashed_out"] for b in state["bets"].values())  

        if multiplier >= crash or all_cashed_out:  
            text = (  
                "💥 <b>FLY CRASHED!</b>\n\n"  
                f"📉 Final Multiplier: <b>{crash if multiplier >= crash else multiplier:.2f}x</b>\n\n"  
                "📊 <b>Results:</b>\n"  
            )  

            for user_id, b in state["bets"].items():  
                name = b["first_name"] or b["username"] or "Player"  

                if b["cashed_out"]:  
                    text += (  
                        f"• {name}: Cashed out @ <b>{b['cashout_mult']:.2f}x</b> "  
                        f"(+<b>{b['win_amount']:,}</b> coins)\n"  
                    )  
                else:  
                    text += f"• {name}: Crashed! (-<b>{b['amount']:,}</b> coins)\n"  

            try:  
                await context.bot.edit_message_text(  
                    chat_id=chat_id,  
                    message_id=state["message_id"],  
                    text=text,  
                    parse_mode="HTML"  
                )  
            except Exception:  
                pass  

            fly_games.pop(chat_id, None)  
            return  

        if multiplier > last_multiplier:  
            keyboard = [[  
                InlineKeyboardButton(  
                    "💰 CASH OUT",  
                    callback_data=f"flycash:{chat_id}"  
                )  
            ]]  

            text = (  
                "🚀 <b>FLYING...</b>\n\n"  
                f"📈 Multiplier: <b>{multiplier:.2f}x</b>\n\n"  
                "👥 <b>Players:</b>\n"  
            )  

            for user_id, b in state["bets"].items():  
                name = b["first_name"] or b["username"] or "Player"  

                if b["cashed_out"]:  
                    text += (  
                        f"• {name}: Cashed out @ <b>{b['cashout_mult']:.2f}x</b> "  
                        f"(<b>{b['win_amount']:,}</b> coins)\n"  
                    )  
                else:  
                    text += f"• {name}: 💰 <b>{b['amount']:,} coins</b> in play\n"  

            try:  
                await context.bot.edit_message_text(  
                    chat_id=chat_id,  
                    message_id=state["message_id"],  
                    text=text,  
                    reply_markup=InlineKeyboardMarkup(keyboard),  
                    parse_mode="HTML"  
                )  
            except Exception:  
                pass  

            last_multiplier = multiplier

async def fly_cashout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = int(query.data.split(":")[1])  
    state = fly_games.get(chat_id)  

    if not state or state["status"] != "flying" or state["stopped"]:  
        await query.answer("Fly round is not active.", show_alert=True)  
        return  

    user_id = query.from_user.id  

    if user_id not in state["bets"]:  
        await query.answer("You are not in this Fly round!", show_alert=True)  
        return  

    b = state["bets"][user_id]  

    if b["cashed_out"]:  
        await query.answer("You already cashed out!", show_alert=True)  
        return  

    elapsed = time.monotonic() - state["started_at"]  
    multiplier = arcade_multiplier(elapsed)  
    winnings = int(b["amount"] * multiplier)  

    b["cashed_out"] = True  
    b["cashout_mult"] = multiplier  
    b["win_amount"] = winnings  

    change_coins(user_id, winnings, f"Fly win @ {multiplier}x")  

    await query.answer(  
        f"Cashed out at {multiplier:.2f}x! (+{winnings:,} coins)",  
        show_alert=True  
    )

# =========================================================
# /STOPFLY — OWNER ONLY
# =========================================================

async def stopfly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only.")
        return

    chat_id = update.effective_chat.id  
    state = fly_games.get(chat_id)  

    if not state:  
        await update.message.reply_text("❌ No Fly round is running.")  
        return  

    state["stopped"] = True  

    for user_id, b in state["bets"].items():  
        if not b["cashed_out"]:  
            change_coins(user_id, b["amount"], "Fly round stopped refund")  

    try:  
        await context.bot.edit_message_text(  
            chat_id=chat_id,  
            message_id=state["message_id"],  
            text=(  
                "🛑 <b>FLY STOPPED BY OWNER</b>\n\n"  
                "The round was cancelled and non-cashed out wagers were refunded."  
            ),  
            parse_mode="HTML"  
        )  
    except Exception:  
        pass  

    fly_games.pop(chat_id, None)  
    await update.message.reply_text("✅ Fly round stopped.")

# =========================================================
# /GIVE + /ADD
# =========================================================

async def give_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only.")
        return

    if not update.message.reply_to_message:  
        await update.message.reply_text(  
            "❌ Reply to the user's message.\n\n"  
            "Example:\n"  
            "/give 5000"  
        )  
        return  

    if not context.args:  
        await update.message.reply_text("❌ Enter an amount.")  
        return  

    try:  
        amount = int(context.args[0])  
    except ValueError:  
        await update.message.reply_text("❌ Amount must be a number.")  
        return  

    if amount <= 0:  
        await update.message.reply_text("❌ Amount must be greater than 0.")  
        return  

    target = update.message.reply_to_message.from_user  
    remember_user(target)  

    change_coins(target.id, amount, f"Owner gave {amount} coins")  

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

async def remove_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only.")
        return

    if not update.message.reply_to_message:  
        await update.message.reply_text("❌ Reply to the user's message.")  
        return  

    if not context.args:  
        await update.message.reply_text("❌ Enter an amount.")  
        return  

    try:  
        amount = int(context.args[0])  
    except ValueError:  
        await update.message.reply_text("❌ Amount must be a number.")  
        return  

    if amount <= 0:  
        await update.message.reply_text("❌ Amount must be greater than 0.")  
        return  

    target = update.message.reply_to_message.from_user  
    remember_user(target)  

    current = get_balance(target.id)  
    actual_remove = min(amount, current)  

    change_coins(target.id, -actual_remove, f"Owner removed {actual_remove} coins")  

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
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only.")
        return

    if not update.message.reply_to_message:  
        await update.message.reply_text("❌ Reply to a user with /admin.")  
        return  

    target = update.message.reply_to_message.from_user  
    remember_user(target)  
    add_admin(target.id)  

    await update.message.reply_text(f"✅ {target.first_name} is now an admin.")

# =========================================================
# /UNADMIN
# =========================================================

async def remove_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only.")
        return

    if not update.message.reply_to_message:  
        await update.message.reply_text("❌ Reply to a user with /unadmin.")  
        return  

    target = update.message.reply_to_message.from_user  
    remove_admin(target.id)  

    await update.message.reply_text(f"✅ {target.first_name} is no longer an admin.")

# =========================================================
# CALLBACK ROUTER
# =========================================================

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if query.data.startswith("join:"):  
        await join_button(update, context)  

    elif query.data.startswith("card:"):  
        await card_selected(update, context)  

    elif query.data.startswith("flybet:"):  
        await fly_bet_button(update, context)  

    elif query.data.startswith("flycash:"):  
        await fly_cashout(update, context)

# =========================================================
# MAIN
# =========================================================

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is missing.")

    if not OWNER_ID:  
        raise RuntimeError("OWNER_ID environment variable is missing.")  

    init_db()  

    application = (  
        Application.builder()  
        .token(BOT_TOKEN)  
        .build()  
    )  

    # Basic Commands 
    application.add_handler(CommandHandler("start", start))  
    application.add_handler(CommandHandler("help", help_command))  
    application.add_handler(CommandHandler("free", free_coins_command))  
    application.add_handler(CommandHandler("bal", balance))  
    application.add_handler(CommandHandler("leaderboard", show_leaderboard))  

    # Parchi Game Commands 
    application.add_handler(CommandHandler("startgame", startgame))  
    application.add_handler(CommandHandler("join", join_command))  
    application.add_handler(CommandHandler("begin", begin))  
    application.add_handler(CommandHandler("endgame", endgame))  

    # Fly Game Commands 
    application.add_handler(CommandHandler("fly", fly))  
    application.add_handler(CommandHandler("f", fly_custom_bet))  
    application.add_handler(CommandHandler("stopfly", stopfly))  

    # Owner Commands 
    application.add_handler(CommandHandler("give", give_coins))  
    application.add_handler(CommandHandler("add", give_coins))  
    application.add_handler(CommandHandler("removec", remove_coins))  
    application.add_handler(CommandHandler("admin", make_admin))  
    application.add_handler(CommandHandler("unadmin", remove_admin_command))  

    # Inline Buttons  
    application.add_handler(CallbackQueryHandler(callbacks))  

    print("🏏 16 Parchi Bot started!")  
    application.run_polling()

if __name__ == "__main__":
    main()
