import os
import sqlite3
import secrets

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# =========================
# CONFIG
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

DB_NAME = "orders.db"


# =========================
# DATABASE
# =========================

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                telegram_id TEXT NOT NULL,
                amount TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                confirmation_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)


def create_order(user_id, telegram_id, amount):
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.execute(
            """
            INSERT INTO orders
            (user_id, telegram_id, amount, status)
            VALUES (?, ?, ?, 'pending')
            """,
            (user_id, telegram_id, amount),
        )
        return cur.lastrowid


def get_order(order_id):
    with sqlite3.connect(DB_NAME) as conn:
        return conn.execute(
            "SELECT * FROM orders WHERE id = ?",
            (order_id,),
        ).fetchone()


def approve_order(order_id, confirmation_id):
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.execute(
            """
            UPDATE orders
            SET status = 'approved',
                confirmation_id = ?
            WHERE id = ?
            AND status = 'pending'
            """,
            (confirmation_id, order_id),
        )
        return cur.rowcount


def reject_order(order_id):
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.execute(
            """
            UPDATE orders
            SET status = 'rejected'
            WHERE id = ?
            AND status = 'pending'
            """,
            (order_id,),
        )
        return cur.rowcount


# =========================
# /START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    await update.message.reply_text(
        f"Hello {user.first_name}! 👋\n\n"
        "Payment/order request banane ke liye:\n"
        "/order 500\n\n"
        "Apne orders dekhne ke liye:\n"
        "/myorders"
    )


# =========================
# /ORDER
# =========================

async def order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not context.args:
        await update.message.reply_text(
            "❌ Amount bhi do.\n\n"
            "Example:\n"
            "/order 500"
        )
        return

    amount = context.args[0]

    try:
        amount_float = float(amount)

        if amount_float <= 0:
            raise ValueError

    except (ValueError, TypeError):
        await update.message.reply_text(
            "❌ Valid amount enter karo.\n\n"
            "Example:\n"
            "/order 500"
        )
        return

    telegram_id = str(user.id)

    order_id = create_order(
        user_id=user.id,
        telegram_id=telegram_id,
        amount=amount,
    )

    await update.message.reply_text(
        "✅ ORDER CREATED\n\n"
        f"Order ID: #{order_id}\n"
        f"Amount: ₹{amount}\n"
        "Status: Pending\n\n"
        "Payment complete hone ke baad owner verification karega."
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ Approve",
                callback_data=f"approve:{order_id}",
            ),
            InlineKeyboardButton(
                "❌ Reject",
                callback_data=f"reject:{order_id}",
            ),
        ]
    ])

    username = (
        f"@{user.username}"
        if user.username
        else "N/A"
    )

    await context.bot.send_message(
        chat_id=OWNER_ID,
        text=(
            "🔔 NEW ORDER\n\n"
            f"Order ID: #{order_id}\n"
            f"User: {user.first_name}\n"
            f"Username: {username}\n"
            f"Telegram ID: {user.id}\n"
            f"Amount: ₹{amount}\n\n"
            "Payment verify karke action choose karo."
        ),
        reply_markup=keyboard,
    )


