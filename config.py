
***

## 4. `config.py`

```python
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required")

OWNER_ID = os.getenv("OWNER_ID")
if not OWNER_ID:
    raise RuntimeError("OWNER_ID is required")
OWNER_ID = int(OWNER_ID)

DATABASE_URL = os.getenv("DATABASE_URL")

LOG_CHANNEL_ID = os.getenv("LOG_CHANNEL_ID")
if LOG_CHANNEL_ID:
    LOG_CHANNEL_ID = int(LOG_CHANNEL_ID)

SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "support")

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
if not API_ID or not API_HASH:
    raise RuntimeError("API_ID and API_HASH are required")

MAINTENANCE_MODE = os.getenv("MAINTENANCE_MODE", "false").lower() == "true"
