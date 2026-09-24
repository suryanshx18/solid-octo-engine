import asyncio, logging, random, os
from datetime import datetime
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, ForeignKey, DateTime, func
from sqlalchemy.orm import declarative_base, sessionmaker
import phonenumbers, aiohttp

# ═══════════════ CONFIGURATION ═══════════════
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///marketplace.db")

# ═══════════════ TRANSLATIONS ═══════════════
TEXTS = {
    "en": {"welcome": "🩸 **BLOODLINE TG ACCOUNT STORE** 🩸\n――――――――――――――――――――――――\n👋 Hey {name}!\n🆔 `{id}`\n\n💵 Balance: `${balance:.2f}`\n📝 Rank: `VIP1`\n――――――――――――――――――――――――\n🪄 Select an option below 🪄",
           "buy_acc": "📦 Buy Accounts", "sell_acc": "📤 Sell Accounts", "top_up": "💳 Top up", "withdraw": "🏦 Withdrawal",
           "profile": "👑 Profile", "referral": "🤝 Referrals", "api_key": "🔑 API Key", "wishlist": "⭐ Wishlist",
           "daily_bonus": "🎁 Daily Bonus", "history": "📜 History", "support": "🛠️ Support", "language": "🌐 Language",
           "official_channel": "📢 Official Channel", "developer": "🧑‍💻 Developer", "admin_panel": "🛠️ Admin Panel"},
    "hi": {"welcome": "🩸 **BLOODLINE TG ACCOUNT STORE** 🩸\n――――――――――――――――――――――――\n👋 नमस्ते {name}!\n🆔 `{id}`\n\n💵 बैलेंस: `${balance:.2f}`\n📝 रैंक: `VIP1`\n――――――――――――――――――――――――\n🪄 नीचे से विकल्प चुनें 🪄",
           "buy_acc": "📦 खाते खरीदें", "sell_acc": "📤 खाते बेचें", "top_up": "💳 टॉप अप", "withdraw": "🏦 निकासी",
           "profile": "👑 प्रोफ़ाइल", "referral": "🤝 रेफरल", "api_key": "🔑 एपीआई कुंजी", "wishlist": "⭐ विशलिस्ट",
           "daily_bonus": "🎁 दैनिक बोनस", "history": "📜 इतिहास", "support": "🛠️ सहायता", "language": "🌐 भाषा",
           "official_channel": "📢 आधिकारिक चैनल", "developer": "🧑‍💻 डेवलपर", "admin_panel": "🛠️ एडमिन पैनल"},
    "ru": {"welcome": "🩸 **BLOODLINE TG ACCOUNT STORE** 🩸\n――――――――――――――――――――――――\n👋 Привет {name}!\n🆔 `{id}`\n\n💵 Баланс: `${balance:.2f}`\n📝 Ранг: `VIP1`\n――――――――――――――――――――――――\n🪄 Выберите опцию ниже 🪄",
           "buy_acc": "📦 Купить аккаунты", "sell_acc": "📤 Продать аккаунты", "top_up": "💳 Пополнить", "withdraw": "🏦 Вывод",
           "profile": "👑 Профиль", "referral": "🤝 Рефералы", "api_key": "🔑 API Ключ", "wishlist": "⭐ Список желаний",
           "daily_bonus": "🎁 Ежедневный бонус", "history": "📜 История", "support": "🛠️ Поддержка", "language": "🌐 Язык",
           "official_channel": "📢 Официальный канал", "developer": "🧑‍💻 Разработчик", "admin_panel": "🛠️ Админ Панель"},
    "ar": {"welcome": "🩸 **BLOODLINE TG ACCOUNT STORE** 🩸\n――――――――――――――――――――――――\n👋 مرحبا {name}!\n🆔 `{id}`\n\n💵 الرصيد: `${balance:.2f}`\n📝 الرتبة: `VIP1`\n――――――――――――――――――――――――\n🪄 اختر خيارًا أدناه 🪄",
           "buy_acc": "📦 شراء حسابات", "sell_acc": "📤 بيع الحسابات", "top_up": "💳 شحن الرصيد", "withdraw": "🏦 سحب",
           "profile": "👑 الملف الشخصي", "referral": "🤝 الإحالات", "api_key": "🔑 مفتاح API", "wishlist": "⭐ قائمة الرغبات",
           "daily_bonus": "🎁 مكافأة يومية", "history": "📜 السجل", "support": "🛠️ الدعم", "language": "🌐 اللغة",
           "official_channel": "📢 القناة الرسمية", "developer": "🧑‍💻 المطور", "admin_panel": "🛠️ لوحة التحكم"}
}

# ═══════════════ DATABASE SETUP ═══════════════
Base = declarative_base()
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

PRICE_GUIDE = {"AL": 0.40, "AM": 0.45, "AR": 0.40, "AZ": 0.80, "CA": 0.18, "CG": 0.30, "CO": 0.20, "DZ": 0.30, "EG": 0.18, "ET": 0.19, "FR": 0.55, "GA": 0.50, "GF": 0.50, "GH": 0.30, "GL": 0.70, "HK": 0.35, "ID": 0.20, "IN": 0.16, "JO": 0.50, "KE": 0.22, "KG": 0.70, "KR": 1.40, "KZ": 0.50, "LK": 0.30, "LY": 0.35, "MA": 0.28, "MG": 0.15, "ML": 0.15, "MM": 0.20, "MN": 0.40, "MX": 0.50, "MY": 0.45, "NG": 0.18, "NL": 0.60, "NP": 0.30, "PG": 0.25, "PH": 0.20, "PK": 0.20, "PL": 0.38, "SA": 0.60, "SN": 0.25, "SY": 0.25, "TH": 0.25, "TR": 0.50, "UA": 1.00, "UZ": 0.40, "VE": 0.80, "YE": 0.35, "ZW": 0.20}

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    balance = Column(Float, default=0.0)
    is_admin = Column(Boolean, default=False)
    is_banned = Column(Boolean, default=False)
    referrer_id = Column(Integer, nullable=True)
    referral_earnings = Column(Float, default=0.0)
    last_bonus_date = Column(DateTime, nullable=True)
    joined_at = Column(DateTime, default=datetime.utcnow)
    wishlist = Column(String, default="")
    lang = Column(String, default="en")

class ApiKey(Base):
    __tablename__ = 'api_keys'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, unique=True)
    api_key = Column(String, unique=True)
    status = Column(String, default="Active")
    created_at = Column(DateTime, default=datetime.utcnow)

class ForceJoinChannel(Base):
    __tablename__ = 'force_join_channels'
    id = Column(Integer, primary_key=True)
    username = Column(String)
    link = Column(String)

class Product(Base):
    __tablename__ = 'products'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    country = Column(String)
    price_usd = Column(Float, default=0.0)
    description = Column(String, nullable=True)

class StockAccount(Base):
    __tablename__ = 'stock_accounts'
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey('products.id'))
    phone = Column(String)
    session_string = Column(String)
    password_2fa = Column(String, nullable=True)
    status = Column(String, default="Available")

class SellRequest(Base):
    __tablename__ = 'sell_requests'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    phone = Column(String)
    session_string = Column(String)
    price_usd = Column(Float)
    status = Column(String, default="Pending")

class TopUpRequest(Base):
    __tablename__ = 'topup_requests'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    amount_inr = Column(Float)
    amount_usd = Column(Float)
    utr = Column(String, nullable=True)
    screenshot_file_id = Column(String, nullable=True)
    status = Column(String, default="Pending")

class WithdrawRequest(Base):
    __tablename__ = 'withdraw_requests'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    amount_usd = Column(Float)
    upi_id = Column(String)
    status = Column(String, default="Pending")

