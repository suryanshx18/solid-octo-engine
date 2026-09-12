from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import Category, Account, RequiredChannel


def main_menu_keyboard() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(text="👤 Profile", callback_data="user_profile")],
        [InlineKeyboardButton(text="💰 Balance", callback_data="user_balance")],
        [InlineKeyboardButton(text="🛒 Products", callback_data="user_products")],
        [InlineKeyboardButton(text="📜 Purchases", callback_data="user_purchases")],
        [InlineKeyboardButton(text="🧾 Transactions", callback_data="user_transactions")],
        [InlineKeyboardButton(text="🎁 Referral", callback_data="user_referral")],
        [InlineKeyboardButton(text="🎟 Coupon", callback_data="user_coupon")],
        [InlineKeyboardButton(text="📞 Support", callback_data="user_support")],
        [InlineKeyboardButton(text="❓ Help", callback_data="user_help")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def categories_keyboard(categories: list[Category]) -> InlineKeyboardMarkup:
    kb = []
    for cat in categories:
        if not cat.is_active:
            continue
        kb.append([InlineKeyboardButton(text=f"{cat.name} – ₹{cat.rate}", callback_data=f"cat_{cat.id}")])
    kb.append([InlineKeyboardButton(text="🏠 Home", callback_data="menu_home")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def accounts_keyboard(accounts: list[Account]) -> InlineKeyboardMarkup:
    kb = []
    for acc in accounts:
        if acc.status != "available":
            continue
        price = acc.price_override if acc.price_override is not None else acc.category.rate
        kb.append([InlineKeyboardButton(text=f"Account #{acc.id} – ₹{price}", callback_data=f"buy_acc_{acc.id}")])
    kb.append([InlineKeyboardButton(text="🔙 Back", callback_data="user_products")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def force_join_keyboard(channels: list[RequiredChannel]) -> InlineKeyboardMarkup:
    kb = []
    for ch in channels:
        label = ch.label or ch.channel_username or "Channel"
        username = ch.channel_username
        if username:
            if username.startswith("@"):
                username = username[1:]
            url = f"https://t.me/{username}"
        else:
            url = "#"
        kb.append([InlineKeyboardButton(text=f"Join {label}", url=url)])
    kb.append([InlineKeyboardButton(text="✅ Verify", callback_data="force_verify")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(text="👥 Users", callback_data="admin_users")],
        [InlineKeyboardButton(text="🛡 Admins", callback_data="admin_admins")],
        [InlineKeyboardButton(text="💰 Balance", callback_data="admin_balance")],
        [InlineKeyboardButton(text="📦 Categories", callback_data="admin_categories")],
        [InlineKeyboardButton(text="📱 Accounts", callback_data="admin_accounts")],
        [InlineKeyboardButton(text="🧾 Deposits", callback_data="admin_deposits")],
        [InlineKeyboardButton(text="🚫 Bans", callback_data="admin_bans")],
        [InlineKeyboardButton(text="📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="📡 Channels", callback_data="admin_channels")],
        [InlineKeyboardButton(text="🎟 Coupons", callback_data="admin_coupons")],
        [InlineKeyboardButton(text="⚙️ Settings", callback_data="admin_settings")],
        [InlineKeyboardButton(text="📊 Stats", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🏠 Home", callback_data="menu_home")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def approve_deposit_keyboard(deposit_id: int) -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(text="✅ Approve", callback_data=f"deposit_approve_{deposit_id}")],
        [InlineKeyboardButton(text="❌ Reject", callback_data=f"deposit_reject_{deposit_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def back_home_keyboard() -> InlineKeyboardMarkup:
    kb = [[InlineKeyboardButton(text="🏠 Home", callback_data="menu_home")]]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def deposit_amount_keyboard() -> InlineKeyboardMarkup:
    kb = [[InlineKeyboardButton(text="🔙 Back", callback_data="menu_home")]]
    return InlineKeyboardMarkup(inline_keyboard=kb)
