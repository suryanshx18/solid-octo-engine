from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from sqlalchemy import select

from database import (
    async_session_maker,
    User,
    Admin,
    Category,
    Account,
    DepositRequest,
    RequiredChannel,
    Coupon,
    LogEntry,
    Purchase,
    Transaction,
)

from keyboards import (
    main_menu_keyboard,
    categories_keyboard,
    accounts_keyboard,
    force_join_keyboard,
    admin_panel_keyboard,
    approve_deposit_keyboard,
    back_home_keyboard,
    deposit_amount_keyboard,
)

from services import (
    get_required_channels,
    check_force_join,
    grant_referral_reward,
    apply_coupon,
    reserve_and_buy_account,
    complete_purchase,
    fail_purchase,
    expire_pending_deposits,
    log_event,
    send_log_message,
    add_balance,
    remove_balance,
    get_setting,
    set_setting,
    get_user_role,
)

from config import (
    OWNER_ID,
    MAINTENANCE_MODE,
    LOG_CHANNEL_ID,
    SUPPORT_USERNAME,
)


router = Router()


# =========================================================
# STATES
# =========================================================

class DepositState(StatesGroup):
    amount = State()
    utr = State()


class BroadcastState(StatesGroup):
    text = State()


# =========================================================
# HELPERS
# =========================================================

async def check_maintenance(message: Message) -> bool:
    if not MAINTENANCE_MODE:
        return False

    async with async_session_maker() as session:
        role = await get_user_role(
            session,
            message.from_user.id,
        )

    if role not in ("superadmin", "owner"):
        await message.answer(
            "🛠 Bot is currently in maintenance mode.\n"
            "Please try again later."
        )
        return True

    return False


async def get_or_create_user(message: Message):
    async with async_session_maker() as session:
        user = await session.scalar(
            select(User).where(
                User.tg_id == message.from_user.id
            )
        )

        if not user:
            user = User(
                tg_id=message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name,
            )

            session.add(user)
            await session.commit()

        return user


async def is_staff(session, tg_id: int) -> bool:
    role = await get_user_role(session, tg_id)
    return role in ("admin", "superadmin", "owner")


async def is_superadmin(session, tg_id: int) -> bool:
    role = await get_user_role(session, tg_id)
    return role in ("superadmin", "owner")


# =========================================================
# START
# =========================================================

@router.message(Command("start"))
async def cmd_start(message: Message):
    if await check_maintenance(message):
        return

    args = message.text.split(maxsplit=1)
    ref_code = args[1].strip() if len(args) > 1 else None

    async with async_session_maker() as session:

        user = await session.scalar(
            select(User).where(
                User.tg_id == message.from_user.id
            )
        )

        is_new = False

        if not user:
            referred_by = None

            if ref_code and ref_code.isdigit():
                ref_id = int(ref_code)

                if ref_id != message.from_user.id:
                    referred_by = ref_id

            user = User(
                tg_id=message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name,
                referred_by=referred_by,
            )

            session.add(user)
            await session.flush()

            is_new = True

            await log_event(
                session,
                "user_registered",
                user.tg_id,
                details="New user",
            )

            await session.commit()

            await send_log_message(
                message.bot,
                f"👤 New user registered: {user.tg_id}",
            )

        else:
            user.username = message.from_user.username
            user.first_name = message.from_user.first_name
            user.last_name = message.from_user.last_name

        # Check banned user
        if user.is_banned:
            await message.answer(
                "🚫 You are banned from using this bot."
            )
            return

        channels = await get_required_channels(session)

        if channels:
            joined, missing = await check_force_join(
                message.bot,
                message.from_user.id,
                channels,
            )

            if not joined:
                kb = force_join_keyboard(missing)

                await message.answer(
                    "👋 Welcome!\n\n"
                    "Please join all required channels "
                    "and then press Verify.",
                    reply_markup=kb,
                )
                return

        if user.referred_by and not user.referral_rewarded:
            await grant_referral_reward(
                session,
                user,
            )
            await session.commit()

        await message.answer(
            "🏠 Welcome to the bot!\n\n"
            "Use the menu below.",
            reply_markup=main_menu_keyboard(),
        )

        await log_event(
            session,
            "user_started",
            user.tg_id,
        )

        await session.commit()


# =========================================================
# FORCE JOIN
# =========================================================

@router.callback_query(F.data == "force_verify")
async def cb_force_verify(callback: CallbackQuery):

    async with async_session_maker() as session:

        user = await session.scalar(
            select(User).where(
                User.tg_id == callback.from_user.id
            )
        )

        if not user:
            await callback.answer(
                "User not found.",
                show_alert=True,
            )
            return

        channels = await get_required_channels(session)

        if not channels:
            await callback.answer("Verified!")

            await callback.message.edit_text(
                "✅ Verification successful!\n\n"
                "Use the menu below.",
                reply_markup=main_menu_keyboard(),
            )
            return

        joined, missing = await check_force_join(
            callback.bot,
            callback.from_user.id,
            channels,
        )

        if not joined:
            await callback.answer(
                "Please join all channels first.",
                show_alert=True,
            )

            await callback.message.edit_text(
                "❌ You haven't joined all required channels.",
                reply_markup=force_join_keyboard(missing),
            )
            return

        if user.referred_by and not user.referral_rewarded:
            await grant_referral_reward(
                session,
                user,
            )

        await session.commit()

        await callback.answer("Verified!")

        await callback.message.edit_text(
            "✅ Verification successful!\n\n"
            "Use the menu below.",
            reply_markup=main_menu_keyboard(),
        )


# =========================================================
# HOME
# =========================================================

@router.callback_query(F.data == "menu_home")
async def cb_home(callback: CallbackQuery):
    await callback.answer()

    await callback.message.edit_text(
        "🏠 Main Menu",
        reply_markup=main_menu_keyboard(),
    )


@router.message(Command("menu"))
async def cmd_menu(message: Message):

    if await check_maintenance(message):
        return

    await message.answer(
        "🏠 Main Menu",
        reply_markup=main_menu_keyboard(),
    )


# =========================================================
# PROFILE
# =========================================================

@router.callback_query(F.data == "user_profile")
async def cb_profile(callback: CallbackQuery):

    async with async_session_maker() as session:

        user = await session.scalar(
            select(User).where(
                User.tg_id == callback.from_user.id
            )
        )

        if not user:
            await callback.answer(
                "User not found.",
                show_alert=True,
            )
            return

        text = (
            "👤 PROFILE\n\n"
            f"🆔 ID: {user.tg_id}\n"
            f"👤 Name: {(user.first_name or '')} "
            f"{(user.last_name or '')}\n"
            f"🔗 Username: @{user.username or 'N/A'}\n"
            f"💰 Balance: ₹{user.balance:.2f}\n"
            f"👥 Referred by: "
            f"{user.referred_by or 'None'}"
        )

        await callback.answer()

        await callback.message.edit_text(
            text,
            reply_markup=back_home_keyboard(),
        )