class Transaction(Base):
    __tablename__ = 'transactions'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    type = Column(String)
    amount = Column(Float)
    status = Column(String)
    date = Column(DateTime, default=datetime.utcnow)

class Rating(Base):
    __tablename__ = 'ratings'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    product_id = Column(Integer)
    score = Column(Integer)
    date = Column(DateTime, default=datetime.utcnow)

class Setting(Base):
    __tablename__ = 'settings'
    key = Column(String, primary_key=True)
    value = Column(String)

Base.metadata.create_all(engine)

# ═══════════════ HELPERS ═══════════════
def get_setting(key, default=None):
    s = db.query(Setting).filter(Setting.key == key).first()
    return s.value if s else default

def set_setting(key, value):
    s = db.query(Setting).filter(Setting.key == key).first()
    if s: s.value = value
    else: db.add(Setting(key=key, value=value))
    db.commit()

def get_user(user_id):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        user = User(id=user_id, balance=0.0)
        db.add(user); db.commit()
    return user

def log_transaction(user_id, t_type, amount, status="Completed"):
    db.add(Transaction(user_id=user_id, type=t_type, amount=amount, status=status))
    db.commit()

# ═══════════════ BOT SETUP ═══════════════
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

class AdminStates(StatesGroup):
    add_prod_name = State(); add_prod_desc = State(); add_prod_price = State(); add_prod_country = State()
    add_stock_phone = State(); add_stock_otp = State(); add_stock_2fa = State()
    set_upi_id = State(); set_qr_code = State(); add_admin_id = State()
    edit_name = State(); edit_price = State(); edit_country = State(); edit_desc = State()
    add_balance = State(); deduct_balance = State(); target_user = State()
    bulk_upload = State(); reply_ticket = State()
    fj_username = State(); fj_link = State()

class UserSellStates(StatesGroup):
    sell_phone = State(); confirm_sell = State(); sell_otp = State(); sell_2fa = State()

class UserTopUpStates(StatesGroup):
    amount_inr = State(); payment_proof = State()

class UserWithdrawStates(StatesGroup):
    amount = State(); upi_id = State()

class UserSupportStates(StatesGroup):
    waiting_message = State()

# ═══════════════ TELETHON LOGIN ═══════════════
async def start_telethon_login(phone, api_id, api_hash):
    client = TelegramClient(StringSession(), int(api_id), api_hash)
    await client.connect()
    try:
        sent_code = await client.send_code_request(phone)
        return client, sent_code.phone_code_hash
    except Exception as e:
        await client.disconnect(); raise e

async def verify_telethon_otp(client, phone, otp, phone_code_hash):
    await client.sign_in(phone, code=otp, phone_code_hash=phone_code_hash)
    return client.session.save()

async def verify_telethon_2fa(client, password):
    await client.sign_in(password=password)
    return client.session.save()

async def fetch_otp_from_tgshark(phone):
    url = "https://tgsharkapi.store/api/v1/get_otp"
    params = {"api_key": TGSHARK_API_KEY, "phone": phone}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=15) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("otp") or data.get("code") or data.get("message")
                return None
    except Exception as e: print(f"TG-Shark API Error: {e}"); return None

# ═══════════════ KEYBOARDS ═══════════════
async def is_user_joined(user_id):
    channels = db.query(ForceJoinChannel).all()
    if not channels: return True
    for ch in channels:
        try:
            member = await bot.get_chat_member(chat_id=f"@{ch.username}", user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]: return False
        except Exception: pass
    return True

