"""Chaos Core configuration.
Set BOT_TOKEN and OWNER_ID as Railway environment variables.
Optional: DATABASE_PATH, STARTING_BALANCE, MIN_BET, MAX_BET.
"""
import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", "0") or 0)
DATABASE_PATH = os.getenv("DATABASE_PATH", "chaos_core.sqlite3")

STARTING_BALANCE = int(os.getenv("STARTING_BALANCE", "10000"))
MIN_BET = int(os.getenv("MIN_BET", "10"))
MAX_BET = int(os.getenv("MAX_BET", "1000000"))

DAILY_BASE = int(os.getenv("DAILY_BASE", "5000"))
WORK_MIN = int(os.getenv("WORK_MIN", "500"))
WORK_MAX = int(os.getenv("WORK_MAX", "3000"))
CRIME_MIN = int(os.getenv("CRIME_MIN", "1000"))
CRIME_MAX = int(os.getenv("CRIME_MAX", "10000"))
COOLDOWN_DAILY = 86400
COOLDOWN_WORK = 3600
COOLDOWN_CRIME = 7200
