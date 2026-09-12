from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, update, delete
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
    add_balance, remove_balance, get_setting, set_setting, get_user_role
)
from config import OWNER_ID, MAINTENANCE_MODE, LOG_CHANNEL_ID
from datetime import datetime, timedelta

router = Router()


class DepositState(StatesGroup):
    amount = State()
    utr = State()


class BroadcastState(StatesGroup):
    text = State()


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
        text = "Profile
ID: " + str(user.tg_id) + "
Name: " + (user.first_name or "") + " " + (user.last_name or "") + "
Username: @" + (user.username or "N/A") + "
Balance: " + str(user.balance) + "
Referred by: " + (str(user.referred_by) if user.referred_by else "None")
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
        text = "Purchase successful! Account #" + str(account.id) + " bought for " + str(price) + ". Phone: " + str(account.phone)
        await callback.message.edit_text(text, reply_markup=back_home_keyboard())
        await send_log_message(callback.bot, "Purchase: user " + str(user.tg_id) + " account #" + str(account.id))


@router.callback_query(F.data == "user_deposit")
async def cb_deposit_menu(callback: CallbackQuery):
    await callback.message.edit_text("Deposit
Enter amount to deposit:", reply_markup=deposit_amount_keyboard())


@router.message(Command("deposit"))
async def cmd_deposit(message: Message):
    if await check_maintenance(message):
        return
    await message.answer("Deposit
Enter amount to deposit:")
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
    await state.set_state(DepositState.utr)


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
        await message.answer("Deposit request created: " + str(amount) + ", UTR: " + utr + ". Waiting for approval.")
        kb = approve_deposit_keyboard(dep.id)
        await send_log_message(message.bot, "Deposit request: user " + str(message.from_user.id) + ", " + str(amount) + ", UTR: " + utr)
        if LOG_CHANNEL_ID:
            try:
                await message.bot.send_message(
                    LOG_CHANNEL_ID,
                    "Deposit request
User: " + str(message.from_user.id) + "
Amount: " + str(amount) + "
UTR: " + utr,
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
        await callback.message.edit_text("Deposit approved: " + str(dep.amount) + " added to user " + str(user.tg_id) + ".")
        await send_log_message(callback.bot, "Deposit approved: user " + str(user.tg_id) + ", " + str(dep.amount) + ", by " + str(callback.from_user.id))
        try:
            await callback.bot.send_message(user.tg_id, "Your deposit of " + str(dep.amount) + " (UTR: " + dep.utr + ") has been approved.")
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
        await callback.message.edit_text("Deposit rejected: " + str(dep.amount) + " for user " + str(user.tg_id) + ".")
        await send_log_message(callback.bot, "Deposit rejected: user " + str(user.tg_id) + ", " + str(dep.amount) + ", by " + str(callback.from_user.id))
        try:
            await callback.bot.send_message(user.tg_id, "Your deposit of " + str(dep.amount) + " (UTR: " + dep.utr + ") has been rejected.")
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
    text = "Superadmin & Owner Commands:
/addadmin, /removeadmin
/addsuperadmin, /removesuperadmin (owner only)
/addbalance, /removebalance
/ban, /unban
/broadcast
/addcategory, /editcategory, /deletecategory
/addaccount, /editaccount, /deleteaccount
/addchannel, /removechannel
/addcoupon, /editcoupon, /deletecoupon
/stats, /coinslist
/maintenance"
    await message.answer(text)


@router.message(Command("coinslist"))
async def cmd_coinslist(message: Message):
    async with async_session_maker() as session:
        role = await get_user_role(session, message.from_user.id)
        if role not in ("superadmin", "owner"):
            await message.answer("Access denied.")
            return
    stmt = select(User).where(User.balance >= 2.0).order_by(User.balance.desc())
    res = await session.execute(stmt)
    users = res.scalars().all()
    lines = []
    for u in users:
        lines.append("ID: " + str(u.tg_id) + ", Balance: " + str(u.balance) + ", @" + (u.username or "N/A"))
    text = "Users with balance >= 2:
" + ("
".join(lines) if lines else "No users.")
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
        await message.answer("Added " + str(amount) + " to user " + str(user.tg_id) + ". New balance: " + str(new_bal))
        await send_log_message(message.bot, "Add balance: user " + str(user.tg_id) + " +" + str(amount) + " by " + str(message.from_user.id))


@router.message(Command("removebalance"))
async def cmd_removebalance(message: Message):
    async with async_session_maker() as session:
        role = await get_user_role(session, message.from_user.id)
        if role not in ("superadmin", "owner"):
            await message.answer("Access denied.")
            return
    args = message.text.split()
    if len(args) != 3:
        await message.answer("Usage: /removebalance <user_id> <amount>")
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
        try:
            await remove_balance(session, user.tg_id, amount, "Removed by " + str(message.from_user.id))
            await session.commit()
            new_bal = user.balance - amount
            await message.answer("Removed " + str(amount) + " from user " + str(user.tg_id) + ". New balance: " + str(new_bal))
            await send_log_message(message.bot, "Remove balance: user " + str(user.tg_id) + " -" + str(amount) + " by " + str(message.from_user.id))
        except ValueError as e:
            await message.answer(str(e))


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
        await message.answer("Banned user " + str(user.tg_id) + ". Reason: " + reason)
        await send_log_message(message.bot, "Ban: user " + str(user.tg_id) + " by " + str(message.from_user.id) + ", reason: " + reason)


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
        await message.answer("Unbanned user " + str(user.tg_id) + ".")
        await send_log_message(message.bot, "Unban: user " + str(user.tg_id) + " by " + str(message.from_user.id))


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    async with async_session_maker() as session:
        role = await get_user_role(session, message.from_user.id)
        if role not in ("superadmin", "owner"):
            await message.answer("Access denied.")
            return
    await message.answer("Send the broadcast message text:")
    await message.state.set_state(BroadcastState.text)


@router.message(StateFilter(BroadcastState.text))
async def broadcast_text(message: Message, state: FSMContext):
    text = message.text
    async with async_session_maker() as session:
        stmt = select(User.tg_id)
        res = await session.execute(stmt)
        user_ids = [r[0] for r in res.all()]
    sent = 0
    failed = 0
    for uid in user_ids:
        try:
            await message.bot.send_message(uid, text)
            sent += 1
        except Exception:
            failed += 1
    await message.answer("Broadcast done: sent=" + str(sent) + ", failed=" + str(failed))
    await send_log_message(message.bot, "Broadcast: sent=" + str(sent) + ", failed=" + str(failed) + " by " + str(message.from_user.id))
    await state.clear()


@router.message(Command("addcategory"))
async def cmd_addcategory(message: Message):
    async with async_session_maker() as session:
        role = await get_user_role(session, message.from_user.id)
        if role not in ("superadmin", "owner", "admin"):
            await message.answer("Access denied.")
            return
    args = message.text.split()
    if len(args) != 3:
        await message.answer("Usage: /addcategory <name> <rate>")
        return
    name = args[1]
    try:
        rate = float(args[2])
    except ValueError:
        await message.answer("Invalid rate.")
        return
    async with async_session_maker() as session:
        existing = await session.execute(select(Category).where(Category.name == name))
        if existing.scalar_one_or_none():
            await message.answer("Category name already exists.")
            return
        cat = Category(name=name, rate=rate)
        session.add(cat)
        await session.commit()
        await message.answer("Category added: " + name + " rate " + str(rate))
        await send_log_message(message.bot, "Add category: " + name + " rate " + str(rate) + " by " + str(message.from_user.id))


@router.message(Command("editcategory"))
async def cmd_editcategory(message: Message):
    async with async_session_maker() as session:
        role = await get_user_role(session, message.from_user.id)
        if role not in ("superadmin", "owner", "admin"):
            await message.answer("Access denied.")
            return
    args = message.text.split()
    if len(args) != 3:
        await message.answer("Usage: /editcategory <name> <new_rate>")
        return
    name = args[1]
    try:
        new_rate = float(args[2])
    except ValueError:
        await message.answer("Invalid rate.")
        return
    async with async_session_maker() as session:
        stmt = select(Category).where(Category.name == name)
        res = await session.execute(stmt)
        cat = res.scalar_one_or_none()
        if not cat:
            await message.answer("Category not found.")
            return
        cat.rate = new_rate
        await session.commit()
        await message.answer("Category updated: " + name + " rate " + str(new_rate))
        await send_log_message(message.bot, "Edit category: " + name + " rate " + str(new_rate) + " by " + str(message.from_user.id))


@router.message(Command("deletecategory"))
async def cmd_deletecategory(message: Message):
    async with async_session_maker() as session:
        role = await get_user_role(session, message.from_user.id)
        if role not in ("superadmin", "owner", "admin"):
            await message.answer("Access denied.")
            return
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Usage: /deletecategory <name>")
        return
    name = args[1]
    async with async_session_maker() as session:
        stmt = select(Category).where(Category.name == name)
        res = await session.execute(stmt)
        cat = res.scalar_one_or_none()
        if not cat:
            await message.answer("Category not found.")
            return
        acc_stmt = select(Account).where(Account.category_id == cat.id)
        acc_res = await session.execute(acc_stmt)
        if acc_res.scalars().first():
            await message.answer("Cannot delete category with existing accounts. Delete accounts first.")
            return
        await session.delete(cat)
        await session.commit()
        await message.answer("Category deleted: " + name)
        await send_log_message(message.bot, "Delete category: " + name + " by " + str(message.from_user.id))


@router.message(Command("addaccount"))
async def cmd_addaccount(message: Message):
    async with async_session_maker() as session:
        role = await get_user_role(session, message.from_user.id)
        if role not in ("superadmin", "owner", "admin"):
            await message.answer("Access denied.")
            return
    args = message.text.split()
    if len(args) != 3:
        await message.answer("Usage: /addaccount <category_id> <phone>")
        return
    try:
        cat_id = int(args[1])
    except ValueError:
        await message.answer("Invalid category_id.")
        return
    phone = args[2]
    async with async_session_maker() as session:
        cat = await session.get(Category, cat_id)
        if not cat:
            await message.answer("Category not found.")
            return
        session_data = "placeholder_session"
        acc = Account(category_id=cat_id, phone=phone, session_data=session_data, added_by=message.from_user.id)
        session.add(acc)
        await session.commit()
        await message.answer("Account added: ID " + str(acc.id) + ", category " + cat.name + ", phone " + phone)
        await send_log_message(message.bot, "Add account: ID " + str(acc.id) + ", category " + cat.name + " by " + str(message.from_user.id))


@router.message(Command("deleteaccount"))
async def cmd_deleteaccount(message: Message):
    async with async_session_maker() as session:
        role = await get_user_role(session, message.from_user.id)
        if role not in ("superadmin", "owner", "admin"):
            await message.answer("Access denied.")
            return
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Usage: /deleteaccount <account_id>")
        return
    try:
        acc_id = int(args[1])
    except ValueError:
        await message.answer("Invalid account_id.")
        return
    async with async_session_maker() as session:
        acc = await session.get(Account, acc_id)
        if not acc:
            await message.answer("Account not found.")
            return
        if acc.status != "available":
            await message.answer("Account is not available (already sold/reserved).")
            return
        await session.delete(acc)
        await session.commit()
        await message.answer("Account deleted: " + str(acc_id))
        await send_log_message(message.bot, "Delete account: " + str(acc_id) + " by " + str(message.from_user.id))


@router.message(Command("addchannel"))
async def cmd_addchannel(message: Message):
    async with async_session_maker() as session:
        role = await get_user_role(session, message.from_user.id)
        if role not in ("superadmin", "owner", "admin"):
            await message.answer("Access denied.")
            return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Usage: /addchannel <channel_id> [@username] [label]")
        return
    try:
        channel_id = int(args[1])
    except ValueError:
        await message.answer("Invalid channel_id.")
        return
    username = args[2] if len(args) > 2 else None
    label = args[3] if len(args) > 3 else None
    async with async_session_maker() as session:
        existing = await session.execute(select(RequiredChannel).where(RequiredChannel.channel_id == channel_id))
        if existing.scalar_one_or_none():
            await message.answer("Channel already exists.")
            return
        ch = RequiredChannel(channel_id=channel_id, channel_username=username, label=label)
        session.add(ch)
        await session.commit()
        await message.answer("Channel added: " + str(channel_id))
        await send_log_message(message.bot, "Add channel: " + str(channel_id) + " by " + str(message.from_user.id))


@router.message(Command("removechannel"))
async def cmd_removechannel(message: Message):
    async with async_session_maker() as session:
        role = await get_user_role(session, message.from_user.id)
        if role not in ("superadmin", "owner", "admin"):
            await message.answer("Access denied.")
            return
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Usage: /removechannel <channel_id>")
        return
    try:
        channel_id = int(args[1])
    except ValueError:
        await message.answer("Invalid channel_id.")
        return
    async with async_session_maker() as session:
        stmt = select(RequiredChannel).where(RequiredChannel.channel_id == channel_id)
        res = await session.execute(stmt)
        ch = res.scalar_one_or_none()
        if not ch:
            await message.answer("Channel not found.")
            return
        await session.delete(ch)
        await session.commit()
        await message.answer("Channel removed: " + str(channel_id))
        await send_log_message(message.bot, "Remove channel: " + str(channel_id) + " by " + str(message.from_user.id))


@router.message(Command("addcoupon"))
async def cmd_addcoupon(message: Message):
    async with async_session_maker() as session:
        role = await get_user_role(session, message.from_user.id)
        if role not in ("superadmin", "owner", "admin"):
            await message.answer("Access denied.")
            return
    args = message.text.split()
    if len(args) != 4:
        await message.answer("Usage: /addcoupon <code> <amount> <max_uses>")
        return
    code, amount_str, max_str = args[1], args[2], args[3]
    try:
        amount = float(amount_str)
        max_uses = int(max_str)
    except ValueError:
        await message.answer("Invalid amount or max_uses.")
        return
    async with async_session_maker() as session:
        existing = await session.execute(select(Coupon).where(Coupon.code == code))
        if existing.scalar_one_or_none():
            await message.answer("Coupon code already exists.")
            return
        coupon = Coupon(code=code, bonus_amount=amount, max_uses=max_uses)
        session.add(coupon)
        await session.commit()
        await message.answer("Coupon added: " + code + " amount " + str(amount) + " max_uses " + str(max_uses))
        await send_log_message(message.bot, "Add coupon: " + code + " by " + str(message.from_user.id))


@router.message(Command("editcoupon"))
async def cmd_editcoupon(message: Message):
    async with async_session_maker() as session:
        role = await get_user_role(session, message.from_user.id)
        if role not in ("superadmin", "owner", "admin"):
            await message.answer("Access denied.")
            return
    args = message.text.split()
    if len(args) != 4:
        await message.answer("Usage: /editcoupon <code> <new_amount> <new_max_uses>")
        return
    code, amount_str, max_str = args[1], args[2], args[3]
    try:
        amount = float(amount_str)
        max_uses = int(max_str)
    except ValueError:
        await message.answer("Invalid amount or max_uses.")
        return
    async with async_session_maker() as session:
        stmt = select(Coupon).where(Coupon.code == code)
        res = await session.execute(stmt)
        coupon = res.scalar_one_or_none()
        if not coupon:
            await message.answer("Coupon not found.")
            return
        coupon.bonus_amount = amount
        coupon.max_uses = max_uses
        await session.commit()
        await message.answer("Coupon updated: " + code + " amount " + str(amount) + " max_uses " + str(max_uses))
        await send_log_message(message.bot, "Edit coupon: " + code + " by " + str(message.from_user.id))


@router.message(Command("deletecoupon"))
async def cmd_deletecoupon(message: Message):
    async with async_session_maker() as session:
        role = await get_user_role(session, message.from_user.id)
        if role not in ("superadmin", "owner", "admin"):
            await message.answer("Access denied.")
            return
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Usage: /deletecoupon <code>")
        return
    code = args[1]
    async with async_session_maker() as session:
        stmt = select(Coupon).where(Coupon.code == code)
        res = await session.execute(stmt)
        coupon = res.scalar_one_or_none()
        if not coupon:
            await message.answer("Coupon not found.")
            return
        await session.delete(coupon)
        await session.commit()
        await message.answer("Coupon deleted: " + code)
        await send_log_message(message.bot, "Delete coupon: " + code + " by " + str(message.from_user.id))


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
        text = "Stats
Total users: " + str(total_users) + "
Total deposits: " + str(total_deposits) + "
Total purchases: " + str(total_purchases) + "
Available accounts: " + str(available_accounts) + "
Banned users: " + str(banned_users)
        await message.answer(text)


@router.message(Command("maintenance"))
async def cmd_maintenance(message: Message):
    async with async_session_maker() as session:
        role = await get_user_role(session, message.from_user.id)
        if role not in ("superadmin", "owner"):
            await message.answer("Access denied.")
            return
    from config import MAINTENANCE_MODE
    await message.answer("Maintenance mode toggle requested. Current env MAINTENANCE_MODE=" + str(MAINTENANCE_MODE) + ". To change, update env and restart bot.")
    await send_log_message(message.bot, "Maintenance toggle requested by " + str(message.from_user.id))


@router.message(Command("addadmin"))
async def cmd_addadmin(message: Message):
    async with async_session_maker() as session:
        role = await get_user_role(session, message.from_user.id)
        if role not in ("superadmin", "owner"):
            await message.answer("Access denied.")
            return
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Usage: /addadmin <user_id>")
        return
    try:
        user_id = int(args[1])
    except ValueError:
        await message.answer("Invalid user_id.")
        return
    async with async_session_maker() as session:
        existing = await session.execute(select(Admin).where(Admin.tg_id == user_id))
        if existing.scalar_one_or_none():
            await message.answer("User is already an admin.")
            return
        admin = Admin(tg_id=user_id, role="admin", added_by=message.from_user.id)
        session.add(admin)
        await session.commit()
        await message.answer("User " + str(user_id) + " promoted to admin.")
        await send_log_message(message.bot, "Add admin: " + str(user_id) + " by " + str(message.from_user.id))


@router.message(Command("removeadmin"))
async def cmd_removeadmin(message: Message):
    async with async_session_maker() as session:
        role = await get_user_role(session, message.from_user.id)
        if role not in ("superadmin", "owner"):
            await message.answer("Access denied.")
            return
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Usage: /removeadmin <user_id>")
        return
    try:
        user_id = int(args[1])
    except ValueError:
        await message.answer("Invalid user_id.")
        return
    async with async_session_maker() as session:
        stmt = select(Admin).where(Admin.tg_id == user_id)
        res = await session.execute(stmt)
        admin = res.scalar_one_or_none()
        if not admin:
            await message.answer("User is not an admin.")
            return
        await session.delete(admin)
        await session.commit()
        await message.answer("User " + str(user_id) + " removed from admins.")
        await send_log_message(message.bot, "Remove admin: " + str(user_id) + " by " + str(message.from_user.id))


@router.message(Command("addsuperadmin"))
async def cmd_addsuperadmin(message: Message):
    async with async_session_maker() as session:
        role = await get_user_role(session, message.from_user.id)
        if role != "owner":
            await message.answer("Only owner can add superadmins.")
            return
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Usage: /addsuperadmin <user_id>")
        return
    try:
        user_id = int(args[1])
    except ValueError:
        await message.answer("Invalid user_id.")
        return
    async with async_session_maker() as session:
        stmt = select(Admin).where(Admin.tg_id == user_id)
        res = await session.execute(stmt)
        admin = res.scalar_one_or_none()
        if admin:
            admin.role = "superadmin"
        else:
            admin = Admin(tg_id=user_id, role="superadmin", added_by=message.from_user.id)
            session.add(admin)
        await session.commit()
        await message.answer("User " + str(user_id) + " promoted to superadmin.")
        await send_log_message(message.bot, "Add superadmin: " + str(user_id) + " by " + str(message.from_user.id))


@router.message(Command("removesuperadmin"))
async def cmd_removesuperadmin(message: Message):
    async with async_session_maker() as session:
        role = await get_user_role(session, message.from_user.id)
        if role != "owner":
            await message.answer("Only owner can remove superadmins.")
            return
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Usage: /removesuperadmin <user_id>")
        return
    try:
        user_id = int(args[1])
    except ValueError:
        await message.answer("Invalid user_id.")
        return
    async with async_session_maker() as session:
        stmt = select(Admin).where(Admin.tg_id == user_id)
        res = await session.execute(stmt)
        admin = res.scalar_one_or_none()
        if not admin or admin.role != "superadmin":
            await message.answer("User is not a superadmin.")
            return
        admin.role = "admin"
        await session.commit()
        await message.answer("User " + str(user_id) + " demoted from superadmin to admin.")
        await send_log_message(message.bot, "Remove superadmin: " + str(user_id) + " by " + str(message.from_user.id))


@router.callback_query(F.data == "user_referral")
async def cb_referral(callback: CallbackQuery):
    async with async_session_maker() as session:
        stmt = select(User).where(User.tg_id == callback.from_user.id)
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()
        if not user:
            await callback.answer("User not found.", show_alert=True)
            return
        ref_link = "https://t.me/" + callback.bot.username + "?start=" + str(callback.from_user.id)
        text = "Referral
Your referral link:
" + ref_link + "
Reward: 1 for each user who joins via your link and verifies channels."
        await callback.message.edit_text(text, reply_markup=back_home_keyboard())


@router.callback_query(F.data == "user_coupon")
async def cb_coupon(callback: CallbackQuery):
    await callback.message.edit_text("Send /coupon <code> to apply a coupon.", reply_markup=back_home_keyboard())


@router.message(Command("coupon"))
async def cmd_coupon(message: Message):
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Usage: /coupon <code>")
        return
    code = args[1]
    async with async_session_maker() as session:
        stmt = select(User).where(User.tg_id == message.from_user.id)
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()
        if not user:
            await message.answer("User not found.")
            return
        ok, msg = await apply_coupon(session, user, code)
        await session.commit()
        await message.answer(msg)
        await send_log_message(message.bot, "Coupon: user " + str(user.tg_id) + ", code " + code + ", success=" + str(ok))


@router.callback_query(F.data == "user_support")
async def cb_support(callback: CallbackQuery):
    from config import SUPPORT_USERNAME
    text = "Support
Contact: @" + SUPPORT_USERNAME
    await callback.message.edit_text(text, reply_markup=back_home_keyboard())


@router.callback_query(F.data == "user_help")
async def cb_help(callback: CallbackQuery):
    text = "Help
Use the menu buttons to navigate.
For more info, contact support."
    await callback.message.edit_text(text, reply_markup=back_home_keyboard())


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    if await check_maintenance(message):
        return
    await message.answer("Main menu:", reply_markup=main_menu_keyboard())


@router.message(Command("profile"))
async def cmd_profile(message: Message):
    if await check_maintenance(message):
        return
    async with async_session_maker() as session:
        stmt = select(User).where(User.tg_id == message.from_user.id)
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()
        if not user:
            await message.answer("User not found.")
            return
        text = "Profile
ID: " + str(user.tg_id) + "
Name: " + (user.first_name or "") + " " + (user.last_name or "") + "
Username: @" + (user.username or "N/A") + "
Balance: " + str(user.balance) + "
Referred by: " + (str(user.referred_by) if user.referred_by else "None")
        await message.answer(text, reply_markup=back_home_keyboard())


@router.message(Command("purchases"))
async def cmd_purchases(message: Message):
    if await check_maintenance(message):
        return
    async with async_session_maker() as session:
        stmt = select(Purchase).where(Purchase.user_tg_id == message.from_user.id).limit(10)
        res = await session.execute(stmt)
        purchases = res.scalars().all()
        if not purchases:
            await message.answer("No purchases yet.", reply_markup=back_home_keyboard())
            return
        lines = []
        for p in purchases:
            lines.append("Account #" + str(p.account_id) + " - " + str(p.price) + " - " + str(p.created_at))
        text = "Your purchases:
" + "
".join(lines)
        await message.answer(text, reply_markup=back_home_keyboard())


@router.message(Command("transactions"))
async def cmd_transactions(message: Message):
    if await check_maintenance(message):
        return
    async with async_session_maker() as session:
        stmt = select(Transaction).where(Transaction.user_tg_id == message.from_user.id).limit(10)
        res = await session.execute(stmt)
        txns = res.scalars().all()
        if not txns:
            await message.answer("No transactions yet.", reply_markup=back_home_keyboard())
            return
        lines = []
        for t in txns:
            sign = "+" if t.amount > 0 else ""
            lines.append(t.type + ": " + sign + str(t.amount) + " - " + (t.description or "") + " - " + str(t.created_at))
        text = "Your transactions:
" + "
".join(lines)
        await message.answer(text, reply_markup=back_home_keyboard())


@router.callback_query(F.data == "user_purchases")
async def cb_user_purchases(callback: CallbackQuery):
    async with async_session_maker() as session:
        stmt = select(Purchase).where(Purchase.user_tg_id == callback.from_user.id).limit(10)
        res = await session.execute(stmt)
        purchases = res.scalars().all()
        if not purchases:
            await callback.message.edit_text("No purchases yet.", reply_markup=back_home_keyboard())
            return
        lines = []
        for p in purchases:
            lines.append("Account #" + str(p.account_id) + " - " + str(p.price))
        text = "Your purchases:
" + "
".join(lines)
        await callback.message.edit_text(text, reply_markup=back_home_keyboard())


@router.callback_query(F.data == "user_transactions")
async def cb_user_transactions(callback: CallbackQuery):
    async with async_session_maker() as session:
        stmt = select(Transaction).where(Transaction.user_tg_id == callback.from_user.id).limit(10)
        res = await session.execute(stmt)
        txns = res.scalars().all()
        if not txns:
            await callback.message.edit_text("No transactions yet.", reply_markup=back_home_keyboard())
            return
        lines = []
        for t in txns:
            sign = "+" if t.amount > 0 else ""
            lines.append(t.type + ": " + sign + str(t.amount))
        text = "Your transactions:
" + "
".join(lines)
        await callback.message.edit_text(text, reply_markup=back_home_keyboard())


@router.errors()
async def error_handler(event, exception):
    print("Error:", exception)