def get_join_keyboard():
    channels = db.query(ForceJoinChannel).all()
    kb = []
    for ch in channels:
        kb.append([InlineKeyboardButton(text=f"📢 Join {ch.username}", url=ch.link, style="primary")])
    kb.append([InlineKeyboardButton(text="✅ I have Joined", callback_data="check_join", style="success")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def user_main_menu_kb(user_id, is_admin=False, lang="en"):
    t = TEXTS.get(lang, TEXTS["en"])
    kb = [
        [InlineKeyboardButton(text=t["buy_acc"], callback_data="buy_acc", style="primary"), InlineKeyboardButton(text=t["sell_acc"], callback_data="sell_acc", style="success")],
        [InlineKeyboardButton(text=t["top_up"], callback_data="top_up", style="primary"), InlineKeyboardButton(text=t["withdraw"], callback_data="user_withdraw", style="danger")],
        [InlineKeyboardButton(text=t["profile"], callback_data="user_profile", style="primary"), InlineKeyboardButton(text=t["referral"], callback_data="user_referral", style="success")],
        [InlineKeyboardButton(text=t["api_key"], callback_data="api_key", style="primary"), InlineKeyboardButton(text=t["wishlist"], callback_data="user_wishlist", style="primary")],
        [InlineKeyboardButton(text=t["daily_bonus"], callback_data="daily_bonus", style="success"), InlineKeyboardButton(text=t["history"], callback_data="user_history", style="primary")],
        [InlineKeyboardButton(text=t["support"], callback_data="user_support", style="primary"), InlineKeyboardButton(text=t["language"], callback_data="language", style="primary")],
        [InlineKeyboardButton(text=t["official_channel"], url="https://t.me/+PhI4EUQ5s3pmZTFl", style="primary"), InlineKeyboardButton(text=t["developer"], callback_data="developer_btn", style="primary")]
    ]
    if user_id == ADMIN_ID or is_admin:
        kb.append([InlineKeyboardButton(text=t["admin_panel"], callback_data="admin_panel", style="danger")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def admin_panel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Stats", callback_data="admin_stats", style="primary"), InlineKeyboardButton(text="🏆 Contest", callback_data="admin_contest", style="primary")],
        [InlineKeyboardButton(text="📦 Manage Products", callback_data="admin_manage_prod", style="primary"), InlineKeyboardButton(text="📥 Manage Stock", callback_data="admin_manage_stock", style="primary")],
        [InlineKeyboardButton(text="👤 Manage Users", callback_data="admin_manage_users", style="primary"), InlineKeyboardButton(text="📁 Bulk Stock", callback_data="admin_bulk_stock", style="primary")],
        [InlineKeyboardButton(text="📦 Add Product", callback_data="admin_add_prod", style="success"), InlineKeyboardButton(text="📥 Add Stock", callback_data="admin_add_stock", style="success")],
        [InlineKeyboardButton(text="👤 Sell Requests", callback_data="admin_sell_reqs", style="primary"), InlineKeyboardButton(text="💰 Top-up Requests", callback_data="admin_topup_reqs", style="primary")],
        [InlineKeyboardButton(text="💸 Withdraw Requests", callback_data="admin_withdraw_reqs", style="danger"), InlineKeyboardButton(text="📱 Sold Accounts", callback_data="admin_sold_accs", style="danger")],
        [InlineKeyboardButton(text="📢 Force Join", callback_data="admin_force_join", style="danger"), InlineKeyboardButton(text="💳 Set UPI ID", callback_data="admin_set_upi", style="primary")],
        [InlineKeyboardButton(text="🖼️ Set QR Code", callback_data="admin_set_qr", style="primary"), InlineKeyboardButton(text="➕ Add Admin", callback_data="admin_add_admin", style="success")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="menu", style="danger")]
    ])

# ═══════════════ START HANDLER ═══════════════
@router.message(CommandStart(deep_link=True))
async def start_with_referral(message: Message, command: CommandObject):
    user = get_user(message.from_user.id)
    if user.is_banned: return await message.answer("🚫 You are banned.")
    args = command.args
    if args and args.startswith("REF_"):
        referrer_id = int(args.split("_")[1])
        if user.referrer_id is None and referrer_id != message.from_user.id:
            user.referrer_id = referrer_id; db.commit()
            await message.answer("🎉 Referral link applied!")
    await send_welcome(message)

@router.message(CommandStart())
async def start_cmd(message: Message):
    await send_welcome(message)

async def send_welcome(message: Message):
    user = get_user(message.from_user.id)
    if user.is_banned: return await message.answer("🚫 You are banned.")
    if not await is_user_joined(message.from_user.id):
        return await message.answer("⚠️ **Bot use karne ke liye pehle hamare Official Channels join karein!**", reply_markup=get_join_keyboard())
    t = TEXTS.get(user.lang, TEXTS["en"])
    text = t["welcome"].format(name=message.from_user.first_name, id=user.id, balance=user.balance)
    await message.answer(text, reply_markup=user_main_menu_kb(user.id, user.is_admin, user.lang))

@router.callback_query(F.data == "check_join")
async def check_join_cb(call: CallbackQuery):
    if await is_user_joined(call.from_user.id):
        await call.message.delete()
        # Fix: Send welcome using call.message
        user = get_user(call.from_user.id)
        t = TEXTS.get(user.lang, TEXTS["en"])
        text = t["welcome"].format(name=call.from_user.first_name, id=user.id, balance=user.balance)
        await call.message.answer(text, reply_markup=user_main_menu_kb(user.id, user.is_admin, user.lang))
    else: await call.answer("❌ Aapne abhi tak saare channels join nahi kiye!", show_alert=True)

@router.callback_query(F.data == "menu")
async def menu_cb(call: CallbackQuery):
    await call.message.delete()
    user = get_user(call.from_user.id)
    t = TEXTS.get(user.lang, TEXTS["en"])
    text = t["welcome"].format(name=call.from_user.first_name, id=user.id, balance=user.balance)
    await call.message.answer(text, reply_markup=user_main_menu_kb(user.id, user.is_admin, user.lang))

# ═══════════════ USER HANDLERS ═══════════════
@router.callback_query(F.data == "admin_panel")
async def admin_panel_callback(call: CallbackQuery):
    user = get_user(call.from_user.id)
    if user.id != ADMIN_ID and not user.is_admin: return await call.answer("❌ Access Denied!", show_alert=True)
    await call.message.edit_text("🩸 **Bloodline Admin Panel** 🩸", reply_markup=admin_panel_kb())

@router.callback_query(F.data == "developer_btn")
async def developer_info(call: CallbackQuery):
    text = f"🧑‍💻 **Developer Info**\n\n👤 Name: Rudra\n📩 Telegram: @RudraBhagwanHun\n\n💬 Kisi bhi query ya support ke liye contact karein."
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💬 Contact Developer", url="https://t.me/RudraBhagwanHun", style="primary")], [InlineKeyboardButton(text="🔙 Back", callback_data="menu", style="danger")]])
    await call.message.answer(text, reply_markup=kb)

@router.callback_query(F.data == "user_profile")
async def user_profile(call: CallbackQuery):
    user = get_user(call.from_user.id)
    text = f"👑 **Profile**\n\nID: `{user.id}`\nBalance: `${user.balance:.2f}`\nReferral Earnings: `${user.referral_earnings:.2f}`"
    await call.message.answer(text)

@router.callback_query(F.data == "daily_bonus")
async def daily_bonus(call: CallbackQuery):
    user = get_user(call.from_user.id); now = datetime.utcnow()
    if user.last_bonus_date and (now - user.last_bonus_date).days < 1:
        return await call.answer("⏳ You already claimed today's bonus!", show_alert=True)
    bonus = 0.01; user.balance += bonus; user.last_bonus_date = now; db.commit()
    log_transaction(user.id, "Daily Bonus", bonus)
    await call.message.answer(f"🎁 You claimed ${bonus:.2f} Daily Bonus!")

@router.callback_query(F.data == "user_referral")
async def user_referral(call: CallbackQuery):
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=REF_{call.from_user.id}"
    user = get_user(call.from_user.id)
    text = f"🤝 **Referral Program**\n\nInvite friends and earn $0.01 per referral!\n\n🔗 Your Link:\n`{ref_link}`\n\n💰 Total Earnings: `${user.referral_earnings:.2f}`"
    await call.message.answer(text)

@router.callback_query(F.data == "api_key")
async def show_api_key(call: CallbackQuery):
    user_id = call.from_user.id
    api_key_obj = db.query(ApiKey).filter(ApiKey.user_id == user_id).first()
    if not api_key_obj:
        new_key = f"BLD-{random.randint(1000,9999)}-{random.randint(1000,9999)}"
        api_key_obj = ApiKey(user_id=user_id, api_key=new_key, status="Active")
        db.add(api_key_obj); db.commit()
    text = f"🔑 **Aapki API Key**\n\n`{api_key_obj.api_key}`\n\n📌 Status: {api_key_obj.status}\n\n📖 **Documentation:**\nEndpoint: `https://api.bloodline.com/v1/buy`\nHeaders: `X-API-Key: {api_key_obj.api_key}`\n\n⚠️ Kisi ke saath share na karein."
    await call.message.answer(text)

@router.callback_query(F.data == "language")
async def language_menu(call: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇬🇧 English", callback_data="set_lang_en", style="primary"), InlineKeyboardButton(text="🇮🇳 Hindi", callback_data="set_lang_hi", style="success")],
        [InlineKeyboardButton(text="🇷🇺 Russian", callback_data="set_lang_ru", style="primary"), InlineKeyboardButton(text="🇸🇦 Arabic", callback_data="set_lang_ar", style="success")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="menu", style="danger")]])
    await call.message.edit_text("🌐 **Select Language / Bhasha Chunein**", reply_markup=kb)

@router.callback_query(F.data.startswith("set_lang_"))
async def set_language(call: CallbackQuery):
    lang_code = call.data.split("_")[2]
    user = get_user(call.from_user.id); user.lang = lang_code; db.commit()
    await call.answer(f"✅ Language set successfully!", show_alert=True)
    # Refresh menu
    t = TEXTS.get(user.lang, TEXTS["en"])
    text = t["welcome"].format(name=call.from_user.first_name, id=user.id, balance=user.balance)
    await call.message.edit_text(text, reply_markup=user_main_menu_kb(user.id, user.is_admin, user.lang))

