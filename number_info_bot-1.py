#!/usr/bin/env python3
"""
⚡ PREMIUM NUMBER INFO TELEGRAM BOT — ONE FILE, AUTO INSTALL, READY TO RUN

Bas run karo:
    python number_info_bot.py

Pehli baar packages auto install ho jayenge.
Token + Admin ID code ke andar already set hain.
"""

from __future__ import annotations

# ===========================================================================
# 🔧 CONFIG — yahan values already bhari hui hain
# ===========================================================================
BOT_TOKEN = "8964272303:AAEgU6v8fbkOrdgCHSXMOXcB0pgoSu2RHzY"
ADMIN_IDS = [8502412097]          # list of admin telegram IDs
DATABASE_URL = "sqlite+aiosqlite:///./bot.db"
NUMBER_API_URL = "https://thanksfor100user.vercel.app/num?number={number}&format=json"
WELCOME_CREDITS = 2
LOOKUP_COST = 1
REFERRAL_REWARD = 1
DAILY_BONUS = 1
LOG_LEVEL = "INFO"
MAX_MAIN_RECORDS = 5
MAX_ALT_RECORDS = 8
API_TIMEOUT = 25.0

# ===========================================================================
# 📦 AUTO PIP INSTALL (agar package missing ho to install karega)
# ===========================================================================
import subprocess
import sys

_REQUIRED = [
    "python-telegram-bot==21.6",
    "httpx==0.27.2",
    "sqlalchemy==2.0.36",
    "aiosqlite==0.20.0",
    "tenacity==9.0.0",
]

def _ensure_packages():
    missing = []
    for pkg in _REQUIRED:
        name = pkg.split("==")[0].replace("-", "_")
        # special cases
        import_name = {
            "python_telegram_bot": "telegram",
            "sqlalchemy": "sqlalchemy",
            "aiosqlite": "aiosqlite",
            "httpx": "httpx",
            "tenacity": "tenacity",
        }.get(name, name)
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pkg)
    if missing:
        print("📦 Installing missing packages:", ", ".join(missing))
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet", *missing],
            stdout=subprocess.DEVNULL,
        )
        print("✅ Packages installed.\n")

_ensure_packages()

# ===========================================================================
# IMPORTS (after auto-install)
# ===========================================================================
import asyncio
import logging
import os
import re
import secrets
import string
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import httpx
from sqlalchemy import (
    BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text,
    UniqueConstraint, func, select, desc,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, ConversationHandler,
    ContextTypes, MessageHandler, filters,
)

# ===========================================================================
# HELPERS
# ===========================================================================
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

logging.basicConfig(
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    stream=sys.stdout,
)
logger = logging.getLogger("numberbot")

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

# ===========================================================================
# DATABASE MODELS
# ===========================================================================
class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    credits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    referred_by: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), nullable=True)
    referral_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    total_lookups: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_referrals: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_daily_bonus: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class CreditTransaction(Base):
    __tablename__ = "credit_transactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(128), nullable=False)
    reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    admin_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class Referral(Base):
    __tablename__ = "referrals"
    __table_args__ = (UniqueConstraint("referrer_id", "referred_id", name="uq_ref"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    referrer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True)
    referred_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, unique=True)
    reward_given: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class LookupHistory(Base):
    __tablename__ = "lookup_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True)
    phone_number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    credits_charged: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    main_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    alt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class BotSetting(Base):
    __tablename__ = "bot_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class AdminLog(Base):
    __tablename__ = "admin_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    target_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class ApiHealth(Base):
    __tablename__ = "api_health"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_success: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_requests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_successes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

# ===========================================================================
# DATABASE ENGINE
# ===========================================================================
_db_url = DATABASE_URL
if _db_url.startswith("postgresql://"):
    _db_url = _db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
elif _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql+asyncpg://", 1)

engine = create_async_engine(_db_url, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)

@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()

async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with get_session() as session:
        defaults = {
            "welcome_credits": str(WELCOME_CREDITS),
            "lookup_cost": str(LOOKUP_COST),
            "referral_reward": str(REFERRAL_REWARD),
            "daily_bonus": str(DAILY_BONUS),
            "maintenance_mode": "false",
            "referral_enabled": "true",
            "api_enabled": "true",
        }
        for key, value in defaults.items():
            r = await session.execute(select(BotSetting).where(BotSetting.key == key))
            if r.scalar_one_or_none() is None:
                session.add(BotSetting(key=key, value=value))
        r = await session.execute(select(ApiHealth).where(ApiHealth.api_name == "primary"))
        if r.scalar_one_or_none() is None:
            session.add(ApiHealth(api_name="primary", is_enabled=True))
    logger.info("Database initialized")

async def get_setting(session: AsyncSession, key: str, default: str = "") -> str:
    r = await session.execute(select(BotSetting).where(BotSetting.key == key))
    row = r.scalar_one_or_none()
    return row.value if row else default

async def set_setting(session: AsyncSession, key: str, value: str) -> None:
    r = await session.execute(select(BotSetting).where(BotSetting.key == key))
    row = r.scalar_one_or_none()
    if row:
        row.value = value
    else:
        session.add(BotSetting(key=key, value=value))

# ===========================================================================
# API CLIENT
# ===========================================================================
@dataclass
class Record:
    name: str = "N/A"
    fname: str = "N/A"
    mobile: str = "N/A"
    alt: str = "N/A"
    circle: str = "N/A"
    doc_id: str = "N/A"
    email: str = "N/A"
    address: str = "N/A"

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Record":
        return cls(
            name=str(d.get("name") or "N/A"),
            fname=str(d.get("fname") or "N/A"),
            mobile=str(d.get("mobile") or "N/A"),
            alt=str(d.get("alt") or "N/A"),
            circle=str(d.get("circle") or "N/A"),
            doc_id=str(d.get("id") or "N/A"),
            email=str(d.get("email") or "N/A"),
            address=str(d.get("address") or "N/A"),
        )

