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
    Category,
    Account,
    DepositRequest,
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
    reserve_and_buy_account,
    complete_purchase,
    fail_purchase,
    log_event,
    send_log_message,
    add_balance,
    get_user_role,
)

from config import MAINTENANCE_MODE, LOG_CHANNEL_ID


router = Router()


# ============================================================
# FSM
# ============================================================

class DepositState(StatesGroup):
    amount = State()
    utr = State()


# ============================================================
# HELPERS
# ============================================================

async def check_maintenance(message: Message) -> bool:
    """
    Returns True when the bot is in maintenance mode and
    the user is not allowed to continue.
    """

    if not MAINTENANCE_MODE:
        return False

    async with async_session_maker() as session:
        role = await get_user_role(
            session,
            message.from_user.id
        )

        if role not in ("superadmin", "owner"):
            await message.answer(
                "🔧 Bot is currently in maintenance mode.\n"
                "Please try again later."
            )
            return True

    return False


async def get_user(session, tg_id: int):
    result = await session.execute(
        select(User).where(User.tg_id == tg_id)
    )
    return result.scalar_one_or_none()


# ============================================================
# START
# ============================================================

@router.message(Command("start"))
async def cmd_start(message: Message):
    if await check_maintenance(message):
        return

    args = message.text.split(maxsplit=1) if message.text else []
    ref_code = args[1].strip() if len(args) > 1 else None

    async with async_session_maker() as session:

        user = await get_user(
            session,
            message.from_user.id
        )

        # ----------------------------------------------------
        # CREATE USER
        # ----------------------------------------------------

        if not user:

            referred_by = None

            if ref_code and ref_code.isdigit():
                referred_by = int(ref_code)

                # Prevent self-referral
                if referred_by == message.from_user.id:
                    referred_by = None

            user = User(
                tg_id=message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name,
                referred_by=referred_by,
            )

            session.add(user)

            await session.flush()

            await log_event(
                session,
                "user_registered",
                user.tg_id,
                None,
                "new user",
            )

            await session.commit()

            await send_log_message(
                message.bot,
                f"🆕 New user: {user.tg_id}"
            )

        # ----------------------------------------------------
        # FORCE JOIN
        # ----------------------------------------------------

        channels = await get_required_channels(session)

        if channels:

            joined, missing = await check_force_join(
                message.bot,
                message.from_user.id,
                channels,
            )

            if not joined:

                await message.answer(
                    "👋 Welcome!\n\n"
                    "Please join all required channels "
                    "and then press Verify.",
                    reply_markup=force_join_keyboard(missing),
                )

                return

        # ----------------------------------------------------
        # REFERRAL REWARD
        # ----------------------------------------------------

        if (
            user.referred_by
            and not user.referral_rewarded
        ):

            await grant_referral_reward(
                session,
                user
            )

            await session.commit()

            await send_log_message(
                message.bot,
                f"🎁 Referral reward for {user.tg_id}"
            )

        # ----------------------------------------------------
        # MAIN MENU
        # ----------------------------------------------------

        await message.answer(
            "🏠 Welcome back!\n\n"
            "Use the menu below.",
            reply_markup=main_menu_keyboard(),
        )

        await log_event(
            session,
            "user_started",
            user.tg_id,
            None,
            None,
        )

        await session.commit()


# ============================================================
# FORCE JOIN VERIFY
# ============================================================

@router.callback_query(F.data == "force_verify")
async def cb_force_verify(callback: CallbackQuery):

    async with async_session_maker() as session:

        user = await get_user(
            session,
            callback.from_user.id
        )

        if not user:

            await callback.answer(
                "User not found.",
                show_alert=True,
            )

            return

        channels = await get_required_channels(session)

        if not channels:

            await callback.answer(
                "No required channels.",
                show_alert=True,
            )

            await callback.message.edit_text(
                "✅ All channels verified.\n\n"
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
                "You have not joined all required channels.",
                show_alert=True,
            )

            await callback.message.edit_text(
                "❌ You haven't joined all required channels yet.",
                reply_markup=force_join_keyboard(missing),
            )

            return

        if (
            user.referred_by
            and not user.referral_rewarded
        ):

            await grant_referral_reward(
                session,
                user
            )

            await session.commit()

            await send_log_message(
                callback.bot,
                f"🎁 Referral reward for {user.tg_id}"
            )

        await callback.answer(
            "Verification successful!"
        )

        await callback.message.edit_text(
            "✅ Verification successful!\n\n"
            "Use the menu below.",
            reply_markup=main_menu_keyboard(),
        )


