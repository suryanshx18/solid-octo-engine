"""Chaos Core - compact 5-file Telegram economy + casino bot."""
import asyncio, html, logging, re, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import config, database, games, admin

logging.basicConfig(level=logging.INFO)
log=logging.getLogger("chaos")

def money(n): return f"{int(n):,} 🪙"

def kb(rows): return InlineKeyboardMarkup(rows)

def main_kb():
    return kb([
        [InlineKeyboardButton("💰 Economy",callback_data="economy"),InlineKeyboardButton("🎰 Casino",callback_data="casino")],
        [InlineKeyboardButton("👤 Profile",callback_data="profile"),InlineKeyboardButton("🏆 Rankings",callback_data="leaderboard")],
        [InlineKeyboardButton("🏅 Achievements",callback_data="achievements"),InlineKeyboardButton("👑 VIP",callback_data="vip")],
        [InlineKeyboardButton("🎁 Rewards",callback_data="rewards"),InlineKeyboardButton("❓ Help",callback_data="help")],
    ])

def economy_kb():
    return kb([
        [InlineKeyboardButton("💳 Balance",callback_data="balance"),InlineKeyboardButton("🎁 Daily",callback_data="daily")],
        [InlineKeyboardButton("💼 Work",callback_data="work"),InlineKeyboardButton("🔫 Crime",callback_data="crime")],
        [InlineKeyboardButton("🏦 Bank",callback_data="bank"),InlineKeyboardButton("🛍 Shop",callback_data="shop")],
        [InlineKeyboardButton("📜 Transactions",callback_data="transactions"),InlineKeyboardButton("🔑 Redeem",callback_data="redeem")],
        [InlineKeyboardButton("⬅️ Home",callback_data="home")],
    ])

def casino_kb():
    return kb([
        [InlineKeyboardButton("🎰 Slots",callback_data="game:slots"),InlineKeyboardButton("🎲 Dice",callback_data="game:dice")],
        [InlineKeyboardButton("🪙 Coin Flip",callback_data="game:coin"),InlineKeyboardButton("🎡 Wheel",callback_data="game:wheel")],
        [InlineKeyboardButton("🃏 Blackjack",callback_data="game:blackjack"),InlineKeyboardButton("💣 Mines",callback_data="game:mines")],
        [InlineKeyboardButton("⬅️ Home",callback_data="home")],
    ])

def bet_kb(game):
    return kb([
        [InlineKeyboardButton("10",callback_data=f"bet:{game}:10"),InlineKeyboardButton("100",callback_data=f"bet:{game}:100"),InlineKeyboardButton("1K",callback_data=f"bet:{game}:1000")],
        [InlineKeyboardButton("10K",callback_data=f"bet:{game}:10000"),InlineKeyboardButton("50K",callback_data=f"bet:{game}:50000")],
        [InlineKeyboardButton("⬅️ Casino",callback_data="casino")],
    ])

async def ensure(update):
    u=update.effective_user
    database.ensure_user(u.id,u.username,u.first_name)
    return database.user(u.id)

async def guard(update):
    r=await ensure(update)
    if r["banned"]: return False
    if r["muted_until"]>int(time.time()): return False
    return True

async def edit(q,text,markup=None):
    try: await q.edit_message_text(text,parse_mode=ParseMode.HTML,reply_markup=markup)
    except Exception:
        try: await q.message.reply_text(text,parse_mode=ParseMode.HTML,reply_markup=markup)
        except Exception: pass

async def start(update,ctx):
    if not await guard(update): return
    await update.message.reply_text(
        "⚡ <b>CHAOS CORE</b> ⚡\n\n"
        "Your virtual economy & casino hub.\n"
        "🪙 Starting wallet: <b>"+money(database.user(update.effective_user.id)["balance"])+"</b>\n\n"
        "Choose an option:",parse_mode=ParseMode.HTML,reply_markup=main_kb())

