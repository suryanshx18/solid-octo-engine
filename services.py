from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import (
    User,
    Account,
    Purchase,
    Transaction,
    DepositRequest,
    RequiredChannel,
    Coupon,
    CouponUsage,
    LogEntry,
    BotSetting,
    Admin,
)

from aiogram import Bot
from config import LOG_CHANNEL_ID


# ============================================================
# TIME HELPER
# ============================================================

def utc_now():
    """
    Return timezone-aware UTC datetime.
    """
    return datetime.now(timezone.utc)


# ============================================================
# LOGGING
# ============================================================

async def log_event(
    session: AsyncSession,
    event_type: str,
    user_tg_id: int = None,
    admin_tg_id: int = None,
    details: str = None,
):
    entry = LogEntry(
        event_type=event_type,
        user_tg_id=user_tg_id,
        admin_tg_id=admin_tg_id,
        details=details,
    )

    session.add(entry)
    await session.flush()


async def send_log_message(bot: Bot, text: str):
    """
    Send a log message to LOG_CHANNEL_ID.

    Logging failures should never crash the bot.
    """
    if not LOG_CHANNEL_ID:
        return

    try:
        await bot.send_message(
            LOG_CHANNEL_ID,
            text,
        )
    except Exception as exc:
        print(f"[LOG ERROR] {exc}")


# ============================================================
# BALANCE
# ============================================================

async def add_balance(
    session: AsyncSession,
    user_tg_id: int,
    amount: float,
    description: str = "Balance added",
):
    """
    Add money to a user's balance and create a transaction.

    Returns:
        True  -> successful
        False -> user not found / invalid amount
    """

    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return False

    if amount <= 0:
        return False

    result = await session.execute(
        select(User).where(
            User.tg_id == user_tg_id
        )
    )

    user = result.scalar_one_or_none()

    if not user:
        return False

    # Make sure balance is usable even if NULL somehow exists.
    if user.balance is None:
        user.balance = 0.0

    user.balance += amount

    transaction = Transaction(
        user_tg_id=user_tg_id,
        amount=amount,
        type="credit",
        description=description,
    )

    session.add(transaction)

    await session.flush()

    return True


async def remove_balance(
    session: AsyncSession,
    user_tg_id: int,
    amount: float,
    description: str = "Balance removed",
):
    """
    Remove money from a user's balance.

    Returns:
        True  -> successful
        False -> insufficient balance / invalid user / invalid amount
    """

    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return False

    if amount <= 0:
        return False

    result = await session.execute(
        select(User).where(
            User.tg_id == user_tg_id
        )
    )

    user = result.scalar_one_or_none()

    if not user:
        return False

    if user.balance is None:
        user.balance = 0.0

    if user.balance < amount:
        return False

    user.balance -= amount

    transaction = Transaction(
        user_tg_id=user_tg_id,
        amount=-amount,
        type="debit",
        description=description,
    )

    session.add(transaction)

    await session.flush()

    return True


# ============================================================
# FORCE JOIN
# ============================================================

async def check_force_join(
    bot: Bot,
    user_id: int,
    channels: list[RequiredChannel],
):
    joined = True
    missing = []

    for ch in channels:
        try:
            member = await bot.get_chat_member(
                ch.channel_id,
                user_id,
            )

            if member.status in (
                "member",
                "administrator",
                "creator",
            ):
                continue

            joined = False
            missing.append(ch)

        except Exception:
            joined = False
            missing.append(ch)

    return joined, missing


async def get_required_channels(
    session: AsyncSession,
) -> list[RequiredChannel]:

    stmt = select(RequiredChannel)

    result = await session.execute(stmt)

    return list(
        result.scalars().all()
    )


# ============================================================
# REFERRAL SYSTEM
# ============================================================

async def grant_referral_reward(
    session: AsyncSession,
    referred_user: User,
):
    if (
        not referred_user.referred_by
        or referred_user.referral_rewarded
    ):
        return

    referrer_stmt = select(User).where(
        User.tg_id == referred_user.referred_by
    )

    result = await session.execute(
        referrer_stmt
    )

    referrer = result.scalar_one_or_none()

    if (
        not referrer
        or referrer.tg_id == referred_user.tg_id
    ):
        referred_user.referral_rewarded = True

        await session.flush()

        return

    if referrer.balance is None:
        referrer.balance = 0.0

    reward = 1.0

    referrer.balance += reward

    transaction = Transaction(
        user_tg_id=referrer.tg_id,
        amount=reward,
        type="referral",
        description=(
            f"Referral reward for "
            f"user {referred_user.tg_id}"
        ),
    )

    session.add(transaction)

    referred_user.referral_rewarded = True

    await session.flush()


# ============================================================
# COUPONS
# ============================================================