# ============================================================
# HOME
# ============================================================

@router.callback_query(F.data == "menu_home")
async def cb_home(callback: CallbackQuery):

    await callback.answer()

    await callback.message.edit_text(
        "🏠 Main menu:",
        reply_markup=main_menu_keyboard(),
    )


# ============================================================
# PROFILE
# ============================================================

@router.callback_query(F.data == "user_profile")
async def cb_profile(callback: CallbackQuery):

    async with async_session_maker() as session:

        user = await get_user(
            session,
            callback.from_user.id
        )

        if not user:

            await callback.answer(
                "User not found.",
                show_alert=True,
            )

            return

        name = " ".join(
            x
            for x in (
                user.first_name,
                user.last_name,
            )
            if x
        ) or "N/A"

        username = (
            f"@{user.username}"
            if user.username
            else "N/A"
        )

        text = (
            "👤 PROFILE\n\n"
            f"🆔 ID: {user.tg_id}\n"
            f"👤 Name: {name}\n"
            f"🔗 Username: {username}\n"
            f"💰 Balance: {user.balance}\n"
            f"👥 Referred by: "
            f"{user.referred_by or 'None'}"
        )

        await callback.answer()

        await callback.message.edit_text(
            text,
            reply_markup=back_home_keyboard(),
        )


# ============================================================
# BALANCE
# ============================================================

@router.callback_query(F.data == "user_balance")
async def cb_balance(callback: CallbackQuery):

    async with async_session_maker() as session:

        user = await get_user(
            session,
            callback.from_user.id
        )

        if not user:

            await callback.answer(
                "User not found.",
                show_alert=True,
            )

            return

        await callback.answer()

        await callback.message.edit_text(
            f"💰 Your balance: {user.balance}",
            reply_markup=back_home_keyboard(),
        )


# ============================================================
# PRODUCTS
# ============================================================

@router.callback_query(F.data == "user_products")
async def cb_products(callback: CallbackQuery):

    async with async_session_maker() as session:

        result = await session.execute(
            select(Category).where(
                Category.is_active.is_(True)
            )
        )

        categories = result.scalars().all()

        await callback.answer()

        await callback.message.edit_text(
            "🛍 Choose a category:",
            reply_markup=categories_keyboard(categories),
        )


# ============================================================
# CATEGORY
# ============================================================

@router.callback_query(F.data.startswith("cat_"))
async def cb_category(callback: CallbackQuery):

    try:
        cat_id = int(
            callback.data[len("cat_"):]
        )

    except (ValueError, TypeError):

        await callback.answer(
            "Invalid category.",
            show_alert=True,
        )

        return

    async with async_session_maker() as session:

        result = await session.execute(
            select(Account).where(
                Account.category_id == cat_id,
                Account.status == "available",
            )
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
            "🛒 Select an account to buy:",
            reply_markup=accounts_keyboard(accounts),
        )


# ============================================================
# BUY ACCOUNT
# ============================================================