@dataclass
class LookupResult:
    success: bool
    query: str = ""
    main_records: List[Record] = field(default_factory=list)
    alt_records: List[Record] = field(default_factory=list)
    error: Optional[str] = None

async def api_lookup(number: str) -> LookupResult:
    url = NUMBER_API_URL.format(number=number) if "{number}" in NUMBER_API_URL else NUMBER_API_URL.format(number)
    try:
        async with httpx.AsyncClient(timeout=API_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url)
    except httpx.TimeoutException:
        await _api_fail("timeout")
        return LookupResult(False, number, error="API timeout. Try again.")
    except Exception as e:
        await _api_fail(str(e))
        return LookupResult(False, number, error=f"Network error: {e}")

    if resp.status_code == 400:
        await _api_fail(resp.text[:200])
        return LookupResult(False, number, error=resp.text.strip() or "Invalid number (min 10 digits).")
    if resp.status_code != 200:
        await _api_fail(f"HTTP {resp.status_code}")
        return LookupResult(False, number, error=f"API HTTP {resp.status_code}")

    try:
        data = resp.json()
    except Exception:
        await _api_fail("non-json")
        return LookupResult(False, number, error="Unreadable API response.")

    if data.get("status") is not True:
        err = data.get("error") or data.get("message") or "No records found."
        await _api_fail(str(err))
        return LookupResult(False, number, error=str(err))

    payload = data.get("data") or {}
    main = [Record.from_dict(r) for r in (payload.get("main_records") or [])]
    alt = [Record.from_dict(r) for r in (payload.get("alt_records") or [])]
    await _api_ok()
    if not main and not alt:
        return LookupResult(True, data.get("query") or number, error="No subscriber records found.")
    return LookupResult(True, data.get("query") or number, main, alt)

async def _api_ok() -> None:
    try:
        async with get_session() as s:
            r = await s.execute(select(ApiHealth).where(ApiHealth.api_name == "primary"))
            row = r.scalar_one_or_none()
            if row:
                row.last_success = utcnow()
                row.consecutive_failures = 0
                row.total_requests += 1
                row.total_successes += 1
                row.last_error = None
    except Exception:
        pass

async def _api_fail(err: str) -> None:
    try:
        async with get_session() as s:
            r = await s.execute(select(ApiHealth).where(ApiHealth.api_name == "primary"))
            row = r.scalar_one_or_none()
            if row:
                row.last_failure = utcnow()
                row.consecutive_failures += 1
                row.total_requests += 1
                row.last_error = err[:500]
    except Exception:
        pass

# ===========================================================================
# CREDITS & USERS
# ===========================================================================
async def add_credits(
    session: AsyncSession, telegram_id: int, amount: int, reason: str,
    reference: Optional[str] = None, admin_id: Optional[int] = None,
) -> Tuple[bool, int, str]:
    if amount == 0:
        return False, 0, "Amount cannot be zero."
    r = await session.execute(select(User).where(User.telegram_id == telegram_id).with_for_update())
    user = r.scalar_one_or_none()
    if not user:
        return False, 0, "User not found."
    new_bal = user.credits + amount
    if new_bal < 0:
        return False, user.credits, "Insufficient credits."
    user.credits = new_bal
    user.updated_at = utcnow()
    session.add(CreditTransaction(
        user_id=telegram_id, amount=amount, balance_after=new_bal,
        reason=reason, reference=reference, admin_id=admin_id,
    ))
    if admin_id:
        session.add(AdminLog(
            admin_id=admin_id,
            action="add_credits" if amount > 0 else "deduct_credits",
            target_user_id=telegram_id,
            details=f"amount={amount}, reason={reason}, bal={new_bal}",
        ))
    return True, new_bal, "OK"

def _gen_ref_code(tid: int) -> str:
    return f"REF{tid}" + "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))

async def get_or_create_user(
    session: AsyncSession, telegram_id: int,
    username: Optional[str] = None, first_name: Optional[str] = None,
    last_name: Optional[str] = None, start_payload: Optional[str] = None,
) -> Tuple[User, bool]:
    r = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = r.scalar_one_or_none()
    if user:
        user.username = username
        user.first_name = first_name
        user.last_name = last_name
        user.updated_at = utcnow()
        return user, False

    user = User(
        telegram_id=telegram_id, username=username, first_name=first_name,
        last_name=last_name, credits=0, referral_code=_gen_ref_code(telegram_id),
    )
    session.add(user)
    await session.flush()

    welcome = int(await get_setting(session, "welcome_credits", str(WELCOME_CREDITS)))
    await add_credits(session, telegram_id, welcome, "welcome_bonus")

    if start_payload and start_payload.startswith("ref_"):
        code = start_payload[4:].strip()
        await _process_referral(session, code, telegram_id)

    await session.refresh(user)
    return user, True

async def _process_referral(session: AsyncSession, referrer_code: str, new_uid: int) -> bool:
    r = await session.execute(select(User).where(User.referral_code == referrer_code))
    referrer = r.scalar_one_or_none()
    if not referrer or referrer.telegram_id == new_uid:
        return False
    exist = await session.execute(select(Referral).where(Referral.referred_id == new_uid))
    if exist.scalar_one_or_none():
        return False
    ref = Referral(referrer_id=referrer.telegram_id, referred_id=new_uid, reward_given=False)
    session.add(ref)
    r2 = await session.execute(select(User).where(User.telegram_id == new_uid))
    nu = r2.scalar_one_or_none()
    if nu:
        nu.referred_by = referrer.telegram_id
    enabled = (await get_setting(session, "referral_enabled", "true")).lower() == "true"
    reward = int(await get_setting(session, "referral_reward", str(REFERRAL_REWARD)))
    if enabled and reward > 0:
        ok, _, _ = await add_credits(session, referrer.telegram_id, reward, "referral_reward", str(new_uid))
        if ok:
            ref.reward_given = True
            referrer.total_referrals += 1
    return True

