from datetime import datetime, timedelta
from sqlalchemy import (
    Column, Integer, BigInteger, String, Boolean, DateTime,
    ForeignKey, Text, Float, UniqueConstraint, Index, select, update
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from config import DATABASE_URL, OWNER_ID

Base = declarative_base()

if DATABASE_URL:
    engine = create_async_engine(DATABASE_URL, echo=False, future=True)
else:
    engine = create_async_engine("sqlite+aiosqlite:///bot.db", echo=False, future=True)

async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    tg_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    balance = Column(Float, default=0.0, nullable=False)
    referred_by = Column(BigInteger, nullable=True, index=True)
    referral_rewarded = Column(Boolean, default=False, nullable=False)
    is_banned = Column(Boolean, default=False, nullable=False, index=True)
    ban_reason = Column(Text, nullable=True)
    ban_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Admin(Base):
    __tablename__ = "admins"
    id = Column(Integer, primary_key=True)
    tg_id = Column(BigInteger, unique=True, nullable=False, index=True)
    role = Column(String, nullable=False)  # admin, superadmin
    added_by = Column(BigInteger, nullable=False)
    added_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    rate = Column(Float, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False, index=True)
    phone = Column(String, nullable=False)
    session_data = Column(Text, nullable=False)
    status = Column(String, default="available", nullable=False, index=True)
    added_by = Column(BigInteger, nullable=False)
    price_override = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    sold_at = Column(DateTime, nullable=True)
    category = relationship("Category")


class DepositRequest(Base):
    __tablename__ = "deposit_requests"
    id = Column(Integer, primary_key=True)
    user_tg_id = Column(BigInteger, nullable=False, index=True)
    amount = Column(Float, nullable=False)
    utr = Column(String, nullable=False)
    status = Column(String, default="pending", nullable=False, index=True)
    approved_by = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)


class Purchase(Base):
    __tablename__ = "purchases"
    id = Column(Integer, primary_key=True)
    user_tg_id = Column(BigInteger, nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    price = Column(Float, nullable=False)
    status = Column(String, default="completed", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    account = relationship("Account")


class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True)
    user_tg_id = Column(BigInteger, nullable=False, index=True)
    amount = Column(Float, nullable=False)
    type = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class RequiredChannel(Base):
    __tablename__ = "required_channels"
    id = Column(Integer, primary_key=True)
    channel_id = Column(BigInteger, unique=True, nullable=False, index=True)
    channel_username = Column(String, nullable=True)
    label = Column(String, nullable=True)
    added_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Coupon(Base):
    __tablename__ = "coupons"
    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, nullable=False, index=True)
    bonus_amount = Column(Float, nullable=False)
    max_uses = Column(Integer, nullable=False)
    used_count = Column(Integer, default=0, nullable=False)
    active = Column(Boolean, default=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=True)
    per_user_limit = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class CouponUsage(Base):
    __tablename__ = "coupon_usages"
    id = Column(Integer, primary_key=True)
    coupon_id = Column(Integer, ForeignKey("coupons.id"), nullable=False)
    user_tg_id = Column(BigInteger, nullable=False)
    used_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (
        UniqueConstraint("coupon_id", "user_tg_id", name="uq_coupon_user"),
    )


class BotSetting(Base):
    __tablename__ = "bot_settings"
    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True, nullable=False, index=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class LogEntry(Base):
    __tablename__ = "log_entries"
    id = Column(Integer, primary_key=True)
    event_type = Column(String, nullable=False, index=True)
    user_tg_id = Column(BigInteger, nullable=True, index=True)
    admin_tg_id = Column(BigInteger, nullable=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# --- Helpers ---

async def get_user(session: AsyncSession, tg_id: int) -> User | None:
    stmt = select(User).where(User.tg_id == tg_id)
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def get_admin(session: AsyncSession, tg_id: int) -> Admin | None:
    stmt = select(Admin).where(Admin.tg_id == tg_id)
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def is_owner(tg_id: int) -> bool:
    return tg_id == OWNER_ID


async def is_superadmin(session: AsyncSession, tg_id: int) -> bool:
    admin = await get_admin(session, tg_id)
    return admin and admin.role == "superadmin"


async def is_admin(session: AsyncSession, tg_id: int) -> bool:
    admin = await get_admin(session, tg_id)
    return admin is not None


async def is_superadmin_or_owner(session: AsyncSession, tg_id: int) -> bool:
    return await is_owner(tg_id) or await is_superadmin(session, tg_id)


async def get_user_role(session: AsyncSession, tg_id: int) -> str:
    if tg_id == OWNER_ID:
        return "owner"
    admin = await get_admin(session, tg_id)
    if not admin:
        return "user"
    return admin.role


async def add_balance(session: AsyncSession, tg_id: int, amount: float, description: str = None):
    user = await get_user(session, tg_id)
    if not user:
        raise ValueError("User not found")
    user.balance += amount
    txn = Transaction(user_tg_id=tg_id, amount=amount, type="adjustment", description=description)
    session.add(txn)


async def remove_balance(session: AsyncSession, tg_id: int, amount: float, description: str = None):
    user = await get_user(session, tg_id)
    if not user:
        raise ValueError("User not found")
    if user.balance < amount:
        raise ValueError("Insufficient balance")
    user.balance -= amount
    txn = Transaction(user_tg_id=tg_id, amount=-amount, type="adjustment", description=description)
    session.add(txn)