@router.callback_query(F.data.startswith("buy_acc_"))
async def cb_buy_account(callback: CallbackQuery):

    try:
        acc_id = int(
            callback.data[len("buy_acc_"):]
        )

    except (ValueError, TypeError):

        await callback.answer(
            "Invalid account.",
            show_alert=True,
        )

        return

    async with async_session_maker() as session:

        user = await get_user(
            session,
            callback.from_user.id
        )

        if not user:

            await callback.answer(
                "User not found.",
                show_alert=True,
            )

            return

        account = await session.get(
            Account,
            acc_id
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

        # ----------------------------------------------------
        # RESERVE + BUY
        # ----------------------------------------------------

        ok, msg, price = await reserve_and_buy_account(
            session,
            user,
            account,
        )

        if not ok:

            await fail_purchase(
                session,
                user,
                account,
                price or 0.0,
            )

            await session.commit()

            await callback.answer(
                msg,
                show_alert=True,
            )

            return

        # ----------------------------------------------------
        # COMPLETE PURCHASE
        # ----------------------------------------------------

        await complete_purchase(
            session,
            user,
            account,
            price,
        )

        await session.commit()

        await callback.answer(
            "Purchase successful!"
        )

        await callback.message.edit_text(
            "✅ PURCHASE SUCCESSFUL\n\n"
            f"🆔 Account: #{account.id}\n"
            f"💰 Price: {price}\n"
            f"📱 Phone: {account.phone}",
            reply_markup=back_home_keyboard(),
        )

        await send_log_message(
            callback.bot,
            f"🛒 Purchase: user "
            f"{user.tg_id} "
            f"account #{account.id}"
        )


# ============================================================
# DEPOSIT MENU
# ============================================================

@router.callback_query(F.data == "user_deposit")
async def cb_deposit_menu(callback: CallbackQuery):

    await callback.answer()

    await callback.message.edit_text(
        "💳 DEPOSIT\n\n"
        "Enter amount to deposit:",
        reply_markup=deposit_amount_keyboard(),
    )


# ============================================================
# /deposit
# ============================================================

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


# ============================================================
# DEPOSIT AMOUNT
# ============================================================

@router.message(
    StateFilter(DepositState.amount)
)
async def deposit_amount(
    message: Message,
    state: FSMContext,
):

    try:

        amount = float(
            (message.text or "").strip()
        )

    except (ValueError, TypeError):

        await message.answer(
            "❌ Invalid amount.\n"
            "Send a valid number."
        )

        return

    if amount <= 0:

        await message.answer(
            "❌ Amount must be greater than 0."
        )

        return

    await state.update_data(
        amount=amount
    )

    await message.answer(
        "🔢 Send the UTR number for this deposit:"
    )

    await state.set_state(
        DepositState.utr
    )


# ============================================================
# DEPOSIT UTR
# ============================================================

@router.message(
    StateFilter(DepositState.utr)
)
async def deposit_utr(
    message: Message,
    state: FSMContext,
):

    utr = (message.text or "").strip()

    if not utr:

        await message.answer(
            "❌ UTR cannot be empty."
        )

        return

    data = await state.get_data()

    amount = data.get("amount")

    if amount is None:

        await state.clear()

        await message.answer(
            "❌ Deposit session expired.\n"
            "Please use /deposit again."
        )

        return

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
                "⚠️ You already have 5 pending deposits."
            )

            await state.clear()

            return

        # ----------------------------------------------------
        # CREATE DEPOSIT
        # ----------------------------------------------------

        expires_at = (
            datetime.utcnow()
            + timedelta(minutes=30)
        )

        deposit = DepositRequest(
            user_tg_id=message.from_user.id,
            amount=amount,
            utr=utr,
            expires_at=expires_at,
            status="pending",
        )

        session.add(deposit)

        await session.commit()

        await message.answer(
            "✅ Deposit request created.\n\n"
            f"💰 Amount: {amount}\n"
            f"🔢 UTR: {utr}\n\n"
            "⏳ Waiting for admin approval."
        )

        keyboard = approve_deposit_keyboard(
            deposit.id
        )

        await send_log_message(
            message.bot,
            f"💳 Deposit request\n"
            f"User: {message.from_user.id}\n"
            f"Amount: {amount}\n"
            f"UTR: {utr}"
        )

        if LOG_CHANNEL_ID:

            try:

                await message.bot.send_message(
                    LOG_CHANNEL_ID,
                    "💳 DEPOSIT REQUEST\n\n"
                    f"👤 User: {message.from_user.id}\n"
                    f"💰 Amount: {amount}\n"
                    f"🔢 UTR: {utr}",
                    reply_markup=keyboard,
                )

            except Exception as exc:

                print(
                    "Could not send deposit log:",
                    exc
                )

        await state.clear()


