import asyncio,html,logging,secrets,time
from telegram import Update,InlineKeyboardButton,InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import Application,CommandHandler,CallbackQueryHandler,ContextTypes
import config,database,games,admin
logging.basicConfig(level=logging.INFO);log=logging.getLogger('chaos')

def money(n):return f'{int(n):,} 🪙'
def kb(rows):return InlineKeyboardMarkup(rows)
def main_kb(uid=None):
    rows=[[InlineKeyboardButton('💰 Economy',callback_data='economy'),InlineKeyboardButton('🎰 Casino',callback_data='casino')],[InlineKeyboardButton('👤 Profile',callback_data='profile'),InlineKeyboardButton('🏆 Rankings',callback_data='leaderboard')],[InlineKeyboardButton('🏅 Achievements',callback_data='achievements'),InlineKeyboardButton('👑 VIP',callback_data='vip')],[InlineKeyboardButton('🎁 Rewards',callback_data='rewards'),InlineKeyboardButton('❓ Help',callback_data='help')]]
    if uid and admin.has_power(uid):rows.append([InlineKeyboardButton('🛡 Admin',callback_data='admin')])
    return kb(rows)
def economy_kb():return kb([[InlineKeyboardButton('💳 Balance',callback_data='balance'),InlineKeyboardButton('🎁 Daily',callback_data='daily')],[InlineKeyboardButton('💼 Work',callback_data='work'),InlineKeyboardButton('🔫 Crime',callback_data='crime')],[InlineKeyboardButton('🏦 Bank',callback_data='bank'),InlineKeyboardButton('🛍 Shop',callback_data='shop')],[InlineKeyboardButton('📜 Transactions',callback_data='transactions'),InlineKeyboardButton('🔑 Redeem',callback_data='redeem')],[InlineKeyboardButton('🎒 Inventory',callback_data='inventory')],[InlineKeyboardButton('⬅️ Home',callback_data='home')]])
def casino_kb():return kb([[InlineKeyboardButton('🎰 Slots',callback_data='game:slots'),InlineKeyboardButton('🎲 Dice',callback_data='game:dice')],[InlineKeyboardButton('🪙 Coin Flip',callback_data='game:coin'),InlineKeyboardButton('🎡 Wheel',callback_data='game:wheel')],[InlineKeyboardButton('🃏 Blackjack',callback_data='game:blackjack'),InlineKeyboardButton('💣 Mines',callback_data='game:mines')],[InlineKeyboardButton('⬅️ Home',callback_data='home')]])
def bet_kb(game):return kb([[InlineKeyboardButton('10',callback_data=f'bet:{game}:10'),InlineKeyboardButton('100',callback_data=f'bet:{game}:100'),InlineKeyboardButton('1K',callback_data=f'bet:{game}:1000')],[InlineKeyboardButton('10K',callback_data=f'bet:{game}:10000'),InlineKeyboardButton('50K',callback_data=f'bet:{game}:50000')],[InlineKeyboardButton('⬅️ Casino',callback_data='casino')]])
async def ensure(update):
    u=update.effective_user;database.ensure_user(u.id,u.username,u.first_name);return database.user(u.id)
async def guard(update,allow_admin=False):
    r=await ensure(update);uid=update.effective_user.id
    if r['banned']:return False
    if database_user_maintenance() and not (allow_admin and admin.has_power(uid)):return False
    if r['muted_until']>int(time.time()):return False
    return True
def database_user_maintenance():return admin.maintenance()
async def safe_answer(q,text=None):
    try:await q.answer(text=text)
    except BadRequest:pass
    except Exception:pass
async def edit(q,text,markup=None):
    try:await q.edit_message_text(text,parse_mode=ParseMode.HTML,reply_markup=markup)
    except BadRequest:
        try:await q.message.reply_text(text,parse_mode=ParseMode.HTML,reply_markup=markup)
        except Exception:pass
    except Exception:log.exception('edit error')