async def get_user(session: AsyncSession, tid: int) -> Optional[User]:
    r = await session.execute(select(User).where(User.telegram_id == tid))
    return r.scalar_one_or_none()

async def claim_daily(session: AsyncSession, tid: int) -> Tuple[bool, str, int]:
    r = await session.execute(select(User).where(User.telegram_id == tid).with_for_update())
    user = r.scalar_one_or_none()
    if not user:
        return False, "User not found.", 0
    bonus = int(await get_setting(session, "daily_bonus", str(DAILY_BONUS)))
    if bonus <= 0:
        return False, "Daily bonus disabled.", user.credits
    now = utcnow()
    if user.last_daily_bonus:
        last = user.last_daily_bonus
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if (now.date() - last.date()).days < 1:
            return False, "Already claimed today. Come back tomorrow!", user.credits
    user.last_daily_bonus = now
    user.credits += bonus
    user.updated_at = now
    session.add(CreditTransaction(user_id=tid, amount=bonus, balance_after=user.credits, reason="daily_bonus"))
    return True, f"✅ Daily bonus of {bonus} credit(s) claimed!", user.credits

async def record_lookup(
    session: AsyncSession, tid: int, phone: str, success: bool,
    charged: int, main_c: int = 0, alt_c: int = 0, error: Optional[str] = None,
) -> None:
    session.add(LookupHistory(
        user_id=tid, phone_number=phone, success=success, credits_charged=charged,
        main_count=main_c, alt_count=alt_c, error_message=error,
    ))
    if success:
        u = await get_user(session, tid)
        if u:
            u.total_lookups += 1

async def referral_stats(session: AsyncSession, tid: int) -> dict:
    total = (await session.execute(select(func.count(Referral.id)).where(Referral.referrer_id == tid))).scalar() or 0
    rewarded = (await session.execute(
        select(func.count(Referral.id)).where(Referral.referrer_id == tid, Referral.reward_given.is_(True))
    )).scalar() or 0
    per = int(await get_setting(session, "referral_reward", str(REFERRAL_REWARD)))
    return {"total": total, "rewarded": rewarded, "earned": rewarded * per}

# ===========================================================================
# VALIDATORS & MESSAGES
# ===========================================================================
def normalize_phone(raw: str) -> Tuple[bool, str, Optional[str]]:
    if not raw:
        return False, "", "Please send a valid phone number."
    cleaned = re.sub(r"[\s\-\(\)\.]", "", raw.strip())
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]
    if not cleaned.isdigit():
        return False, "", "Only digits allowed (optional +)."
    if len(cleaned) < 10:
        return False, "", "Minimum 10 digits required."
    if len(cleaned) > 15:
        return False, "", "Maximum 15 digits allowed."
    return True, cleaned, None

def esc(t: str) -> str:
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def main_menu_text(name: str, uid: int, credits: int) -> str:
    return (
        f"<b>⚡ PREMIUM NUMBER INFO</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Welcome, <b>{esc(name or 'User')}</b>\n\n"
        f"🆔 User ID: <code>{uid}</code>\n"
        f"💳 Available Credits: <b>{credits}</b>\n\n"
        f"<i>Select an option below</i>"
    )

def format_result(res: LookupResult) -> str:
    if not res.success:
        return (
            f"<b>❌ LOOKUP FAILED</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Query: <code>{esc(res.query)}</code>\n"
            f"Error: {esc(res.error or 'Unknown')}\n\n"
            f"<i>No credits deducted.</i>"
        )
    if res.error and not res.main_records and not res.alt_records:
        return (
            f"<b>🔍 LOOKUP RESULT</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🔢 Number: <code>{esc(res.query)}</code>\n"
            f"⚡ Status: No records found\n\n<i>{esc(res.error)}</i>"
        )
    parts = [
        "<b>🔍 LOOKUP RESULT</b>", "━━━━━━━━━━━━━━━━━━━━", "",
        f"🔢 Number: <code>{esc(res.query)}</code>",
        "⚡ Status: Records Found ✅", "",
    ]
    main = res.main_records[:MAX_MAIN_RECORDS]
    alt = res.alt_records[:MAX_ALT_RECORDS]
    if main:
        parts.append(f"<b>═══ PRIMARY ({len(res.main_records)} total)</b>\n")
        for i, r in enumerate(main, 1):
            parts.append(
                f"<b>┌── Main #{i}</b>\n"
                f"├ 👤 Name: <code>{esc(r.name)}</code>\n"
                f"├ 👨 Father: <code>{esc(r.fname)}</code>\n"
                f"├ 📞 Mobile: <code>{esc(r.mobile)}</code>\n"
                f"├ 🔁 Alt: <code>{esc(r.alt)}</code>\n"
                f"├ 📶 Circle: <code>{esc(r.circle)}</code>\n"
                f"├ 🆔 Doc: <code>{esc(r.doc_id)}</code>\n"
                f"├ 📧 Email: <code>{esc(r.email)}</code>\n"
                f"└ 🏡 Addr: <code>{esc(r.address)}</code>\n"
            )
        if len(res.main_records) > MAX_MAIN_RECORDS:
            parts.append(f"<i>… +{len(res.main_records) - MAX_MAIN_RECORDS} more</i>")
        parts.append("")
    if alt:
        parts.append(f"<b>═══ ALTERNATE ({len(res.alt_records)} total)</b>\n")
        for i, r in enumerate(alt, 1):
            parts.append(
                f"<b>┌── Alt #{i}</b>\n"
                f"├ 👤 Name: <code>{esc(r.name)}</code>\n"
                f"├ 👨 Father: <code>{esc(r.fname)}</code>\n"
                f"├ 📞 Mobile: <code>{esc(r.mobile)}</code>\n"
                f"├ 🔁 Alt: <code>{esc(r.alt)}</code>\n"
                f"├ 📶 Circle: <code>{esc(r.circle)}</code>\n"
                f"├ 🆔 Doc: <code>{esc(r.doc_id)}</code>\n"
                f"├ 📧 Email: <code>{esc(r.email)}</code>\n"
                f"└ 🏡 Addr: <code>{esc(r.address)}</code>\n"
            )
        if len(res.alt_records) > MAX_ALT_RECORDS:
            parts.append(f"<i>… +{len(res.alt_records) - MAX_ALT_RECORDS} more</i>")
    text = "\n".join(parts)
    if len(text) > 4000:
        text = text[:3950] + "\n\n<i>… truncated</i>"
    return text