@router.message(Command("profile"))
async def cmd_profile(message: Message):

    if await check_maintenance(message):
        return

    async with async_session_maker() as session:

        user = await session.scalar(
            select(User).where(
                User.tg_id == message.from_user.id
            )
        )

        if not user:
            await message.answer("User not found.")
            return

        text = (
            "👤 PROFILE\n\n"
            f"🆔 ID: {user.tg_id}\n"
            f"👤 Name: {(user.first_name or '')} "
            f"{(user.last_name or '')}\n"
            f"🔗 Username: @{user.username or 'N/A'}\n"
            f"💰 Balance: ₹{user.balance:.2f}\n"
            f"👥 Referred by: "
            f"{user.referred_by or 'None'}"
        )

        await message.answer(
            text,
            reply_markup=back_home_keyboard(),
        )


# =========================================================
# BALANCE
# =========================================================

@router.callback_query(F.data == "user_balance")
async def cb_balance(callback: CallbackQuery):

    async with async_session_maker() as session:

        user = await session.scalar(
            select(User).where(
                User.tg_id == callback.from_user.id
            )
        )

        if not user:
            await callback.answer(
                "User not found.",
                show_alert=True,
            )
            return

        await callback.answer()

        await callback.message.edit_text(
            f"💰 Your Balance\n\n"
            f"₹{user.balance:.2f}",
            reply_markup=back_home_keyboard(),
        )


# =========================================================
# PRODUCTS / CATEGORIES
# =========================================================

@router.callback_query(F.data == "user_products")
async def cb_products(callback: CallbackQuery):

    async with async_session_maker() as session:

        result = await session.execute(
            select(Category)
            .where(Category.is_active.is_(True))
            .order_by(Category.id)
        )

        categories = result.scalars().all()

        if not categories:
            await callback.answer(
                "No categories available.",
                show_alert=True,
            )
            return

        await callback.answer()

        await callback.message.edit_text(
            "🛒 Choose a category:",
            reply_markup=categories_keyboard(categories),
        )


@router.callback_query(F.data.startswith("cat_"))
async def cb_category(callback: CallbackQuery):

    try:
        cat_id = int(
            callback.data.split("_", 1)[1]
        )
    except (ValueError, IndexError):
        await callback.answer(
            "Invalid category.",
            show_alert=True,
        )
        return

    async with async_session_maker() as session:

        category = await session.get(
            Category,
            cat_id,
        )

        if not category or not category.is_active:
            await callback.answer(
                "Category not found.",
                show_alert=True,
            )
            return

        result = await session.execute(
            select(Account)
            .where(
                Account.category_id == cat_id,
                Account.status == "available",
            )
            .order_by(Account.id)
        )

        accounts = result.scalars().all()

        if not accounts:
            await callback.answer(
                "No accounts available.",
                show_alert=True,
            )
            return

        await callback.answer()

        await callback.message.edit_text(
            f"📦 {category.name}\n\n"
            f"Rate: ₹{category.rate:.2f}\n\n"
            "Select an account:",
            reply_markup=accounts_keyboard(accounts),
        )


# =========================================================
# BUY ACCOUNT
# =========================================================

@router.callback_query(F.data.startswith("buy_acc_"))
async def cb_buy_account(callback: CallbackQuery):

    try:
        acc_id = int(
            callback.data.split("_")[2]
        )
    except (ValueError, IndexError):
        await callback.answer(
            "Invalid account.",
            show_alert=True,
        )
        return

    async with async_session_maker() as session:

        user = await session.scalar(
            select(User).where(
                User.tg_id == callback.from_user.id
            )
        )

        if not user:
            await callback.answer(
                "User not found.",
                show_alert=True,
            )
            return

        if user.is_banned:
            await callback.answer(
                "You are banned.",
                show_alert=True,
            )
            return

        account = await session.get(
            Account,
            acc_id,
        )

        if not account:
            await callback.answer(
                "Account not found.",
                show_alert=True,
            )
            return

        if account.status != "available":
            await callback.answer(
                "Account is no longer available.",
                show_alert=True,
            )
            return

        ok, msg, price = await reserve_and_buy_account(
            session,
            user,
            account,
        )

        if not ok:
            await session.rollback()

            await callback.answer(
                msg,
                show_alert=True,
            )
            return

        try:
            await complete_purchase(
                session,
                user,
                account,
                price,
            )

            await session.commit()

        except Exception:
            await session.rollback()

            await callback.answer(
                "Purchase failed. Please try again.",
                show_alert=True,
            )
            return

        await callback.answer("Purchase successful!")

        text = (
            "✅ PURCHASE SUCCESSFUL\n\n"
            f"🆔 Account ID: #{account.id}\n"
            f"💰 Price: ₹{price:.2f}\n"
            f"📱 Phone: {account.phone}\n\n"
            "Thank you for your purchase."
        )

        await callback.message.edit_text(
            text,
            reply_markup=back_home_keyboard(),
        )

        await send_log_message(
            callback.bot,
            f"🛒 Purchase\n"
            f"User: {user.tg_id}\n"
            f"Account: #{account.id}\n"
            f"Price: ₹{price:.2f}",
        )


# =========================================================
# DEPOSIT
# =========================================================

@router.callback_query(F.data == "user_deposit")
async def cb_deposit_menu(callback: CallbackQuery):

    await callback.answer()

    await callback.message.edit_text(
        "💳 DEPOSIT\n\n"
        "Enter the amount you want to deposit:",
        reply_markup=deposit_amount_keyboard(),
    )


@router.message(Command("deposit"))
async def cmd_deposit(
    message: Message,
    state: FSMContext,
):

    if await check_maintenance(message):
        return

    await message.answer(
        "💳 DEPOSIT\n\n"
        "Enter amount to deposit:"
    )

    await state.set_state(
        DepositState.amount
    )


@router.message(StateFilter(DepositState.amount))
async def deposit_amount(
    message: Message,
    state: FSMContext,
):

    try:
        amount = float(
            message.text.strip()
        )
    except (ValueError, AttributeError):
        await message.answer(
            "❌ Invalid amount.\n"
            "Send a number."
        )
        return

    if amount <= 0:
        await message.answer(
            "❌ Amount must be greater than zero."
        )
        return

    await state.update_data(
        amount=amount
    )

    await message.answer(
        "🧾 Now send the UTR number:"
    )

    await state.set_state(
        DepositState.utr
    )