# --- TOP UP ---
@router.callback_query(F.data == "top_up")
async def top_up_start(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Enter amount in INR you want to deposit (e.g., 100, 500):"); await state.set_state(UserTopUpStates.amount_inr)

@router.message(UserTopUpStates.amount_inr)
async def process_topup_amount(message: Message, state: FSMContext):
    try: inr_amount = float(message.text); usd_amount = inr_amount * 0.01
    except ValueError: return await message.answer("❌ Invalid amount. Please enter a number.")
    upi_id = get_setting("upi_id"); qr_code = get_setting("qr_code")
    if not upi_id: return await message.answer("❌ Admin hasn't set UPI ID yet.")
    await state.update_data(amount_inr=inr_amount, amount_usd=usd_amount)
    text = f"💳 **Payment Details**\n\nAmount: **{inr_amount} INR**\nYou get: **${usd_amount:.2f}**\n\nUPI ID: `{upi_id}`\n\n👉 **Please pay and send the SCREENSHOT or UTR below.**"
    if qr_code: await message.answer_photo(photo=qr_code, caption=text)
    else: await message.answer(text)
    await state.set_state(UserTopUpStates.payment_proof)

@router.message(UserTopUpStates.payment_proof)
async def process_payment_proof(message: Message, state: FSMContext):
    data = await state.get_data()
    screenshot_file_id = message.photo[-1].file_id if message.photo else None
    utr_text = message.caption if message.photo else message.text
    new_req = TopUpRequest(user_id=message.from_user.id, amount_inr=data['amount_inr'], amount_usd=data['amount_usd'], utr=utr_text, screenshot_file_id=screenshot_file_id)
    db.add(new_req); db.commit()
    admin_text = f"🔔 **New Top-Up Request!**\n\nUser ID: `{message.from_user.id}`\nAmount: **{data['amount_inr']} INR** (${data['amount_usd']:.2f})\nUTR/Note: `{utr_text}`"
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Approve", callback_data=f"topup_appr_{new_req.id}", style="success"), InlineKeyboardButton(text="❌ Reject", callback_data=f"topup_rej_{new_req.id}", style="danger")]])
    if screenshot_file_id: await bot.send_photo(ADMIN_ID, photo=screenshot_file_id, caption=admin_text, reply_markup=admin_kb)
    else: await bot.send_message(ADMIN_ID, admin_text, reply_markup=admin_kb)
    await message.answer("✅ Request submitted! Admin will verify and add balance soon."); await state.clear()

# --- WITHDRAW ---
@router.callback_query(F.data == "user_withdraw")
async def withdraw_start(call: CallbackQuery, state: FSMContext):
    user = get_user(call.from_user.id)
    await call.message.answer(f"Your Balance: ${user.balance:.2f}\n\nEnter amount in USD to withdraw (Min $0.50):"); await state.set_state(UserWithdrawStates.amount)

@router.message(UserWithdrawStates.amount)
async def process_withdraw_amount(message: Message, state: FSMContext):
    try:
        amt = float(message.text); user = get_user(message.from_user.id)
        if amt < 0.50 or amt > user.balance: return await message.answer("❌ Invalid amount or insufficient balance (Min $0.50).")
        await state.update_data(amount=amt); await message.answer("Enter your UPI ID:"); await state.set_state(UserWithdrawStates.upi_id)
    except ValueError: await message.answer("❌ Invalid number.")

@router.message(UserWithdrawStates.upi_id)
async def process_withdraw_upi(message: Message, state: FSMContext):
    data = await state.get_data()
    req = WithdrawRequest(user_id=message.from_user.id, amount_usd=data['amount'], upi_id=message.text)
    db.add(req); db.commit()
    await bot.send_message(ADMIN_ID, f"🔔 **Withdraw Request**\nUser: `{message.from_user.id}`\nAmount: ${data['amount']:.2f}\nUPI: `{message.text}`",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Approve", callback_data=f"wd_appr_{req.id}", style="success"), InlineKeyboardButton(text="❌ Reject", callback_data=f"wd_rej_{req.id}", style="danger")]]))
    await message.answer("✅ Withdrawal request sent to admin."); await state.clear()

# --- SELL ACCOUNT ---
@router.callback_query(F.data == "sell_acc")
async def sell_acc_start(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Enter Your Phone Number (with country code, e.g., +919876543210):"); await state.set_state(UserSellStates.sell_phone)

@router.message(UserSellStates.sell_phone)
async def sell_phone(message: Message, state: FSMContext):
    phone = message.text
    try:
        parsed = phonenumbers.parse(phone, None); country = phonenumbers.region_code_for_number(parsed)
        price = PRICE_GUIDE.get(country, 0.20)
    except: return await message.answer("❌ Invalid phone number. Use country code.")
    await state.update_data(phone=phone, price=price, country=country)
    text = f"🌍 Country: {country}\n💰 Our Offer: ${price:.2f}\n\nDo you want to sell?"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Accept", callback_data="confirm_sell_yes", style="success"), InlineKeyboardButton(text="❌ Cancel", callback_data="confirm_sell_no", style="danger")]])
    await message.answer(text, reply_markup=kb); await state.set_state(UserSellStates.confirm_sell)

@router.callback_query(F.data == "confirm_sell_yes")
async def confirm_sell_yes(call: CallbackQuery, state: FSMContext):
    data = await state.get_data(); await call.message.edit_text("⏳ Sending OTP...")
    try:
        client, phone_code_hash = await start_telethon_login(data['phone'], API_ID, API_HASH)
        await state.update_data(client=client, phone_code_hash=phone_code_hash)
        await call.message.answer("Enter OTP:"); await state.set_state(UserSellStates.sell_otp)
    except Exception as e: await call.message.answer(f"❌ Error: {e}"); await state.clear()

@router.callback_query(F.data == "confirm_sell_no")
async def confirm_sell_no(call: CallbackQuery, state: FSMContext): await call.message.edit_text("❌ Selling cancelled."); await state.clear()

@router.message(UserSellStates.sell_otp)
async def sell_otp(message: Message, state: FSMContext):
    data = await state.get_data(); client = data['client']
    try:
        session = await verify_telethon_otp(client, data['phone'], message.text, data['phone_code_hash'])
        await setup_new_2fa_and_save(client, data, message, session)
    except errors.SessionPasswordNeededError:
        await message.answer("🔐 2FA Detected. Enter current 2FA Password:"); await state.set_state(UserSellStates.sell_2fa)
    except Exception as e: await message.answer(f"❌ Invalid OTP: {e}")

@router.message(UserSellStates.sell_2fa)
async def sell_2fa(message: Message, state: FSMContext):
    data = await state.get_data(); client = data['client']
    try:
        await client.sign_in(password=message.text); session = client.session.save()
        await setup_new_2fa_and_save(client, data, message, session)
    except Exception as e: await message.answer(f"❌ Wrong 2FA: {e}")

async def setup_new_2fa_and_save(client, data, message, session):
    new_2fa = str(random.randint(100000, 999999))
    try: await client.edit_2fa(new_password=new_2fa)
    except: pass
    req = SellRequest(user_id=message.from_user.id, phone=data['phone'], session_string=session, price_usd=data['price'])
    db.add(req); db.commit()
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Approve", callback_data=f"sell_appr_{req.id}", style="success"), InlineKeyboardButton(text="❌ Reject", callback_data=f"sell_rej_{req.id}", style="danger")]])
    await bot.send_message(ADMIN_ID, f"🔔 **Sell Request**\nUser: `{message.from_user.id}`\nPhone: `{data['phone']}`\nPrice: ${data['price']:.2f}\nNew 2FA: `{new_2fa}`", reply_markup=admin_kb)
    await message.answer(f"✅ Verified! 2FA set to `{new_2fa}`.\n\n👉 **Please LOGOUT from your Telegram app now.** Wait for admin approval.")
    await state.clear(); await client.disconnect()

# --- BUY ACCOUNT ---
@router.callback_query(F.data == "buy_acc")
async def buy_acc_menu(call: CallbackQuery):
    products = db.query(Product).all()
    if not products: return await call.message.answer("❌ No products available.")
    kb = [[InlineKeyboardButton(text=f"{p.name} - ${p.price_usd:.2f}", callback_data=f"view_prod_{p.id}", style="primary")] for p in products]
    await call.message.answer("🛒 Select a product:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("view_prod_"))
async def view_product(call: CallbackQuery):
    prod_id = int(call.data.split("_")[2]); product = db.query(Product).filter(Product.id == prod_id).first()
    if not product: return await call.answer("❌ Product not found.", show_alert=True)
    text = (f"📦 **{product.name}**\n\n🌍 Country: {product.country}\n💵 Price: ${product.price_usd:.2f}\n\n📝 **Description:**\n{product.description or 'No description provided.'}")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Confirm Buy", callback_data=f"confirm_buy_{prod_id}", style="success"), InlineKeyboardButton(text="❌ Cancel", callback_data="buy_acc", style="danger")], [InlineKeyboardButton(text="⭐ Add to Wishlist", callback_data=f"wishlist_add_{prod_id}", style="primary")]])
    await call.message.edit_text(text, reply_markup=kb)

@router.callback_query(F.data.startswith("confirm_buy_"))
async def confirm_buy(call: CallbackQuery):
    prod_id = int(call.data.split("_")[2]); product = db.query(Product).filter(Product.id == prod_id).first()
    user = get_user(call.from_user.id)
    if user.balance < product.price_usd: return await call.answer(f"❌ Insufficient balance! Need ${product.price_usd:.2f}", show_alert=True)
    stock = db.query(StockAccount).filter(StockAccount.product_id == prod_id, StockAccount.status == "Available").order_by(func.random()).first()
    if not stock: return await call.message.answer("😔 Out of stock.")
    user.balance -= product.price_usd; stock.status = "Sold"; db.commit()
    log_transaction(user.id, "Buy Account", -product.price_usd)
    text = f"🎉 **Purchase Successful!**\n\nProduct: {product.name}\nPhone: `{stock.phone}`\n\nLogin with this number, and click Get OTP when needed."
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📩 Get OTP", callback_data=f"get_otp_{stock.id}", style="primary")]])
    await call.message.edit_text(text, reply_markup=kb)
    rating_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="1 ⭐", callback_data=f"rate_1_{product.id}", style="danger"), InlineKeyboardButton(text="2 ⭐", callback_data=f"rate_2_{product.id}", style="danger")], [InlineKeyboardButton(text="3 ⭐", callback_data=f"rate_3_{product.id}", style="primary"), InlineKeyboardButton(text="4 ⭐", callback_data=f"rate_4_{product.id}", style="success")], [InlineKeyboardButton(text="5 ⭐", callback_data=f"rate_5_{product.id}", style="success")]])
    await bot.send_message(call.from_user.id, f"⭐ **Apna experience rate karein!**\n\nAapne `{product.name}` kharida. Kripya 1 se 5 star dein:", reply_markup=rating_kb)