# ===========================================================================
# KEYBOARDS
# ===========================================================================
def kb_main(admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("🔍 Lookup Number", callback_data="lookup"),
         InlineKeyboardButton("👤 My Account", callback_data="account")],
        [InlineKeyboardButton("🤝 Refer & Earn", callback_data="referral"),
         InlineKeyboardButton("📜 Lookup History", callback_data="history")],
        [InlineKeyboardButton("🎁 Daily Bonus", callback_data="daily"),
         InlineKeyboardButton("💎 Premium Info", callback_data="premium_info")],
        [InlineKeyboardButton("ℹ️ Help & Support", callback_data="help")],
    ]
    if admin:
        rows.append([InlineKeyboardButton("👑 Admin Panel", callback_data="admin")])
    return InlineKeyboardMarkup(rows)

def kb_back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Main Menu", callback_data="main_menu")]])

def kb_lookup_again() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔍 Lookup Another", callback_data="lookup"),
        InlineKeyboardButton("◀️ Main Menu", callback_data="main_menu"),
    ]])

def kb_referral() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Get My Referral Link", callback_data="ref_link")],
        [InlineKeyboardButton("📊 Referral Statistics", callback_data="ref_stats")],
        [InlineKeyboardButton("◀️ Main Menu", callback_data="main_menu")],
    ])

def kb_admin() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Bot Statistics", callback_data="admin_stats"),
         InlineKeyboardButton("🔌 API Status", callback_data="admin_api")],
        [InlineKeyboardButton("➕ Add Credits", callback_data="admin_add"),
         InlineKeyboardButton("➖ Deduct Credits", callback_data="admin_deduct")],
        [InlineKeyboardButton("🔍 Search User", callback_data="admin_search"),
         InlineKeyboardButton("🚫 Block/Unblock", callback_data="admin_block")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="admin_settings"),
         InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton("📜 Admin Logs", callback_data="admin_logs")],
        [InlineKeyboardButton("◀️ Main Menu", callback_data="main_menu")],
    ])

def kb_settings() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Lookup Cost", callback_data="set_lookup_cost")],
        [InlineKeyboardButton("🎁 Welcome Credits", callback_data="set_welcome")],
        [InlineKeyboardButton("🤝 Referral Reward", callback_data="set_referral")],
        [InlineKeyboardButton("☀️ Daily Bonus", callback_data="set_daily")],
        [InlineKeyboardButton("🛠 Toggle Maintenance", callback_data="toggle_maint")],
        [InlineKeyboardButton("◀️ Admin", callback_data="admin")],
    ])

def kb_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="main_menu")]])

def kb_broadcast_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Confirm Send", callback_data="broadcast_confirm"),
        InlineKeyboardButton("❌ Cancel", callback_data="admin"),
    ]])

# ===========================================================================
# CONVERSATION STATES
# ===========================================================================
WAITING_NUMBER = 1
WAITING_ADMIN = 2
WAITING_BROADCAST = 3

# ===========================================================================
# HANDLERS — START / MENU
# ===========================================================================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.effective_user or not update.message:
        return ConversationHandler.END
    user = update.effective_user
    payload = context.args[0] if context.args else None

    async with get_session() as session:
        maint = (await get_setting(session, "maintenance_mode", "false")).lower() == "true"
        if maint and not is_admin(user.id):
            await update.message.reply_text(
                "<b>🛠 MAINTENANCE MODE</b>\nBot is under maintenance. Try later.",
                parse_mode="HTML",
            )
            return ConversationHandler.END
        db_user, is_new = await get_or_create_user(
            session, user.id, user.username, user.first_name, user.last_name, payload,
        )
        if db_user.is_blocked:
            await update.message.reply_text("🚫 Your account is blocked.")
            return ConversationHandler.END
        credits = db_user.credits

    text = main_menu_text(user.first_name or "User", user.id, credits)
    if is_new:
        text = "✅ <b>Welcome!</b> You received welcome credits.\n\n" + text
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb_main(is_admin(user.id)))
    return ConversationHandler.END

async def cb_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    user = q.from_user
    async with get_session() as session:
        maint = (await get_setting(session, "maintenance_mode", "false")).lower() == "true"
        if maint and not is_admin(user.id):
            await q.edit_message_text("<b>🛠 Maintenance</b>", parse_mode="HTML")
            return ConversationHandler.END
        db = await get_user(session, user.id)
        credits = db.credits if db else 0
    await q.edit_message_text(
        main_menu_text(user.first_name or "User", user.id, credits),
        parse_mode="HTML", reply_markup=kb_main(is_admin(user.id)),
    )
    context.user_data.clear()
    return ConversationHandler.END

# ===========================================================================
# HANDLERS — LOOKUP
# ===========================================================================
async def cb_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    user = q.from_user
    async with get_session() as session:
        db = await get_user(session, user.id)
        if not db or db.is_blocked:
            await q.edit_message_text("🚫 Blocked or not registered. /start")
            return ConversationHandler.END
        cost = int(await get_setting(session, "lookup_cost", str(LOOKUP_COST)))
        if db.credits < cost:
            await q.edit_message_text(
                f"❌ Insufficient credits ({db.credits}). Need {cost}.\n"
                f"Earn via Referrals or Daily Bonus.",
                parse_mode="HTML", reply_markup=kb_cancel(),
            )
            return ConversationHandler.END
    await q.edit_message_text(
        f"<b>🔍 LOOKUP NUMBER</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Send a 10–15 digit phone number.\n\n"
        f"💳 Cost: <b>{cost}</b> credit(s)\n"
        f"💰 Balance: <b>{db.credits}</b>\n\n"
        f"<i>Credits deducted only on success.</i>",
        parse_mode="HTML", reply_markup=kb_cancel(),
    )
    return WAITING_NUMBER

