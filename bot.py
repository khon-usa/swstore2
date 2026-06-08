# -*- coding: utf-8 -*-
# ============================================================
#   SW STORE BOT - BARCHA KODLAR BITTA FAYLDA
# ============================================================

import aiosqlite
import asyncio
import random
import string
from datetime import datetime
from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, filters, ContextTypes
)

# ============================================================
#   CONFIG
# ============================================================

TOKEN = "8015373007:AAF_ia152YfnwlJCikXIQEdmIgahQ-V2O6Y"
ADMIN_IDS = [6273410095]
KARTA = "8600 1104 6209 0477"
KARTA_EGASI = "Kapitalbank"
BOT_USERNAME = "swstoree_bot"

VIP_LEVELS = {
    "bronza": {"min_orders": 3,  "discount": 5,  "name": "🥉 Bronza"},
    "kumush": {"min_orders": 10, "discount": 10, "name": "🥈 Kumush"},
    "oltin":  {"min_orders": 25, "discount": 15, "name": "🥇 Oltin"},
}

DAILY_BONUS   = 10
REFERAL_BONUS = 50
TOKEN_VALUE   = 100   # 1 token = 100 so'm chegirma

# ============================================================
#   DATABASE
# ============================================================

DB_PATH = "swstore.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            telegram_id INTEGER UNIQUE,
            username TEXT,
            full_name TEXT,
            phone TEXT,
            tokens INTEGER DEFAULT 0,
            vip_level TEXT DEFAULT 'oddiy',
            total_orders INTEGER DEFAULT 0,
            referal_code TEXT UNIQUE,
            refered_by INTEGER,
            last_bonus DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            emoji TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER,
            name TEXT,
            description TEXT,
            price INTEGER,
            photo_id TEXT,
            sizes TEXT DEFAULT 'S,M,L,XL',
            stock INTEGER DEFAULT 100,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (category_id) REFERENCES categories(id)
        );
        CREATE TABLE IF NOT EXISTS cart (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            product_id INTEGER,
            size TEXT,
            quantity INTEGER DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users(telegram_id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            total_price INTEGER,
            discount INTEGER DEFAULT 0,
            address TEXT,
            phone TEXT,
            status TEXT DEFAULT 'kutilmoqda',
            payment_photo TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(telegram_id)
        );
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            product_id INTEGER,
            size TEXT,
            quantity INTEGER,
            price INTEGER,
            FOREIGN KEY (order_id) REFERENCES orders(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        );
        CREATE TABLE IF NOT EXISTS promo_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            discount INTEGER,
            max_uses INTEGER DEFAULT 100,
            used_count INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS token_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        await db.commit()

        categories = [
            ("Futbolka", "👕"), ("Shim", "👖"), ("Short", "🩳"),
            ("Ayol kiyim", "👗"), ("Aksessuarlar", "👟"),
        ]
        for cat in categories:
            try:
                await db.execute("INSERT INTO categories (name, emoji) VALUES (?, ?)", cat)
            except Exception:
                pass
        await db.commit()

# --- User ---
async def get_user(telegram_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)) as cur:
            return await cur.fetchone()

async def create_user(telegram_id, username, full_name, referal_code, refered_by=None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (telegram_id, username, full_name, referal_code, refered_by) VALUES (?,?,?,?,?)",
            (telegram_id, username, full_name, referal_code, refered_by)
        )
        await db.commit()

async def update_user_phone(telegram_id, phone):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET phone=? WHERE telegram_id=?", (phone, telegram_id))
        await db.commit()

async def add_tokens(telegram_id, amount, reason):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET tokens=tokens+? WHERE telegram_id=?", (amount, telegram_id))
        await db.execute("INSERT INTO token_history (user_id, amount, reason) VALUES (?,?,?)",
                         (telegram_id, amount, reason))
        await db.commit()

async def use_tokens(telegram_id, amount):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET tokens=tokens-? WHERE telegram_id=?", (amount, telegram_id))
        await db.execute("INSERT INTO token_history (user_id, amount, reason) VALUES (?,?,?)",
                         (telegram_id, -amount, "Chegirma uchun ishlatildi"))
        await db.commit()

