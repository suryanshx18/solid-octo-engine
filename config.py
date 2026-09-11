import os

BOT_TOKEN = os.getenv('BOT_TOKEN', '').strip()
OWNER_ID = int(os.getenv('OWNER_ID', '0') or 0)
DB_PATH = os.getenv('DB_PATH', 'groupguard_ultra.db')
LOG_CHAT_ID = int(os.getenv('LOG_CHAT_ID', '0') or 0)
TAG_DELAY = float(os.getenv('TAG_DELAY', '0.35') or 0.35)
DEFAULT_WARN_LIMIT = int(os.getenv('DEFAULT_WARN_LIMIT', '3') or 3)

if not BOT_TOKEN:
    raise RuntimeError('BOT_TOKEN is missing. Set it in Railway variables.')
if not OWNER_ID:
    raise RuntimeError('OWNER_ID is missing. Set it in Railway variables.')

