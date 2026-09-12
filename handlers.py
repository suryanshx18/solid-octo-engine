from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from database import (
    async_session_maker, User, Admin, Category, Account,
    DepositRequest, RequiredChannel, Coupon, BotSetting, LogEntry, Purchase, Transaction
)
from keyboards import (
    main_menu_keyboard, categories_keyboard, accounts_keyboard,
    force_join_keyboard, admin_panel_keyboard, approve_deposit_keyboard,
    back_home_keyboard, deposit_amount_keyboard
)
from services import (
    get_required_channels, check_force_join, grant_referral_reward,
    apply_coupon, reserve_and_buy_account, complete_purchase, fail_purchase,
    expire_pending_deposits, log_event, send_log_message,
    add_balance, remove_balance, get_setting, set_setting, get_user_role,
    NL,
)
from config import OWNER_ID, MAINTENANCE_MODE, LOG_CHANNEL_ID
from datetime import datetime, timedelta

router = Router()


class DepositState(StatesGroup):
    amount = State()
    utr = State()


async def check_maintenance(message: Message) -> bool:
    if MAINTENANCE_MODE:
        async with async_session_maker() as session:
            role = await get_user_role(session, message.from_user.id)
            if role not in ("superadmin", "owner"):
                await message.answer("Bot is in maintenance mode. Try later.")
                return True
    return False


@router.message(Command("start"))
async def cmd_start(message: Message):
    if await check_maintenance(message):
        return
    args = message.text.split(maxsplit=1)
    ref_code = args[1] if len(args) > 1 else None
    async with async_session_maker() as session:
        stmt = select(User).where(User.tg_id == message.from_user.id)
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()
        if not user:
            user = User(
                tg_id=message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name,
                referred_by=int(ref_code) if ref_code and ref_code.isdigit() else None,
            )
            session.add(user)
            await session.commit()
            await log_event(session, "user_registered", user.tg_id, None, "new user")
            await send_log_message(message.bot, "New user: " + str(user.tg_id))
        channels = await get_required_channels(session)
        if channels:
            joined, missing = await check_force_join(message.bot, message.from_user.id, channels)
            if not joined:
                kb = force_join_keyboard(missing)
                await message.answer("Welcome! Please join all required channels and press Verify.", reply_markup=kb)
                return
        if user.referred_by and not user.referral_rewarded:
            await grant_referral_reward(session, user)
            await send_log_message(message.bot, "Referral reward for " + str(user.tg_id))
        await message.answer("Welcome back! Use the menu below.", reply_markup=main_menu_keyboard())
        await log_event(session, "user_started", user.tg_id, None, None)


@router.callback_query(F.data == "force_verify")
async def cb_force_verify(callback: CallbackQuery):
    async with async_session_maker() as session:
        stmt = select(User).where(User.tg_id == callback.from_user.id)
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()
        if not user:
            await callback.answer("User not found.", show_alert=True)
            return
        channels = await get_required_channels(session)
        if not channels:
            await callback.answer("No required channels.", show_alert=True)
            await callback.message.edit_text("All channels verified. Use the menu below.", reply_markup=main_menu_keyboard())
            return
        joined, missing = await check_force_join(callback.bot, callback.from_user.id, channels)
        if not joined:
            kb = force_join_keyboard(missing)
            await callback.message.edit_text("You haven't joined all channels yet.", reply_markup=kb)
            return
        if user.referred_by and not user.referral_rewarded:
            await grant_referral_reward(session, user)
            await send_log_message(callback.bot, "Referral reward for " + str(user.tg_id))
        await callback.message.edit_text("Verification successful! Use the menu below.", reply_markup=main_menu_keyboard())


@router.callback_query(F.data == "menu_home")
async def cb_home(callback: CallbackQuery):
    await callback.message.edit_text("Main menu:", reply_markup=main_menu_keyboard())


