"""Virtual-currency casino games. No real-money wagering/cashout."""
import secrets, random
import database
from config import MIN_BET, MAX_BET

def valid_bet(user_id, bet):
    if bet < MIN_BET or bet > MAX_BET: return False
    return database.user(user_id)["balance"] >= bet

def finish(uid, game, bet, net, result):
    if net > 0: database.change_balance(uid, net, game, result)
    database.log_game(uid, game, bet, result, net)
    return net

def slots(uid, bet):
    if not valid_bet(uid,bet): return None
    if not database.change_balance(uid,-bet,"slots","bet"): return None
    symbols=["🍒","🍋","🔔","⭐","7️⃣"]
    reels=[secrets.choice(symbols) for _ in range(3)]
    if len(set(reels))==1: mult={"7️⃣":15,"⭐":10,"🔔":7,"🍒":5,"🍋":3}[reels[0]]
    elif len(set(reels))==2: mult=2
    else: mult=0
    payout=bet*mult
    net=payout-bet
    if payout: database.change_balance(uid,payout,"slots","payout")
    database.log_game(uid,"slots",bet," ".join(reels),net)
    return reels, net, payout

def dice(uid, bet):
    if not valid_bet(uid,bet): return None
    if not database.change_balance(uid,-bet,"dice","bet"): return None
    roll=secrets.randbelow(6)+1
    # High (4-6) pays 2x, low (1-3) loses
    if roll>=4:
        payout=bet*2; database.change_balance(uid,payout,"dice","payout"); net=bet
    else: payout=0; net=-bet
    database.log_game(uid,"dice",bet,str(roll),net)
    return roll,net,payout

def coin(uid, bet, choice):
    if not valid_bet(uid,bet): return None
    if choice not in ("heads","tails"): return None
    if not database.change_balance(uid,-bet,"coin","bet"): return None
    result=secrets.choice(("heads","tails"))
    if result==choice:
        payout=bet*2; database.change_balance(uid,payout,"coin","payout"); net=bet
    else: payout=0; net=-bet
    database.log_game(uid,"coin",bet,result,net)
    return result,net,payout

def wheel(uid,bet):
    if not valid_bet(uid,bet): return None
    if not database.change_balance(uid,-bet,"wheel","bet"): return None
    mult=secrets.choice([0,0,0,2,3,5,10])
    payout=bet*mult
    if payout: database.change_balance(uid,payout,"wheel","payout")
    net=payout-bet
    database.log_game(uid,"wheel",bet,f"{mult}x",net)
    return mult,net,payout

def _deck():
    return [(r,s) for r in "23456789TJQKA" for s in "♠♥♦♣"]

def value(hand):
    total=0; aces=0
    for r,_ in hand:
        if r in "TJQK": total+=10
        elif r=="A": total+=11; aces+=1
        else: total+=int(r)
    while total>21 and aces:
        total-=10; aces-=1
    return total

ACTIVE={}

def blackjack_start(uid,bet):
    if not valid_bet(uid,bet) or uid in ACTIVE: return None
    if not database.change_balance(uid,-bet,"blackjack","bet"): return None
    d=_deck(); random.shuffle(d)
    player=[d.pop(),d.pop()]; dealer=[d.pop(),d.pop()]
    ACTIVE[uid]={"bet":bet,"deck":d,"player":player,"dealer":dealer}
    if value(player)==21:
        payout=bet*2.5
        database.change_balance(uid,int(payout),"blackjack","blackjack")
        database.log_game(uid,"blackjack",bet,"blackjack",int(payout)-bet)
        del ACTIVE[uid]
        return "blackjack",player,dealer,int(payout)
    return "started",player,[dealer[0],("?", "?")],None

def blackjack_hit(uid):
    g=ACTIVE.get(uid)
    if not g:return None
    g["player"].append(g["deck"].pop())
    if value(g["player"])>21:
        net=-g["bet"]; database.log_game(uid,"blackjack",g["bet"],"bust",net); del ACTIVE[uid]
        return "bust",g["player"],g["dealer"],0
    return "continue",g["player"],[g["dealer"][0],("?", "?")],None

def blackjack_stand(uid):
    g=ACTIVE.get(uid)
    if not g:return None
    while value(g["dealer"])<17:g["dealer"].append(g["deck"].pop())
    pv,dv=value(g["player"]),value(g["dealer"]); bet=g["bet"]
    if dv>21 or pv>dv:
        payout=bet*2; net=bet
    elif pv==dv:payout=bet; net=0
    else:payout=0; net=-bet
    if payout: database.change_balance(uid,payout,"blackjack","payout")
    database.log_game(uid,"blackjack",bet,f"{pv}-{dv}",net); del ACTIVE[uid]
    return "done",g["player"],g["dealer"],payout

MINES={}

def mines_start(uid,bet):
    if not valid_bet(uid,bet) or uid in MINES:return None
    if not database.change_balance(uid,-bet,"mines","bet"):return None
    bombs=set(secrets.choice(range(25)) for _ in range(5))
    while len(bombs)<5:bombs.add(secrets.randbelow(25))
    MINES[uid]={"bet":bet,"bombs":bombs,"opened":set()}
    return MINES[uid]

def mines_pick(uid,cell):
    g=MINES.get(uid)
    if not g:return None
    if cell in g["opened"]:return "already",len(g["opened"])
    if cell in g["bombs"]:
        database.log_game(uid,"mines",g["bet"],"boom",-g["bet"]); del MINES[uid]
        return "boom",0
    g["opened"].add(cell)
    return "safe",len(g["opened"])

def mines_cashout(uid):
    g=MINES.get(uid)
    if not g:return None
    n=len(g["opened"])
    if n==0:return "none",0
    mult=1+0.25*n
    payout=int(g["bet"]*mult)
    database.change_balance(uid,payout,"mines","cashout")
    net=payout-g["bet"]
    database.log_game(uid,"mines",g["bet"],f"cashout {n}",net)
    del MINES[uid]
    return "cashout",payout