@router.message(StateFilter(DepositState.utr))
async def deposit_utr(
    message: Message,
    state: FSMContext,
):

    utr = (
        message.text.strip()
        if message.text
        else ""
    )

    if not utr:
        await message.answer(
            "❌ UTR cannot be empty."
        )
        return

    data = await state.get_data()
    amount = float(data["amount"])

    async with async_session_maker() as session:

        result = await session.execute(
            select(DepositRequest).where(
                DepositRequest.user_tg_id
                == message.from_user.id,
                DepositRequest.status
                == "pending",
            )
        )

        pending = result.scalars().all()

        if len(pending) >= 5:
            await message.answer(
                "❌ You already have 5 pending deposits."
            )
            await state.clear()
            return

        expires_at = (
            datetime.utcnow()
            + timedelta(minutes=30)
        )

        deposit = DepositRequest(
            user_tg_id=message.from_user.id,
            amount=amount,
            utr=utr,
            status="pending",
            expires_at=expires_at,
        )

        session.add(deposit)

        await session.flush()

        deposit_id = deposit.id

        await session.commit()

        await log_event(
            session,
            "deposit_created",
            message.from_user.id,
            details=f"Deposit #{deposit_id}",
        )

    await message.answer(
        "✅ Deposit request created!\n\n"
        f"💰 Amount: ₹{amount:.2f}\n"
        f"🧾 UTR: {utr}\n"
        f"🆔 Request: #{deposit_id}\n\n"
        "Waiting for admin approval."
    )

    kb = approve_deposit_keyboard(
        deposit_id
    )

    if LOG_CHANNEL_ID:

        try:
            await message.bot.send_message(
                LOG_CHANNEL_ID,
                "💳 NEW DEPOSIT REQUEST\n\n"
                f"👤 User: {message.from_user.id}\n"
                f"💰 Amount: ₹{amount:.2f}\n"
                f"🧾 UTR: {utr}\n"
                f"🆔 Request: #{deposit_id}",
                reply_markup=kb,
            )
        except Exception as e:
            print(
                "Deposit log error:",
                e,
            )

    await state.clear()


# =========================================================
# APPROVE DEPOSIT
# =========================================================

@router.callback_query(
    F.data.startswith("deposit_approve_")
)
async def cb_deposit_approve(
    callback: CallbackQuery,
):

    try:
        dep_id = int(
            callback.data.split("_")[2]
        )
    except (ValueError, IndexError):
        await callback.answer(
            "Invalid deposit.",
            show_alert=True,
        )
        return

    async with async_session_maker() as session:

        role = await get_user_role(
            session,
            callback.from_user.id,
        )

        if role not in (
            "admin",
            "superadmin",
            "owner",
        ):
            await callback.answer(
                "Access denied.",
                show_alert=True,
            )
            return

        deposit = await session.get(
            DepositRequest,
            dep_id,
        )

        if not deposit:
            await callback.answer(
                "Deposit not found.",
                show_alert=True,
            )
            return

        if deposit.status != "pending":
            await callback.answer(
                "Deposit already processed.",
                show_alert=True,
            )
            return

        if (
            deposit.expires_at
            and deposit.expires_at < datetime.utcnow()
        ):
            deposit.status = "expired"
            await session.commit()

            await callback.answer(
                "Deposit has expired.",
                show_alert=True,
            )
            return

        user = await session.get(
            User,
            deposit.user_tg_id,
        )

        if not user:
            await callback.answer(
                "User not found.",
                show_alert=True,
            )
            return

        user.balance += deposit.amount

        deposit.status = "approved"
        deposit.approved_by = (
            callback.from_user.id
        )

        session.add(
            Transaction(
                user_tg_id=user.tg_id,
                amount=deposit.amount,
                type="deposit",
                description=(
                    "Deposit approved - "
                    f"UTR {deposit.utr}"
                ),
            )
        )

        await session.commit()

        await callback.answer(
            "Deposit approved!"
        )

        await callback.message.edit_text(
            "✅ DEPOSIT APPROVED\n\n"
            f"User: {user.tg_id}\n"
            f"Amount: ₹{deposit.amount:.2f}\n"
            f"UTR: {deposit.utr}",
        )

        await send_log_message(
            callback.bot,
            "✅ Deposit approved\n"
            f"User: {user.tg_id}\n"
            f"Amount: ₹{deposit.amount:.2f}\n"
            f"By: {callback.from_user.id}",
        )

        try:
            await callback.bot.send_message(
                user.tg_id,
                "✅ Your deposit has been approved!\n\n"
                f"Amount: ₹{deposit.amount:.2f}\n"
                f"UTR: {deposit.utr}",
            )
        except Exception:
            pass


# =========================================================
# REJECT DEPOSIT
# =========================================================

@router.callback_query(
    F.data.startswith("deposit_reject_")
)
async def cb_deposit_reject(
    callback: CallbackQuery,
):

    try:
        dep_id = int(
            callback.data.split("_")[2]
        )
    except (ValueError, IndexError):
        await callback.answer(
            "Invalid deposit.",
            show_alert=True,
        )
        return

    async with async_session_maker() as session:

        role = await get_user_role(
            session,
            callback.from_user.id,
        )

        if role not in (
            "admin",
            "superadmin",
            "owner",
        ):
            await callback.answer(
                "Access denied.",
                show_alert=True,
            )
            return

        deposit = await session.get(
            DepositRequest,
            dep_id,
        )

        if not deposit:
            await callback.answer(
                "Deposit not found.",
                show_alert=True,
            )
            return

        if deposit.status != "pending":
            await callback.answer(
                "Deposit already processed.",
                show_alert=True,
            )
            return

        user = await session.get(
            User,
            deposit.user_tg_id,
        )

        if not user:
            await callback.answer(
                "User not found.",
                show_alert=True,
            )
            return

        deposit.status = "rejected"
        deposit.approved_by = (
            callback.from_user.id
        )

        await session.commit()

        await callback.answer(
            "Deposit rejected."
        )

        await callback.message.edit_text(
            "❌ DEPOSIT REJECTED\n\n"
            f"User: {user.tg_id}\n"
            f"Amount: ₹{deposit.amount:.2f}\n"
            f"UTR: {deposit.utr}",
        )

        await send_log_message(
            callback.bot,
            "❌ Deposit rejected\n"
            f"User: {user.tg_id}\n"
            f"Amount: ₹{deposit.amount:.2f}\n"
            f"By: {callback.from_user.id}",
        )

        try:
            await callback.bot.send_message(
                user.tg_id,
                "❌ Your deposit was rejected.\n\n"
                f"Amount: ₹{deposit.amount:.2f}\n"
                f"UTR: {deposit.utr}",
            )
        except Exception:
            pass


# =========================================================
# ADMIN PANEL
# =========================================================