@router.callback_query(F.data.startswith("rate_"))
async def save_rating(call: CallbackQuery):
    parts = call.data.split("_"); score = int(parts[1]); prod_id = int(parts[2])
    db.add(Rating(user_id=call.from_user.id, product_id=prod_id, score=score)); db.commit()
    await call.message.edit_text(f"✅ Shukriya! Aapne {score} ⭐ diya.")
    if score <= 2:
        product = db.query(Product).filter(Product.id == prod_id).first()
        await bot.send_message(ADMIN_ID, f"⚠️ **LOW RATING ALERT!**\n\n👤 User: `{call.from_user.id}`\n📦 Product: {product.name if product else 'Unknown'}\n⭐ Rating: {score} Star")

@router.callback_query(F.data.startswith("get_otp_"))
async def fetch_otp(call: CallbackQuery):
    stock_id = int(call.data.split("_")[2]); stock = db.query(StockAccount).filter(StockAccount.id == stock_id).first()
    await call.message.answer("⏳ Checking OTP from TG-Shark API...")
    otp = await fetch_otp_from_tgshark(stock.phone)
    if otp:
        resp = f"🔑 **OTP:** `{otp}`\n"
        if stock.password_2fa: resp += f"🔐 **2FA Password:** `{stock.password_2fa}`"
        await call.message.answer(resp)
    else: await call.message.answer("❌ OTP abhi tak nahi aaya. 10 second wait karke dobara try karein.")

@router.callback_query(F.data == "user_history")
async def user_history(call: CallbackQuery):
    txs = db.query(Transaction).filter(Transaction.user_id == call.from_user.id).order_by(Transaction.date.desc()).limit(10).all()
    if not txs: return await call.message.answer("📜 No transactions yet.")
    text = "📜 **Last 10 Transactions**\n\n"
    for t in txs: text += f"`{t.date.strftime('%m-%d %H:%M')}` | {t.type} | ${t.amount:.2f} | {t.status}\n"
    await call.message.answer(text)

@router.callback_query(F.data == "user_support")
async def support_start(call: CallbackQuery, state: FSMContext):
    await call.message.answer("📩 **Support Ticket**\n\nApni problem ya query likh kar bhejein. Admin jald hi reply karega:"); await state.set_state(UserSupportStates.waiting_message)

@router.message(UserSupportStates.waiting_message)
async def support_send(message: Message, state: FSMContext):
    await state.clear(); ticket_id = random.randint(1000, 9999)
    admin_text = f"🎫 **New Support Ticket #{ticket_id}**\n\n👤 User: {message.from_user.first_name} (`{message.from_user.id}`)\n📝 Message: {message.text}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💬 Reply", callback_data=f"reply_ticket_{message.from_user.id}", style="primary")]])
    await bot.send_message(ADMIN_ID, admin_text, reply_markup=kb)
    await message.answer(f"✅ Ticket #{ticket_id} submit ho gaya! Admin jald reply karega.")

@router.callback_query(F.data.startswith("reply_ticket_"))
async def admin_reply_ticket(call: CallbackQuery, state: FSMContext):
    await state.update_data(reply_to=int(call.data.split("_")[2]))
    await call.message.answer("✍️ User ko reply likhein:"); await state.set_state(AdminStates.reply_ticket)

@router.message(AdminStates.reply_ticket)
async def send_ticket_reply(message: Message, state: FSMContext):
    data = await state.get_data()
    try:
        await bot.send_message(data['reply_to'], f"📩 **Support Reply:**\n\n{message.text}"); await message.answer("✅ Reply bhej diya gaya!")
    except Exception as e: await message.answer(f"❌ Error: {e}")
    await state.clear()

@router.callback_query(F.data.startswith("wishlist_add_"))
async def add_to_wishlist(call: CallbackQuery):
    prod_id = call.data.split("_")[2]; user = get_user(call.from_user.id)
    wl = user.wishlist.split(",") if user.wishlist else []
    if prod_id not in wl:
        wl.append(prod_id); user.wishlist = ",".join(wl); db.commit(); await call.answer("⭐ Wishlist me add ho gaya!", show_alert=True)
    else: await call.answer("Pehle se wishlist me hai!", show_alert=True)

@router.callback_query(F.data == "user_wishlist")
async def show_wishlist(call: CallbackQuery):
    user = get_user(call.from_user.id)
    if not user.wishlist: return await call.message.answer("⭐ Aapki wishlist khaali hai.")
    text = "⭐ **Aapki Wishlist**\n\n"
    for pid in user.wishlist.split(","):
        p = db.query(Product).filter(Product.id == int(pid)).first()
        if p: text += f"📦 {p.name} - ${p.price_usd:.2f}\n"
    await call.message.answer(text)

# ═══════════════ ADMIN HANDLERS ═══════════════
@router.callback_query(F.data == "admin_back")
async def admin_back(call: CallbackQuery): await call.message.edit_text("🩸 **Bloodline Admin Panel** 🩸", reply_markup=admin_panel_kb())

@router.callback_query(F.data == "admin_stats")
async def admin_stats(call: CallbackQuery):
    total_users = db.query(User).count(); total_balance = db.query(func.sum(User.balance)).scalar() or 0.0
    total_sold = db.query(StockAccount).filter(StockAccount.status == "Sold").count()
    pending_sells = db.query(SellRequest).filter(SellRequest.status == "Pending").count()
    pending_topups = db.query(TopUpRequest).filter(TopUpRequest.status == "Pending").count()
    pending_wd = db.query(WithdrawRequest).filter(WithdrawRequest.status == "Pending").count()
    text = (f"📊 **Bot Statistics**\n\n👥 Users: `{total_users}`\n💰 Balance in System: `${total_balance:.2f}`\n📦 Accounts Sold: `{total_sold}`\n⏳ Pending Sells: `{pending_sells}`\n⏳ Pending Top-ups: `{pending_topups}`\n⏳ Pending Withdrawals: `{pending_wd}`")
    await call.message.answer(text)