# ============================================================
# APPROVE DEPOSIT
# ============================================================

@router.callback_query(
    F.data.startswith("deposit_approve_")
)
async def cb_deposit_approve(
    callback: CallbackQuery,
):

    try:

        dep_id = int(
            callback.data[
                len("deposit_approve_"):
            ]
        )

    except (ValueError, TypeError):

        await callback.answer(
            "Invalid deposit.",
            show_alert=True,
        )

        return

    async with async_session_maker() as session:

        role = await get_user_role(
            session,
            callback.from_user.id
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
            dep_id
        )

        if not deposit:

            await callback.answer(
                "Deposit not found.",
                show_alert=True,
            )

            return

        if deposit.status != "pending":

            await callback.answer(
                "Deposit is already processed.",
                show_alert=True,
            )

            return

        # ----------------------------------------------------
        # EXPIRATION
        # ----------------------------------------------------

        if (
            deposit.expires_at
            and deposit.expires_at <= datetime.utcnow()
        ):

            deposit.status = "expired"

            await session.commit()

            await callback.answer(
                "Deposit expired.",
                show_alert=True,
            )

            return

        user = await session.get(
            User,
            deposit.user_tg_id
        )

        if not user:

            await callback.answer(
                "User not found.",
                show_alert=True,
            )

            return

        # ----------------------------------------------------
        # APPROVE
        # ----------------------------------------------------

        user.balance += deposit.amount

        deposit.status = "approved"

        deposit.approved_by = (
            callback.from_user.id
        )

        transaction = Transaction(
            user_tg_id=user.tg_id,
            amount=deposit.amount,
            type="deposit",
            description=(
                f"Deposit approved: "
                f"UTR {deposit.utr}"
            ),
        )

        session.add(transaction)

        await session.commit()

        await callback.answer(
            "Deposit approved!"
        )

        try:

            await callback.message.edit_text(
                "✅ DEPOSIT APPROVED\n\n"
                f"💰 Amount: {deposit.amount}\n"
                f"👤 User: {user.tg_id}\n"
                f"👮 Approved by: "
                f"{callback.from_user.id}"
            )

        except Exception:
            pass

        await send_log_message(
            callback.bot,
            f"✅ Deposit approved\n"
            f"User: {user.tg_id}\n"
            f"Amount: {deposit.amount}\n"
            f"By: {callback.from_user.id}"
        )

        try:

            await callback.bot.send_message(
                user.tg_id,
                "✅ Your deposit has been approved!\n\n"
                f"💰 Amount: {deposit.amount}\n"
                f"🔢 UTR: {deposit.utr}"
            )

        except Exception as exc:

            print(
                "Could not notify deposit user:",
                exc
            )


# ============================================================
# REJECT DEPOSIT
# ============================================================