@router.callback_query(F.data == "admin_panel")
async def cb_admin_panel(
    callback: CallbackQuery,
):

    async with async_session_maker() as session:

        if not await is_staff(
            session,
            callback.from_user.id,
        ):
            await callback.answer(
                "Access denied.",
                show_alert=True,
            )
            return

    await callback.answer()

    await callback.message.edit_text(
        "🛠 ADMIN PANEL",
        reply_markup=admin_panel_keyboard(),
    )


@router.message(Command("admin"))
async def cmd_admin(message: Message):

    if await check_maintenance(message):
        return

    async with async_session_maker() as session:

        if not await is_staff(
            session,
            message.from_user.id,
        ):
            await message.answer(
                "❌ Access denied."
            )
            return

    await message.answer(
        "🛠 ADMIN PANEL",
        reply_markup=admin_panel_keyboard(),
    )


@router.message(Command("dfchat"))
async def cmd_dfchat(message: Message):

    async with async_session_maker() as session:

        if not await is_superadmin(
            session,
            message.from_user.id,
        ):
            await message.answer(
                "❌ Access denied."
            )
            return

    text = (
        "🛡 ADMIN COMMANDS\n\n"

        "👑 Admin Management\n"
        "/addadmin <user_id>\n"
        "/removeadmin <user_id>\n"
        "/addsuperadmin <user_id>\n"
        "/removesuperadmin <user_id>\n\n"

        "💰 Balance\n"
        "/addbalance <user_id> <amount>\n"
        "/removebalance <user_id> <amount>\n\n"

        "🚫 Users\n"
        "/ban <user_id> [reason]\n"
        "/unban <user_id>\n\n"

        "📢 Broadcast\n"
        "/broadcast\n\n"

        "📦 Categories\n"
        "/addcategory <name> <rate>\n"
        "/editcategory <name> <rate>\n"
        "/deletecategory <name>\n\n"

        "📱 Accounts\n"
        "/addaccount <category_id> <phone>\n"
        "/deleteaccount <account_id>\n\n"

        "📢 Channels\n"
        "/addchannel <channel_id> [@username] [label]\n"
        "/removechannel <channel_id>\n\n"

        "🎟 Coupons\n"
        "/addcoupon <code> <amount> <max_uses>\n"
        "/editcoupon <code> <amount> <max_uses>\n"
        "/deletecoupon <code>\n\n"

        "📊 Statistics\n"
        "/stats\n"
        "/coinslist\n"
        "/maintenance"
    )

    await message.answer(text)


# =========================================================
# COINS LIST
# =========================================================

@router.message(Command("coinslist"))
async def cmd_coinslist(message: Message):

    async with async_session_maker() as session:

        if not await is_superadmin(
            session,
            message.from_user.id,
        ):
            await message.answer(
                "❌ Access denied."
            )
            return

        result = await session.execute(
            select(User)
            .where(User.balance >= 2.0)
            .order_by(User.balance.desc())
        )

        users = result.scalars().all()

    lines = []

    for user in users:
        lines.append(
            f"🆔 {user.tg_id} | "
            f"₹{user.balance:.2f} | "
            f"@{user.username or 'N/A'}"
        )

    text = (
        "💰 USERS WITH BALANCE ≥ ₹2\n\n"
        + (
            "\n".join(lines)
            if lines
            else "No users."
        )
    )

    await message.answer(text)


# =========================================================
# ADD BALANCE
# =========================================================

@router.message(Command("addbalance"))
async def cmd_addbalance(message: Message):

    async with async_session_maker() as session:

        if not await is_superadmin(
            session,
            message.from_user.id,
        ):
            await message.answer(
                "❌ Access denied."
            )
            return

    args = message.text.split()

    if len(args) != 3:
        await message.answer(
            "Usage:\n"
            "/addbalance <user_id> <amount>"
        )
        return

    try:
        user_id = int(args[1])
        amount = float(args[2])
    except ValueError:
        await message.answer(
            "❌ Invalid user ID or amount."
        )
        return

    if amount <= 0:
        await message.answer(
            "❌ Amount must be greater than zero."
        )
        return

    async with async_session_maker() as session:

        user = await session.get(
            User,
            user_id,
        )

        if not user:
            await message.answer(
                "❌ User not found."
            )
            return

        old_balance = user.balance

        await add_balance(
            session,
            user.tg_id,
            amount,
            f"Added by {message.from_user.id}",
        )

        new_balance = old_balance + amount

        await session.commit()

    await message.answer(
        "✅ Balance added\n\n"
        f"User: {user_id}\n"
        f"Added: ₹{amount:.2f}\n"
        f"New balance: ₹{new_balance:.2f}"
    )

    await send_log_message(
        message.bot,
        f"💰 Balance added\n"
        f"User: {user_id}\n"
        f"Amount: ₹{amount:.2f}\n"
        f"By: {message.from_user.id}",
    )


# =========================================================
# REMOVE BALANCE
# =========================================================

@router.message(Command("removebalance"))
async def cmd_removebalance(message: Message):

    async with async_session_maker() as session:

        if not await is_superadmin(
            session,
            message.from_user.id,
        ):
            await message.answer(
                "❌ Access denied."
            )
            return

    args = message.text.split()

    if len(args) != 3:
        await message.answer(
            "Usage:\n"
            "/removebalance <user_id> <amount>"
        )
        return

    try:
        user_id = int(args[1])
        amount = float(args[2])
    except ValueError:
        await message.answer(
            "❌ Invalid user ID or amount."
        )
        return

    if amount <= 0:
        await message.answer(
            "❌ Amount must be greater than zero."
        )
        return

    async with async_session_maker() as session:

        user = await session.get(
            User,
            user_id,
        )

        if not user:
            await message.answer(
                "❌ User not found."
            )
            return

        try:
            old_balance = user.balance

            await remove_balance(
                session,
                user.tg_id,
                amount,
                f"Removed by {message.from_user.id}",
            )

            new_balance = old_balance - amount

            await session.commit()

        except ValueError as e:
            await session.rollback()

            await message.answer(
                f"❌ {e}"
            )
            return

    await message.answer(
        "✅ Balance removed\n\n"
        f"User: {user_id}\n"
        f"Removed: ₹{amount:.2f}\n"
        f"New balance: ₹{new_balance:.2f}"
    )


# =========================================================
# BAN
# =========================================================