def cooldown_text(left):return f'{left//3600}h {(left%3600)//60}m'
def reward_amount(kind):
    if kind=='daily':return config.DAILY_BASE+secrets.randbelow(config.DAILY_BASE)
    if kind=='work':return secrets.randbelow(config.WORK_MAX-config.WORK_MIN+1)+config.WORK_MIN
    return secrets.randbelow(config.CRIME_MAX-config.CRIME_MIN+1)+config.CRIME_MIN if secrets.randbelow(100)<45 else -(secrets.randbelow(config.CRIME_MAX//2)+1)
async def do_reward(uid,kind):
    seconds={'daily':config.COOLDOWN_DAILY,'work':config.COOLDOWN_WORK,'crime':config.COOLDOWN_CRIME}[kind];ok,left=database.cooldown_ready(uid,kind,seconds)
    if not ok:return None,left
    amount=reward_amount(kind);return amount,0 if database.change_balance(uid,amount,kind,kind) else -1
async def start(update,ctx):
    if not await guard(update):return
    r=database.user(update.effective_user.id);await update.message.reply_text(f'⚡ <b>CHAOS CORE</b> ⚡\n\nVirtual economy & casino hub.\n🪙 Wallet: <b>{money(r["balance"])}</b>\n\nChoose an option:',parse_mode=ParseMode.HTML,reply_markup=main_kb(r['user_id']))
async def help_cmd(update,ctx):
    await update.message.reply_text('<b>Chaos Core</b>\n\n/economy commands: /balance /daily /work /crime /pay USER_ID AMOUNT /deposit AMOUNT /withdraw AMOUNT /redeem CODE\n\n<b>Casino commands:</b> /slots BET /dice BET /coin BET heads|tails /wheel BET /blackjack BET /mines BET\nYou can also play every game from the Casino buttons in /start.\n\nOwner/Admin: /admin /unadmin /give /remove /setbalance /ban /unban /warn /mute /unmute /stats /maintenance /broadcast\nOwner promo: /createpromo CODE AMOUNT USES [DAYS] /promos /delpromo CODE',parse_mode=ParseMode.HTML)
async def balance_cmd(update,ctx):
    if not await guard(update):return
    r=database.user(update.effective_user.id);await update.message.reply_text(f'💳 Wallet: <b>{money(r["balance"])}</b>\n🏦 Bank: <b>{money(r["bank"])}</b>\n✨ XP: {r["xp"]} • Level {r["level"]} • VIP {r["vip"]}',parse_mode=ParseMode.HTML)
async def simple_reward(update,ctx,kind):
    if not await guard(update):return
    r,left=await do_reward(update.effective_user.id,kind)
    if r is None:await update.message.reply_text(f'⏳ Try again in {cooldown_text(left)}.');return
    if r==-1:await update.message.reply_text('❌ Failed.');return
    await update.message.reply_text(f'{"🎉" if r>0 else "🚨"} {kind.title()}: <b>{money(r)}</b>',parse_mode=ParseMode.HTML)
async def daily(update,ctx):await simple_reward(update,ctx,'daily')
async def work(update,ctx):await simple_reward(update,ctx,'work')
async def crime(update,ctx):await simple_reward(update,ctx,'crime')
async def pay(update,ctx):
    if not await guard(update):return
    try:t,a=int(ctx.args[0]),int(ctx.args[1])
    except:await update.message.reply_text('Usage: /pay USER_ID AMOUNT');return
    await update.message.reply_text('✅ Transfer complete.' if database.transfer(update.effective_user.id,t,a) else '❌ Transfer failed.')
async def bank_cmd(update,ctx,deposit):
    if not await guard(update):return
    try:a=int(ctx.args[0])
    except:await update.message.reply_text('Usage: /deposit AMOUNT' if deposit else '/withdraw AMOUNT');return
    await update.message.reply_text('✅ Bank transfer complete.' if database.bank_move(update.effective_user.id,a,deposit) else '❌ Insufficient funds.')
async def deposit(update,ctx):await bank_cmd(update,ctx,True)
async def withdraw(update,ctx):await bank_cmd(update,ctx,False)
async def redeem(update,ctx):
    if not await guard(update):return
    if not ctx.args:await update.message.reply_text('Usage: /redeem CODE');return
    amount=database.redeem_promo(update.effective_user.id,ctx.args[0]);await update.message.reply_text(f'🎁 Promo redeemed: <b>{money(amount)}</b>' if amount else '❌ Invalid, expired, used, or exhausted promo code.',parse_mode=ParseMode.HTML)
async def gift(update,ctx):await pay(update,ctx)
async def promo_create(update,ctx):
    if not admin.is_owner(update.effective_user.id):await update.message.reply_text('⛔ Owner only.');return
    try:
        code,amount,uses=ctx.args[0].upper(),int(ctx.args[1]),int(ctx.args[2]);days=int(ctx.args[3]) if len(ctx.args)>3 else 0
    except:await update.message.reply_text('Usage: /createpromo CODE AMOUNT USES [DAYS]');return
    exp=int(time.time())+days*86400 if days>0 else 0
    await update.message.reply_text('✅ Promo created.' if database.create_promo(code,amount,uses,exp) else '❌ Could not create promo (duplicate or invalid).')
async def promos(update,ctx):
    if not admin.is_owner(update.effective_user.id):await update.message.reply_text('⛔ Owner only.');return
    rows=database.promos();text='<b>🎁 Promos</b>\n\n'
    for r in rows:text+=f'<code>{html.escape(r["code"])}</code> — {money(r["amount"])} — {r["uses"]}/{r["max_uses"]} — {"ON" if r["active"] else "OFF"}\n'
    await update.message.reply_text(text if rows else 'No promo codes.',parse_mode=ParseMode.HTML)
async def delpromo(update,ctx):
    if not admin.is_owner(update.effective_user.id):await update.message.reply_text('⛔ Owner only.');return
    if not ctx.args:await update.message.reply_text('Usage: /delpromo CODE');return
    await update.message.reply_text('✅ Deleted.' if database.delete_promo(ctx.args[0]) else '❌ Not found.')
def fmt_cards(h):return ' '.join(r+s for r,s in h)
def mines_kb(opened):
    rows=[]
    for st in range(0,25,5):rows.append([InlineKeyboardButton('🟩' if i in opened else '⬜',callback_data=f'mines:{i}') for i in range(st,st+5)])
    rows.append([InlineKeyboardButton('💰 Cash Out',callback_data='mines:cashout')]);return kb(rows)
async def direct_slots(update,ctx):
    if not await guard(update): return
    try: bet=int(ctx.args[0])
    except (IndexError,ValueError):
        await update.message.reply_text('Usage: /slots BET\nExample: /slots 100'); return
    r=games.slots(update.effective_user.id,bet)
    if not r:
        await update.message.reply_text('❌ Invalid bet or insufficient balance.'); return
    reels,net,payout=r
    await update.message.reply_text(f'🎰 <b>Slots</b>\n{" ".join(reels)}\nPayout: <b>{money(payout)}</b>\nNet: <b>{money(net)}</b>',parse_mode=ParseMode.HTML,reply_markup=casino_kb())

async def direct_dice(update,ctx):
    if not await guard(update): return
    try: bet=int(ctx.args[0])
    except (IndexError,ValueError):
        await update.message.reply_text('Usage: /dice BET\nExample: /dice 100'); return
    r=games.dice(update.effective_user.id,bet)
    if not r:
        await update.message.reply_text('❌ Invalid bet or insufficient balance.'); return
    await update.message.reply_text(f'🎲 <b>Dice</b>\nRolled: <b>{r[0]}</b>\nPayout: <b>{money(r[2])}</b>\nNet: <b>{money(r[1])}</b>',parse_mode=ParseMode.HTML,reply_markup=casino_kb())

async def direct_coin(update,ctx):
    if not await guard(update): return
    if len(ctx.args)<2 or ctx.args[1].lower() not in ('heads','tails'):
        await update.message.reply_text('Usage: /coin BET heads|tails\nExample: /coin 100 heads'); return
    try: bet=int(ctx.args[0])
    except ValueError:
        await update.message.reply_text('Usage: /coin BET heads|tails\nExample: /coin 100 heads'); return
    choice=ctx.args[1].lower(); r=games.coin(update.effective_user.id,bet,choice)
    if not r:
        await update.message.reply_text('❌ Invalid bet or insufficient balance.'); return
    await update.message.reply_text(f'🪙 <b>Coin Flip</b>\nYou chose: <b>{choice.title()}</b>\nResult: <b>{r[0].title()}</b>\nPayout: <b>{money(r[2])}</b>\nNet: <b>{money(r[1])}</b>',parse_mode=ParseMode.HTML,reply_markup=casino_kb())

async def direct_wheel(update,ctx):
    if not await guard(update): return
    try: bet=int(ctx.args[0])
    except (IndexError,ValueError):
        await update.message.reply_text('Usage: /wheel BET\nExample: /wheel 100'); return
    r=games.wheel(update.effective_user.id,bet)
    if not r:
        await update.message.reply_text('❌ Invalid bet or insufficient balance.'); return
    await update.message.reply_text(f'🎡 <b>Wheel</b>\nLanded on: <b>{r[0]}x</b>\nPayout: <b>{money(r[2])}</b>\nNet: <b>{money(r[1])}</b>',parse_mode=ParseMode.HTML,reply_markup=casino_kb())

async def direct_blackjack(update,ctx):
    if not await guard(update): return
    try: bet=int(ctx.args[0])
    except (IndexError,ValueError):
        await update.message.reply_text('Usage: /blackjack BET\nExample: /blackjack 100'); return
    uid=update.effective_user.id; r=games.blackjack_start(uid,bet)
    if not r:
        await update.message.reply_text('❌ Invalid bet, insufficient balance, or you already have an active Blackjack game.'); return
    st,ph,dh,pay=r
    if st=='blackjack':
        await update.message.reply_text(f'🃏 <b>Blackjack!</b>\nYou: {fmt_cards(ph)}\nDealer: {fmt_cards(dh)}\nPayout: <b>{money(pay)}</b>',parse_mode=ParseMode.HTML,reply_markup=casino_kb()); return
    await update.message.reply_text(f'🃏 <b>Blackjack</b>\nYou: {fmt_cards(ph)} ({games.value(ph)})\nDealer: {fmt_cards(dh)}\nChoose:',parse_mode=ParseMode.HTML,reply_markup=kb([[InlineKeyboardButton('👊 Hit',callback_data='bj:hit'),InlineKeyboardButton('✋ Stand',callback_data='bj:stand')],[InlineKeyboardButton('⬅️ Casino',callback_data='casino')]]))

async def direct_mines(update,ctx):
    if not await guard(update): return
    try: bet=int(ctx.args[0])
    except (IndexError,ValueError):
        await update.message.reply_text('Usage: /mines BET\nExample: /mines 100'); return
    r=games.mines_start(update.effective_user.id,bet)
    if not r:
        await update.message.reply_text('❌ Invalid bet, insufficient balance, or you already have an active Mines game.'); return
    await update.message.reply_text('💣 <b>Mines</b>\nPick a tile or cash out.',parse_mode=ParseMode.HTML,reply_markup=mines_kb(set()))

async def game_result(q,title,r,desc):
    if not r:await edit(q,'❌ Invalid bet or insufficient balance.',casino_kb());return
    net=r[1];await edit(q,f'🎮 <b>{title}</b>\n{desc(r)}\n{"🟢 +" if net>0 else "🔴 "}{money(net)}',casino_kb())
async def callback(update,ctx):
    q=update.callback_query;await safe_answer(q)
    try:
        if not await guard(update,allow_admin=True):return
        uid=q.from_user.id;d=q.data
        if d=='home':await edit(q,'⚡ <b>CHAOS CORE</b>\n\nChoose an option:',main_kb(uid))
        elif d=='economy':await edit(q,'💰 <b>Economy</b>',economy_kb())
        elif d=='casino':await edit(q,'🎰 <b>Casino</b>\nVirtual coins only.',casino_kb())
        elif d=='help':await edit(q,'<b>Help</b>\nUse /help for commands.',main_kb(uid))
        elif d=='balance':
            r=database.user(uid);await edit(q,f'💳 Wallet: <b>{money(r["balance"])}</b>\n🏦 Bank: <b>{money(r["bank"])}</b>\n✨ XP {r["xp"]} • Level {r["level"]}',economy_kb())
        elif d in ('daily','work','crime'):
            r,left=await do_reward(uid,d);await edit(q,f'⏳ Try again in {cooldown_text(left)}.' if r is None else f'{"🎉" if r>0 else "🚨"} <b>{d.title()}</b>: {money(r)}',economy_kb())
        elif d=='transactions':
            rows=database.recent_transactions(uid);txt='📜 <b>Transactions</b>\n\n'+('\n'.join(f'{html.escape(x["kind"])}: {money(x["amount"])}' for x in rows) or 'None');await edit(q,txt,economy_kb())
        elif d=='bank':await edit(q,'🏦 <b>Bank</b>\nUse /deposit AMOUNT or /withdraw AMOUNT.',economy_kb())
        elif d=='redeem':await edit(q,'🔑 <b>Redeem</b>\nUse /redeem CODE.',economy_kb())
        elif d=='inventory':
            rows=database.inventory(uid);txt='🎒 <b>Inventory</b>\n\n'+('\n'.join(f'{x["item"]}: {x["qty"]}' for x in rows) or 'Empty');await edit(q,txt,economy_kb())
        elif d=='shop':
            rows=[[InlineKeyboardButton(f'{name} — {money(price)}',callback_data=f'buy:{key}')] for key,(price,name) in config.SHOP_ITEMS.items()];rows.append([InlineKeyboardButton('⬅️ Economy',callback_data='economy')]);await edit(q,'🛍 <b>Shop</b>\nBuy items with coins.',kb(rows))
        elif d.startswith('buy:'):
            key=d.split(':',1)[1];price,name=config.SHOP_ITEMS.get(key,(0,''));ok=database.change_balance(uid,-price,'shop',key) if price else False
            if ok:database.add_item(uid,key);await edit(q,f'✅ Bought <b>{html.escape(name)}</b>.',economy_kb())
            else:await edit(q,'❌ Not enough coins.',economy_kb())
        elif d=='profile':
            r=database.user(uid);await edit(q,f'👤 <b>{html.escape(r["first_name"] or r["username"] or str(uid))}</b>\nID: <code>{uid}</code>\n🪙 {money(r["balance"])}\n🏦 {money(r["bank"])}\n✨ XP {r["xp"]} • Level {r["level"]}\n👑 VIP {r["vip"]}',main_kb(uid))
        elif d=='leaderboard':
            txt='🏆 <b>Leaderboard</b>\n\n';rows=database.top_users(10)
            for i,r in enumerate(rows,1):txt+=f'{i}. {html.escape(r["first_name"] or r["username"] or str(r["user_id"]))} — {money(r["balance"]+r["bank"])}\n'
            await edit(q,txt,main_kb(uid))
        elif d=='achievements':
            r=database.achievements(uid);await edit(q,'🏅 <b>Achievements</b>\n\n'+('\n'.join('🏅 '+x['achievement'] for x in r) if r else 'Play games and earn XP to unlock achievements.'),main_kb(uid))
        elif d=='vip':
            rows=[[InlineKeyboardButton(f'VIP {tier} — {money(cost)}',callback_data=f'vipbuy:{tier}')] for tier,cost in config.VIP_COSTS.items()];rows.append([InlineKeyboardButton('⬅️ Home',callback_data='home')]);await edit(q,'👑 <b>VIP</b>\nHigher tiers are permanent upgrades.',kb(rows))
        elif d.startswith('vipbuy:'):
            tier=int(d.split(':')[1]);cost=config.VIP_COSTS[tier];r=database.user(uid)
            if r['vip']>=tier:await edit(q,'You already have this tier or higher.',main_kb(uid))
            elif database.change_balance(uid,-cost,'vip',f'tier {tier}'):
                with database.connect() as c:c.execute('UPDATE users SET vip=? WHERE user_id=?',(tier,uid));c.commit()
                await edit(q,f'👑 VIP {tier} activated!',main_kb(uid))
            else:await edit(q,'❌ Not enough coins.',main_kb(uid))
        elif d=='rewards':await edit(q,'🎁 <b>Rewards</b>\nDaily, work, crime and promo rewards are available from Economy.',main_kb(uid))
        elif d.startswith('game:'):
            game=d.split(':')[1]
            if game=='coin':
                await edit(q,'🪙 Choose side:',kb([[InlineKeyboardButton('Heads',callback_data='coin:heads'),InlineKeyboardButton('Tails',callback_data='coin:tails')],[InlineKeyboardButton('⬅️ Casino',callback_data='casino')]]))
            else:await edit(q,f'🎮 <b>{game.title()}</b>\nChoose your bet:',bet_kb(game))
        elif d.startswith('coin:'):
            ch=d.split(':')[1];await edit(q,f'🪙 {ch.title()} selected.',kb([[InlineKeyboardButton('10',callback_data=f'bet:coin:{ch}:10'),InlineKeyboardButton('100',callback_data=f'bet:coin:{ch}:100'),InlineKeyboardButton('1K',callback_data=f'bet:coin:{ch}:1000')],[InlineKeyboardButton('10K',callback_data=f'bet:coin:{ch}:10000'),InlineKeyboardButton('50K',callback_data=f'bet:coin:{ch}:50000')]]))
        elif d.startswith('bet:'):
            p=d.split(':');game=p[1];choice=p[2] if game=='coin' else None;bet=int(p[3] if game=='coin' else p[2])
            if game=='blackjack':
                r=games.blackjack_start(uid,bet)
                if not r:await edit(q,'❌ Invalid bet or active game.',casino_kb());return
                st,ph,dh,pay=r
                if st=='blackjack':await edit(q,f'🃏 <b>Blackjack!</b>\nYou: {fmt_cards(ph)}\nDealer: {fmt_cards(dh)}\nPayout: {money(pay)}',casino_kb())
                else:await edit(q,f'🃏 You: {fmt_cards(ph)} ({games.value(ph)})\nDealer: {fmt_cards(dh)}',kb([[InlineKeyboardButton('👊 Hit',callback_data='bj:hit'),InlineKeyboardButton('✋ Stand',callback_data='bj:stand')],[InlineKeyboardButton('⬅️ Casino',callback_data='casino')]]))
            elif game=='mines':
                r=games.mines_start(uid,bet);await edit(q,'💣 <b>Mines</b>\nPick a tile.',mines_kb(set())) if r else await edit(q,'❌ Invalid bet or active Mines game.',casino_kb())
            elif game=='coin':await game_result(q,'Coin Flip',games.coin(uid,bet,choice),lambda r:f'Result: {r[0].title()}')
            elif game=='slots':await game_result(q,'Slots',games.slots(uid,bet),lambda r:' '.join(r[0]))
            elif game=='dice':await game_result(q,'Dice',games.dice(uid,bet),lambda r:f'Rolled: {r[0]}')
            elif game=='wheel':await game_result(q,'Wheel',games.wheel(uid,bet),lambda r:f'Landed on {r[0]}x')
        elif d=='bj:hit':
            r=games.blackjack_hit(uid)
            if not r:await edit(q,'No active Blackjack game.',casino_kb())
            elif r[0]=='continue':await edit(q,f'🃏 You: {fmt_cards(r[1])} ({games.value(r[1])})\nDealer: {fmt_cards(r[2])}',kb([[InlineKeyboardButton('👊 Hit',callback_data='bj:hit'),InlineKeyboardButton('✋ Stand',callback_data='bj:stand')]]))
            else:await edit(q,f'💥 Bust!\nYou: {fmt_cards(r[1])} ({games.value(r[1])})',casino_kb())
        elif d=='bj:stand':
            r=games.blackjack_stand(uid)
            if not r:await edit(q,'No active Blackjack game.',casino_kb());return
            await edit(q,f'🃏 <b>Blackjack</b>\nYou: {games.value(r[1])}\nDealer: {games.value(r[2])}\nPayout: {money(r[3]) if r[3] else "0 🪙"}',casino_kb())
        elif d.startswith('mines:'):
            if d=='mines:cashout':r=games.mines_cashout(uid);await edit(q,f'💰 Cashed out {money(r[1])}.' if r and r[0]=='cashout' else '❌ Nothing to cash out.',casino_kb());return
            r=games.mines_pick(uid,int(d.split(':')[1]));
            if r and r[0]=='safe':await edit(q,f'💚 Safe! Opened: {r[1]}',mines_kb(games.MINES.get(uid,{}).get('opened',set())))
            elif r and r[0]=='boom':await edit(q,'💥 BOOM! Bet lost.',casino_kb())
            elif r and r[0]=='cashout':await edit(q,f'🏆 All safe enough! Payout {money(r[1])}.',casino_kb())
            else:await edit(q,'❌ No active game.',casino_kb())
        elif d=='admin':await admin_panel(q)
        else:await edit(q,'⚡ Menu',main_kb(uid))
    except Exception:log.exception('callback error');await edit(q,'⚠️ An error occurred. Please try again.',main_kb(q.from_user.id))
async def admin_panel(q):
    if not admin.has_power(q.from_user.id):await edit(q,'⛔ Admin only.',main_kb(q.from_user.id));return
    u,c,g=database.stats();await edit(q,f'🛡 <b>Admin Panel</b>\nUsers: {u}\nCoins: {money(c)}\nGames: {g}\nMaintenance: {"ON" if admin.maintenance() else "OFF"}\n\nUse admin commands.',main_kb(q.from_user.id))
def parse2(ctx,usage):
    try:return int(ctx.args[0]),int(ctx.args[1])
    except:raise ValueError(usage)
async def admin_cmd(update,ctx):
    if not admin.is_owner(update.effective_user.id):await update.message.reply_text('⛔ Owner only.');return
    try:t=int(ctx.args[0])
    except:await update.message.reply_text('Usage: /admin USER_ID');return
    await update.message.reply_text('✅ Admin added.' if admin.set_admin(update.effective_user.id,t,True) else '❌ Failed.')
async def unadmin_cmd(update,ctx):
    if not admin.is_owner(update.effective_user.id):await update.message.reply_text('⛔ Owner only.');return
    try:t=int(ctx.args[0])
    except:await update.message.reply_text('Usage: /unadmin USER_ID');return
    await update.message.reply_text('✅ Admin removed.' if admin.set_admin(update.effective_user.id,t,False) else '❌ Failed.')
async def admin_money(update,ctx,action):
    if not admin.has_power(update.effective_user.id):await update.message.reply_text('⛔ Admin only.');return
    try:t,a=parse2(ctx,f'Usage: /{action} USER_ID AMOUNT')
    except ValueError as e:await update.message.reply_text(str(e));return
    fn={'give':admin.give,'remove':admin.remove,'setbalance':admin.set_balance}[action];await update.message.reply_text('✅ Done.' if fn(update.effective_user.id,t,a) else '❌ Failed.')
async def give(update,ctx):await admin_money(update,ctx,'give')
async def remove(update,ctx):await admin_money(update,ctx,'remove')
async def setbalance(update,ctx):await admin_money(update,ctx,'setbalance')
async def ban_cmd(update,ctx):
    if not admin.has_power(update.effective_user.id):await update.message.reply_text('⛔ Admin only.');return
    try:t=int(ctx.args[0])
    except:await update.message.reply_text('Usage: /ban USER_ID');return
    await update.message.reply_text('✅ Banned.' if admin.ban(update.effective_user.id,t) else '❌ Failed.')
async def unban_cmd(update,ctx):
    if not admin.has_power(update.effective_user.id):await update.message.reply_text('⛔ Admin only.');return
    try:t=int(ctx.args[0])
    except:await update.message.reply_text('Usage: /unban USER_ID');return
    await update.message.reply_text('✅ Unbanned.' if admin.ban(update.effective_user.id,t,False) else '❌ Failed.')
async def warn_cmd(update,ctx):
    if not admin.has_power(update.effective_user.id):await update.message.reply_text('⛔ Admin only.');return
    try:t=int(ctx.args[0])
    except:await update.message.reply_text('Usage: /warn USER_ID');return
    await update.message.reply_text('⚠️ Warning added.' if admin.warn(update.effective_user.id,t) else '❌ Failed.')
async def mute_cmd(update,ctx,enabled):
    if not admin.has_power(update.effective_user.id):await update.message.reply_text('⛔ Admin only.');return
    try:t=int(ctx.args[0]);mins=int(ctx.args[1]) if enabled else 0
    except:await update.message.reply_text('/mute USER_ID MINUTES' if enabled else '/unmute USER_ID');return
    with database.connect() as c:database._ensure(c,t);c.execute('UPDATE users SET muted_until=? WHERE user_id=?',(int(time.time())+mins*60 if enabled else 0,t));c.commit()
    database.audit(update.effective_user.id,'mute' if enabled else 'unmute',t,str(mins));await update.message.reply_text('✅ Done.')
async def mute(update,ctx):await mute_cmd(update,ctx,True)
async def unmute(update,ctx):await mute_cmd(update,ctx,False)
async def stats(update,ctx):
    if not admin.has_power(update.effective_user.id):await update.message.reply_text('⛔ Admin only.');return
    u,c,g=database.stats();await update.message.reply_text(f'📊 Users: {u}\n🪙 Economy: {money(c)}\n🎮 Games: {g}')
async def maintenance_cmd(update,ctx):
    if not admin.is_owner(update.effective_user.id):await update.message.reply_text('⛔ Owner only.');return
    v=ctx.args[0].lower() if ctx.args else 'status'
    if v in ('on','off'):admin.maintenance(v=='on')
    await update.message.reply_text(f'Maintenance: {"ON" if admin.maintenance() else "OFF"}')
async def broadcast(update,ctx):
    if not admin.has_power(update.effective_user.id):await update.message.reply_text('⛔ Admin only.');return
    text=' '.join(ctx.args).strip()
    if not text:await update.message.reply_text('Usage: /broadcast MESSAGE');return
    sent=failed=0
    for row in database.all_users():
        try:await ctx.bot.send_message(row['user_id'],text);sent+=1
        except Exception:failed+=1
        await asyncio.sleep(.05)
    await update.message.reply_text(f'📢 Sent: {sent}\n❌ Failed: {failed}')
async def post_init(app):database.init_db();database.ensure_user(config.OWNER_ID)
def main():
    if not config.BOT_TOKEN:raise SystemExit('BOT_TOKEN is missing.')
    if not config.OWNER_ID:raise SystemExit('OWNER_ID is missing.')
    app=Application.builder().token(config.BOT_TOKEN).post_init(post_init).build()
    cmds={'start':start,'help':help_cmd,'balance':balance_cmd,'daily':daily,'work':work,'crime':crime,'pay':pay,'deposit':deposit,'withdraw':withdraw,'redeem':redeem,'gift':gift,'createpromo':promo_create,'promos':promos,'delpromo':delpromo,'admin':admin_cmd,'unadmin':unadmin_cmd,'give':give,'remove':remove,'setbalance':setbalance,'ban':ban_cmd,'unban':unban_cmd,'warn':warn_cmd,'mute':mute,'unmute':unmute,'stats':stats,'maintenance':maintenance_cmd,'broadcast':broadcast,'slots':direct_slots,'dice':direct_dice,'coin':direct_coin,'wheel':direct_wheel,'blackjack':direct_blackjack,'mines':direct_mines}
    for n,f in cmds.items():app.add_handler(CommandHandler(n,f))
    app.add_handler(CallbackQueryHandler(callback));log.info('Chaos Core starting');app.run_polling(allowed_updates=Update.ALL_TYPES)
if __name__=='__main__':main()