@router.callback_query(
    F.data.startswith("deposit_reject_")
)
async def cb_deposit_reject(
    callback: CallbackQuery,
):

    try:

        dep_id = int(
            callback.data[
                len("deposit_reject_"):
            ]
        )

    except (ValueError, TypeError):

        await callback.answer(
            "Invalid deposit.",
            show_alert=True,
        )

        return

    async with async_session_maker() as session:

        role = await get_user_role(
            session,
            callback.from_user.id
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
            dep_id
        )

        if not deposit:

            await callback.answer(
                "Deposit not found.",
                show_alert=True,
            )

            return

        if deposit.status != "pending":

            await callback.answer(
                "Deposit is already processed.",
                show_alert=True,
            )

            return

        if (
            deposit.expires_at
            and deposit.expires_at <= datetime.utcnow()
        ):

            deposit.status = "expired"

            await session.commit()

            await callback.answer(
                "Deposit expired.",
                show_alert=True,
            )

            return

        user = await session.get(
            User,
            deposit.user_tg_id
        )

        if not user:

            await callback.answer(
                "User not found.",
                show_alert=True,
            )

            return

        # ----------------------------------------------------
        # REJECT
        # ----------------------------------------------------

        deposit.status = "rejected"

        deposit.approved_by = (
            callback.from_user.id
        )

        await session.commit()

        await callback.answer(
            "Deposit rejected."
        )

        try:

            await callback.message.edit_text(
                "❌ DEPOSIT REJECTED\n\n"
                f"💰 Amount: {deposit.amount}\n"
                f"👤 User: {user.tg_id}\n"
                f"👮 Rejected by: "
                f"{callback.from_user.id}"
            )

        except Exception:
            pass

        await send_log_message(
            callback.bot,
            f"❌ Deposit rejected\n"
            f"User: {user.tg_id}\n"
            f"Amount: {deposit.amount}\n"
            f"By: {callback.from_user.id}"
        )

        try:

            await callback.bot.send_message(
                user.tg_id,
                "❌ Your deposit has been rejected.\n\n"
                f"💰 Amount: {deposit.amount}\n"
                f"🔢 UTR: {deposit.utr}"
            )

        except Exception as exc:

            print(
                "Could not notify rejected deposit user:",
                exc
            )


# ============================================================
# ADMIN PANEL
# ============================================================

@router.callback_query(F.data == "admin_panel")
async def cb_admin_panel(
    callback: CallbackQuery,
):

    async with async_session_maker() as session:

        role = await get_user_role(
            session,
            callback.from_user.id
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

        await callback.answer()

        await callback.message.edit_text(
            "🛠 ADMIN PANEL",
            reply_markup=admin_panel_keyboard(),
        )


# ============================================================
# /admin
# ============================================================

@router.message(Command("admin"))
async def cmd_admin(message: Message):

    if await check_maintenance(message):
        return

    async with async_session_maker() as session:

        role = await get_user_role(
            session,
            message.from_user.id
        )

        if role not in (
            "admin",
            "superadmin",
            "owner",
        ):

            await message.answer(
                "❌ Access denied."
            )

            return

        await message.answer(
            "🛠 ADMIN PANEL",
            reply_markup=admin_panel_keyboard(),
        )


# ============================================================
# /dfchat
# ============================================================

@router.message(Command("dfchat"))
async def cmd_dfchat(message: Message):

    async with async_session_maker() as session:

        role = await get_user_role(
            session,
            message.from_user.id
        )

        if role not in (
            "superadmin",
            "owner",
        ):

            await message.answer(
                "❌ Access denied."
            )

            return

    await message.answer(
        "👑 SUPERADMIN / OWNER COMMANDS\n\n"

        "👮 Admin:\n"
        "/addadmin\n"
        "/removeadmin\n"
        "/addsuperadmin\n"
        "/removesuperadmin\n\n"

        "💰 Balance:\n"
        "/addbalance\n"
        "/removebalance\n\n"

        "🚫 Users:\n"
        "/ban\n"
        "/unban\n\n"

        "📢 System:\n"
        "/broadcast\n"
        "/maintenance\n\n"

        "🛍 Products:\n"
        "/addcategory\n"
        "/editcategory\n"
        "/deletecategory\n"
        "/addaccount\n"
        "/editaccount\n"
        "/deleteaccount\n\n"

        "📢 Channels:\n"
        "/addchannel\n"
        "/removechannel\n\n"

        "🎟 Coupons:\n"
        "/addcoupon\n"
        "/editcoupon\n"
        "/deletecoupon\n\n"

        "📊 Statistics:\n"
        "/stats\n"
        "/coinslist"
    )


# ============================================================
# /addbalance
# ============================================================

@router.message(Command("addbalance"))
async def cmd_addbalance(message: Message):

    async with async_session_maker() as session:

        role = await get_user_role(
            session,
            message.from_user.id
        )

        if role not in (
            "superadmin",
            "owner",
        ):

            await message.answer(
                "❌ Access denied."
            )

            return

    args = (
        message.text.split()
        if message.text
        else []
    )

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
            "❌ Amount must be greater than 0."
        )

        return

    async with async_session_maker() as session:

        user = await session.get(
            User,
            user_id
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

        await session.commit()

        await message.answer(
            f"✅ Added {amount}.\n"
            f"👤 User: {user.tg_id}\n"
            f"💰 Previous balance: {old_balance}\n"
            f"💰 New balance: {old_balance + amount}"
        )

        await send_log_message(
            message.bot,
            f"💰 Balance added\n"
            f"User: {user.tg_id}\n"
            f"Amount: +{amount}\n"
            f"By: {message.from_user.id}"
        )


# ============================================================
# /ban
# ============================================================

@router.message(Command("ban"))
async def cmd_ban(message: Message):

    async with async_session_maker() as session:

        role = await get_user_role(
            session,
            message.from_user.id
        )

        if role not in (
            "admin",
            "superadmin",
            "owner",
        ):

            await message.answer(
                "❌ Access denied."
            )

            return

    args = (
        message.text.split()
        if message.text
        else []
    )

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
        " ".join(args[2:])
        if len(args) > 2
        else "No reason"
    )

    async with async_session_maker() as session:

        user = await session.get(
            User,
            user_id
        )

        if not user:

            await message.answer(
                "❌ User not found."
            )

            return

        user.is_banned = True
        user.ban_reason = reason
        user.ban_until = None

        await session.commit()

        await message.answer(
            f"🚫 User banned.\n\n"
            f"User: {user.tg_id}\n"
            f"Reason: {reason}"
        )

        await send_log_message(
            message.bot,
            f"🚫 Ban\n"
            f"User: {user.tg_id}\n"
            f"By: {message.from_user.id}\n"
            f"Reason: {reason}"
        )