@router.message(Command("ban"))
async def cmd_ban(message: Message):

    async with async_session_maker() as session:

        if not await is_staff(
            session,
            message.from_user.id,
        ):
            await message.answer(
                "❌ Access denied."
            )
            return

    args = message.text.split(maxsplit=2)

    if len(args) < 2:
        await message.answer(
            "Usage:\n"
            "/ban <user_id> [reason]"
        )
        return

    try:
        user_id = int(args[1])
    except ValueError:
        await message.answer(
            "❌ Invalid user ID."
        )
        return

    reason = (
        args[2]
        if len(args) > 2
        else "No reason provided"
    )

    async with async_session_maker() as session:

        user = await session.get(
            User,
            user_id,
        )

        if not user:
            await message.answer(
                "❌ User not found."
            )
            return

        if user_id == OWNER_ID:
            await message.answer(
                "❌ You cannot ban the owner."
            )
            return

        user.is_banned = True
        user.ban_reason = reason
        user.ban_until = None

        await session.commit()

    await message.answer(
        f"🚫 User {user_id} banned.\n"
        f"Reason: {reason}"
    )

    await send_log_message(
        message.bot,
        f"🚫 Ban\n"
        f"User: {user_id}\n"
        f"By: {message.from_user.id}\n"
        f"Reason: {reason}",
    )


# =========================================================
# UNBAN
# =========================================================

@router.message(Command("unban"))
async def cmd_unban(message: Message):

    async with async_session_maker() as session:

        if not await is_staff(
            session,
            message.from_user.id,
        ):
            await message.answer(
                "❌ Access denied."
            )
            return

    args = message.text.split()

    if len(args) != 2:
        await message.answer(
            "Usage:\n"
            "/unban <user_id>"
        )
        return

    try:
        user_id = int(args[1])
    except ValueError:
        await message.answer(
            "❌ Invalid user ID."
        )
        return

    async with async_session_maker() as session:

        user = await session.get(
            User,
            user_id,
        )

        if not user:
            await message.answer(
                "❌ User not found."
            )
            return

        user.is_banned = False
        user.ban_reason = None
        user.ban_until = None

        await session.commit()

    await message.answer(
        f"✅ User {user_id} has been unbanned."
    )


# =========================================================
# BROADCAST
# =========================================================

@router.message(Command("broadcast"))
async def cmd_broadcast(
    message: Message,
    state: FSMContext,
):

    async with async_session_maker() as session:

        if not await is_superadmin(
            session,
            message.from_user.id,
        ):
            await message.answer(
                "❌ Access denied."
            )
            return

    await message.answer(
        "📢 Send the broadcast message now."
    )

    await state.set_state(
        BroadcastState.text
    )


@router.message(StateFilter(BroadcastState.text))
async def broadcast_text(
    message: Message,
    state: FSMContext,
):

    text = message.text

    if not text:
        await message.answer(
            "❌ Broadcast must contain text."
        )
        return

    async with async_session_maker() as session:

        result = await session.execute(
            select(User.tg_id)
        )

        user_ids = [
            row[0]
            for row in result.all()
        ]

    sent = 0
    failed = 0

    for user_id in user_ids:

        try:
            await message.bot.send_message(
                user_id,
                text,
            )
            sent += 1

        except Exception:
            failed += 1

    await message.answer(
        "📢 Broadcast completed\n\n"
        f"✅ Sent: {sent}\n"
        f"❌ Failed: {failed}"
    )

    await send_log_message(
        message.bot,
        f"📢 Broadcast\n"
        f"Sent: {sent}\n"
        f"Failed: {failed}\n"
        f"By: {message.from_user.id}",
    )

    await state.clear()


# =========================================================
# CATEGORY MANAGEMENT
# =========================================================

@router.message(Command("addcategory"))
async def cmd_addcategory(message: Message):

    async with async_session_maker() as session:

        if not await is_staff(
            session,
            message.from_user.id,
        ):
            await message.answer(
                "❌ Access denied."
            )
            return

    args = message.text.split()

    if len(args) != 3:
        await message.answer(
            "Usage:\n"
            "/addcategory <name> <rate>"
        )
        return

    name = args[1]

    try:
        rate = float(args[2])
    except ValueError:
        await message.answer(
            "❌ Invalid rate."
        )
        return

    if rate <= 0:
        await message.answer(
            "❌ Rate must be greater than zero."
        )
        return

    async with async_session_maker() as session:

        existing = await session.scalar(
            select(Category).where(
                Category.name == name
            )
        )

        if existing:
            await message.answer(
                "❌ Category already exists."
            )
            return

        category = Category(
            name=name,
            rate=rate,
            is_active=True,
        )

        session.add(category)

        await session.commit()

    await message.answer(
        f"✅ Category added\n\n"
        f"Name: {name}\n"
        f"Rate: ₹{rate:.2f}"
    )


@router.message(Command("editcategory"))
async def cmd_editcategory(message: Message):

    async with async_session_maker() as session:

        if not await is_staff(
            session,
            message.from_user.id,
        ):
            await message.answer(
                "❌ Access denied."
            )
            return

    args = message.text.split()

    if len(args) != 3:
        await message.answer(
            "Usage:\n"
            "/editcategory <name> <new_rate>"
        )
        return

    name = args[1]

    try:
        rate = float(args[2])
    except ValueError:
        await message.answer(
            "❌ Invalid rate."
        )
        return

    if rate <= 0:
        await message.answer(
            "❌ Rate must be greater than zero."
        )
        return

    async with async_session_maker() as session:

        category = await session.scalar(
            select(Category).where(
                Category.name == name
            )
        )

        if not category:
            await message.answer(
                "❌ Category not found."
            )
            return

        category.rate = rate

        await session.commit()

    await message.answer(
        f"✅ Category updated\n\n"
        f"{name}: ₹{rate:.2f}"
    )


@router.message(Command("deletecategory"))
async def cmd_deletecategory(message: Message):

    async with async_session_maker() as session:

        if not await is_staff(
            session,
            message.from_user.id,
        ):
            await message.answer(
                "❌ Access denied."
            )
            return

    args = message.text.split()

    if len(args) != 2:
        await message.answer(
            "Usage:\n"
            "/deletecategory <name>"
        )
        return

    name = args[1]

    async with async_session_maker() as session:

        category = await session.scalar(
            select(Category).where(
                Category.name == name
            )
        )

        if not category:
            await message.answer(
                "❌ Category not found."
            )
            return

        account_exists = await session.scalar(
            select(Account.id)
            .where(
                Account.category_id == category.id
            )
            .limit(1)
        )

        if account_exists:
            await message.answer(
                "❌ Cannot delete category while "
                "accounts are attached to it."
            )
            return

        await session.delete(category)
        await session.commit()

    await message.answer(
        f"✅ Category '{name}' deleted."
    )


# =========================================================
# ACCOUNT MANAGEMENT
# =========================================================