@router.callback_query(F.data == "user_profile")
async def cb_profile(callback: CallbackQuery):
    async with async_session_maker() as session:
        stmt = select(User).where(User.tg_id == callback.from_user.id)
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()
        if not user:
            await callback.answer("User not found.", show_alert=True)
            return

        lines = []
        lines.append("Profile")
        lines.append("ID: " + str(user.tg_id))
        name_part = ""
        if user.first_name:
            name_part += user.first_name
        if user.last_name:
            if name_part:
                name_part += " "
            name_part += user.last_name
        lines.append("Name: " + (name_part if name_part else "N/A"))
        lines.append("Username: @" + (user.username if user.username else "N/A"))
        lines.append("Balance: " + str(user.balance))
        lines.append("Referred by: " + (str(user.referred_by) if user.referred_by else "None"))

        text = NL().join(lines)

        await callback.message.edit_text(text, reply_markup=back_home_keyboard())


@router.callback_query(F.data == "user_balance")
async def cb_balance(callback: CallbackQuery):
    async with async_session_maker() as session:
        stmt = select(User).where(User.tg_id == callback.from_user.id)
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()
        if not user:
            await callback.answer("User not found.", show_alert=True)
            return
        await callback.message.edit_text("Your balance: " + str(user.balance), reply_markup=back_home_keyboard())


@router.callback_query(F.data == "user_products")
async def cb_products(callback: CallbackQuery):
    async with async_session_maker() as session:
        stmt = select(Category).where(Category.is_active == True)
        res = await session.execute(stmt)
        cats = res.scalars().all()
        await callback.message.edit_text("Choose a category:", reply_markup=categories_keyboard(cats))


@router.callback_query(F.data.startswith("cat_"))
async def cb_category(callback: CallbackQuery):
    cat_id = int(callback.data.split("_")[1])
    async with async_session_maker() as session:
        stmt = select(Account).where(Account.category_id == cat_id, Account.status == "available")
        res = await session.execute(stmt)
        accs = res.scalars().all()
        if not accs:
            await callback.answer("No accounts available.", show_alert=True)
            return
        kb = accounts_keyboard(accs)
        await callback.message.edit_text("Select an account to buy:", reply_markup=kb)


@router.callback_query(F.data.startswith("buy_acc_"))
async def cb_buy_account(callback: CallbackQuery):
    acc_id = int(callback.data.split("_")[3])
    async with async_session_maker() as session:
        stmt = select(User).where(User.tg_id == callback.from_user.id)
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()
        if not user:
            await callback.answer("User not found.", show_alert=True)
            return
        stmt = select(Account).where(Account.id == acc_id)
        res = await session.execute(stmt)
        account = res.scalar_one_or_none()
        if not account or account.status != "available":
            await callback.answer("Account no longer available.", show_alert=True)
            return
        ok, msg, price = await reserve_and_buy_account(session, user, account)
        if not ok:
            await fail_purchase(session, user, account, price if price else 0.0)
            await callback.answer(msg, show_alert=True)
            return
        await complete_purchase(session, user, account, price)
        await session.commit()
        t1 = "Purchase successful! Account #"
        t2 = str(account.id)
        t3 = " bought for "
        t4 = str(price)
        t5 = ". Phone: "
        t6 = str(account.phone)
        text = t1 + t2 + t3 + t4 + t5 + t6
        await callback.message.edit_text(text, reply_markup=back_home_keyboard())
        await send_log_message(callback.bot, "Purchase: user " + str(user.tg_id) + " account #" + str(account.id))


@router.callback_query(F.data == "user_deposit")
async def cb_deposit_menu(callback: CallbackQuery):
    lines = []
    lines.append("Deposit")
    lines.append("Enter amount to deposit:")
    text = NL().join(lines)
    await callback.message.edit_text(text, reply_markup=deposit_amount_keyboard())


@router.message(Command("deposit"))
async def cmd_deposit(message: Message):
    if await check_maintenance(message):
        return
    lines = []
    lines.append("Deposit")
    lines.append("Enter amount to deposit:")
    text = NL().join(lines)
    await message.answer(text)
    await message.state.set_state(DepositState.amount)


@router.message(StateFilter(DepositState.amount))
async def deposit_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.strip())
        if amount <= 0:
            await message.answer("Invalid amount. Send a positive number.")
            return
    except ValueError:
        await message.answer("Invalid amount. Send a number.")
        return
    await state.update_data(amount=amount)
    await message.answer("Send UTR number for this deposit:")
    await message.state.set_state(DepositState.utr)