# ============================================================
# /unban
# ============================================================

@router.message(Command("unban"))
async def cmd_unban(message: Message):

    async with async_session_maker() as session:

        role = await get_user_role(
            session,
            message.from_user.id
        )

        if role not in (
            "admin",
            "superadmin",
            "owner",
        ):

            await message.answer(
                "❌ Access denied."
            )

            return

    args = (
        message.text.split()
        if message.text
        else []
    )

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
            user_id
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
            f"✅ User {user.tg_id} has been unbanned."
        )

        await send_log_message(
            message.bot,
            f"✅ Unban\n"
            f"User: {user.tg_id}\n"
            f"By: {message.from_user.id}"
        )


# ============================================================
# /stats
# ============================================================

@router.message(Command("stats"))
async def cmd_stats(message: Message):

    async with async_session_maker() as session:

        role = await get_user_role(
            session,
            message.from_user.id
        )

        if role not in (
            "admin",
            "superadmin",
            "owner",
        ):

            await message.answer(
                "❌ Access denied."
            )

            return

        users = (
            await session.execute(
                select(User)
            )
        ).scalars().all()

        deposits = (
            await session.execute(
                select(DepositRequest)
            )
        ).scalars().all()

        purchases = (
            await session.execute(
                select(Purchase)
            )
        ).scalars().all()

        accounts = (
            await session.execute(
                select(Account).where(
                    Account.status == "available"
                )
            )
        ).scalars().all()

        banned_users = (
            await session.execute(
                select(User).where(
                    User.is_banned.is_(True)
                )
            )
        ).scalars().all()

        await message.answer(
            "📊 BOT STATISTICS\n\n"
            f"👥 Total users: {len(users)}\n"
            f"💳 Total deposits: {len(deposits)}\n"
            f"🛒 Total purchases: {len(purchases)}\n"
            f"📦 Available accounts: {len(accounts)}\n"
            f"🚫 Banned users: {len(banned_users)}"
        )


# ============================================================
# ERROR HANDLER
# ============================================================

@router.errors()
async def error_handler(
    event,
    exception,
):

    print(
        f"[BOT ERROR] {type(exception).__name__}: "
        f"{exception}"
    )

    return True