@router.message(Command("addaccount"))
async def cmd_addaccount(message: Message):

    async with async_session_maker() as session:

        if not await is_staff(
            session,
            message.from_user.id,
        ):
            await message.answer(
                "❌ Access denied."
            )
            return

    args = message.text.split()

    if len(args) != 3:
        await message.answer(
            "Usage:\n"
            "/addaccount <category_id> <phone>"
        )
        return

    try:
        category_id = int(args[1])
    except ValueError:
        await message.answer(
            "❌ Invalid category ID."
        )
        return

    phone = args[2]

    async with async_session_maker() as session:

        category = await session.get(
            Category,
            category_id,
        )

        if not category:
            await message.answer(
                "❌ Category not found."
            )
            return

        account = Account(
            category_id=category_id,
            phone=phone,
            session_data="placeholder_session",
            status="available",
            added_by=message.from_user.id,
        )

        session.add(account)

        await session.flush()

        account_id = account.id

        await session.commit()

    await message.answer(
        "✅ Account added\n\n"
        f"ID: #{account_id}\n"
        f"Category: {category.name}\n"
        f"Phone: {phone}"
    )


@router.message(Command("deleteaccount"))
async def cmd_deleteaccount(message: Message):

    async with async_session_maker() as session:

        if not await is_staff(
            session,
            message.from_user.id,
        ):
            await message.answer(
                "❌ Access denied."
            )
            return

    args = message.text.split()

    if len(args) != 2:
        await message.answer(
            "Usage:\n"
            "/deleteaccount <account_id>"
        )
        return

    try:
        account_id = int(args[1])
    except ValueError:
        await message.answer(
            "❌ Invalid account ID."
        )
        return

    async with async_session_maker() as session:

        account = await session.get(
            Account,
            account_id,
        )

        if not account:
            await message.answer(
                "❌ Account not found."
            )
            return

        if account.status != "available":
            await message.answer(
                "❌ Account is already sold/reserved."
            )
            return

        await session.delete(account)
        await session.commit()

    await message.answer(
        f"✅ Account #{account_id} deleted."
    )


# =========================================================
# CHANNEL MANAGEMENT
# =========================================================

@router.message(Command("addchannel"))
async def cmd_addchannel(message: Message):

    async with async_session_maker() as session:

        if not await is_staff(
            session,
            message.from_user.id,
        ):
            await message.answer(
                "❌ Access denied."
            )
            return

    args = message.text.split()

    if len(args) < 2:
        await message.answer(
            "Usage:\n"
            "/addchannel <channel_id> [@username] [label]"
        )
        return

    try:
        channel_id = int(args[1])
    except ValueError:
        await message.answer(
            "❌ Invalid channel ID."
        )
        return

    username = (
        args[2]
        if len(args) > 2
        else None
    )

    label = (
        " ".join(args[3:])
        if len(args) > 3
        else None
    )

    async with async_session_maker() as session:

        existing = await session.scalar(
            select(RequiredChannel).where(
                RequiredChannel.channel_id
                == channel_id
            )
        )

        if existing:
            await message.answer(
                "❌ Channel already exists."
            )
            return

        channel = RequiredChannel(
            channel_id=channel_id,
            channel_username=username,
            label=label,
        )

        session.add(channel)

        await session.commit()

    await message.answer(
        f"✅ Required channel added:\n"
        f"{channel_id}"
    )


@router.message(Command("removechannel"))
async def cmd_removechannel(message: Message):

    async with async_session_maker() as session:

        if not await is_staff(
            session,
            message.from_user.id,
        ):
            await message.answer(
                "❌ Access denied."
            )
            return

    args = message.text.split()

    if len(args) != 2:
        await message.answer(
            "Usage:\n"
            "/removechannel <channel_id>"
        )
        return

    try:
        channel_id = int(args[1])
    except ValueError:
        await message.answer(
            "❌ Invalid channel ID."
        )
        return

    async with async_session_maker() as session:

        channel = await session.scalar(
            select(RequiredChannel).where(
                RequiredChannel.channel_id
                == channel_id
            )
        )

        if not channel:
            await message.answer(
                "❌ Channel not found."
            )
            return

        await session.delete(channel)
        await session.commit()

    await message.answer(
        f"✅ Channel {channel_id} removed."
    )


# =========================================================
# COUPONS
# =========================================================

@router.callback_query(F.data == "user_coupon")
async def cb_coupon(callback: CallbackQuery):

    await callback.answer()

    await callback.message.edit_text(
        "🎟 COUPONS\n\n"
        "Use:\n"
        "/coupon <code>",
        reply_markup=back_home_keyboard(),
    )


@router.message(Command("coupon"))
async def cmd_coupon(message: Message):

    args = message.text.split()

    if len(args) != 2:
        await message.answer(
            "Usage:\n"
            "/coupon <code>"
        )
        return

    code = args[1]

    async with async_session_maker() as session:

        user = await session.scalar(
            select(User).where(
                User.tg_id == message.from_user.id
            )
        )

        if not user:
            await message.answer(
                "❌ User not found."
            )
            return

        if user.is_banned:
            await message.answer(
                "🚫 You are banned."
            )
            return

        ok, result = await apply_coupon(
            session,
            user,
            code,
        )

        if ok:
            await session.commit()
        else:
            await session.rollback()

    await message.answer(result)

    await send_log_message(
        message.bot,
        f"🎟 Coupon\n"
        f"User: {message.from_user.id}\n"
        f"Code: {code}\n"
        f"Success: {ok}",
    )


@router.message(Command("addcoupon"))
async def cmd_addcoupon(message: Message):

    async with async_session_maker() as session:

        if not await is_staff(
            session,
            message.from_user.id,
        ):
            await message.answer(
                "❌ Access denied."
            )
            return

    args = message.text.split()

    if len(args) != 4:
        await message.answer(
            "Usage:\n"
            "/addcoupon <code> <amount> <max_uses>"
        )
        return

    code = args[1].upper()

    try:
        amount = float(args[2])
        max_uses = int(args[3])
    except ValueError:
        await message.answer(
            "❌ Invalid amount or max uses."
        )
        return

    if amount <= 0 or max_uses <= 0:
        await message.answer(
            "❌ Amount and max uses must be positive."
        )
        return

    async with async_session_maker() as session:

        existing = await session.scalar(
            select(Coupon).where(
                Coupon.code == code
            )
        )

        if existing:
            await message.answer(
                "❌ Coupon already exists."
            )
            return

        coupon = Coupon(
            code=code,
            bonus_amount=amount,
            max_uses=max_uses,
            used_count=0,
            active=True,
        )

        session.add(coupon)

        await session.commit()

    await message.answer(
        "✅ Coupon created\n\n"
        f"Code: {code}\n"
        f"Bonus: ₹{amount:.2f}\n"
        f"Max uses: {max_uses}"
    )