async def apply_coupon(
    session: AsyncSession,
    user: User,
    code: str,
) -> tuple[bool, str]:

    code = (code or "").strip()

    if not code:
        return False, "Invalid coupon."

    now = utc_now()

    coupon_stmt = select(Coupon).where(
        Coupon.code == code,
        Coupon.active.is_(True),
    )

    result = await session.execute(
        coupon_stmt
    )

    coupon = result.scalar_one_or_none()

    if not coupon:
        return False, "Invalid coupon."

    if (
        coupon.expires_at
        and now > coupon.expires_at
    ):
        return False, "Coupon expired."

    if (
        coupon.max_uses is not None
        and coupon.used_count >= coupon.max_uses
    ):
        return False, "Coupon max uses reached."

    usage_stmt = select(CouponUsage).where(
        CouponUsage.coupon_id == coupon.id,
        CouponUsage.user_tg_id == user.tg_id,
    )

    result = await session.execute(
        usage_stmt
    )

    usages = result.scalars().all()

    if (
        coupon.per_user_limit is not None
        and len(usages) >= coupon.per_user_limit
    ):
        return False, "You already used this coupon."

    bonus = float(coupon.bonus_amount or 0)

    if bonus <= 0:
        return False, "Coupon has no valid bonus."

    if user.balance is None:
        user.balance = 0.0

    user.balance += bonus

    coupon.used_count += 1

    usage = CouponUsage(
        coupon_id=coupon.id,
        user_tg_id=user.tg_id,
    )

    session.add(usage)

    transaction = Transaction(
        user_tg_id=user.tg_id,
        amount=bonus,
        type="coupon",
        description=f"Coupon {code}",
    )

    session.add(transaction)

    await session.flush()

    return True, f"Added ₹{bonus} to your balance."


# ============================================================
# ACCOUNT PURCHASE
# ============================================================

async def reserve_and_buy_account(
    session: AsyncSession,
    user: User,
    account: Account,
) -> tuple[bool, str, float]:

    if not account:
        return False, "Account not found.", 0.0

    if account.status != "available":
        return (
            False,
            "Account no longer available.",
            0.0,
        )

    price = (
        account.price_override
        if account.price_override is not None
        else account.category.rate
    )

    price = float(price)

    if price <= 0:
        return False, "Invalid account price.", 0.0

    if user.balance is None:
        user.balance = 0.0

    if user.balance < price:
        return False, "Insufficient balance.", price

    # Reserve account.
    account.status = "reserved"

    # Deduct balance.
    user.balance -= price

    await session.flush()

    return True, "Reserved", price


async def complete_purchase(
    session: AsyncSession,
    user: User,
    account: Account,
    price: float,
):
    """
    Convert reserved account into completed/sold purchase.
    """

    account.status = "sold"
    account.sold_at = utc_now()

    purchase = Purchase(
        user_tg_id=user.tg_id,
        account_id=account.id,
        price=price,
    )

    session.add(purchase)

    transaction = Transaction(
        user_tg_id=user.tg_id,
        amount=-price,
        type="purchase",
        description=(
            f"Purchase account #{account.id}"
        ),
    )

    session.add(transaction)

    await session.flush()


async def fail_purchase(
    session: AsyncSession,
    user: User,
    account: Account,
    price: float,
):
    """
    Release a reserved account and refund the user.
    """

    if account.status != "reserved":
        return

    account.status = "available"

    if user.balance is None:
        user.balance = 0.0

    if price and price > 0:
        user.balance += price

    await session.flush()


# ============================================================
# DEPOSIT EXPIRATION
# ============================================================

async def expire_pending_deposits(
    session: AsyncSession,
):
    now = utc_now()

    stmt = (
        update(DepositRequest)
        .where(
            DepositRequest.status == "pending",
            DepositRequest.expires_at < now,
        )
        .values(
            status="expired"
        )
    )

    await session.execute(stmt)

    await session.flush()


# ============================================================
# BOT SETTINGS
# ============================================================

async def get_setting(
    session: AsyncSession,
    key: str,
    default: str = "",
) -> str:

    stmt = select(BotSetting).where(
        BotSetting.key == key
    )

    result = await session.execute(stmt)

    setting = result.scalar_one_or_none()

    if setting:
        return setting.value

    return default


async def set_setting(
    session: AsyncSession,
    key: str,
    value: str,
):
    stmt = select(BotSetting).where(
        BotSetting.key == key
    )

    result = await session.execute(stmt)

    setting = result.scalar_one_or_none()

    if setting:
        setting.value = value
    else:
        setting = BotSetting(
            key=key,
            value=value,
        )

        session.add(setting)

    await session.flush()


# ============================================================
# USER ROLE
# ============================================================

async def get_user_role(
    session: AsyncSession,
    user_tg_id: int,
) -> str:

    # Owner/superadmin/admin lookup.
    result = await session.execute(
        select(Admin).where(
            Admin.tg_id == user_tg_id
        )
    )

    admin = result.scalar_one_or_none()

    if not admin:
        return "user"

    # Support common role names.
    role = getattr(
        admin,
        "role",
        None,
    )

    if role:
        return str(role).lower()

    # Fallback if the Admin model uses flags.
    if getattr(admin, "is_owner", False):
        return "owner"

    if getattr(admin, "is_superadmin", False):
        return "superadmin"

    return "admin"