async def msg_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.effective_user:
        return ConversationHandler.END
    user = update.effective_user
    valid, phone, err = normalize_phone(update.message.text or "")
    if not valid:
        await update.message.reply_text(f"❌ {err}", reply_markup=kb_cancel())
        return WAITING_NUMBER

    status = await update.message.reply_text(f"⏳ Looking up <code>{phone}</code>…", parse_mode="HTML")

    async with get_session() as session:
        db = await get_user(session, user.id)
        if not db or db.is_blocked:
            await status.edit_text("🚫 Blocked.")
            return ConversationHandler.END
        cost = int(await get_setting(session, "lookup_cost", str(LOOKUP_COST)))
        if db.credits < cost:
            await status.edit_text("❌ Insufficient credits.", reply_markup=kb_lookup_again())
            return ConversationHandler.END

        result = await api_lookup(phone)

        if not result.success:
            await record_lookup(session, user.id, phone, False, 0, error=result.error)
            await status.edit_text(format_result(result), parse_mode="HTML", reply_markup=kb_lookup_again())
            return ConversationHandler.END

        ok, new_bal, msg = await add_credits(session, user.id, -cost, "lookup", phone)
        if not ok:
            await record_lookup(session, user.id, phone, False, 0, error="charge_failed")
            await status.edit_text(f"❌ Charge failed: {msg}", reply_markup=kb_lookup_again())
            return ConversationHandler.END

        await record_lookup(
            session, user.id, phone, True, cost,
            len(result.main_records), len(result.alt_records),
        )

    text = format_result(result) + f"\n\n💳 Credits left: <b>{new_bal}</b>"
    await status.edit_text(text, parse_mode="HTML", reply_markup=kb_lookup_again())
    return ConversationHandler.END

# ===========================================================================
# HANDLERS — ACCOUNT / HISTORY / DAILY / HELP / REFERRAL
# ===========================================================================
async def cb_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    async with get_session() as session:
        u = await get_user(session, q.from_user.id)
    if not u:
        await q.edit_message_text("Please /start first.")
        return
    name = esc(f"{u.first_name or ''} {u.last_name or ''}".strip() or "—")
    uname = f"@{esc(u.username)}" if u.username else "—"
    text = (
        f"<b>👤 MY ACCOUNT</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Name: {name}\n🔗 Username: {uname}\n"
        f"🆔 ID: <code>{u.telegram_id}</code>\n"
        f"💳 Credits: <b>{u.credits}</b>\n"
        f"🔍 Lookups: <b>{u.total_lookups}</b>\n"
        f"🤝 Referrals: <b>{u.total_referrals}</b>\n"
        f"📅 Joined: {u.created_at.strftime('%Y-%m-%d') if u.created_at else '—'}"
    )
    await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb_back())

async def cb_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    async with get_session() as session:
        rows = (await session.execute(
            select(LookupHistory).where(LookupHistory.user_id == q.from_user.id)
            .order_by(desc(LookupHistory.created_at)).limit(10)
        )).scalars().all()
    if not rows:
        text = "<b>📜 LOOKUP HISTORY</b>\n━━━━━━━━━━━━━━━━━━━━\n\nNo lookups yet."
    else:
        lines = ["<b>📜 LOOKUP HISTORY</b>", "━━━━━━━━━━━━━━━━━━━━", "", "<i>Last 10:</i>", ""]
        for r in rows:
            st = "✅" if r.success else "❌"
            ts = r.created_at.strftime("%m-%d %H:%M") if r.created_at else "—"
            lines.append(f"{st} <code>{r.phone_number}</code> · {r.credits_charged}cr · {ts}")
        text = "\n".join(lines)
    await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb_back())

async def cb_daily(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    async with get_session() as session:
        ok, msg, bal = await claim_daily(session, q.from_user.id)
    text = f"<b>🎁 DAILY BONUS</b>\n━━━━━━━━━━━━━━━━━━━━\n\n{msg}"
    if ok:
        text += f"\n\n💳 Balance: <b>{bal}</b>"
    await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb_back())

async def cb_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    text = (
        "<b>ℹ️ HELP & SUPPORT</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>How to use</b>\n"
        "1. Tap 🔍 Lookup Number\n"
        "2. Send 10–15 digit number\n"
        "3. 1 credit per successful lookup\n\n"
        "<b>Credits</b>\n"
        "• Welcome bonus on join\n"
        "• Refer friends\n"
        "• Daily bonus once/day\n\n"
        "<i>Invalid numbers are not charged. Use responsibly.</i>"
    )
    await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb_back())

async def cb_premium(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    text = (
        "<b>💎 PREMIUM INFORMATION</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        "Telecom subscriber intelligence aggregator.\n\n"
        "• Fast number lookup\n• Main + alternate records\n"
        "• Credit system + referrals + daily bonus\n"
        "• Full admin panel\n\n"
        "<i>Data accuracy depends on upstream API.</i>"
    )
    await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb_back())

async def cb_referral(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    async with get_session() as session:
        stats = await referral_stats(session, q.from_user.id)
    text = (
        f"<b>🎁 REFER & EARN</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Invite friends and earn credits.\n\n"
        f"👥 Total Referrals: <b>{stats['total']}</b>\n"
        f"💰 Credits Earned: <b>{stats['earned']}</b>"
    )
    await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb_referral())

async def cb_ref_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    async with get_session() as session:
        u = await get_user(session, q.from_user.id)
    if not u:
        await q.edit_message_text("Please /start first.")
        return
    bot = await context.bot.get_me()
    link = f"https://t.me/{bot.username}?start=ref_{u.referral_code}"
    text = (
        f"<b>🔗 YOUR REFERRAL LINK</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<code>{link}</code>\n\n"
        f"Share this. New users who start with it earn you credits."
    )
    await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb_referral())