# --- FORCE JOIN MANAGEMENT ---
@router.callback_query(F.data == "admin_force_join")
async def admin_force_join(call: CallbackQuery):
    channels = db.query(ForceJoinChannel).all()
    text = f"📢 **Force Join Channels ({len(channels)}/4)**\n\n"
    kb = []
    if not channels: text += "Koi channel add nahi hai.\n"
    for ch in channels:
        text += f"• @{ch.username} — [Link]({ch.link})\n"
        kb.append([InlineKeyboardButton(text=f"🗑️ Delete @{ch.username}", callback_data=f"del_fj_{ch.id}", style="danger")])
    if len(channels) < 4:
        kb.append([InlineKeyboardButton(text="➕ Add Channel", callback_data="add_fj", style="success")])
    kb.append([InlineKeyboardButton(text="🔙 Back", callback_data="admin_panel", style="danger")])
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "add_fj")
async def add_fj_start(call: CallbackQuery, state: FSMContext):
    channels = db.query(ForceJoinChannel).all()
    if len(channels) >= 4: return await call.answer("❌ Max 4 channels allowed!", show_alert=True)
    await call.message.answer("Enter Channel Username (without @, e.g., BloodlineOfficial):"); await state.set_state(AdminStates.fj_username)

@router.message(AdminStates.fj_username)
async def add_fj_username(message: Message, state: FSMContext):
    await state.update_data(fj_username=message.text.replace("@", ""))
    await message.answer("Enter Channel Link (e.g., https://t.me/BloodlineOfficial):"); await state.set_state(AdminStates.fj_link)

@router.message(AdminStates.fj_link)
async def add_fj_link(message: Message, state: FSMContext):
    data = await state.get_data()
    db.add(ForceJoinChannel(username=data['fj_username'], link=message.text)); db.commit()
    await message.answer("✅ Channel added to Force Join!"); await state.clear()

@router.callback_query(F.data.startswith("del_fj_"))
async def del_fj(call: CallbackQuery):
    fj_id = int(call.data.split("_")[2])
    db.query(ForceJoinChannel).filter(ForceJoinChannel.id == fj_id).delete(); db.commit()
    await call.answer("🗑️ Channel deleted!", show_alert=True)
    await admin_force_join(call)

# --- ADD PRODUCT ---
@router.callback_query(F.data == "admin_add_prod")
async def add_prod_start(call: CallbackQuery, state: FSMContext): await call.message.answer("Enter Product Name:"); await state.set_state(AdminStates.add_prod_name)

@router.message(AdminStates.add_prod_name)
async def add_prod_name(message: Message, state: FSMContext):
    await state.update_data(prod_name=message.text); await message.answer("Enter Product Description:"); await state.set_state(AdminStates.add_prod_desc)

@router.message(AdminStates.add_prod_desc)
async def add_prod_desc(message: Message, state: FSMContext):
    await state.update_data(prod_desc=message.text); await message.answer("Enter Price in INR (e.g., 30 for $0.30):"); await state.set_state(AdminStates.add_prod_price)

@router.message(AdminStates.add_prod_price)
async def add_prod_price(message: Message, state: FSMContext):
    try: price_usd = float(message.text) * 0.01
    except: return await message.answer("❌ Invalid price.")
    await state.update_data(price_usd=price_usd); await message.answer("Enter Country Name:"); await state.set_state(AdminStates.add_prod_country)

@router.message(AdminStates.add_prod_country)
async def add_prod_country(message: Message, state: FSMContext):
    data = await state.get_data()
    db.add(Product(name=data['prod_name'], country=message.text, price_usd=data['price_usd'], description=data.get('prod_desc')))
    db.commit(); await message.answer("✅ Product added!"); await state.clear()