async def help_cmd(update,ctx):
    await update.message.reply_text(
        "<b>Chaos Core Commands</b>\n\n"
        "/start /help /balance /daily /work /crime\n"
        "/pay USER_ID AMOUNT\n/deposit AMOUNT\n/withdraw AMOUNT\n"
        "/redeem CODE\n/gift USER_ID AMOUNT\n\n"
        "Owner/Admin:\n/admin USER_ID\n/unadmin USER_ID\n/give USER_ID AMOUNT\n/remove USER_ID AMOUNT\n"
        "/setbalance USER_ID AMOUNT\n/ban USER_ID\n/unban USER_ID\n/warn USER_ID\n/broadcast MESSAGE\n/stats\n/maintenance on|off",
        parse_mode=ParseMode.HTML)

async def balance_cmd(update,ctx):
    if not await guard(update): return
    r=await ensure(update)
    await update.message.reply_text(f"💳 <b>Wallet:</b> {money(r['balance'])}\n🏦 <b>Bank:</b> {money(r['bank'])}\n✨ <b>XP:</b> {r['xp']}  • Level {r['level']}",parse_mode=ParseMode.HTML)

async def simple_reward(update,kind):
    if not await guard(update): return
    uid=update.effective_user.id
    seconds={"daily":config.COOLDOWN_DAILY,"work":config.COOLDOWN_WORK,"crime":config.COOLDOWN_CRIME}[kind]
    ok,left=database.cooldown_ready(uid,kind,seconds)
    if not ok:
        await update.message.reply_text(f"⏳ Try again in {left//3600}h {(left%3600)//60}m."); return
    import secrets
    if kind=="daily": amount=config.DAILY_BASE+secrets.randbelow(config.DAILY_BASE)
    elif kind=="work": amount=secrets.randbelow(config.WORK_MAX-config.WORK_MIN+1)+config.WORK_MIN
    else:
        if secrets.randbelow(100)<45:
            amount=secrets.randbelow(config.CRIME_MAX-config.CRIME_MIN+1)+config.CRIME_MIN
        else:
            amount=-(secrets.randbelow(config.CRIME_MAX//2)+1)
    if database.change_balance(uid,amount,kind,kind):
        await update.message.reply_text(("🎁" if amount>=0 else "🚨")+f" {kind.title()}: <b>{money(amount)}</b>",parse_mode=ParseMode.HTML)
    else: await update.message.reply_text("❌ Not enough balance.")

async def daily(update,ctx): await simple_reward(update,"daily")
async def work(update,ctx): await simple_reward(update,"work")
async def crime(update,ctx): await simple_reward(update,"crime")

async def pay(update,ctx):
    if not await guard(update):return
    try: target=int(ctx.args[0]); amount=int(ctx.args[1])
    except: await update.message.reply_text("Usage: /pay USER_ID AMOUNT"); return
    if database.transfer(update.effective_user.id,target,amount):
        await update.message.reply_text(f"✅ Sent {money(amount)}.")
    else: await update.message.reply_text("❌ Transfer failed.")

async def bank_cmd(update,ctx,deposit):
    if not await guard(update):return
    try: amount=int(ctx.args[0])
    except: await update.message.reply_text("Usage: /deposit AMOUNT" if deposit else "Usage: /withdraw AMOUNT"); return
    if database.bank_move(update.effective_user.id,amount,deposit):
        await update.message.reply_text("✅ Bank transfer complete.")
    else: await update.message.reply_text("❌ Insufficient funds.")

async def deposit(update,ctx): await bank_cmd(update,ctx,True)
async def withdraw(update,ctx): await bank_cmd(update,ctx,False)

async def redeem(update,ctx):
    await update.message.reply_text("Promo creation is owner-only in this compact build; redemption UI is reserved for the next expansion.")

async def gift(update,ctx):
    if not await guard(update):return
    try: target=int(ctx.args[0]); amount=int(ctx.args[1])
    except: await update.message.reply_text("Usage: /gift USER_ID AMOUNT"); return
    if database.transfer(update.effective_user.id,target,amount):
        await update.message.reply_text(f"🎁 Gifted {money(amount)}.")
    else: await update.message.reply_text("❌ Gift failed.")

async def callback(update,ctx):
    q=update.callback_query
    try:
        await q.answer()
        if not await guard(update): return
        uid=q.from_user.id; data=q.data
        if data=="home": await edit(q,"⚡ <b>CHAOS CORE</b>\n\nChoose an option:",main_kb())
        elif data=="economy": await edit(q,"💰 <b>Economy</b>\nManage your wallet, bank and rewards.",economy_kb())
        elif data=="casino": await edit(q,"🎰 <b>Casino</b>\nVirtual coins only. Choose a game:",casino_kb())
        elif data=="balance":
            r=database.user(uid); await edit(q,f"💳 Wallet: <b>{money(r['balance'])}</b>\n🏦 Bank: <b>{money(r['bank'])}</b>\n✨ XP {r['xp']} • Level {r['level']}",economy_kb())
        elif data in ("daily","work","crime"):
            seconds={"daily":config.COOLDOWN_DAILY,"work":config.COOLDOWN_WORK,"crime":config.COOLDOWN_CRIME}[data]
            ok,left=database.cooldown_ready(uid,data,seconds)
            if not ok: await edit(q,f"⏳ Cooldown: {left//3600}h {(left%3600)//60}m",economy_kb()); return
            import secrets
            if data=="daily": amount=config.DAILY_BASE+secrets.randbelow(config.DAILY_BASE)
            elif data=="work": amount=secrets.randbelow(config.WORK_MAX-config.WORK_MIN+1)+config.WORK_MIN
            else: amount=(secrets.randbelow(config.CRIME_MAX-config.CRIME_MIN+1)+config.CRIME_MIN) if secrets.randbelow(100)<45 else -(secrets.randbelow(config.CRIME_MAX//2)+1)
            database.change_balance(uid,amount,data,data)
            await edit(q,f"{'🎉' if amount>0 else '🚨'} <b>{data.title()}</b>\nResult: {money(amount)}",economy_kb())
        elif data=="profile":
            r=database.user(uid); name=html.escape(r["first_name"] or r["username"] or str(uid))
            await edit(q,f"👤 <b>{name}</b>\nID: <code>{uid}</code>\n🪙 {money(r['balance'])}\n🏦 {money(r['bank'])}\n✨ XP {r['xp']} • Level {r['level']}\n👑 VIP {r['vip']}",main_kb())
        elif data=="leaderboard":
            rows=database.top_users(10); text="🏆 <b>Leaderboard</b>\n\n"
            for i,r in enumerate(rows,1): text+=f"{i}. {html.escape(r['first_name'] or r['username'] or str(r['user_id']))} — {money(r['balance'])}\n"
            await edit(q,text,main_kb())
        elif data=="transactions":
            rows=database.recent_transactions(uid); text="📜 <b>Recent Transactions</b>\n\n"
            text += "\n".join(f"{r['kind']}: {money(r['amount'])}" for r in rows) or "No transactions."
            await edit(q,text,economy_kb())
        elif data=="bank": await edit(q,"🏦 <b>Bank</b>\nUse /deposit AMOUNT or /withdraw AMOUNT.",economy_kb())
        elif data=="shop": await edit(q,"🛍 <b>Shop</b>\nShop framework is ready for custom items.",economy_kb())
        elif data=="achievements": await edit(q,"🏅 Achievements\nMilestones are tracked in the database.",main_kb())
        elif data=="vip": await edit(q,"👑 VIP\nVIP data is stored per user. Owner can extend tiers.",main_kb())
        elif data=="rewards": await edit(q,"🎁 Rewards\nUse Daily, Work, Crime and promo redemption.",economy_kb())
        elif data=="help": await help_cmd_callback(q)
        elif data.startswith("game:"):
            game=data.split(":")[1]
            if game=="coin": await edit(q,"🪙 <b>Coin Flip</b>\nChoose side, then bet:",kb([[InlineKeyboardButton("Heads",callback_data="coin:heads"),InlineKeyboardButton("Tails",callback_data="coin:tails")],[InlineKeyboardButton("⬅️ Casino",callback_data="casino")]]))
            else: await edit(q,f"🎮 <b>{game.title()}</b>\nSelect your bet:",bet_kb(game))
        elif data.startswith("coin:"):
            choice=data.split(":")[1]
            await edit(q,f"🪙 {choice.title()} selected. Choose bet:",kb([[InlineKeyboardButton("10",callback_data=f"bet:coin:{choice}:10"),InlineKeyboardButton("100",callback_data=f"bet:coin:{choice}:100"),InlineKeyboardButton("1K",callback_data=f"bet:coin:{choice}:1000")],[InlineKeyboardButton("10K",callback_data=f"bet:coin:{choice}:10000"),InlineKeyboardButton("50K",callback_data=f"bet:coin:{choice}:50000")]]))
        elif data.startswith("bet:"):
            parts=data.split(":"); game=parts[1]; choice=None
            if game=="coin" and len(parts)==4: choice=parts[2]; bet=int(parts[3])
            else: bet=int(parts[2])
            if game=="blackjack":
                r=games.blackjack_start(uid,bet)
                if not r: await edit(q,"❌ Invalid bet or an active game exists.",casino_kb()); return
                status,p,d,pay=r; text=f"🃏 <b>Blackjack</b>\nYou: {' '.join(a+s for a,s in p)} ({games.value(p)})\nDealer: {' '.join(a+s for a,s in d)}"
                await edit(q,text,kb([[InlineKeyboardButton("👊 Hit",callback_data="bj:hit"),InlineKeyboardButton("✋ Stand",callback_data="bj:stand")],[InlineKeyboardButton("⬅️ Casino",callback_data="casino")]]))
            elif game=="mines":
                r=games.mines_start(uid,bet)
                if not r: await edit(q,"❌ Invalid bet or active Mines game.",casino_kb()); return
                await edit(q,"💣 <b>Mines</b>\nPick a tile:",mines_kb(set()))
            elif game=="coin":
                r=games.coin(uid,bet,choice)
                await game_result(q,"Coin Flip",r,casino_kb(),lambda x:f"Result: {x[0].title()}")
            elif game=="slots":
                r=games.slots(uid,bet); await game_result(q,"Slots",r,casino_kb(),lambda x:" ".join(x[0]))
            elif game=="dice":
                r=games.dice(uid,bet); await game_result(q,"Dice",r,casino_kb(),lambda x:f"Rolled: {x[0]}")
            elif game=="wheel":
                r=games.wheel(uid,bet); await game_result(q,"Wheel",r,casino_kb(),lambda x:f"Landed on {x[0]}x")
        elif data=="bj:hit":
            r=games.blackjack_hit(uid)
            if not r: await edit(q,"No active Blackjack game.",casino_kb()); return
            status,p,d,pay=r
            if status=="continue": await edit(q,f"🃏 You: {' '.join(a+s for a,s in p)} ({games.value(p)})\nDealer: {' '.join(a+s for a,s in d)}",kb([[InlineKeyboardButton("👊 Hit",callback_data="bj:hit"),InlineKeyboardButton("✋ Stand",callback_data="bj:stand")]]))
            else: await edit(q,f"🃏 <b>Bust!</b>\nYou: {' '.join(a+s for a,s in p)} ({games.value(p)})",casino_kb())
        elif data=="bj:stand":
            r=games.blackjack_stand(uid); status,p,d,pay=r
            await edit(q,f"🃏 <b>Blackjack</b>\nYou {games.value(p)} vs Dealer {games.value(d)}\n{'Payout: '+money(pay) if pay else 'No payout.'}",casino_kb())
        elif data.startswith("mines:"):
            cell=int(data.split(":")[1]); r=games.mines_pick(uid,cell)
            if r and r[0]=="safe": await edit(q,f"💣 Safe tile! Opened: {r[1]}",mines_kb(games.MINES.get(uid,{}).get("opened",set())))
            elif r and r[0]=="boom": await edit(q,"💥 BOOM! You lost the bet.",casino_kb())
            else: await edit(q,"❌ No active game.",casino_kb())
        elif data=="mines:cashout":
            r=games.mines_cashout(uid)
            await edit(q,f"💰 Cashed out: {money(r[1])}" if r and r[0]=="cashout" else "❌ Nothing to cash out.",casino_kb())
        elif data=="admin":
            await admin_panel(q)
        else: await edit(q,"⚡ Menu",main_kb())
    except Exception:
        log.exception("callback error")
        try: await q.edit_message_text("⚠️ Something went wrong. Please try again.",reply_markup=main_kb())
        except Exception: pass

def mines_kb(opened):
    rows=[]
    for start in range(0,25,5):
        rows.append([InlineKeyboardButton("🟩" if i in opened else "⬜",callback_data=f"mines:{i}") for i in range(start,start+5)])
    rows.append([InlineKeyboardButton("💰 Cash Out",callback_data="mines:cashout")])
    return kb(rows)

async def game_result(q,title,r,markup,desc):
    if not r: await edit(q,"❌ Invalid bet or insufficient balance.",markup); return
    net=r[1]
    await edit(q,f"🎮 <b>{title}</b>\n{desc(r)}\n{'🟢 +' if net>0 else '🔴 '}{money(net)}",markup)

async def help_cmd_callback(q):
    await edit(q,"<b>Help</b>\nUse the buttons or /help for commands.",main_kb())

async def admin_panel(q):
    if not admin.has_power(q.from_user.id): await edit(q,"⛔ Admin only.",main_kb()); return
    with database.connect() as c: count=c.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
    await edit(q,f"🛡 <b>Admin Panel</b>\nUsers: {count}\nOwner: {config.OWNER_ID}",main_kb())

def target_amount(ctx):
    return int(ctx.args[0]),int(ctx.args[1])

async def admin_cmd(update,ctx):
    if not admin.is_owner(update.effective_user.id): await update.message.reply_text("⛔ Owner only."); return
    try: target=int(ctx.args[0])
    except: await update.message.reply_text("Usage: /admin USER_ID"); return
    await update.message.reply_text("✅ Admin added." if admin.set_admin(update.effective_user.id,target,True) else "❌ Failed.")

async def unadmin_cmd(update,ctx):
    if not admin.is_owner(update.effective_user.id): await update.message.reply_text("⛔ Owner only."); return
    try: target=int(ctx.args[0])
    except: await update.message.reply_text("Usage: /unadmin USER_ID"); return
    await update.message.reply_text("✅ Admin removed." if admin.set_admin(update.effective_user.id,target,False) else "❌ Failed.")

async def admin_money(update,ctx,action):
    if not admin.has_power(update.effective_user.id): await update.message.reply_text("⛔ Admin only."); return
    try: target,amount=target_amount(ctx)
    except: await update.message.reply_text(f"Usage: /{action} USER_ID AMOUNT"); return
    fn={"give":admin.give,"remove":admin.remove,"setbalance":admin.set_balance}[action]
    ok=fn(update.effective_user.id,target,amount)
    await update.message.reply_text("✅ Done." if ok else "❌ Failed.")

async def give(update,ctx): await admin_money(update,ctx,"give")
async def remove(update,ctx): await admin_money(update,ctx,"remove")
async def setbalance(update,ctx): await admin_money(update,ctx,"setbalance")

async def ban_cmd(update,ctx):
    if not admin.has_power(update.effective_user.id): await update.message.reply_text("⛔ Admin only."); return
    try:t=int(ctx.args[0])
    except:await update.message.reply_text("Usage: /ban USER_ID");return
    await update.message.reply_text("✅ Banned." if admin.ban(update.effective_user.id,t,True) else "❌ Failed.")
async def unban_cmd(update,ctx):
    if not admin.has_power(update.effective_user.id): await update.message.reply_text("⛔ Admin only."); return
    try:t=int(ctx.args[0])
    except:await update.message.reply_text("Usage: /unban USER_ID");return
    await update.message.reply_text("✅ Unbanned." if admin.ban(update.effective_user.id,t,False) else "❌ Failed.")
async def warn_cmd(update,ctx):
    if not admin.has_power(update.effective_user.id): await update.message.reply_text("⛔ Admin only."); return
    try:t=int(ctx.args[0])
    except:await update.message.reply_text("Usage: /warn USER_ID");return
    await update.message.reply_text("⚠️ Warning added." if admin.warn(update.effective_user.id,t) else "❌ Failed.")

async def stats(update,ctx):
    if not admin.has_power(update.effective_user.id): await update.message.reply_text("⛔ Admin only."); return
    with database.connect() as c:
        users=c.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
        coins=c.execute("SELECT COALESCE(SUM(balance+bank),0) n FROM users").fetchone()["n"]
        games_n=c.execute("SELECT COUNT(*) n FROM games").fetchone()["n"]
    await update.message.reply_text(f"📊 Users: {users}\n🪙 Economy: {money(coins)}\n🎮 Games: {games_n}")

async def maintenance_cmd(update,ctx):
    if not admin.is_owner(update.effective_user.id): await update.message.reply_text("⛔ Owner only."); return
    val=(ctx.args[0].lower() if ctx.args else "status")
    if val in ("on","off"): admin.maintenance(val=="on")
    await update.message.reply_text("Maintenance: ON" if admin.maintenance() else "Maintenance: OFF")

async def broadcast(update,ctx):
    if not admin.has_power(update.effective_user.id): await update.message.reply_text("⛔ Admin only."); return
    text=" ".join(ctx.args).strip()
    if not text: await update.message.reply_text("Usage: /broadcast MESSAGE"); return
    sent=failed=0
    for row in database.all_users():
        try:
            await ctx.bot.send_message(row["user_id"],text)
            sent+=1
            await asyncio.sleep(0.04)
        except Exception: failed+=1
    await update.message.reply_text(f"📢 Broadcast complete.\nSent: {sent}\nFailed: {failed}")

async def post_init(app):
    database.init_db()
    if config.OWNER_ID:
        database.ensure_user(config.OWNER_ID)

def main():
    if not config.BOT_TOKEN: raise SystemExit("BOT_TOKEN is missing.")
    if not config.OWNER_ID: raise SystemExit("OWNER_ID is missing.")
    app=Application.builder().token(config.BOT_TOKEN).post_init(post_init).build()
    commands={
        "start":start,"help":help_cmd,"balance":balance_cmd,"daily":daily,"work":work,"crime":crime,
        "pay":pay,"deposit":deposit,"withdraw":withdraw,"redeem":redeem,"gift":gift,
        "admin":admin_cmd,"unadmin":unadmin_cmd,"give":give,"remove":remove,"setbalance":setbalance,
        "ban":ban_cmd,"unban":unban_cmd,"warn":warn_cmd,"stats":stats,"maintenance":maintenance_cmd,
        "broadcast":broadcast,
    }
    for name,fn in commands.items(): app.add_handler(CommandHandler(name,fn))
    app.add_handler(CallbackQueryHandler(callback))
    log.info("Chaos Core starting")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__=="__main__": main()