@router.message(Command("editcoupon"))
async def cmd_editcoupon(message: Message):

    async with async_session_maker() as session:

        if not await is_staff(
            session,
            message.from_user.id,
        ):
            await message.answer(
                "❌ Access denied."
            )
            return

    args = message.text.split()

    if len(args) != 4:
        await message.answer(
            "Usage:\n"
            "/editcoupon <code> <amount> <max_uses>"
        )
        return

    code = args[1].upper()

    try:
        amount = float(args[2])
        max_uses = int(args[3])
    except ValueError:
        await message.answer(
            "❌ Invalid values."
        )
        return

    async with async_session_maker() as session:

        coupon = await session.scalar(
            select(Coupon).where(
                Coupon.code == code
            )
        )

        if not coupon:
            await message.answer(
                "❌ Coupon not found."
            )
            return

        coupon.bonus_amount = amount
        coupon.max_uses = max_uses

        await session.commit()

    await message.answer(
        f"✅ Coupon {code} updated."
    )


@router.message(Command("deletecoupon"))
async def cmd_deletecoupon(message: Message):

    async with async_session_maker() as session:

        if not await is_staff(
            session,
            message.from_user.id,
        ):
            await message.answer(
                "❌ Access denied."
            )
            return

    args = message.text.split()

    if len(args) != 2:
        await message.answer(
            "Usage:\n"
            "/deletecoupon <code>"
        )
        return

    code = args[1].upper()

    async with async_session_maker() as session:

        coupon = await session.scalar(
            select(Coupon).where(
                Coupon.code == code
            )
        )

        if not coupon:
            await message.answer(
                "❌ Coupon not found."
            )
            return

        await session.delete(coupon)
        await session.commit()

    await message.answer(
        f"✅ Coupon {code} deleted."
    )


# =========================================================
# STATISTICS
# =========================================================

@router.message(Command("stats"))
async def cmd_stats(message: Message):

    async with async_session_maker() as session:

        if not await is_staff(
            session,
            message.from_user.id,
        ):
            await message.answer(
                "❌ Access denied."
            )
            return

        total_users = (
            await session.scalar(
                select(User.id)
                .count()
            )
            if False
            else None
        )

        users = await session.execute(
            select(User.id)
        )
        total_users = len(users.all())

        deposits = await session.execute(
            select(DepositRequest.id)
        )
        total_deposits = len(deposits.all())

        purchases = await session.execute(
            select(Purchase.id)
        )
        total_purchases = len(purchases.all())

        accounts = await session.execute(
            select(Account.id).where(
                Account.status == "available"
            )
        )
        available_accounts = len(
            accounts.all()
        )

        banned = await session.execute(
            select(User.id).where(
                User.is_banned.is_(True)
            )
        )
        banned_users = len(banned.all())

    text = (
        "📊 BOT STATISTICS\n\n"
        f"👥 Total users: {total_users}\n"
        f"💳 Total deposits: {total_deposits}\n"
        f"🛒 Total purchases: {total_purchases}\n"
        f"📦 Available accounts: {available_accounts}\n"
        f"🚫 Banned users: {banned_users}"
    )

    await message.answer(text)


# =========================================================
# MAINTENANCE
# =========================================================

@router.message(Command("maintenance"))
async def cmd_maintenance(message: Message):

    async with async_session_maker() as session:

        if not await is_superadmin(
            session,
            message.from_user.id,
        ):
            await message.answer(
                "❌ Access denied."
            )
            return

    await message.answer(
        "🛠 Maintenance mode is controlled "
        "by the MAINTENANCE_MODE environment variable.\n\n"
        f"Current value: {MAINTENANCE_MODE}\n\n"
        "Change the Railway variable and restart "
        "the bot."
    )


# =========================================================
# ADMIN MANAGEMENT
# =========================================================

@router.message(Command("addadmin"))
async def cmd_addadmin(message: Message):

    async with async_session_maker() as session:

        if not await is_superadmin(
            session,
            message.from_user.id,
        ):
            await message.answer(
                "❌ Access denied."
            )
            return

    args = message.text.split()

    if len(args) != 2:
        await message.answer(
            "Usage:\n"
            "/addadmin <user_id>"
        )
        return

    try:
        user_id = int(args[1])
    except ValueError:
        await message.answer(
            "❌ Invalid user ID."
        )
        return

    if user_id == OWNER_ID:
        await message.answer(
            "❌ Owner does not need admin promotion."
        )
        return

    async with async_session_maker() as session:

        admin = await session.scalar(
            select(Admin).where(
                Admin.tg_id == user_id
            )
        )

        if admin:
            await message.answer(
                "❌ User is already an admin."
            )
            return

        session.add(
            Admin(
                tg_id=user_id,
                role="admin",
                added_by=message.from_user.id,
            )
        )

        await session.commit()

    await message.answer(
        f"✅ User {user_id} promoted to admin."
    )


@router.message(Command("removeadmin"))
async def cmd_removeadmin(message: Message):

    async with async_session_maker() as session:

        if not await is_superadmin(
            session,
            message.from_user.id,
        ):
            await message.answer(
                "❌ Access denied."
            )
            return

    args = message.text.split()

    if len(args) != 2:
        await message.answer(
            "Usage:\n"
            "/removeadmin <user_id>"
        )
        return

    try:
        user_id = int(args[1])
    except ValueError:
        await message.answer(
            "❌ Invalid user ID."
        )
        return

    async with async_session_maker() as session:

        admin = await session.scalar(
            select(Admin).where(
                Admin.tg_id == user_id
            )
        )

        if not admin:
            await message.answer(
                "❌ User is not an admin."
            )
            return

        if admin.role == "superadmin":
            await message.answer(
                "❌ Use /removesuperadmin first."
            )
            return

        await session.delete(admin)
        await session.commit()

    await message.answer(
        f"✅ User {user_id} removed from admins."
    )


@router.message(Command("addsuperadmin"))
async def cmd_addsuperadmin(message: Message):

    async with async_session_maker() as session:

        role = await get_user_role(
            session,
            message.from_user.id,
        )

        if role != "owner":
            await message.answer(
                "❌ Only the owner can manage superadmins."
            )
            return

    args = message.text.split()

    if len(args) != 2:
        await message.answer(
            "Usage:\n"
            "/addsuperadmin <user_id>"
        )
        return

    try:
        user_id = int(args[1])
    except ValueError:
        await message.answer(
            "❌ Invalid user ID."
        )
        return

    if user_id == OWNER_ID:
        await message.answer(
            "❌ This user is already the owner."
        )
        return

    async with async_session_maker() as session:

        admin = await session.scalar(
            select(Admin).where(
                Admin.tg_id == user_id
            )
        )

        if admin:
            admin.role = "superadmin"
        else:
            session.add(
                Admin(
                    tg_id=user_id,
                    role="superadmin",
                    added_by=message.from_user.id,
                )
            )

        await session.commit()

    await message.answer(
        f"👑 User {user_id} is now superadmin."
    )