async def claim_daily_bonus(telegram_id):
    today = datetime.now().date().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT last_bonus FROM users WHERE telegram_id=?", (telegram_id,)) as cur:
            row = await cur.fetchone()
            if row and row["last_bonus"] == today:
                return False
        await db.execute("UPDATE users SET last_bonus=?, tokens=tokens+? WHERE telegram_id=?",
                         (today, DAILY_BONUS, telegram_id))
        await db.execute("INSERT INTO token_history (user_id, amount, reason) VALUES (?,?,?)",
                         (telegram_id, DAILY_BONUS, "Kunlik bonus"))
        await db.commit()
        return True

async def update_vip(telegram_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT total_orders FROM users WHERE telegram_id=?", (telegram_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                return
            orders = row["total_orders"]
        level = "oddiy"
        if orders >= VIP_LEVELS["oltin"]["min_orders"]:
            level = "oltin"
        elif orders >= VIP_LEVELS["kumush"]["min_orders"]:
            level = "kumush"
        elif orders >= VIP_LEVELS["bronza"]["min_orders"]:
            level = "bronza"
        await db.execute("UPDATE users SET vip_level=? WHERE telegram_id=?", (level, telegram_id))
        await db.commit()

# --- Kategoriya ---
async def get_categories():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM categories") as cur:
            return await cur.fetchall()

# --- Mahsulot ---
async def get_products_by_category(category_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM products WHERE category_id=? AND is_active=1", (category_id,)
        ) as cur:
            return await cur.fetchall()

async def get_product(product_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM products WHERE id=?", (product_id,)) as cur:
            return await cur.fetchone()

async def search_products(query):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM products WHERE name LIKE ? AND is_active=1", (f"%{query}%",)
        ) as cur:
            return await cur.fetchall()

async def add_product(category_id, name, description, price, photo_id, sizes):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO products (category_id, name, description, price, photo_id, sizes) VALUES (?,?,?,?,?,?)",
            (category_id, name, description, price, photo_id, sizes)
        )
        await db.commit()

async def delete_product(product_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE products SET is_active=0 WHERE id=?", (product_id,))
        await db.commit()

async def get_all_products():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT p.*, c.name as cat_name FROM products p JOIN categories c ON p.category_id=c.id WHERE p.is_active=1"
        ) as cur:
            return await cur.fetchall()

# --- Savatcha ---
async def add_to_cart(user_id, product_id, size):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM cart WHERE user_id=? AND product_id=? AND size=?",
            (user_id, product_id, size)
        ) as cur:
            existing = await cur.fetchone()
        if existing:
            await db.execute("UPDATE cart SET quantity=quantity+1 WHERE id=?", (existing[0],))
        else:
            await db.execute("INSERT INTO cart (user_id, product_id, size) VALUES (?,?,?)",
                             (user_id, product_id, size))
        await db.commit()

async def get_cart(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT c.*, p.name, p.price, p.photo_id FROM cart c JOIN products p ON c.product_id=p.id WHERE c.user_id=?",
            (user_id,)
        ) as cur:
            return await cur.fetchall()

async def clear_cart(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM cart WHERE user_id=?", (user_id,))
        await db.commit()

async def remove_cart_item(cart_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM cart WHERE id=?", (cart_id,))
        await db.commit()

# --- Buyurtma ---
async def create_order(user_id, total_price, discount, address, phone, items):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO orders (user_id, total_price, discount, address, phone) VALUES (?,?,?,?,?)",
            (user_id, total_price, discount, address, phone)
        )
        order_id = cursor.lastrowid
        for item in items:
            await db.execute(
                "INSERT INTO order_items (order_id, product_id, size, quantity, price) VALUES (?,?,?,?,?)",
                (order_id, item['product_id'], item['size'], item['quantity'], item['price'])
            )
        await db.execute("UPDATE users SET total_orders=total_orders+1 WHERE telegram_id=?", (user_id,))
        await db.commit()
        return order_id

async def update_order_status(order_id, status, payment_photo=None):
    async with aiosqlite.connect(DB_PATH) as db:
        if payment_photo:
            await db.execute("UPDATE orders SET status=?, payment_photo=? WHERE id=?",
                             (status, payment_photo, order_id))
        else:
            await db.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
        await db.commit()

async def get_user_orders(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC LIMIT 10", (user_id,)
        ) as cur:
            return await cur.fetchall()

async def get_order_items(order_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT oi.*, p.name FROM order_items oi JOIN products p ON oi.product_id=p.id WHERE oi.order_id=?",
            (order_id,)
        ) as cur:
            return await cur.fetchall()

# --- Promo kod ---
async def check_promo(code):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM promo_codes WHERE code=? AND is_active=1 AND used_count<max_uses", (code,)
        ) as cur:
            return await cur.fetchone()