# --- ADD STOCK ---
@router.callback_query(F.data == "admin_add_stock")
async def add_stock_start(call: CallbackQuery):
    prods = db.query(Product).all()
    if not prods: return await call.message.answer("❌ Add a product first.")
    kb = [[InlineKeyboardButton(text=f"{p.name}", callback_data=f"stock_prod_{p.id}", style="primary")] for p in prods]
    await call.message.answer("Select Product:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("stock_prod_"))
async def add_stock_phone(call: CallbackQuery, state: FSMContext):
    await state.update_data(product_id=int(call.data.split("_")[2])); await call.message.answer("Enter Phone Number:"); await state.set_state(AdminStates.add_stock_phone)

@router.message(AdminStates.add_stock_phone)
async def add_stock_send_otp(message: Message, state: FSMContext):
    phone = message.text; await state.update_data(phone=phone); await message.answer("⏳ Sending OTP...")
    try:
        client, phone_code_hash = await start_telethon_login(phone, API_ID, API_HASH)
        await state.update_data(client=client, phone_code_hash=phone_code_hash); await message.answer("Enter OTP:"); await state.set_state(AdminStates.add_stock_otp)
    except Exception as e: await message.answer(f"❌ Error: {e}"); await state.clear()

@router.message(AdminStates.add_stock_otp)
async def add_stock_verify_otp(message: Message, state: FSMContext):
    data = await state.get_data()
    try:
        session = await verify_telethon_otp(data['client'], data['phone'], message.text, data['phone_code_hash'])
        db.add(StockAccount(product_id=data['product_id'], phone=data['phone'], session_string=session)); db.commit()
        await message.answer("✅ Stock added!"); await state.clear(); await data['client'].disconnect()
    except errors.SessionPasswordNeededError: await message.answer("🔐 Enter 2FA Password:"); await state.set_state(AdminStates.add_stock_2fa)
    except Exception as e: await message.answer(f"❌ Error: {e}")

@router.message(AdminStates.add_stock_2fa)
async def add_stock_verify_2fa(message: Message, state: FSMContext):
    data = await state.get_data()
    try:
        session = await verify_telethon_2fa(data['client'], message.text)
        db.add(StockAccount(product_id=data['product_id'], phone=data['phone'], session_string=session, password_2fa=message.text)); db.commit()
        await message.answer("✅ Stock with 2FA added!"); await state.clear(); await data['client'].disconnect()
    except Exception as e: await message.answer(f"❌ Error: {e}")

# --- BULK STOCK UPLOAD ---
@router.callback_query(F.data == "admin_bulk_stock")
async def bulk_stock_start(call: CallbackQuery, state: FSMContext):
    await call.message.answer("📁 **Bulk Stock Upload**\n\nEk `.txt` file bhejein jisme har line par ye format ho:\n`phone,session_string,2fa_password`")
    await state.set_state(AdminStates.bulk_upload)

@router.message(AdminStates.bulk_upload, F.document)
async def process_bulk_upload(message: Message, state: FSMContext):
    if not message.document.file_name.endswith(".txt"): return await message.answer("❌ Sirf .txt file allowed hai!")
    file = await bot.get_file(message.document.file_id); downloaded = await bot.download_file(file.file_path)
    content = downloaded.read().decode("utf-8"); added = 0; failed = 0
    for line in content.strip().split("\n"):
        parts = line.split(",")
        if len(parts) >= 2:
            phone = parts[0].strip(); session = parts[1].strip(); two_fa = parts[2].strip() if len(parts) > 2 else None
            db.add(StockAccount(product_id=1, phone=phone, session_string=session, password_2fa=two_fa)); added += 1
        else: failed += 1
    db.commit(); await message.answer(f"✅ **Bulk Upload Complete!**\n\n➕ Added: {added}\n❌ Failed: {failed}"); await state.clear()

# --- MANAGE PRODUCTS ---
@router.callback_query(F.data == "admin_manage_prod")
async def manage_prod_list(call: CallbackQuery):
    prods = db.query(Product).all()
    if not prods: return await call.message.answer("❌ No products.")
    kb = [[InlineKeyboardButton(text=f"{p.name} (${p.price_usd:.2f})", callback_data=f"mng_prod_{p.id}", style="primary")] for p in prods]
    kb.append([InlineKeyboardButton(text="🔙 Back", callback_data="admin_back", style="danger")])
    await call.message.answer("Manage Products:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("mng_prod_"))
async def manage_prod_options(call: CallbackQuery):
    pid = int(call.data.split("_")[2])
    kb = [[InlineKeyboardButton(text="✏️ Name", callback_data=f"edit_pname_{pid}", style="primary"), InlineKeyboardButton(text="💵 Price", callback_data=f"edit_pprice_{pid}", style="primary")],
          [InlineKeyboardButton(text="🌍 Country", callback_data=f"edit_pcountry_{pid}", style="primary"), InlineKeyboardButton(text="📝 Description", callback_data=f"edit_pdesc_{pid}", style="primary")],
          [InlineKeyboardButton(text="🗑️ Delete", callback_data=f"del_prod_{pid}", style="danger")],
          [InlineKeyboardButton(text="🔙 Back", callback_data="admin_manage_prod", style="danger")]]
    await call.message.edit_text(f"Managing Product ID: `{pid}`", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("edit_pdesc_"))
async def edit_pdesc(call: CallbackQuery, state: FSMContext):
    await state.update_data(prod_id=int(call.data.split("_")[2])); await call.message.answer("Enter new Description:"); await state.set_state(AdminStates.edit_desc)

@router.message(AdminStates.edit_desc)
async def save_pdesc(message: Message, state: FSMContext):
    data = await state.get_data(); prod = db.query(Product).filter(Product.id == data['prod_id']).first()
    prod.description = message.text; db.commit(); await message.answer("✅ Description Updated!"); await state.clear()

@router.callback_query(F.data.startswith("del_prod_"))
async def del_prod(call: CallbackQuery):
    pid = int(call.data.split("_")[2])
    db.query(StockAccount).filter(StockAccount.product_id == pid).delete(); db.query(Product).filter(Product.id == pid).delete(); db.commit()
    await call.message.answer("🗑️ Deleted!")

# --- MANAGE STOCK ---
@router.callback_query(F.data == "admin_manage_stock")
async def manage_stock_list(call: CallbackQuery):
    prods = db.query(Product).all(); kb = []
    for p in prods:
        cnt = db.query(StockAccount).filter(StockAccount.product_id == p.id, StockAccount.status == "Available").count()
        kb.append([InlineKeyboardButton(text=f"{p.name} ({cnt} in stock)", callback_data=f"mng_stock_{p.id}", style="primary")])
    kb.append([InlineKeyboardButton(text="🔙 Back", callback_data="admin_back", style="danger")])
    await call.message.answer("Select product to view stock:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("mng_stock_"))
async def view_stock(call: CallbackQuery):
    pid = int(call.data.split("_")[2])
    stocks = db.query(StockAccount).filter(StockAccount.product_id == pid, StockAccount.status == "Available").limit(10).all()
    if not stocks: return await call.message.answer("❌ No stock.")
    kb = [[InlineKeyboardButton(text=f"🗑️ {s.phone}", callback_data=f"del_stock_{s.id}", style="danger")] for s in stocks]
    kb.append([InlineKeyboardButton(text="🔙 Back", callback_data="admin_manage_stock", style="danger")])
    await call.message.answer("Click to delete:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("del_stock_"))
async def del_stock(call: CallbackQuery):
    db.query(StockAccount).filter(StockAccount.id == int(call.data.split("_")[2])).delete(); db.commit(); await call.message.answer("🗑️ Stock deleted!")


# --- MANAGE USERS ---
@router.callback_query(F.data == "admin_manage_users")
async def manage_users_start(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Enter User's Telegram ID:"); await state.set_state(AdminStates.target_user)

@router.message(AdminStates.target_user)
async def show_user_profile(message: Message, state: FSMContext):
    try: uid = int(message.text)
    except: return await message.answer("❌ Invalid ID.")
    user = get_user(uid); await state.update_data(target_uid=uid)
    text = f"👤 **User Profile**\nID: `{user.id}`\nBalance: `${user.balance:.2f}`\nBanned: `{user.is_banned}`"
    kb = [[InlineKeyboardButton(text="➕ Add Balance", callback_data="usr_add_bal", style="success"), InlineKeyboardButton(text="➖ Deduct Balance", callback_data="usr_ded_bal", style="danger")],
          [InlineKeyboardButton(text="🚫 Ban", callback_data="usr_ban", style="danger"), InlineKeyboardButton(text="✅ Unban", callback_data="usr_unban", style="success")],
          [InlineKeyboardButton(text="🔙 Back", callback_data="admin_back", style="danger")]]
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "usr_ban")
async def ban_user(call: CallbackQuery, state: FSMContext):
    data = await state.get_data(); user = get_user(data['target_uid']); user.is_banned = True; db.commit()
    await call.message.answer("🚫 User Banned!"); await bot.send_message(user.id, "🚫 You have been banned.")

@router.callback_query(F.data == "usr_unban")
async def unban_user(call: CallbackQuery, state: FSMContext):
    data = await state.get_data(); user = get_user(data['target_uid']); user.is_banned = False; db.commit()
    await call.message.answer("✅ User Unbanned!"); await bot.send_message(user.id, "✅ You have been unbanned.")

@router.callback_query(F.data == "usr_add_bal")
async def add_bal_start(call: CallbackQuery, state: FSMContext): await call.message.answer("Enter amount in USD to ADD:"); await state.set_state(AdminStates.add_balance)

@router.message(AdminStates.add_balance)
async def save_add_bal(message: Message, state: FSMContext):
    data = await state.get_data(); user = get_user(data['target_uid'])
    try:
        amt = float(message.text); user.balance += amt; db.commit(); log_transaction(user.id, "Admin Add", amt)
        await message.answer(f"✅ Added ${amt:.2f}."); await bot.send_message(user.id, f"🎁 Admin added ${amt:.2f} to your balance!")
    except: await message.answer("❌ Invalid amount.")
    await state.clear()

@router.callback_query(F.data == "usr_ded_bal")
async def ded_bal_start(call: CallbackQuery, state: FSMContext): await call.message.answer("Enter amount in USD to DEDUCT:"); await state.set_state(AdminStates.deduct_balance)

@router.message(AdminStates.deduct_balance)
async def save_ded_bal(message: Message, state: FSMContext):
    data = await state.get_data(); user = get_user(data['target_uid'])
    try:
        amt = float(message.text); user.balance -= amt
        if user.balance < 0: user.balance = 0.0
        db.commit(); log_transaction(user.id, "Admin Deduct", -amt); await message.answer(f"✅ Deducted ${amt:.2f}.")
    except: await message.answer("❌ Invalid amount.")
    await state.clear()

@router.callback_query(F.data.startswith("sell_appr_"))
async def approve_sell(call: CallbackQuery):
    req = db.query(SellRequest).filter(SellRequest.id == int(call.data.split("_")[2])).first()
    if req and req.status == "Pending":
        req.status = "Approved"; user = get_user(req.user_id); user.balance += req.price_usd; db.commit()
        log_transaction(user.id, "Sell Account", req.price_usd)
        db.add(StockAccount(product_id=1, phone=req.phone, session_string=req.session_string, status="Available")); db.commit()
        await call.message.edit_text("✅ Approved & Added to Stock."); await bot.send_message(req.user_id, f"🎉 Account approved! ${req.price_usd:.2f} added to balance.")

@router.callback_query(F.data.startswith("sell_rej_"))
async def reject_sell(call: CallbackQuery):
    req = db.query(SellRequest).filter(SellRequest.id == int(call.data.split("_")[2])).first()
    if req: req.status = "Rejected"; db.commit(); await call.message.edit_text("❌ Rejected."); await bot.send_message(req.user_id, "😔 Your account was rejected.")

@router.callback_query(F.data.startswith("topup_appr_"))
async def approve_topup(call: CallbackQuery):
    req = db.query(TopUpRequest).filter(TopUpRequest.id == int(call.data.split("_")[2])).first()
    if req and req.status == "Pending":
        req.status = "Approved"; user = get_user(req.user_id); user.balance += req.amount_usd; db.commit()
        log_transaction(user.id, "TopUp", req.amount_usd)
        await call.message.edit_text(f"✅ Approved! Added ${req.amount_usd:.2f}."); await bot.send_message(req.user_id, f"🎉 Top-up approved! ${req.amount_usd:.2f} added.")

@router.callback_query(F.data.startswith("topup_rej_"))
async def reject_topup(call: CallbackQuery):
    req = db.query(TopUpRequest).filter(TopUpRequest.id == int(call.data.split("_")[2])).first()
    if req: req.status = "Rejected"; db.commit(); await call.message.edit_text("❌ Rejected."); await bot.send_message(req.user_id, "😔 Top-up rejected.")

@router.callback_query(F.data.startswith("wd_appr_"))
async def approve_wd(call: CallbackQuery):
    req = db.query(WithdrawRequest).filter(WithdrawRequest.id == int(call.data.split("_")[2])).first()
    if req and req.status == "Pending":
        req.status = "Approved"; user = get_user(req.user_id); user.balance -= req.amount_usd; db.commit()
        log_transaction(user.id, "Withdraw", -req.amount_usd); await call.message.edit_text("✅ Withdrawal Approved.")
        await bot.send_message(req.user_id, f"✅ Withdrawal of ${req.amount_usd:.2f} approved! Admin will pay to your UPI soon.")

@router.callback_query(F.data == "admin_set_upi")
async def set_upi_start(call: CallbackQuery, state: FSMContext):
    await call.message.answer(f"Current UPI: `{get_setting('upi_id') or 'Not set'}`\nEnter new UPI ID:"); await state.set_state(AdminStates.set_upi_id)

@router.message(AdminStates.set_upi_id)
async def save_upi(message: Message, state: FSMContext): set_setting("upi_id", message.text); await message.answer("✅ UPI ID Updated!"); await state.clear()

@router.callback_query(F.data == "admin_set_qr")
async def set_qr_start(call: CallbackQuery, state: FSMContext): await call.message.answer("Send the QR Code Image:"); await state.set_state(AdminStates.set_qr_code)

@router.message(AdminStates.set_qr_code, F.photo)
async def save_qr(message: Message, state: FSMContext): set_setting("qr_code", message.photo[-1].file_id); await message.answer("✅ QR Code Updated!"); await state.clear()

@router.callback_query(F.data == "admin_sold_accs")
async def list_sold_accounts(call: CallbackQuery):
    accs = db.query(StockAccount).filter(StockAccount.status == "Sold").limit(10).all()
    if not accs: return await call.message.answer("❌ No sold accounts.")
    kb = [[InlineKeyboardButton(text=f"📱 {a.phone}", callback_data=f"admin_otp_{a.id}", style="primary")] for a in accs]
    kb.append([InlineKeyboardButton(text="🔙 Back", callback_data="admin_back", style="danger")])
    await call.message.answer("Select number to fetch OTP:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("admin_otp_"))
async def admin_fetch_otp(call: CallbackQuery):
    acc = db.query(StockAccount).filter(StockAccount.id == int(call.data.split("_")[2])).first()
    await call.message.answer(f"⏳ Fetching OTP for `{acc.phone}`..."); otp = await fetch_otp_from_tgshark(acc.phone)
    if otp:
        resp = f"✅ **OTP:** `{otp}`\n"
        if acc.password_2fa: resp += f"🔐 **2FA:** `{acc.password_2fa}`"
        await call.message.answer(resp)
    else: await call.message.answer("❌ No OTP found. Wait a bit and try again.")

@router.callback_query(F.data == "admin_add_admin")
async def add_admin_start(call: CallbackQuery, state: FSMContext): await call.message.answer("Enter Telegram ID to make Admin:"); await state.set_state(AdminStates.add_admin_id)

@router.message(AdminStates.add_admin_id)
async def save_admin(message: Message, state: FSMContext):
    try:
        uid = int(message.text); user = get_user(uid); user.is_admin = True; db.commit(); await message.answer(f"✅ User `{uid}` is now Admin!")
    except: await message.answer("❌ Invalid ID.")
    await state.clear()

@router.callback_query(F.data == "admin_contest")
async def contest_menu(call: CallbackQuery):
    user = get_user(call.from_user.id)
    if user.id != ADMIN_ID and not user.is_admin: return
    contest_start = get_setting("contest_start_time"); status = "🟢 ACTIVE" if contest_start else "🔴 INACTIVE"
    text = f"🏆 **Referral Contest**\n\nStatus: {status}\n\n1. **Start Contest:** Isse contest start hoga.\n2. **Leaderboard:** Top referrers ki list dekhein.\n3. **End Contest:** Contest end karein aur winner nikaalein."
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="▶️ Start Contest", callback_data="contest_start", style="success")], [InlineKeyboardButton(text="📊 Leaderboard", callback_data="contest_leaderboard", style="primary")], [InlineKeyboardButton(text="⏹️ End Contest", callback_data="contest_end", style="danger")], [InlineKeyboardButton(text="🔙 Back", callback_data="admin_panel", style="danger")]])
    await call.message.edit_text(text, reply_markup=kb)

@router.callback_query(F.data == "contest_start")
async def start_contest(call: CallbackQuery): set_setting("contest_start_time", datetime.utcnow().isoformat()); await call.answer("✅ Contest Start ho gaya!", show_alert=True)

@router.callback_query(F.data == "contest_end")
async def end_contest(call: CallbackQuery):
    start_time_str = get_setting("contest_start_time")
    if not start_time_str: return await call.answer("❌ Koi active contest nahi hai!", show_alert=True)
    start_time = datetime.fromisoformat(start_time_str)
    top_referrers = db.query(User.referrer_id, func.count(User.id).label('count')).filter(User.joined_at >= start_time, User.referrer_id.isnot(None)).group_by(User.referrer_id).order_by(func.count(User.id).desc()).limit(5).all()
    set_setting("contest_start_time", "")
    if not top_referrers: return await call.message.edit_text("🏆 **Contest Ended!**\n\nKisi ne bhi refer nahi kiya.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data="admin_contest", style="danger")]]))
    text = "🏆 **Contest Winners (Top 5)** 🏆\n\n"
    for i, (uid, count) in enumerate(top_referrers, 1):
        user_obj = get_user(uid); text += f"{i}. 👤 `{uid}` — **{count} Referrals** (Balance: ${user_obj.balance:.2f})\n"
    text += "\n🎁 **Ab aap manually winner ko prize de sakte hain (Balance Add karke).**"
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data="admin_contest", style="danger")]]))

@router.callback_query(F.data == "contest_leaderboard")
async def contest_leaderboard(call: CallbackQuery):
    start_time_str = get_setting("contest_start_time")
    if start_time_str: start_time = datetime.fromisoformat(start_time_str); title = "📊 **Live Contest Leaderboard**\n\n"
    else: start_time = datetime.min; title = "📊 **All-Time Leaderboard**\n\n"
    top_referrers = db.query(User.referrer_id, func.count(User.id).label('count')).filter(User.joined_at >= start_time, User.referrer_id.isnot(None)).group_by(User.referrer_id).order_by(func.count(User.id).desc()).limit(10).all()
    if not top_referrers: return await call.message.edit_text("📊 Koi data nahi hai.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data="admin_contest", style="danger")]]))
    for i, (uid, count) in enumerate(top_referrers, 1): title += f"{i}. 👤 `{uid}` — **{count} Referrals**\n"
    await call.message.edit_text(title, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data="admin_contest", style="danger")]]))

# ═══════════════ MAIN ═══════════════
async def main():
    logging.basicConfig(level=logging.INFO)
    print("🩸 Bloodline TG Account Store is starting...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