@router.message(StateFilter(DepositState.utr))
async def deposit_utr(message: Message, state: FSMContext):
    utr = message.text.strip()
    if not utr:
        await message.answer("UTR cannot be empty.")
        return
    data = await state.get_data()
    amount = data["amount"]
    async with async_session_maker() as session:
        stmt = select(DepositRequest).where(
            DepositRequest.user_tg_id == message.from_user.id,
            DepositRequest.status == "pending"
        )
        res = await session.execute(stmt)
        pending = res.scalars().all()
        if len(pending) >= 5:
            await message.answer("You already have 5 pending deposits.")
            await state.clear()
            return
        expires_at = datetime.utcnow() + timedelta(minutes=30)
        dep = DepositRequest(
            user_tg_id=message.from_user.id,
            amount=amount,
            utr=utr,
            expires_at=expires_at
        )
        session.add(dep)
        await session.commit()
        m1 = "Deposit request created: "
        m2 = str(amount)
        m3 = ", UTR: "
        m4 = utr
        m5 = ". Waiting for approval."
        await message.answer(m1 + m2 + m3 + m4 + m5)
        kb = approve_deposit_keyboard(dep.id)
        log1 = "Deposit request: user "
        log2 = str(message.from_user.id)
        log3 = ", "
        log4 = str(amount)
        log5 = ", UTR: "
        log6 = utr
        await send_log_message(message.bot, log1 + log2 + log3 + log4 + log5 + log6)
        if LOG_CHANNEL_ID:
            try:
                lines = []
                lines.append("Deposit request")
                lines.append("User: " + str(message.from_user.id))
                lines.append("Amount: " + str(amount))
                lines.append("UTR: " + utr)
                full = NL().join(lines)
                await message.bot.send_message(
                    LOG_CHANNEL_ID,
                    full,
                    reply_markup=kb
                )
            except Exception:
                pass
        await state.clear()


@router.callback_query(F.data.startswith("deposit_approve_"))
async def cb_deposit_approve(callback: CallbackQuery):
    dep_id = int(callback.data.split("_")[3])
    async with async_session_maker() as session:
        role = await get_user_role(session, callback.from_user.id)
        if role not in ("superadmin", "owner", "admin"):
            await callback.answer("Access denied.", show_alert=True)
            return
        dep = await session.get(DepositRequest, dep_id)
        if not dep or dep.status != "pending":
            await callback.answer("Invalid or expired deposit.", show_alert=True)
            return
        user = await session.get(User, dep.user_tg_id)
        if not user:
            await callback.answer("User not found.", show_alert=True)
            return
        user.balance += dep.amount
        dep.status = "approved"
        dep.approved_by = callback.from_user.id
        txn = Transaction(user_tg_id=user.tg_id, amount=dep.amount, type="deposit", description="Deposit approved: UTR " + dep.utr)
        session.add(txn)
        await session.commit()
        r1 = "Deposit approved: "
        r2 = str(dep.amount)
        r3 = " added to user "
        r4 = str(user.tg_id)
        r5 = "."
        await callback.message.edit_text(r1 + r2 + r3 + r4 + r5)
        l1 = "Deposit approved: user "
        l2 = str(user.tg_id)
        l3 = ", "
        l4 = str(dep.amount)
        l5 = ", by "
        l6 = str(callback.from_user.id)
        await send_log_message(callback.bot, l1 + l2 + l3 + l4 + l5 + l6)
        try:
            n1 = "Your deposit of "
            n2 = str(dep.amount)
            n3 = " (UTR: "
            n4 = dep.utr
            n5 = ") has been approved."
            await callback.bot.send_message(user.tg_id, n1 + n2 + n3 + n4 + n5)
        except Exception:
            pass


