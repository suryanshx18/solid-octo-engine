import sqlite3
import secrets
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# =========================
# CONFIG
# =========================

BOT_TOKEN = "PASTE_YOUR_BOT_TOKEN_HERE"

# Apna Telegram numeric user ID yahan daalo
OWNER_ID = 123456789

# =========================
# DATABASE
# =========================

DB_NAME = "orders.db"


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
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

    conn.commit()
    conn.close()


def create_order(user_id, telegram_id, amount):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO orders
        (user_id, telegram_id, amount, status)
        VALUES (?, ?, ?, 'pending')
        """,
        (user_id, telegram_id, amount),
    )

    order_id = cur.lastrowid

    conn.commit()
    conn.close()

    return order_id


def get_order(order_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM orders WHERE id = ?",
        (order_id,)
    )

    order = cur.fetchone()

    conn.close()

    return order


def approve_order(order_id, confirmation_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE orders
        SET status = 'approved',
            confirmation_id = ?
        WHERE id = ?
        AND status = 'pending'
        """,
        (confirmation_id, order_id),
    )

    changed = cur.rowcount

    conn.commit()
    conn.close()

    return changed


def reject_order(order_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE orders
        SET status = 'rejected'
        WHERE id = ?
        AND status = 'pending'
        """,
        (order_id,),
    )

    changed = cur.rowcount

    conn.commit()
    conn.close()

    return changed


# =========================
# /START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    await update.message.reply_text(
        f"Hello {user.first_name}!\n\n"
        "Payment/order request banane ke liye:\n"
        "/order\n\n"
        "Example:\n"
        "/order 500"
    )


# =========================
# CREATE ORDER
# =========================

async def order(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    if not context.args:
        await update.message.reply_text(
            "Amount bhi do.\n\n"
            "Example:\n"
            "/order 500"
        )
        return

    amount = context.args[0]

    # Basic validation
    try:
        amount_float = float(amount)

        if amount_float <= 0:
            raise ValueError

    except ValueError:
        await update.message.reply_text(
            "Valid amount enter karo.\n"
            "Example: /order 500"
        )
        return

    # User apna Telegram ID submit kar raha hai
    telegram_id = str(user.id)

    order_id = create_order(
        user_id=user.id,
        telegram_id=telegram_id,
        amount=amount,
    )

    await update.message.reply_text(
        f"Order created successfully.\n\n"
        f"Order ID: #{order_id}\n"
        f"Amount: ₹{amount}\n"
        f"Status: Pending\n\n"
        "Payment complete hone ke baad owner verification karega."
    )

# Owner notification
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ Approve",
                callback_data=f"approve:{order_id}"
            ),
            InlineKeyboardButton(
                "❌ Reject",
                callback_data=f"reject:{order_id}"
            ),
        ]
    ])

    await context.bot.send_message(
        chat_id=OWNER_ID,
        text=(
            "🔔 NEW ORDER\n\n"
            f"Order ID: #{order_id}\n"
            f"User: {user.first_name}\n"
            f"Username: @{user.username if user.username else 'N/A'}\n"
            f"Telegram ID: {user.id}\n"
            f"Amount: ₹{amount}\n\n"
            "Payment verify karke action choose karo."
        ),
        reply_markup=keyboard,
    )


# =========================
# OWNER BUTTONS
# =========================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    # Sirf owner buttons use kar sakta hai
    if query.from_user.id != OWNER_ID:
        await query.answer(
            "You are not authorized.",
            show_alert=True
        )
        return

    data = query.data

    action, order_id = data.split(":")

    order_id = int(order_id)

    order_data = get_order(order_id)

    if not order_data:
        await query.edit_message_text(
            "❌ Order not found."
        )
        return

    # Database structure:
    # id, user_id, telegram_id, amount,
    # status, confirmation_id, created_at

    db_order_id = order_data[0]
    user_id = order_data[1]
    telegram_id = order_data[2]
    amount = order_data[3]
    status = order_data[4]

    if status != "pending":
        await query.answer(
            f"Order already {status}.",
            show_alert=True
        )
        return

    # =========================
    # APPROVE
    # =========================

    if action == "approve":

        confirmation_id = (
            "CONF-"
            + secrets.token_hex(5).upper()
        )

        changed = approve_order(
            order_id,
            confirmation_id
        )

        if changed == 0:
            await query.answer(
                "Order already processed.",
                show_alert=True
            )
            return

        # User ko confirmation
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "✅ PAYMENT APPROVED\n\n"
                f"Order ID: #{order_id}\n"
                f"Amount: ₹{amount}\n\n"
                f"Confirmation ID:\n"
                f"{confirmation_id}\n\n"
                "Your order has been approved."
            ),
            parse_mode="Markdown",
        )

        await query.edit_message_text(
            (
                "✅ ORDER APPROVED\n\n"
                f"Order ID: #{order_id}\n"
                f"Telegram ID: {telegram_id}\n"
                f"Amount: ₹{amount}\n"
                f"Confirmation ID: {confirmation_id}"
            )
        )

    # =========================
    # REJECT
    # =========================

    elif action == "reject":

        changed = reject_order(order_id)

        if changed == 0:
            await query.answer(
                "Order already processed.",
                show_alert=True
            )
            return

        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "❌ PAYMENT/ORDER REJECTED\n\n"
                f"Order ID: #{order_id}\n"
                f"Amount: ₹{amount}\n\n"
                "Please contact the owner if you think this was a mistake."
            )
        )

        await query.edit_message_text(
            (
                "❌ ORDER REJECTED\n\n"
                f"Order ID: #{order_id}\n"
                f"Telegram ID: {telegram_id}\n"
                f"Amount: ₹{amount}"
            )
        )


# =========================
# /MYORDERS
# =========================

async def myorders(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user_id = update.effective_user.id

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, amount, status, confirmation_id
        FROM orders
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 10
        """,
        (user_id,),
    )

    orders = cur.fetchall()

    conn.close()

    if not orders:
        await update.message.reply_text(
            "Tumhara koi order nahi mila."
        )
        return

    text = "📋 YOUR ORDERS\n\n"

    for order_id, amount, status, confirmation_id in orders:

        text += (
            f"Order #{order_id}\n"
            f"Amount: ₹{amount}\n"
            f"Status: {status}\n"
        )

        if confirmation_id:
            text += f"Confirmation: {confirmation_id}\n"

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

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, user_id, amount, status
        FROM orders
        WHERE status = 'pending'
        ORDER BY id DESC
        LIMIT 20
        """
    )

    orders = cur.fetchall()

    conn.close()

    if not orders:
        await update.message.reply_text(
            "No pending orders."
        )
        return

    text = "🔔 PENDING ORDERS\n\n"

    for order_id, user_id, amount, status in orders:

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

    app = Application.builder().token(
        BOT_TOKEN
    ).build()

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


if name == "main":
    main()
