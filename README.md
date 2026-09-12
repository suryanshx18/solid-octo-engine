# Telegram Shop Bot

Production-ready Telegram shop bot with:

- User panel: profile, balance, products, purchases, referrals, coupons.
- Admin panel: users, admins, balance, categories, accounts, deposits, bans, broadcast, channels, coupons, settings, stats.
- Owner panel: superadmin management.
- Force-join channels.
- Deposit via UTR with admin approval, 30‑minute timeout, and max 5 pending deposits.
- Referral system (₹1 reward).
- Coupons (bonus balance, usage limits).
- Balance management (`/addbalance`, `/removebalance`).
- Ban/unban.
- Broadcast (superadmin+owner only).
- Logging to channel.
- `/stats`, `/coinslist`, `/dfchat`.
- Maintenance mode.

MTProto-based Telegram account login/OTP is supported at the database level; integrate your Pyrogram flow in `handlers.py` where indicated.

## Setup

1. Clone or extract this repo.
2. Copy `.env.example` to `.env` and fill values:
   - `BOT_TOKEN`: from @BotFather
   - `OWNER_ID`: your Telegram user ID
   - `DATABASE_URL`: PostgreSQL URL (Railway) or leave empty for SQLite
   - `LOG_CHANNEL_ID`: ID of log channel
   - `API_ID`, `API_HASH`: from my.telegram.org
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