@router.callback_query(F.data.startswith("deposit_reject_"))
async def cb_deposit_reject(callback: CallbackQuery):
    dep_id = int(callback.data.split("_")[3])
    async with async_session_maker() as session:
        role = await get_user_role(session, callback.from_user.id)
        if role not in ("superadmin", "owner", "admin"):
            await callback.answer("Access denied.", show_alert=True)
            return
        dep = await session.get(DepositRequest, dep_id)
        if not dep or dep.status != "pending":
            await callback.answer("Invalid or expired deposit.", show_alert=True)
            return
        user = await session.get(User, dep.user_tg_id)
        dep.status = "rejected"
        dep.approved_by = callback.from_user.id
        await session.commit()
        j1 = "Deposit rejected: "
        j2 = str(dep.amount)
        j3 = " for user "
        j4 = str(user.tg_id)
        j5 = "."
        await callback.message.edit_text(j1 + j2 + j3 + j4 + j5)
        k1 = "Deposit rejected: user "
        k2 = str(user.tg_id)
        k3 = ", "
        k4 = str(dep.amount)
        k5 = ", by "
        k6 = str(callback.from_user.id)
        await send_log_message(callback.bot, k1 + k2 + k3 + k4 + k5 + k6)
        try:
            q1 = "Your deposit of "
            q2 = str(dep.amount)
            q3 = " (UTR: "
            q4 = dep.utr
            q5 = ") has been rejected."
            await callback.bot.send_message(user.tg_id, q1 + q2 + q3 + q4 + q5)
        except Exception:
            pass


@router.callback_query(F.data == "admin_panel")
async def cb_admin_panel(callback: CallbackQuery):
    async with async_session_maker() as session:
        role = await get_user_role(session, callback.from_user.id)
        if role not in ("admin", "superadmin", "owner"):
            await callback.answer("Access denied.", show_alert=True)
            return
        await callback.message.edit_text("Admin panel:", reply_markup=admin_panel_keyboard())


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if await check_maintenance(message):
        return
    async with async_session_maker() as session:
        role = await get_user_role(session, message.from_user.id)
        if role not in ("admin", "superadmin", "owner"):
            await message.answer("Access denied.")
            return
        await message.answer("Admin panel:", reply_markup=admin_panel_keyboard())


@router.message(Command("dfchat"))
async def cmd_dfchat(message: Message):
    async with async_session_maker() as session:
        role = await get_user_role(session, message.from_user.id)
        if role not in ("superadmin", "owner"):
            await message.answer("Access denied.")
            return
    text = "Superadmin and Owner Commands: /addadmin, /removeadmin, /addsuperadmin, /removesuperadmin (owner only), /addbalance, /removebalance, /ban, /unban, /broadcast, /addcategory, /editcategory, /deletecategory, /addaccount, /editaccount, /deleteaccount, /addchannel, /removechannel, /addcoupon, /editcoupon, /deletecoupon, /stats, /coinslist, /maintenance"
    await message.answer(text)


@router.message(Command("addbalance"))
async def cmd_addbalance(message: Message):
    async with async_session_maker() as session:
        role = await get_user_role(session, message.from_user.id)
        if role not in ("superadmin", "owner"):
            await message.answer("Access denied.")
            return
    args = message.text.split()
    if len(args) != 3:
        await message.answer("Usage: /addbalance <user_id> <amount>")
        return
    try:
        user_id = int(args[1])
        amount = float(args[2])
    except ValueError:
        await message.answer("Invalid user_id or amount.")
        return
    async with async_session_maker() as session:
        user = await session.get(User, user_id)
        if not user:
            await message.answer("User not found.")
            return
        await add_balance(session, user.tg_id, amount, "Added by " + str(message.from_user.id))
        await session.commit()
        new_bal = user.balance + amount
        a1 = "Added "
        a2 = str(amount)
        a3 = " to user "
        a4 = str(user.tg_id)
        a5 = ". New balance: "
        a6 = str(new_bal)
        await message.answer(a1 + a2 + a3 + a4 + a5 + a6)
        b1 = "Add balance: user "
        b2 = str(user.tg_id)
        b3 = " +"
        b4 = str(amount)
        b5 = " by "
        b6 = str(message.from_user.id)
        await send_log_message(message.bot, b1 + b2 + b3 + b4 + b5 + b6)


