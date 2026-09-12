from datetime import datetime, timedelta
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from database import (
    User, Account, Purchase, Transaction, DepositRequest,
    RequiredChannel, Coupon, CouponUsage, LogEntry, BotSetting, Admin
)
from aiogram import Bot
from config import LOG_CHANNEL_ID


async def log_event(session: AsyncSession, event_type: str, user_tg_id: int = None, admin_tg_id: int = None, details: str = None):
    entry = LogEntry(event_type=event_type, user_tg_id=user_tg_id, admin_tg_id=admin_tg_id, details=details)
    session.add(entry)
    await session.flush()


async def send_log_message(bot: Bot, text: str):
    if not LOG_CHANNEL_ID:
        return
    try:
        await bot.send_message(LOG_CHANNEL_ID, text)
    except Exception:
        pass


async def check_force_join(bot: Bot, user_id: int, channels: list[RequiredChannel]):
    joined = True
    missing = []
    for ch in channels:
        try:
            member = await bot.get_chat_member(ch.channel_id, user_id)
            if member.status in ("member", "administrator", "creator"):
                continue
            else:
                joined = False
                missing.append(ch)
        except Exception:
            joined = False
            missing.append(ch)
    return joined, missing


async def get_required_channels(session: AsyncSession) -> list[RequiredChannel]:
    stmt = select(RequiredChannel)
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def grant_referral_reward(session: AsyncSession, referred_user: User):
    if not referred_user.referred_by or referred_user.referral_rewarded:
        return
    referrer_stmt = select(User).where(User.tg_id == referred_user.referred_by)
    res = await session.execute(referrer_stmt)
    referrer = res.scalar_one_or_none()
    if not referrer or referrer.tg_id == referred_user.tg_id:
        referred_user.referral_rewarded = True
        await session.flush()
        return
    referrer.balance += 1.0
    txn = Transaction(user_tg_id=referrer.tg_id, amount=1.0, type="referral", description=f"Referral reward for user {referred_user.tg_id}")
    session.add(txn)
    referred_user.referral_rewarded = True
    await session.flush()


async def apply_coupon(session: AsyncSession, user: User, code: str) -> tuple[bool, str]:
    now = datetime.utcnow()
    coupon_stmt = select(Coupon).where(Coupon.code == code, Coupon.active == True)
    res = await session.execute(coupon_stmt)
    coupon = res.scalar_one_or_none()
    if not coupon:
        return False, "Invalid coupon."
    if coupon.expires_at and now > coupon.expires_at:
        return False, "Coupon expired."
    if coupon.used_count >= coupon.max_uses:
        return False, "Coupon max uses reached."
    usage_stmt = select(CouponUsage).where(CouponUsage.coupon_id == coupon.id, CouponUsage.user_tg_id == user.tg_id)
    res = await session.execute(usage_stmt)
    usages = res.scalars().all()
    if len(usages) >= coupon.per_user_limit:
        return False, "You already used this coupon."
    user.balance += coupon.bonus_amount
    coupon.used_count += 1
    usage = CouponUsage(coupon_id=coupon.id, user_tg_id=user.tg_id)
    session.add(usage)
    txn = Transaction(user_tg_id=user.tg_id, amount=coupon.bonus_amount, type="coupon", description=f"Coupon {code}")
    session.add(txn)
    return True, f"Added ₹{coupon.bonus_amount} to your balance."


async def reserve_and_buy_account(session: AsyncSession, user: User, account: Account) -> tuple[bool, str, float]:
    price = account.price_override if account.price_override is not None else account.category.rate
    if user.balance < price:
        return False, "Insufficient balance.", 0.0
    if account.status != "available":
        return False, "Account no longer available.", 0.0
    account.status = "reserved"
    user.balance -= price
    await session.flush()
    return True, "Reserved", price


async def complete_purchase(session: AsyncSession, user: User, account: Account, price: float):
    account.status = "sold"
    account.sold_at = datetime.utcnow()
    purchase = Purchase(user_tg_id=user.tg_id, account_id=account.id, price=price)
    session.add(purchase)
    txn = Transaction(user_tg_id=user.tg_id, amount=-price, type="purchase", description=f"Purchase account #{account.id}")
    session.add(txn)
    await session.flush()


async def fail_purchase(session: AsyncSession, user: User, account: Account, price: float):
    if account.status != "reserved":
        return
    account.status = "available"
    user.balance += price
    await session.flush()


async def expire_pending_deposits(session: AsyncSession):
    now = datetime.utcnow()
    stmt = (
        update(DepositRequest)
        .where(DepositRequest.status == "pending", DepositRequest.expires_at < now)
        .values(status="expired")
    )
    await session.execute(stmt)
    await session.flush()


async def get_setting(session: AsyncSession, key: str, default: str = "") -> str:
    stmt = select(BotSetting).where(BotSetting.key == key)
    res = await session.execute(stmt)
    setting = res.scalar_one_or_none()
    return setting.value if setting else default


async def set_setting(session: AsyncSession, key: str, value: str):
    stmt = select(BotSetting).where(BotSetting.key == key)
    res = await session.execute(stmt)
    setting = res.scalar_one_or_none()
    if setting:
        setting.value = value
    else:
        setting = BotSetting(key=key, value=value)
        session.add(setting)
    await session.flush()