# =========================
# APPROVE / REJECT BUTTONS
# =========================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query

    if query.from_user.id != OWNER_ID:
        await query.answer(
            "❌ You are not authorized.",
            show_alert=True,
        )
        return

    await query.answer()

    try:
        action, order_id_text = query.data.split(":", 1)
        order_id = int(order_id_text)

    except (ValueError, AttributeError):
        await query.edit_message_text(
            "❌ Invalid button data."
        )
        return

    if action not in ("approve", "reject"):
        await query.edit_message_text(
            "❌ Unknown action."
        )
        return

    order_data = get_order(order_id)

    if not order_data:
        await query.edit_message_text(
            "❌ Order not found."
        )
        return

    # id, user_id, telegram_id, amount,
    # status, confirmation_id, created_at

    user_id = order_data[1]
    telegram_id = order_data[2]
    amount = order_data[3]
    status = order_data[4]

    if status != "pending":
        await query.answer(
            f"Order already {status}.",
            show_alert=True,
        )
        return

    # =====================
    # APPROVE
    # =====================

    if action == "approve":

        confirmation_id = (
            "CONF-"
            + secrets.token_hex(5).upper()
        )

        changed = approve_order(
            order_id,
            confirmation_id,
        )

        if changed == 0:
            await query.answer(
                "Order already processed.",
                show_alert=True,
            )
            return

        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "✅ PAYMENT APPROVED\n\n"
                    f"Order ID: #{order_id}\n"
                    f"Amount: ₹{amount}\n\n"
                    "Confirmation ID:\n"
                    f"{confirmation_id}\n\n"
                    "Your order has been approved."
                ),
            )

        except Exception as e:
            print(
                f"Could not notify user "
                f"{user_id}: {e}"
            )

        await query.edit_message_text(
            "✅ ORDER APPROVED\n\n"
            f"Order ID: #{order_id}\n"
            f"Telegram ID: {telegram_id}\n"
            f"Amount: ₹{amount}\n"
            f"Confirmation ID: {confirmation_id}"
        )

    # =====================
    # REJECT
    # =====================

    elif action == "reject":

        changed = reject_order(order_id)

        if changed == 0:
            await query.answer(
                "Order already processed.",
                show_alert=True,
            )
            return

        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "❌ PAYMENT/ORDER REJECTED\n\n"
                    f"Order ID: #{order_id}\n"
                    f"Amount: ₹{amount}\n\n"
                    "Please contact the owner "
                    "if you think this was a mistake."
                ),
            )

        except Exception as e:
            print(
                f"Could not notify user "
                f"{user_id}: {e}"
            )

        await query.edit_message_text(
            "❌ ORDER REJECTED\n\n"
            f"Order ID: #{order_id}\n"
            f"Telegram ID: {telegram_id}\n"
            f"Amount: ₹{amount}"
        )


# =========================
# /MYORDERS
# =========================

async def myorders(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    user_id = update.effective_user.id

    with sqlite3.connect(DB_NAME) as conn:
        orders = conn.execute(
            """
            SELECT id, amount, status, confirmation_id
            FROM orders
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 10
            """,
            (user_id,),
        ).fetchall()

    if not orders:
        await update.message.reply_text(
            "Tumhara koi order nahi mila."
        )
        return

    text = "📋 YOUR ORDERS\n\n"

    for (
        order_id,
        amount,
        status,
        confirmation_id,
    ) in orders:

        text += (
            f"Order #{order_id}\n"
            f"Amount: ₹{amount}\n"
            f"Status: {status}\n"
        )

        if confirmation_id:
            text += (
                f"Confirmation: "
                f"{confirmation_id}\n"
            )

        text += "\n"

    await update.message.reply_text(text)


# =========================
# /ADMIN
# =========================

async def admin(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text(
            "❌ Unauthorized."
        )
        return

    with sqlite3.connect(DB_NAME) as conn:
        orders = conn.execute(
            """
            SELECT id, user_id, amount, status
            FROM orders
            WHERE status = 'pending'
            ORDER BY id DESC
            LIMIT 20
            """
        ).fetchall()

    if not orders:
        await update.message.reply_text(
            "✅ No pending orders."
        )
        return

    text = "🔔 PENDING ORDERS\n\n"

    for (
        order_id,
        user_id,
        amount,
        status,
    ) in orders:

        text += (
            f"#{order_id}\n"
            f"User ID: {user_id}\n"
            f"Amount: ₹{amount}\n"
            f"Status: {status}\n\n"
        )

    await update.message.reply_text(text)


# =========================
# MAIN
# =========================

def main():

    init_db()

    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN environment variable "
            "is missing."
        )

    if OWNER_ID == 0:
        raise RuntimeError(
            "OWNER_ID environment variable "
            "is missing or invalid."
        )

    app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("order", order)
    )

    app.add_handler(
        CommandHandler("myorders", myorders)
    )

    app.add_handler(
        CommandHandler("admin", admin)
    )

    app.add_handler(
        CallbackQueryHandler(button_handler)
    )

    print("Bot is running...")

    app.run_polling()


# =========================
# PYTHON ENTRY POINT
# =========================

if __name__ == "__main__":
    main()
