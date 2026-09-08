import os

BOT_TOKEN = os.getenv('BOT_TOKEN', '').strip()
try: OWNER_ID = int(os.getenv('OWNER_ID', '0'))
except ValueError: OWNER_ID = 0
DATABASE_PATH = os.getenv('DATABASE_PATH', 'chaos_core.db')
STARTING_BALANCE = int(os.getenv('STARTING_BALANCE', '1000'))
MIN_BET = int(os.getenv('MIN_BET', '10'))
MAX_BET = int(os.getenv('MAX_BET', '50000'))
DAILY_BASE = 1000
WORK_MIN, WORK_MAX = 150, 700
CRIME_MIN, CRIME_MAX = 100, 1200
COOLDOWN_DAILY, COOLDOWN_WORK, COOLDOWN_CRIME = 86400, 3600, 1800
SHOP_ITEMS = {'lucky': (5000, 'Lucky Charm'), 'shield': (10000, 'Protection Shield'), 'crate': (2500, 'Mystery Crate')}
VIP_COSTS = {1: 25000, 2: 75000, 3: 200000}
