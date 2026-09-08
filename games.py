import random,secrets,database
from config import MIN_BET,MAX_BET

def valid_bet(uid,bet):
    try:bet=int(bet)
    except:return False
    r=database.user(uid);return MIN_BET<=bet<=MAX_BET and r['balance']>=bet

def slots(uid,bet):
    if not valid_bet(uid,bet) or not database.change_balance(uid,-bet,'slots','bet'):return None
    s=['🍒','🍋','🔔','⭐','7️⃣']; reels=[secrets.choice(s) for _ in range(3)]; mult=({"7️⃣":15,"⭐":10,"🔔":7,"🍒":5,"🍋":3}.get(reels[0],0) if len(set(reels))==1 else 2 if len(set(reels))==2 else 0); payout=bet*mult
    if payout:database.change_balance(uid,payout,'slots','payout')
    net=payout-bet;database.log_game(uid,'slots',bet,' '.join(reels),net);return reels,net,payout

def dice(uid,bet):
    if not valid_bet(uid,bet) or not database.change_balance(uid,-bet,'dice','bet'):return None
    roll=secrets.randbelow(6)+1;payout=bet*2 if roll>=4 else 0
    if payout:database.change_balance(uid,payout,'dice','payout')
    net=payout-bet;database.log_game(uid,'dice',bet,str(roll),net);return roll,net,payout

def coin(uid,bet,choice):
    if choice not in ('heads','tails') or not valid_bet(uid,bet) or not database.change_balance(uid,-bet,'coin','bet'):return None
    result=secrets.choice(('heads','tails'));payout=bet*2 if result==choice else 0
    if payout:database.change_balance(uid,payout,'coin','payout')
    net=payout-bet;database.log_game(uid,'coin',bet,result,net);return result,net,payout

def wheel(uid,bet):
    if not valid_bet(uid,bet) or not database.change_balance(uid,-bet,'wheel','bet'):return None
    mult=secrets.choice((0,0,0,2,3,5,10));payout=bet*mult
    if payout:database.change_balance(uid,payout,'wheel','payout')
    net=payout-bet;database.log_game(uid,'wheel',bet,f'{mult}x',net);return mult,net,payout

def _deck():return [(r,s) for r in '23456789TJQKA' for s in '♠♥♦♣']
def value(hand):
    total=aces=0
    for r,_ in hand: total+=11 if r=='A' else 10 if r in 'TJQK' else int(r);aces+=r=='A'
    while total>21 and aces:total-=10;aces-=1
    return total
ACTIVE={}
def blackjack_start(uid,bet):
    if not valid_bet(uid,bet) or uid in ACTIVE or not database.change_balance(uid,-bet,'blackjack','bet'):return None
    d=_deck();random.SystemRandom().shuffle(d);p=[d.pop(),d.pop()];dealer=[d.pop(),d.pop()];ACTIVE[uid]={'bet':bet,'deck':d,'player':p,'dealer':dealer}
    if value(p)==21:
        payout=bet*5//2;database.change_balance(uid,payout,'blackjack','blackjack');database.log_game(uid,'blackjack',bet,'blackjack',payout-bet);del ACTIVE[uid];return 'blackjack',p,dealer,payout
    return 'started',p,[dealer[0],('?', '?')],0

def blackjack_hit(uid):
    g=ACTIVE.get(uid)
    if not g:return None
    g['player'].append(g['deck'].pop())
    if value(g['player'])>21:del ACTIVE[uid];database.log_game(uid,'blackjack',g['bet'],'bust',-g['bet']);return 'bust',g['player'],g['dealer'],0
    return 'continue',g['player'],[g['dealer'][0],('?', '?')],0

def blackjack_stand(uid):
    g=ACTIVE.get(uid)
    if not g:return None
    while value(g['dealer'])<17:g['dealer'].append(g['deck'].pop())
    pv,dv,bet=value(g['player']),value(g['dealer']),g['bet'];payout=bet*2 if dv>21 or pv>dv else bet if pv==dv else 0;net=payout-bet
    if payout:database.change_balance(uid,payout,'blackjack','payout')
    database.log_game(uid,'blackjack',bet,f'{pv}-{dv}',net);del ACTIVE[uid];return 'done',g['player'],g['dealer'],payout
MINES={}
def mines_start(uid,bet):
    if not valid_bet(uid,bet) or uid in MINES or not database.change_balance(uid,-bet,'mines','bet'):return None
    bombs=set(secrets.randbelow(25) for _ in range(5));MINES[uid]={'bet':bet,'bombs':bombs,'opened':set()};return MINES[uid]
def mines_pick(uid,cell):
    g=MINES.get(uid)
    if not g or cell<0 or cell>24:return None
    if cell in g['opened']:return 'already',len(g['opened'])
    if cell in g['bombs']:database.log_game(uid,'mines',g['bet'],'boom',-g['bet']);del MINES[uid];return 'boom',0
    g['opened'].add(cell)
    if len(g['opened'])==20:return mines_cashout(uid)
    return 'safe',len(g['opened'])
def mines_cashout(uid):
    g=MINES.get(uid)
    if not g or not g['opened']:return 'none',0
    payout=int(g['bet']*(1+0.25*len(g['opened'])));database.change_balance(uid,payout,'mines','cashout');database.log_game(uid,'mines',g['bet'],f'cashout {len(g["opened"])}',payout-g['bet']);del MINES[uid];return 'cashout',payout