async def cb_ref_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    async with get_session() as session:
        stats = await referral_stats(session, q.from_user.id)
    text = (
        f"<b>📊 REFERRAL STATISTICS</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Total: <b>{stats['total']}</b>\n"
        f"✅ Rewarded: <b>{stats['rewarded']}</b>\n"
        f"💰 Earned: <b>{stats['earned']}</b>"
    )
    await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb_referral())

# ===========================================================================
# HANDLERS — ADMIN
# ===========================================================================
async def cb_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        await q.edit_message_text("⛔ Unauthorized.")
        return ConversationHandler.END
    await q.edit_message_text(
        "<b>👑 ADMIN PANEL</b>\n━━━━━━━━━━━━━━━━━━━━\n\nSelect an action:",
        parse_mode="HTML", reply_markup=kb_admin(),
    )
    context.user_data.clear()
    return ConversationHandler.END

async def cb_admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    async with get_session() as session:
        users = (await session.execute(select(func.count(User.id)))).scalar() or 0
        lookups = (await session.execute(select(func.count(LookupHistory.id)))).scalar() or 0
        success = (await session.execute(
            select(func.count(LookupHistory.id)).where(LookupHistory.success.is_(True))
        )).scalar() or 0
        credits = (await session.execute(select(func.sum(User.credits)))).scalar() or 0
        refs = (await session.execute(select(func.count(Referral.id)))).scalar() or 0
        blocked = (await session.execute(
            select(func.count(User.id)).where(User.is_blocked.is_(True))
        )).scalar() or 0
    text = (
        f"<b>📊 BOT STATISTICS</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Users: <b>{users}</b>\n🚫 Blocked: <b>{blocked}</b>\n"
        f"🔍 Lookups: <b>{lookups}</b>\n✅ Success: <b>{success}</b>\n"
        f"💳 Credits in system: <b>{credits}</b>\n🤝 Referrals: <b>{refs}</b>"
    )
    await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb_admin())

async def cb_admin_api(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    async with get_session() as session:
        r = await session.execute(select(ApiHealth).where(ApiHealth.api_name == "primary"))
        api = r.scalar_one_or_none()
        enabled = (await get_setting(session, "api_enabled", "true")).lower() == "true"
    if not api:
        text = "No API data yet."
    else:
        last_ok = api.last_success.strftime("%Y-%m-%d %H:%M") if api.last_success else "Never"
        last_fail = api.last_failure.strftime("%Y-%m-%d %H:%M") if api.last_failure else "Never"
        text = (
            f"<b>🔌 API STATUS</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Enabled: <b>{'Yes' if enabled else 'No'}</b>\n"
            f"Requests: <b>{api.total_requests}</b>\n"
            f"Successes: <b>{api.total_successes}</b>\n"
            f"Consec fails: <b>{api.consecutive_failures}</b>\n"
            f"Last OK: {last_ok}\nLast Fail: {last_fail}\n"
            f"Error: <code>{(api.last_error or '—')[:120]}</code>"
        )
    await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb_admin())

async def cb_admin_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    async with get_session() as session:
        lc = await get_setting(session, "lookup_cost", str(LOOKUP_COST))
        wc = await get_setting(session, "welcome_credits", str(WELCOME_CREDITS))
        rr = await get_setting(session, "referral_reward", str(REFERRAL_REWARD))
        db = await get_setting(session, "daily_bonus", str(DAILY_BONUS))
        mt = await get_setting(session, "maintenance_mode", "false")
    text = (
        f"<b>⚙️ BOT SETTINGS</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💳 Lookup Cost: <b>{lc}</b>\n🎁 Welcome: <b>{wc}</b>\n"
        f"🤝 Referral: <b>{rr}</b>\n☀️ Daily: <b>{db}</b>\n"
        f"🛠 Maintenance: <b>{mt}</b>\n\nTap to change."
    )
    await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb_settings())