@router.message(Command("removesuperadmin"))
async def cmd_removesuperadmin(message: Message):

    async with async_session_maker() as session:

        role = await get_user_role(
            session,
            message.from_user.id,
        )

        if role != "owner":
            await message.answer(
                "❌ Only owner can remove superadmins."
            )
            return

    args = message.text.split()

    if len(args) != 2:
        await message.answer(
            "Usage:\n"
            "/removesuperadmin <user_id>"
        )
        return

    try:
        user_id = int(args[1])
    except ValueError:
        await message.answer(
            "❌ Invalid user ID."
        )
        return

    async with async_session_maker() as session:

        admin = await session.scalar(
            select(Admin).where(
                Admin.tg_id == user_id
            )
        )

        if not admin or admin.role != "superadmin":
            await message.answer(
                "❌ User is not a superadmin."
            )
            return

        admin.role = "admin"

        await session.commit()

    await message.answer(
        f"✅ User {user_id} demoted to admin."
    )


# =========================================================
# REFERRAL
# =========================================================

@router.callback_query(F.data == "user_referral")
async def cb_referral(callback: CallbackQuery):

    me = await callback.bot.get_me()

    ref_link = (
        f"https://t.me/{me.username}"
        f"?start={callback.from_user.id}"
    )

    text = (
        "👥 REFERRAL\n\n"
        "Invite users using your link:\n\n"
        f"{ref_link}\n\n"
        "🎁 Reward: 1 for each new user "
        "who joins through your link and verifies."
    )

    await callback.answer()

    await callback.message.edit_text(
        text,
        reply_markup=back_home_keyboard(),
    )


# =========================================================
# SUPPORT
# =========================================================

@router.callback_query(F.data == "user_support")
async def cb_support(callback: CallbackQuery):

    username = SUPPORT_USERNAME or "support"

    await callback.answer()

    await callback.message.edit_text(
        "🆘 SUPPORT\n\n"
        f"Contact: @{username}",
        reply_markup=back_home_keyboard(),
    )


# =========================================================
# HELP
# =========================================================

@router.callback_query(F.data == "user_help")
async def cb_help(callback: CallbackQuery):

    await callback.answer()

    await callback.message.edit_text(
        "ℹ️ HELP\n\n"
        "Use the buttons to navigate.\n"
        "Use /profile to view your profile.\n"
        "Use /deposit to add balance.\n"
        "Use /purchases to view purchases.\n"
        "Use /transactions to view transactions.\n"
        "Use /coupon <code> to redeem a coupon.",
        reply_markup=back_home_keyboard(),
    )


# =========================================================
# PURCHASE HISTORY
# =========================================================

@router.message(Command("purchases"))
async def cmd_purchases(message: Message):

    if await check_maintenance(message):
        return

    async with async_session_maker() as session:

        result = await session.execute(
            select(Purchase)
            .where(
                Purchase.user_tg_id
                == message.from_user.id
            )
            .order_by(
                Purchase.created_at.desc()
            )
            .limit(10)
        )

        purchases = result.scalars().all()

    if not purchases:
        await message.answer(
            "🛒 No purchases yet.",
            reply_markup=back_home_keyboard(),
        )
        return

    lines = []

    for purchase in purchases:
        lines.append(
            f"🆔 Account #{purchase.account_id}\n"
            f"💰 ₹{purchase.price:.2f}\n"
            f"📅 {purchase.created_at}"
        )

    await message.answer(
        "🛒 YOUR PURCHASES\n\n"
        + "\n\n".join(lines),
        reply_markup=back_home_keyboard(),
    )


@router.callback_query(F.data == "user_purchases")
async def cb_user_purchases(
    callback: CallbackQuery,
):

    async with async_session_maker() as session:

        result = await session.execute(
            select(Purchase)
            .where(
                Purchase.user_tg_id
                == callback.from_user.id
            )
            .order_by(
                Purchase.created_at.desc()
            )
            .limit(10)
        )

        purchases = result.scalars().all()

    if not purchases:
        await callback.answer(
            "No purchases yet.",
            show_alert=True,
        )
        return

    lines = []

    for purchase in purchases:
        lines.append(
            f"🆔 Account #{purchase.account_id}"
            f" — ₹{purchase.price:.2f}"
        )

    await callback.answer()

    await callback.message.edit_text(
        "🛒 YOUR PURCHASES\n\n"
        + "\n".join(lines),
        reply_markup=back_home_keyboard(),
    )


# =========================================================
# TRANSACTIONS
# =========================================================

@router.message(Command("transactions"))
async def cmd_transactions(message: Message):

    if await check_maintenance(message):
        return

    async with async_session_maker() as session:

        result = await session.execute(
            select(Transaction)
            .where(
                Transaction.user_tg_id
                == message.from_user.id
            )
            .order_by(
                Transaction.created_at.desc()
            )
            .limit(10)
        )

        transactions = result.scalars().all()

    if not transactions:
        await message.answer(
            "💳 No transactions yet.",
            reply_markup=back_home_keyboard(),
        )
        return

    lines = []

    for transaction in transactions:

        sign = (
            "+"
            if transaction.amount > 0
            else ""
        )

        lines.append(
            f"{transaction.type}: "
            f"{sign}₹{transaction.amount:.2f}"
        )

    await message.answer(
        "💳 YOUR TRANSACTIONS\n\n"
        + "\n".join(lines),
        reply_markup=back_home_keyboard(),
    )


@router.callback_query(F.data == "user_transactions")
async def cb_user_transactions(
    callback: CallbackQuery,
):

    async with async_session_maker() as session:

        result = await session.execute(
            select(Transaction)
            .where(
                Transaction.user_tg_id
                == callback.from_user.id
            )
            .order_by(
                Transaction.created_at.desc()
            )
            .limit(10)
        )

        transactions = result.scalars().all()

    if not transactions:
        await callback.answer(
            "No transactions yet.",
            show_alert=True,
        )
        return

    lines = []

    for transaction in transactions:

        sign = (
            "+"
            if transaction.amount > 0
            else ""
        )

        lines.append(
            f"{transaction.type}: "
            f"{sign}₹{transaction.amount:.2f}"
        )

    await callback.answer()

    await callback.message.edit_text(
        "💳 YOUR TRANSACTIONS\n\n"
        + "\n".join(lines),
        reply_markup=back_home_keyboard(),
    )


# =========================================================
# ERROR HANDLER
# =========================================================

@router.errors()
async def error_handler(
    event,
    exception,
):
    print(
        "❌ Handler error:",
        repr(exception),
        )