@router.message(Command("ban"))
async def cmd_ban(message: Message):
    async with async_session_maker() as session:
        role = await get_user_role(session, message.from_user.id)
        if role not in ("superadmin", "owner", "admin"):
            await message.answer("Access denied.")
            return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Usage: /ban <user_id> [reason]")
        return
    try:
        user_id = int(args[1])
    except ValueError:
        await message.answer("Invalid user_id.")
        return
    reason = " ".join(args[2:]) if len(args) > 2 else "No reason"
    async with async_session_maker() as session:
        user = await session.get(User, user_id)
        if not user:
            await message.answer("User not found.")
            return
        user.is_banned = True
        user.ban_reason = reason
        user.ban_until = None
        await session.commit()
        c1 = "Banned user "
        c2 = str(user.tg_id)
        c3 = ". Reason: "
        c4 = reason
        await message.answer(c1 + c2 + c3 + c4)
        d1 = "Ban: user "
        d2 = str(user.tg_id)
        d3 = " by "
        d4 = str(message.from_user.id)
        d5 = ", reason: "
        d6 = reason
        await send_log_message(message.bot, d1 + d2 + d3 + d4 + d5 + d6)


@router.message(Command("unban"))
async def cmd_unban(message: Message):
    async with async_session_maker() as session:
        role = await get_user_role(session, message.from_user.id)
        if role not in ("superadmin", "owner", "admin"):
            await message.answer("Access denied.")
            return
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Usage: /unban <user_id>")
        return
    try:
        user_id = int(args[1])
    except ValueError:
        await message.answer("Invalid user_id.")
        return
    async with async_session_maker() as session:
        user = await session.get(User, user_id)
        if not user:
            await message.answer("User not found.")
            return
        user.is_banned = False
        user.ban_reason = None
        user.ban_until = None
        await session.commit()
        e1 = "Unbanned user "
        e2 = str(user.tg_id)
        e3 = "."
        await message.answer(e1 + e2 + e3)
        f1 = "Unban: user "
        f2 = str(user.tg_id)
        f3 = " by "
        f4 = str(message.from_user.id)
        await send_log_message(message.bot, f1 + f2 + f3 + f4)


@router.message(Command("makeowner"))
async def cmd_makeowner(message: Message):
    # ONE-TIME OWNER MAKER – remove or guard this after first use
    async with async_session_maker() as session:
        tg_id = message.from_user.id

        result = await session.execute(
            select(Admin).where(Admin.tg_id == tg_id)
        )
        admin = result.scalar_one_or_none()

        if admin:
            admin.role = "owner"
            if hasattr(admin, "is_owner"):
                admin.is_owner = True
            if hasattr(admin, "is_superadmin"):
                admin.is_superadmin = False
        else:
            admin = Admin(
                tg_id=tg_id,
                role="owner",
            )
            if hasattr(admin, "is_owner"):
                admin.is_owner = True
            if hasattr(admin, "is_superadmin"):
                admin.is_superadmin = False
            session.add(admin)

        await session.commit()

    await message.answer("You are now owner.")


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    async with async_session_maker() as session:
        role = await get_user_role(session, message.from_user.id)
        if role not in ("superadmin", "owner", "admin"):
            await message.answer("Access denied.")
            return
        total_users = len((await session.execute(select(User))).scalars().all())
        total_deposits = len((await session.execute(select(DepositRequest))).scalars().all())
        total_purchases = len((await session.execute(select(Purchase))).scalars().all())
        available_accounts = len((await session.execute(select(Account).where(Account.status == "available"))).scalars().all())
        banned_users = len((await session.execute(select(User).where(User.is_banned == True))).scalars().all())
        lines = []
        lines.append("Stats")
        lines.append("Total users: " + str(total_users))
        lines.append("Total deposits: " + str(total_deposits))
        lines.append("Total purchases: " + str(total_purchases))
        lines.append("Available accounts: " + str(available_accounts))
        lines.append("Banned users: " + str(banned_users))
        text = NL().join(lines)
        await message.answer(text)


@router.errors()
async def error_handler(event, exception):
    print("Error:", exception)