async def cb_toggle_maint(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    async with get_session() as session:
        cur = (await get_setting(session, "maintenance_mode", "false")).lower()
        new = "false" if cur == "true" else "true"
        await set_setting(session, "maintenance_mode", new)
        session.add(AdminLog(admin_id=q.from_user.id, action="toggle_maintenance", details=new))
    await q.edit_message_text(f"🛠 Maintenance → <b>{new}</b>", parse_mode="HTML", reply_markup=kb_settings())

async def cb_admin_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return ConversationHandler.END
    context.user_data["admin_action"] = "add"
    await q.edit_message_text(
        "Send: <code>USER_ID AMOUNT</code>\nExample: <code>123456789 10</code>",
        parse_mode="HTML", reply_markup=kb_cancel(),
    )
    return WAITING_ADMIN

async def cb_admin_deduct(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return ConversationHandler.END
    context.user_data["admin_action"] = "deduct"
    await q.edit_message_text(
        "Send: <code>USER_ID AMOUNT</code>",
        parse_mode="HTML", reply_markup=kb_cancel(),
    )
    return WAITING_ADMIN

async def cb_admin_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return ConversationHandler.END
    context.user_data["admin_action"] = "search"
    await q.edit_message_text("Send Telegram User ID:", reply_markup=kb_cancel())
    return WAITING_ADMIN

async def cb_admin_block(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return ConversationHandler.END
    context.user_data["admin_action"] = "block"
    await q.edit_message_text(
        "Send: <code>USER_ID block</code> or <code>USER_ID unblock</code>",
        parse_mode="HTML", reply_markup=kb_cancel(),
    )
    return WAITING_ADMIN

async def cb_set_setting(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return ConversationHandler.END
    mapping = {
        "set_lookup_cost": ("lookup_cost", "Lookup Cost"),
        "set_welcome": ("welcome_credits", "Welcome Credits"),
        "set_referral": ("referral_reward", "Referral Reward"),
        "set_daily": ("daily_bonus", "Daily Bonus"),
    }
    if q.data not in mapping:
        return ConversationHandler.END
    key, label = mapping[q.data]
    context.user_data["admin_action"] = "set"
    context.user_data["setting_key"] = key
    await q.edit_message_text(
        f"Send new integer value for <b>{label}</b>:",
        parse_mode="HTML", reply_markup=kb_cancel(),
    )
    return WAITING_ADMIN

async def msg_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not is_admin(update.effective_user.id):
        return ConversationHandler.END
    action = context.user_data.get("admin_action")
    parts = (update.message.text or "").strip().split()

    async with get_session() as session:
        if action in ("add", "deduct"):
            if len(parts) != 2 or not parts[0].isdigit() or not parts[1].lstrip("-").isdigit():
                await update.message.reply_text("Format: USER_ID AMOUNT")
                return WAITING_ADMIN
            uid, amt = int(parts[0]), int(parts[1])
            amt = abs(amt) if action == "add" else -abs(amt)
            ok, bal, msg = await add_credits(
                session, uid, amt, "admin_adjustment", admin_id=update.effective_user.id,
            )
            await update.message.reply_text(
                f"{'✅' if ok else '❌'} {msg}. Balance: {bal}" if ok else f"❌ {msg}",
                reply_markup=kb_admin(),
            )
        elif action == "search":
            if not parts or not parts[0].isdigit():
                await update.message.reply_text("Send numeric ID.")
                return WAITING_ADMIN
            u = await get_user(session, int(parts[0]))
            if not u:
                await update.message.reply_text("Not found.", reply_markup=kb_admin())
            else:
                await update.message.reply_text(
                    f"ID: {u.telegram_id}\nName: {u.first_name}\nCredits: {u.credits}\n"
                    f"Lookups: {u.total_lookups}\nBlocked: {u.is_blocked}\nJoined: {u.created_at}",
                    reply_markup=kb_admin(),
                )
        elif action == "block":
            if len(parts) != 2 or not parts[0].isdigit() or parts[1] not in ("block", "unblock"):
                await update.message.reply_text("Format: USER_ID block|unblock")
                return WAITING_ADMIN
            uid = int(parts[0])
            u = await get_user(session, uid)
            if not u:
                await update.message.reply_text("Not found.", reply_markup=kb_admin())
            else:
                u.is_blocked = parts[1] == "block"
                session.add(AdminLog(
                    admin_id=update.effective_user.id,
                    action=parts[1], target_user_id=uid,
                ))
                await update.message.reply_text(
                    f"✅ User {uid} {parts[1]}ed.", reply_markup=kb_admin(),
                )
        elif action == "set":
            key = context.user_data.get("setting_key")
            if not key or not parts or not parts[0].isdigit():
                await update.message.reply_text("Send non-negative integer.")
                return WAITING_ADMIN
            val = str(max(0, int(parts[0])))
            await set_setting(session, key, val)
            session.add(AdminLog(
                admin_id=update.effective_user.id, action="set_setting", details=f"{key}={val}",
            ))
            await update.message.reply_text(
                f"✅ {key} = {val}", parse_mode="HTML", reply_markup=kb_settings(),
            )
        else:
            await update.message.reply_text("Unknown action.", reply_markup=kb_admin())

    context.user_data.clear()
    return ConversationHandler.END

async def cb_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return ConversationHandler.END
    context.user_data["admin_action"] = "broadcast"
    await q.edit_message_text(
        "Send the broadcast message (HTML ok). You will get a preview.",
        reply_markup=kb_cancel(),
    )
    return WAITING_BROADCAST

async def msg_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not is_admin(update.effective_user.id):
        return ConversationHandler.END
    context.user_data["broadcast_text"] = update.message.text or ""
    await update.message.reply_text(
        f"<b>📢 PREVIEW</b>\n━━━━━━━━━━━━━━━━━━━━\n\n{context.user_data['broadcast_text']}\n\nConfirm?",
        parse_mode="HTML", reply_markup=kb_broadcast_confirm(),
    )
    return ConversationHandler.END

async def cb_broadcast_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    text = context.user_data.get("broadcast_text")
    if not text:
        await q.edit_message_text("No message.", reply_markup=kb_admin())
        return
    await q.edit_message_text("📤 Sending…")
    async with get_session() as session:
        ids = [r[0] for r in (await session.execute(
            select(User.telegram_id).where(User.is_blocked.is_(False))
        )).all()]
    ok = fail = 0
    for uid in ids:
        try:
            await context.bot.send_message(uid, text, parse_mode="HTML")
            ok += 1
        except Exception:
            fail += 1
    async with get_session() as session:
        session.add(AdminLog(
            admin_id=q.from_user.id, action="broadcast",
            details=f"sent={ok}, failed={fail}",
        ))
    await q.edit_message_text(f"✅ Sent: {ok} | Failed: {fail}", reply_markup=kb_admin())
    context.user_data.clear()

async def cb_admin_logs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    async with get_session() as session:
        rows = (await session.execute(
            select(AdminLog).order_by(desc(AdminLog.created_at)).limit(15)
        )).scalars().all()
    if not rows:
        text = "No logs yet."
    else:
        lines = ["<b>📜 ADMIN LOGS</b>", "━━━━━━━━━━━━━━━━━━━━", ""]
        for r in rows:
            ts = r.created_at.strftime("%m-%d %H:%M") if r.created_at else "—"
            lines.append(f"• {ts} | {r.action} | {r.admin_id} | {r.details or ''}")
        text = "\n".join(lines)[:4000]
    await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb_admin())

# ===========================================================================
# SLASH COMMANDS (admin)
# ===========================================================================
async def cmd_addcredits(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Usage: /addcredits USER_ID AMOUNT")
        return
    try:
        uid, amt = int(context.args[0]), int(context.args[1])
    except ValueError:
        await update.message.reply_text("Invalid numbers.")
        return
    async with get_session() as session:
        ok, bal, msg = await add_credits(
            session, uid, abs(amt), "admin_cmd", admin_id=update.effective_user.id,
        )
    await update.message.reply_text(f"{'✅' if ok else '❌'} Balance: {bal}" if ok else f"❌ {msg}")

async def cmd_deductcredits(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Usage: /deductcredits USER_ID AMOUNT")
        return
    try:
        uid, amt = int(context.args[0]), int(context.args[1])
    except ValueError:
        await update.message.reply_text("Invalid numbers.")
        return
    async with get_session() as session:
        ok, bal, msg = await add_credits(
            session, uid, -abs(amt), "admin_cmd", admin_id=update.effective_user.id,
        )
    await update.message.reply_text(f"{'✅' if ok else '❌'} Balance: {bal}" if ok else f"❌ {msg}")

async def cmd_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /user USER_ID")
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid ID.")
        return
    async with get_session() as session:
        u = await get_user(session, uid)
    if not u:
        await update.message.reply_text("Not found.")
        return
    await update.message.reply_text(
        f"ID: {u.telegram_id}\nCredits: {u.credits}\nLookups: {u.total_lookups}\n"
        f"Blocked: {u.is_blocked}\nJoined: {u.created_at}"
    )

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    async with get_session() as session:
        users = (await session.execute(select(func.count(User.id)))).scalar() or 0
        lookups = (await session.execute(select(func.count(LookupHistory.id)))).scalar() or 0
    await update.message.reply_text(f"Users: {users}\nLookups: {lookups}")

async def cmd_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    async with get_session() as session:
        cur = (await get_setting(session, "maintenance_mode", "false")).lower()
        new = "false" if cur == "true" else "true"
        await set_setting(session, "maintenance_mode", new)
    await update.message.reply_text(f"Maintenance → {new}")

# ===========================================================================
# BUILD & RUN
# ===========================================================================
async def post_init(app: Application) -> None:
    await init_db()
    me = await app.bot.get_me()
    logger.info("Bot online as @%s (id=%s)", me.username, me.id)
    print(f"\n✅ Bot started: @{me.username}")
    print(f"   Admin ID: {ADMIN_IDS}")
    print("   Telegram pe /start dabao\n")

def main() -> None:
    if not BOT_TOKEN or BOT_TOKEN.startswith("YOUR_"):
        print("❌ BOT_TOKEN set nahi hai!")
        sys.exit(1)

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .concurrent_updates(True)
        .build()
    )

    lookup_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(cb_lookup, pattern="^lookup$")],
        states={WAITING_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, msg_number)]},
        fallbacks=[
            CallbackQueryHandler(cb_main_menu, pattern="^main_menu$"),
            CommandHandler("start", cmd_start),
        ],
        allow_reentry=True, name="lookup", persistent=False,
    )

    admin_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(cb_admin_add, pattern="^admin_add$"),
            CallbackQueryHandler(cb_admin_deduct, pattern="^admin_deduct$"),
            CallbackQueryHandler(cb_admin_search, pattern="^admin_search$"),
            CallbackQueryHandler(cb_admin_block, pattern="^admin_block$"),
            CallbackQueryHandler(cb_set_setting, pattern="^set_"),
        ],
        states={WAITING_ADMIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, msg_admin_input)]},
        fallbacks=[
            CallbackQueryHandler(cb_main_menu, pattern="^main_menu$"),
            CallbackQueryHandler(cb_admin, pattern="^admin$"),
            CommandHandler("start", cmd_start),
        ],
        allow_reentry=True, name="admin_input", persistent=False,
    )

    broadcast_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(cb_broadcast_start, pattern="^admin_broadcast$")],
        states={WAITING_BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, msg_broadcast)]},
        fallbacks=[
            CallbackQueryHandler(cb_admin, pattern="^admin$"),
            CallbackQueryHandler(cb_main_menu, pattern="^main_menu$"),
            CommandHandler("start", cmd_start),
        ],
        allow_reentry=True, name="broadcast", persistent=False,
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(lookup_conv)
    app.add_handler(admin_conv)
    app.add_handler(broadcast_conv)

    app.add_handler(CallbackQueryHandler(cb_main_menu, pattern="^main_menu$"))
    app.add_handler(CallbackQueryHandler(cb_account, pattern="^account$"))
    app.add_handler(CallbackQueryHandler(cb_history, pattern="^history$"))
    app.add_handler(CallbackQueryHandler(cb_daily, pattern="^daily$"))
    app.add_handler(CallbackQueryHandler(cb_help, pattern="^help$"))
    app.add_handler(CallbackQueryHandler(cb_premium, pattern="^premium_info$"))
    app.add_handler(CallbackQueryHandler(cb_referral, pattern="^referral$"))
    app.add_handler(CallbackQueryHandler(cb_ref_link, pattern="^ref_link$"))
    app.add_handler(CallbackQueryHandler(cb_ref_stats, pattern="^ref_stats$"))
    app.add_handler(CallbackQueryHandler(cb_admin, pattern="^admin$"))
    app.add_handler(CallbackQueryHandler(cb_admin_stats, pattern="^admin_stats$"))
    app.add_handler(CallbackQueryHandler(cb_admin_api, pattern="^admin_api$"))
    app.add_handler(CallbackQueryHandler(cb_admin_settings, pattern="^admin_settings$"))
    app.add_handler(CallbackQueryHandler(cb_toggle_maint, pattern="^toggle_maint$"))
    app.add_handler(CallbackQueryHandler(cb_broadcast_confirm, pattern="^broadcast_confirm$"))
    app.add_handler(CallbackQueryHandler(cb_admin_logs, pattern="^admin_logs$"))

    app.add_handler(CommandHandler("addcredits", cmd_addcredits))
    app.add_handler(CommandHandler("deductcredits", cmd_deductcredits))
    app.add_handler(CommandHandler("user", cmd_user))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("maintenance", cmd_maintenance))

    async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.exception("Error: %s", context.error)

    app.add_error_handler(on_error)

    print("🚀 Starting Premium Number Info Bot…")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