async def use_promo(code):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE promo_codes SET used_count=used_count+1 WHERE code=?", (code,))
        await db.commit()

async def add_promo(code, discount, max_uses):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO promo_codes (code, discount, max_uses) VALUES (?,?,?)",
                         (code, discount, max_uses))
        await db.commit()

# --- Statistika ---
async def get_top_referals(limit=10):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT u.full_name, u.username, COUNT(r.id) as ref_count
            FROM users u LEFT JOIN users r ON r.refered_by=u.telegram_id
            GROUP BY u.telegram_id ORDER BY ref_count DESC LIMIT ?
        """, (limit,)) as cur:
            return await cur.fetchall()

async def get_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT COUNT(*) as count FROM users") as cur:
            users = (await cur.fetchone())["count"]
        async with db.execute("SELECT COUNT(*) as count FROM orders") as cur:
            orders = (await cur.fetchone())["count"]
        async with db.execute("SELECT SUM(total_price) as total FROM orders WHERE status='yetkazildi'") as cur:
            revenue = (await cur.fetchone())["total"] or 0
        return {"users": users, "orders": orders, "revenue": revenue}

# ============================================================
#   BOT HANDLERS
# ============================================================

# ConversationHandler states
(
    REGISTER_NAME, REGISTER_PHONE,
    CHECKOUT_ADDRESS, CHECKOUT_PHONE, CHECKOUT_PROMO, CHECKOUT_TOKENS, CHECKOUT_PAYMENT,
    ADMIN_PRODUCT_CAT, ADMIN_PRODUCT_NAME, ADMIN_PRODUCT_DESC,
    ADMIN_PRODUCT_PRICE, ADMIN_PRODUCT_PHOTO, ADMIN_PRODUCT_SIZES,
    ADMIN_PROMO_CODE, ADMIN_PROMO_DISCOUNT, ADMIN_PROMO_USES,
    ADMIN_DELETE_ID, SEARCH_QUERY,
) = range(18)

def main_menu(user=None):
    buttons = [
        ["🛍 Katalog", "🔍 Qidiruv"],
        ["🛒 Savatcha", "📦 Buyurtmalarim"],
        ["👤 Profil", "🎁 Kunlik bonus"],
        ["👥 Referal", "🏷 Promo kod"],
    ]
    if user and user["telegram_id"] in ADMIN_IDS:
        buttons.append(["⚙️ Admin panel"])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def admin_menu():
    return ReplyKeyboardMarkup([
        ["➕ Mahsulot qo'shish", "🗑 Mahsulot o'chirish"],
        ["🎟 Promo kod yaratish", "📊 Statistika"],
        ["🔙 Orqaga"],
    ], resize_keyboard=True)

# /start
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = ctx.args
    refered_by = None
    if args:
        ref_code = args[0]
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT telegram_id FROM users WHERE referal_code=?", (ref_code,)) as cur:
                row = await cur.fetchone()
                if row and row["telegram_id"] != user.id:
                    refered_by = row["telegram_id"]

    existing = await get_user(user.id)
    if not existing:
        ctx.user_data["refered_by"] = refered_by
        await update.message.reply_text(
            "👋 Xush kelibsiz! Ismingizni kiriting:"
        )
        return REGISTER_NAME

    db_user = await get_user(user.id)
    await update.message.reply_text(
        f"👋 Xush kelibsiz, {db_user['full_name']}!",
        reply_markup=main_menu(db_user)
    )
    return ConversationHandler.END

async def register_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["full_name"] = update.message.text
    kb = ReplyKeyboardMarkup(
        [[KeyboardButton("📱 Telefon raqamni yuborish", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True
    )
    await update.message.reply_text("📱 Telefon raqamingizni yuboring:", reply_markup=kb)
    return REGISTER_PHONE

async def register_phone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if update.message.contact:
        phone = update.message.contact.phone_number
    else:
        phone = update.message.text

    full_name = ctx.user_data.get("full_name", user.full_name)
    referal_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    refered_by = ctx.user_data.get("refered_by")

    await create_user(user.id, user.username, full_name, referal_code, refered_by)
    await update_user_phone(user.id, phone)

    if refered_by:
        await add_tokens(refered_by, REFERAL_BONUS, f"Referal bonus: {full_name}")

    db_user = await get_user(user.id)
    await update.message.reply_text(
        f"✅ Ro'yxatdan o'tdingiz!\n👤 Ism: {full_name}\n📱 Telefon: {phone}",
        reply_markup=main_menu(db_user)
    )
    return ConversationHandler.END

# Katalog
async def catalog(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cats = await get_categories()
    buttons = [[InlineKeyboardButton(f"{c['emoji']} {c['name']}", callback_data=f"cat_{c['id']}")]
               for c in cats]
    await update.message.reply_text("📂 Kategoriyani tanlang:",
                                    reply_markup=InlineKeyboardMarkup(buttons))

async def cat_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cat_id = int(query.data.split("_")[1])
    products = await get_products_by_category(cat_id)
    if not products:
        await query.edit_message_text("❌ Bu kategoriyada mahsulot yo'q.")
        return
    for p in products:
        text = f"*{p['name']}*\n{p['description']}\n💰 {p['price']:,} so'm\n📦 Hajmlar: {p['sizes']}"
        btn = InlineKeyboardMarkup([[
            InlineKeyboardButton("🛒 Savatga qo'shish", callback_data=f"addcart_{p['id']}")
        ]])
        if p["photo_id"]:
            await query.message.reply_photo(p["photo_id"], caption=text, parse_mode="Markdown", reply_markup=btn)
        else:
            await query.message.reply_text(text, parse_mode="Markdown", reply_markup=btn)

async def addcart_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.split("_")[1])
    product = await get_product(product_id)
    sizes = product["sizes"].split(",")
    buttons = [[InlineKeyboardButton(s.strip(), callback_data=f"size_{product_id}_{s.strip()}")]
               for s in sizes]
    await query.message.reply_text("📏 Hajmni tanlang:", reply_markup=InlineKeyboardMarkup(buttons))

async def size_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, product_id, size = query.data.split("_")
    await add_to_cart(query.from_user.id, int(product_id), size)
    await query.edit_message_text(f"✅ Savatchaga qo'shildi! Hajm: {size}")

# Qidiruv
async def search_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Mahsulot nomini kiriting:")
    return SEARCH_QUERY

async def search_query(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    results = await search_products(update.message.text)
    if not results:
        await update.message.reply_text("❌ Mahsulot topilmadi.")
    else:
        for p in results:
            text = f"*{p['name']}*\n{p['description']}\n💰 {p['price']:,} so'm"
            btn = InlineKeyboardMarkup([[
                InlineKeyboardButton("🛒 Savatga", callback_data=f"addcart_{p['id']}")
            ]])
            if p["photo_id"]:
                await update.message.reply_photo(p["photo_id"], caption=text, parse_mode="Markdown", reply_markup=btn)
            else:
                await update.message.reply_text(text, parse_mode="Markdown", reply_markup=btn)
    return ConversationHandler.END

# Savatcha
async def show_cart(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    items = await get_cart(user_id)
    if not items:
        await update.message.reply_text("🛒 Savatchangiz bo'sh.")
        return
    total = sum(i["price"] * i["quantity"] for i in items)
    text = "🛒 *Savatchangiz:*\n\n"
    buttons = []
    for item in items:
        text += f"• {item['name']} ({item['size']}) x{item['quantity']} — {item['price'] * item['quantity']:,} so'm\n"
        buttons.append([InlineKeyboardButton(f"❌ {item['name']} ({item['size']})",
                                             callback_data=f"rmcart_{item['id']}")])
    text += f"\n💰 *Jami: {total:,} so'm*"
    buttons.append([InlineKeyboardButton("✅ Buyurtma berish", callback_data="checkout")])
    buttons.append([InlineKeyboardButton("🗑 Savatchani tozalash", callback_data="clearcart")])
    await update.message.reply_text(text, parse_mode="Markdown",
                                    reply_markup=InlineKeyboardMarkup(buttons))

async def cart_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "clearcart":
        await clear_cart(query.from_user.id)
        await query.edit_message_text("🗑 Savatcha tozalandi.")
    elif query.data.startswith("rmcart_"):
        cart_id = int(query.data.split("_")[1])
        await remove_cart_item(cart_id)
        await query.edit_message_text("✅ Mahsulot olib tashlandi.")
    elif query.data == "checkout":
        await query.edit_message_text("🏠 Yetkazib berish manzilini kiriting:")
        ctx.user_data["checkout_step"] = "address"
        return CHECKOUT_ADDRESS

async def checkout_address(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["address"] = update.message.text
    await update.message.reply_text("📱 Telefon raqamingizni kiriting:")
    return CHECKOUT_PHONE

async def checkout_phone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["order_phone"] = update.message.text
    await update.message.reply_text("🏷 Promo kod bormi? (yo'q bo'lsa — bo'sh qoldiring):")
    return CHECKOUT_PROMO

async def checkout_promo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    ctx.user_data["promo_discount"] = 0
    if code:
        promo = await check_promo(code)
        if promo:
            ctx.user_data["promo_discount"] = promo["discount"]
            ctx.user_data["promo_code"] = code
            await update.message.reply_text(f"✅ Promo kod qabul qilindi! -{promo['discount']}% chegirma")
        else:
            await update.message.reply_text("❌ Noto'g'ri promo kod.")
    user = await get_user(update.effective_user.id)
    tokens = user["tokens"]
    await update.message.reply_text(
        f"🪙 Sizda {tokens} token bor. Nechta token ishlatmoqchisiz? (0 kiriting agar ishlatmasangiz)\n"
        f"1 token = {TOKEN_VALUE} so'm chegirma"
    )
    return CHECKOUT_TOKENS

async def checkout_tokens(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        tokens_use = int(update.message.text.strip())
    except ValueError:
        tokens_use = 0
    user = await get_user(update.effective_user.id)
    tokens_use = min(tokens_use, user["tokens"])
    ctx.user_data["tokens_use"] = tokens_use

    items = await get_cart(update.effective_user.id)
    total = sum(i["price"] * i["quantity"] for i in items)
    promo_d = ctx.user_data.get("promo_discount", 0)
    vip_d = VIP_LEVELS.get(user["vip_level"], {}).get("discount", 0) if user["vip_level"] != "oddiy" else 0
    discount = max(promo_d, vip_d)
    total_after = int(total * (1 - discount / 100)) - tokens_use * TOKEN_VALUE
    total_after = max(total_after, 0)
    ctx.user_data["final_total"] = total_after
    ctx.user_data["discount"] = discount

    await update.message.reply_text(
        f"💳 To'lov:\n"
        f"Karta: `{KARTA}`\n"
        f"Egasi: {KARTA_EGASI}\n"
        f"Summa: *{total_after:,} so'm*\n\n"
        f"To'lov chekini (screenshot) yuboring:",
        parse_mode="Markdown"
    )
    return CHECKOUT_PAYMENT

async def checkout_payment(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not update.message.photo:
        await update.message.reply_text("❌ Iltimos, to'lov chekini rasm sifatida yuboring.")
        return CHECKOUT_PAYMENT

    photo_id = update.message.photo[-1].file_id
    items = await get_cart(user_id)
    order_items = [{"product_id": i["product_id"], "size": i["size"],
                    "quantity": i["quantity"], "price": i["price"]} for i in items]

    order_id = await create_order(
        user_id,
        ctx.user_data["final_total"],
        ctx.user_data["discount"],
        ctx.user_data["address"],
        ctx.user_data["order_phone"],
        order_items
    )
    await update_order_status(order_id, "to'lov_tekshirilmoqda", photo_id)

    if ctx.user_data.get("tokens_use", 0) > 0:
        await use_tokens(user_id, ctx.user_data["tokens_use"])
    if ctx.user_data.get("promo_code"):
        await use_promo(ctx.user_data["promo_code"])

    await update_vip(user_id)
    await clear_cart(user_id)

    db_user = await get_user(user_id)
    await update.message.reply_text(
        f"✅ Buyurtma #{order_id} qabul qilindi!\n"
        f"💰 Summa: {ctx.user_data['final_total']:,} so'm\n"
        f"📍 Manzil: {ctx.user_data['address']}\n"
        f"⏳ To'lov tekshirilmoqda...",
        reply_markup=main_menu(db_user)
    )

    # Admin ga xabar
    for admin_id in ADMIN_IDS:
        try:
            await ctx.bot.send_photo(
                admin_id, photo_id,
                caption=f"🆕 Buyurtma #{order_id}\n👤 User: {user_id}\n💰 {ctx.user_data['final_total']:,} so'm"
            )
        except Exception:
            pass

    return ConversationHandler.END

# Profil
async def profile(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = await get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text("Avval ro'yxatdan o'ting: /start")
        return
    vip = VIP_LEVELS.get(user["vip_level"], {}).get("name", "Oddiy") if user["vip_level"] != "oddiy" else "Oddiy"
    text = (
        f"👤 *Profil*\n\n"
        f"Ism: {user['full_name']}\n"
        f"📱 Telefon: {user['phone'] or 'kiritilmagan'}\n"
        f"🪙 Tokenlar: {user['tokens']}\n"
        f"⭐ VIP: {vip}\n"
        f"📦 Buyurtmalar: {user['total_orders']}\n"
        f"🔗 Referal kod: `{user['referal_code']}`\n"
        f"🔗 Referal link: https://t.me/{BOT_USERNAME}?start={user['referal_code']}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# Buyurtmalar tarixi
async def my_orders(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    orders = await get_user_orders(update.effective_user.id)
    if not orders:
        await update.message.reply_text("📦 Buyurtmalaringiz yo'q.")
        return
    text = "📦 *So'nggi buyurtmalar:*\n\n"
    for o in orders:
        text += f"#{o['id']} — {o['total_price']:,} so'm — {o['status']} — {o['created_at'][:10]}\n"
    await update.message.reply_text(text, parse_mode="Markdown")

# Kunlik bonus
async def daily_bonus(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    result = await claim_daily_bonus(update.effective_user.id)
    if result:
        await update.message.reply_text(f"🎁 +{DAILY_BONUS} token oldiniz! Ertaga qaytib keling.")
    else:
        await update.message.reply_text("⏳ Bugun bonusni allaqachon oldingiz. Ertaga qaytib keling!")

# Referal
async def referal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = await get_user(update.effective_user.id)
    if not user:
        return
    link = f"https://t.me/{BOT_USERNAME}?start={user['referal_code']}"
    await update.message.reply_text(
        f"👥 *Referal tizimi*\n\n"
        f"Do'stingizni taklif qiling va {REFERAL_BONUS} token oling!\n\n"
        f"🔗 Sizning havolangiz:\n{link}",
        parse_mode="Markdown"
    )

# Promo kod
async def promo_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏷 Promo kodingizni kiriting:")
    return CHECKOUT_PROMO

# ============================================================
#   ADMIN PANEL
# ============================================================

async def admin_panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    await update.message.reply_text("⚙️ Admin panel", reply_markup=admin_menu())

async def admin_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    stats = await get_stats()
    await update.message.reply_text(
        f"📊 *Statistika*\n\n"
        f"👥 Foydalanuvchilar: {stats['users']}\n"
        f"📦 Buyurtmalar: {stats['orders']}\n"
        f"💰 Daromad: {stats['revenue']:,} so'm",
        parse_mode="Markdown"
    )

async def admin_add_product_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    cats = await get_categories()
    buttons = [[InlineKeyboardButton(f"{c['emoji']} {c['name']}", callback_data=f"acat_{c['id']}")]
               for c in cats]
    await update.message.reply_text("Kategoriyani tanlang:", reply_markup=InlineKeyboardMarkup(buttons))
    return ADMIN_PRODUCT_CAT

async def admin_product_cat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data["new_cat"] = int(query.data.split("_")[1])
    await query.edit_message_text("Mahsulot nomini kiriting:")
    return ADMIN_PRODUCT_NAME

async def admin_product_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["new_name"] = update.message.text
    await update.message.reply_text("Tavsif kiriting:")
    return ADMIN_PRODUCT_DESC

async def admin_product_desc(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["new_desc"] = update.message.text
    await update.message.reply_text("Narxi (so'mda):")
    return ADMIN_PRODUCT_PRICE

async def admin_product_price(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        ctx.user_data["new_price"] = int(update.message.text.replace(" ", "").replace(",", ""))
    except ValueError:
        await update.message.reply_text("❌ Noto'g'ri narx. Qaytadan:")
        return ADMIN_PRODUCT_PRICE
    await update.message.reply_text("Mahsulot rasmini yuboring (yoki /skip):")
    return ADMIN_PRODUCT_PHOTO

async def admin_product_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        ctx.user_data["new_photo"] = update.message.photo[-1].file_id
    else:
        ctx.user_data["new_photo"] = None
    await update.message.reply_text("Hajmlarni kiriting (vergul bilan, masalan: S,M,L,XL):")
    return ADMIN_PRODUCT_SIZES

async def admin_product_sizes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    sizes = update.message.text.strip()
    await add_product(
        ctx.user_data["new_cat"],
        ctx.user_data["new_name"],
        ctx.user_data["new_desc"],
        ctx.user_data["new_price"],
        ctx.user_data["new_photo"],
        sizes
    )
    await update.message.reply_text("✅ Mahsulot qo'shildi!", reply_markup=admin_menu())
    return ConversationHandler.END

async def admin_delete_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    products = await get_all_products()
    if not products:
        await update.message.reply_text("Mahsulotlar yo'q.")
        return ConversationHandler.END
    text = "O'chirmoqchi bo'lgan mahsulot ID sini kiriting:\n\n"
    for p in products:
        text += f"#{p['id']} — {p['name']} ({p['cat_name']}) — {p['price']:,} so'm\n"
    await update.message.reply_text(text)
    return ADMIN_DELETE_ID

async def admin_delete_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        pid = int(update.message.text.strip())
        await delete_product(pid)
        await update.message.reply_text(f"✅ #{pid} mahsulot o'chirildi.", reply_markup=admin_menu())
    except ValueError:
        await update.message.reply_text("❌ Noto'g'ri ID.")
    return ConversationHandler.END

async def admin_promo_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    await update.message.reply_text("Promo kod kiriting:")
    return ADMIN_PROMO_CODE

async def admin_promo_code(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["promo_new_code"] = update.message.text.strip().upper()
    await update.message.reply_text("Chegirma foizi (masalan: 10):")
    return ADMIN_PROMO_DISCOUNT

async def admin_promo_discount(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        ctx.user_data["promo_new_disc"] = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Raqam kiriting:")
        return ADMIN_PROMO_DISCOUNT
    await update.message.reply_text("Maksimal foydalanish soni:")
    return ADMIN_PROMO_USES

async def admin_promo_uses(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        uses = int(update.message.text.strip())
    except ValueError:
        uses = 100
    await add_promo(ctx.user_data["promo_new_code"], ctx.user_data["promo_new_disc"], uses)
    await update.message.reply_text(
        f"✅ Promo kod yaratildi!\n"
        f"Kod: {ctx.user_data['promo_new_code']}\n"
        f"Chegirma: {ctx.user_data['promo_new_disc']}%\n"
        f"Foydalanish: {uses}",
        reply_markup=admin_menu()
    )
    return ConversationHandler.END

async def back_to_main(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = await get_user(update.effective_user.id)
    await update.message.reply_text("🏠 Bosh menyu", reply_markup=main_menu(user))

# ============================================================
#   MAIN
# ============================================================

def main():
    app = Application.builder().token(TOKEN).build()

    # Ro'yxatdan o'tish
    reg_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            REGISTER_NAME:  [MessageHandler(filters.TEXT & ~filters.COMMAND, register_name)],
            REGISTER_PHONE: [MessageHandler(filters.CONTACT | filters.TEXT, register_phone)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    # Checkout
    checkout_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(cart_callback, pattern="^checkout$")],
        states={
            CHECKOUT_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, checkout_address)],
            CHECKOUT_PHONE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, checkout_phone)],
            CHECKOUT_PROMO:   [MessageHandler(filters.TEXT & ~filters.COMMAND, checkout_promo)],
            CHECKOUT_TOKENS:  [MessageHandler(filters.TEXT & ~filters.COMMAND, checkout_tokens)],
            CHECKOUT_PAYMENT: [MessageHandler(filters.PHOTO, checkout_payment)],
        },
        fallbacks=[],
    )

    # Qidiruv
    search_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🔍 Qidiruv$"), search_start)],
        states={
            SEARCH_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_query)],
        },
        fallbacks=[],
    )

    # Admin — mahsulot qo'shish
    add_product_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕ Mahsulot qo'shish$"), admin_add_product_start)],
        states={
            ADMIN_PRODUCT_CAT:   [CallbackQueryHandler(admin_product_cat, pattern="^acat_")],
            ADMIN_PRODUCT_NAME:  [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_product_name)],
            ADMIN_PRODUCT_DESC:  [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_product_desc)],
            ADMIN_PRODUCT_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_product_price)],
            ADMIN_PRODUCT_PHOTO: [MessageHandler(filters.PHOTO | filters.TEXT, admin_product_photo)],
            ADMIN_PRODUCT_SIZES: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_product_sizes)],
        },
        fallbacks=[],
    )

    # Admin — mahsulot o'chirish
    del_product_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🗑 Mahsulot o'chirish$"), admin_delete_start)],
        states={
            ADMIN_DELETE_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_delete_id)],
        },
        fallbacks=[],
    )

    # Admin — promo kod
    promo_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🎟 Promo kod yaratish$"), admin_promo_start)],
        states={
            ADMIN_PROMO_CODE:     [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_promo_code)],
            ADMIN_PROMO_DISCOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_promo_discount)],
            ADMIN_PROMO_USES:     [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_promo_uses)],
        },
        fallbacks=[],
    )

    app.add_handler(reg_conv)
    app.add_handler(checkout_conv)
    app.add_handler(search_conv)
    app.add_handler(add_product_conv)
    app.add_handler(del_product_conv)
    app.add_handler(promo_conv)

    app.add_handler(CallbackQueryHandler(cat_callback,    pattern="^cat_"))
    app.add_handler(CallbackQueryHandler(addcart_callback, pattern="^addcart_"))
    app.add_handler(CallbackQueryHandler(size_callback,   pattern="^size_"))
    app.add_handler(CallbackQueryHandler(cart_callback,   pattern="^(clearcart|rmcart_)"))

    app.add_handler(MessageHandler(filters.Regex("^🛍 Katalog$"),       catalog))
    app.add_handler(MessageHandler(filters.Regex("^🛒 Savatcha$"),       show_cart))
    app.add_handler(MessageHandler(filters.Regex("^📦 Buyurtmalarim$"),  my_orders))
    app.add_handler(MessageHandler(filters.Regex("^👤 Profil$"),         profile))
    app.add_handler(MessageHandler(filters.Regex("^🎁 Kunlik bonus$"),   daily_bonus))
    app.add_handler(MessageHandler(filters.Regex("^👥 Referal$"),        referal))
    app.add_handler(MessageHandler(filters.Regex("^🏷 Promo kod$"),      promo_handler))
    app.add_handler(MessageHandler(filters.Regex("^⚙️ Admin panel$"),    admin_panel))
    app.add_handler(MessageHandler(filters.Regex("^📊 Statistika$"),     admin_stats))
    app.add_handler(MessageHandler(filters.Regex("^🔙 Orqaga$"),         back_to_main))

    print("✅ SW Store Bot ishga tushdi!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if name == "__main__":
    import asyncio
    asyncio.run(init_db())
    asyncio.run(main()) if False else main()
