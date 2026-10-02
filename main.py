import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

import flet as ft
import httpx
import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field


INK = "#17231F"
MUTED = "#68736D"
PAPER = "#F7F8F3"
WHITE = "#FFFFFF"
GREEN = "#174B3A"
LIME = "#DDF36A"
ORANGE = "#F47B4B"
LINE = "#E6E9E1"

PRODUCTS = [
    {"id": "phone-01", "name": "Galaxy A35 5G · 128GB", "category": "Phones", "price": 429900, "was": 489900, "rating": "4.8", "reviews": 124, "tag": "TOP PICK", "seller": "Mobile Hub NG", "image": "https://images.unsplash.com/photo-1592750475338-74b7b21085ab?auto=format&fit=crop&w=700&q=85"},
    {"id": "headphones-01", "name": "Studio Wireless Headphones", "category": "Electronics", "price": 38500, "was": 52000, "rating": "4.7", "reviews": 86, "tag": "DEAL", "seller": "Sound House", "image": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?auto=format&fit=crop&w=700&q=85"},
    {"id": "sneakers-01", "name": "Everyday Runner Sneakers", "category": "Fashion", "price": 27900, "was": 35000, "rating": "4.6", "reviews": 53, "tag": "SELLER FAVE", "seller": "The Good Sole", "image": "https://images.unsplash.com/photo-1542291026-7eec264c27ff?auto=format&fit=crop&w=700&q=85"},
    {"id": "watch-01", "name": "Minimal Classic Wristwatch", "category": "Fashion", "price": 31500, "was": 42000, "rating": "4.9", "reviews": 41, "tag": "NEW", "seller": "Time & Tide NG", "image": "https://images.unsplash.com/photo-1523275335684-37898b6baf30?auto=format&fit=crop&w=700&q=85"},
    {"id": "chair-01", "name": "Oak & Linen Accent Chair", "category": "Home", "price": 118000, "was": 145000, "rating": "4.8", "reviews": 29, "tag": "LOCAL MAKER", "seller": "Form & Foundry", "image": "https://images.unsplash.com/photo-1503602642458-232111445657?auto=format&fit=crop&w=700&q=85"},
    {"id": "skincare-01", "name": "Daily Glow Skincare Set", "category": "Beauty", "price": 18750, "was": 24000, "rating": "4.7", "reviews": 68, "tag": "GREAT VALUE", "seller": "Nourish Beauty", "image": "https://images.unsplash.com/photo-1608248543803-ba4f8c70ae0b?auto=format&fit=crop&w=700&q=85"},
    {"id": "bag-01", "name": "Everywhere Everyday Tote", "category": "Fashion", "price": 22400, "was": 29000, "rating": "4.8", "reviews": 37, "tag": "MADE IN NIGERIA", "seller": "Aso & Co.", "image": "https://images.unsplash.com/photo-1548036328-c9fa89d128fa?auto=format&fit=crop&w=700&q=85"},
    {"id": "speaker-01", "name": "Portable Bluetooth Speaker", "category": "Electronics", "price": 46500, "was": 59000, "rating": "4.5", "reviews": 92, "tag": "DEAL", "seller": "Sound House", "image": "https://images.unsplash.com/photo-1608043152269-423dbba4e7e1?auto=format&fit=crop&w=700&q=85"},
]
CATEGORIES = ["All finds", "Phones", "Electronics", "Fashion", "Home", "Beauty"]
DB_PATH = os.environ.get("KWAJIBUY_DB_PATH", "data/kwajibu.sqlite3")
ORDER_STATUSES = ("new", "confirmed", "dispatched", "delivered", "cancelled")


def naira(amount):
    return "₦{:,.0f}".format(amount)


def dashboard_metric(label, value, icon, detail, accent=GREEN):
    return ft.Container(
        col={"xs": 12, "sm": 6, "lg": 3},
        height=112,
        content=ft.Row(
            [
                ft.Container(
                    content=ft.Icon(icon, color=accent, size=21),
                    width=42,
                    height=42,
                    bgcolor="#EEF5F0",
                    border_radius=10,
                    alignment=ft.alignment.center,
                ),
                ft.Column(
                    [
                        ft.Text(label.upper(), color=MUTED, size=10, weight=ft.FontWeight.BOLD),
                        ft.Text(value, color=INK, size=20, weight=ft.FontWeight.BOLD),
                        ft.Text(detail, color=MUTED, size=10, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    ],
                    spacing=3,
                    expand=True,
                ),
            ],
            spacing=11,
        ),
        bgcolor=WHITE,
        border=ft.border.all(1, LINE),
        border_radius=9,
        padding=14,
    )


def initialize_database():
    database_directory = os.path.dirname(DB_PATH)
    if database_directory:
        os.makedirs(database_directory, exist_ok=True)
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                customer_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                delivery_address TEXT NOT NULL,
                total_ngn INTEGER NOT NULL,
                payment_method TEXT NOT NULL,
                customer_email TEXT NOT NULL DEFAULT '',
                order_status TEXT NOT NULL DEFAULT 'new',
                payment_status TEXT NOT NULL DEFAULT 'pending',
                paystack_reference TEXT UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        existing_columns = {row[1] for row in connection.execute("PRAGMA table_info(orders)")}
        migrations = {
            "customer_email": "TEXT NOT NULL DEFAULT ''",
            "order_status": "TEXT NOT NULL DEFAULT 'new'",
            "payment_status": "TEXT NOT NULL DEFAULT 'pending'",
            "paystack_reference": "TEXT",
        }
        for column, definition in migrations.items():
            if column not in existing_columns:
                connection.execute("ALTER TABLE orders ADD COLUMN {} {}".format(column, definition))
        connection.execute(
            "UPDATE orders SET payment_status = 'not_required' WHERE payment_method = 'pay_on_delivery' AND payment_status = 'pending'"
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL REFERENCES orders(order_id),
                product_id TEXT NOT NULL,
                product_name TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                unit_price_ngn INTEGER NOT NULL
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS payment_events (
                event_key TEXT PRIMARY KEY,
                paystack_reference TEXT NOT NULL,
                received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS customer_profiles (
                email TEXT PRIMARY KEY,
                full_name TEXT NOT NULL,
                phone TEXT NOT NULL DEFAULT '',
                delivery_address TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                full_name TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('shopper', 'seller', 'admin')),
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS user_sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS seller_profiles (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                store_name TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS products (
                product_id TEXT PRIMARY KEY,
                seller_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                seller_name TEXT NOT NULL,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                price_ngn INTEGER NOT NULL CHECK (price_ngn > 0),
                compare_at_ngn INTEGER NOT NULL CHECK (compare_at_ngn >= price_ngn),
                image_url TEXT NOT NULL DEFAULT '',
                rating TEXT NOT NULL DEFAULT 'New',
                review_count INTEGER NOT NULL DEFAULT 0,
                tag TEXT NOT NULL DEFAULT 'NEW FIND',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        connection.executemany(
            """INSERT OR IGNORE INTO products
               (product_id, seller_name, name, category, price_ngn, compare_at_ngn, image_url, rating, review_count, tag)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (product["id"], product["seller"], product["name"], product["category"], product["price"], product["was"], product["image"], product["rating"], product["reviews"], product["tag"])
                for product in PRODUCTS
            ],
        )


def list_products(seller_id=None, include_inactive=False):
    query = """SELECT products.product_id AS id, products.name, products.category,
                      products.price_ngn AS price, products.compare_at_ngn AS was,
                      products.rating, products.review_count AS reviews, products.tag,
                      COALESCE(seller_profiles.store_name, products.seller_name) AS seller,
                      products.image_url AS image, products.seller_id, products.active,
                      products.created_at
               FROM products LEFT JOIN seller_profiles ON seller_profiles.user_id = products.seller_id"""
    conditions = []
    parameters = []
    if seller_id is not None:
        conditions.append("products.seller_id = ?")
        parameters.append(seller_id)
    if not include_inactive:
        conditions.append("products.active = 1")
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY products.created_at DESC, products.product_id"
    with sqlite3.connect(DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(query, parameters).fetchall()]


def get_product(product_id, active_only=True):
    products = list_products(include_inactive=not active_only)
    return next((product for product in products if product["id"] == product_id), None)


def create_seller_product(seller_id, name, category, price, compare_at, image_url="", tag="NEW FIND"):
    seller = safe_user(seller_id)
    if not seller or seller["role"] != "seller" or seller.get("seller_status") != "approved":
        raise ValueError("An approved seller account is required to list products.")
    name = (name or "").strip()
    category = (category or "").strip()
    tag = (tag or "NEW FIND").strip()[:32]
    if len(name) < 3 or category not in CATEGORIES[1:]:
        raise ValueError("Enter a product name and choose a supported category.")
    try:
        price = int(price)
        compare_at = int(compare_at)
    except (TypeError, ValueError) as error:
        raise ValueError("Enter valid whole-number prices in Naira.") from error
    if price <= 0 or compare_at < price:
        raise ValueError("Price must be positive and compare-at price cannot be lower.")
    product_id = "seller-" + uuid.uuid4().hex[:12]
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            "INSERT INTO products (product_id, seller_id, seller_name, name, category, price_ngn, compare_at_ngn, image_url, tag) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (product_id, seller_id, seller["store_name"], name, category, price, compare_at, (image_url or "").strip(), tag),
        )
    return get_product(product_id)


def update_seller_product(seller_id, product_id, name, category, price, compare_at, image_url="", tag="NEW FIND"):
    owned_product = next((product for product in list_products(seller_id=seller_id, include_inactive=True) if product["id"] == product_id), None)
    if not owned_product:
        raise ValueError("Product not found in your store.")
    name = (name or "").strip()
    if len(name) < 3 or category not in CATEGORIES[1:]:
        raise ValueError("Enter a product name and choose a supported category.")
    try:
        price = int(price)
        compare_at = int(compare_at)
    except (TypeError, ValueError) as error:
        raise ValueError("Enter valid whole-number prices in Naira.") from error
    if price <= 0 or compare_at < price:
        raise ValueError("Price must be positive and compare-at price cannot be lower.")
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            "UPDATE products SET name = ?, category = ?, price_ngn = ?, compare_at_ngn = ?, image_url = ?, tag = ? WHERE product_id = ? AND seller_id = ?",
            (name, category, price, compare_at, (image_url or "").strip(), (tag or "NEW FIND").strip()[:32], product_id, seller_id),
        )
    return get_product(product_id)


def deactivate_seller_product(seller_id, product_id):
    set_seller_product_active(seller_id, product_id, False)


def set_seller_product_active(seller_id, product_id, active):
    with sqlite3.connect(DB_PATH) as connection:
        cursor = connection.execute(
            "UPDATE products SET active = ? WHERE product_id = ? AND seller_id = ?",
            (1 if active else 0, product_id, seller_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("Product not found in your store.")


def record_order(customer_name, phone, delivery_address, cart, payment_method="pay_on_delivery", email=""):
    products_by_id = {product["id"]: product for product in list_products()}
    if not cart or any(item_id not in products_by_id or not isinstance(quantity, int) or quantity < 1 for item_id, quantity in cart.items()):
        raise ValueError("The cart contains no valid items.")
    order_id = "KW-" + uuid.uuid4().hex[:8].upper()
    total = sum(products_by_id[item_id]["price"] * quantity for item_id, quantity in cart.items())
    initial_payment_status = "not_required" if payment_method == "pay_on_delivery" else "pending"
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            "INSERT INTO orders (order_id, customer_name, phone, delivery_address, total_ngn, payment_method, customer_email, payment_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (order_id, customer_name.strip(), phone.strip(), delivery_address.strip(), total, payment_method, email.strip(), initial_payment_status),
        )
        connection.executemany(
            "INSERT INTO order_items (order_id, product_id, product_name, quantity, unit_price_ngn) VALUES (?, ?, ?, ?, ?)",
            [
                (order_id, item_id, products_by_id[item_id]["name"], quantity, products_by_id[item_id]["price"])
                for item_id, quantity in cart.items()
            ],
        )
        if email.strip():
            connection.execute(
                """INSERT INTO customer_profiles (email, full_name, phone, delivery_address)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(email) DO UPDATE SET full_name = excluded.full_name,
                       phone = excluded.phone, delivery_address = excluded.delivery_address,
                       updated_at = CURRENT_TIMESTAMP""",
                (email.strip().lower(), customer_name.strip(), phone.strip(), delivery_address.strip()),
            )
    return order_id, total


def get_customer_profile(email):
    normalized_email = (email or "").strip().lower()
    if not normalized_email:
        return None
    with sqlite3.connect(DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT email, full_name, phone, delivery_address, created_at, updated_at FROM customer_profiles WHERE email = ?",
            (normalized_email,),
        ).fetchone()
        return dict(row) if row else None


def save_customer_profile(email, full_name, phone, delivery_address):
    normalized_email = (email or "").strip().lower()
    if "@" not in normalized_email or not full_name.strip() or not phone.strip() or not delivery_address.strip():
        raise ValueError("Enter a valid email, name, phone number, and delivery address.")
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            """INSERT INTO customer_profiles (email, full_name, phone, delivery_address)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(email) DO UPDATE SET full_name = excluded.full_name,
                   phone = excluded.phone, delivery_address = excluded.delivery_address,
                   updated_at = CURRENT_TIMESTAMP""",
            (normalized_email, full_name.strip(), phone.strip(), delivery_address.strip()),
        )
    return get_customer_profile(normalized_email)


PASSWORD_ITERATIONS = 310000
SELLER_STATUSES = ("pending", "approved", "rejected")


def hash_password(password, salt=None):
    salt_bytes = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, PASSWORD_ITERATIONS)
    return salt_bytes.hex(), digest.hex()


def safe_user(user_id):
    with sqlite3.connect(DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        user = connection.execute(
            "SELECT id, email, full_name, role, active, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if not user:
            return None
        result = dict(user)
        if result["role"] == "seller":
            seller = connection.execute(
                "SELECT store_name, status FROM seller_profiles WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            result["store_name"] = seller["store_name"] if seller else ""
            result["seller_status"] = seller["status"] if seller else "pending"
        return result


def get_user_by_email(email):
    normalized_email = (email or "").strip().lower()
    with sqlite3.connect(DB_PATH) as connection:
        row = connection.execute("SELECT id FROM users WHERE email = ?", (normalized_email,)).fetchone()
    return safe_user(row[0]) if row else None


def register_user(email, password, full_name, role="shopper", phone="", address="", store_name=""):
    normalized_email = (email or "").strip().lower()
    if role not in ("shopper", "seller"):
        raise ValueError("Choose a shopper account or submit a seller application.")
    if "@" not in normalized_email or len(password or "") < 12 or not (full_name or "").strip():
        raise ValueError("Enter a valid email, your name, and a password of at least 12 characters.")
    if role == "seller" and not (store_name or "").strip():
        raise ValueError("A store name is required for a seller application.")
    salt, password_digest = hash_password(password)
    try:
        with sqlite3.connect(DB_PATH) as connection:
            cursor = connection.execute(
                "INSERT INTO users (email, full_name, password_salt, password_hash, role) VALUES (?, ?, ?, ?, ?)",
                (normalized_email, full_name.strip(), salt, password_digest, role),
            )
            user_id = cursor.lastrowid
            if role == "seller":
                connection.execute(
                    "INSERT INTO seller_profiles (user_id, store_name, status) VALUES (?, ?, 'pending')",
                    (user_id, store_name.strip()),
                )
            else:
                connection.execute(
                    "INSERT INTO customer_profiles (email, full_name, phone, delivery_address) VALUES (?, ?, ?, ?) ON CONFLICT(email) DO UPDATE SET full_name = excluded.full_name, phone = excluded.phone, delivery_address = excluded.delivery_address, updated_at = CURRENT_TIMESTAMP",
                    (normalized_email, full_name.strip(), phone.strip(), address.strip()),
                )
    except sqlite3.IntegrityError as error:
        raise ValueError("That email or store name is already registered.") from error
    return safe_user(user_id)


def authenticate_user(email, password):
    normalized_email = (email or "").strip().lower()
    with sqlite3.connect(DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        user = connection.execute(
            "SELECT id, password_salt, password_hash, active FROM users WHERE email = ?",
            (normalized_email,),
        ).fetchone()
    if not user or not user["active"]:
        return None
    _, candidate = hash_password(password or "", bytes.fromhex(user["password_salt"]))
    if not hmac.compare_digest(candidate, user["password_hash"]):
        return None
    return safe_user(user["id"])


def create_login_session(user_id):
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    expires_at = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            "INSERT INTO user_sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (token_hash, user_id, expires_at),
        )
    return token


def get_user_for_session(token):
    if not token:
        return None
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with sqlite3.connect(DB_PATH) as connection:
        row = connection.execute(
            "SELECT user_id FROM user_sessions WHERE token_hash = ? AND expires_at > ?",
            (token_hash, datetime.now(timezone.utc).isoformat()),
        ).fetchone()
    return safe_user(row[0]) if row else None


def revoke_login_session(token):
    if not token:
        return
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute("DELETE FROM user_sessions WHERE token_hash = ?", (token_hash,))


def set_seller_status(user_id, status):
    if status not in SELLER_STATUSES:
        raise ValueError("Unsupported seller status.")
    with sqlite3.connect(DB_PATH) as connection:
        cursor = connection.execute("UPDATE seller_profiles SET status = ? WHERE user_id = ?", (status, user_id))
        if cursor.rowcount != 1:
            raise ValueError("Seller application not found.")


def list_sellers():
    with sqlite3.connect(DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        return [
            dict(row)
            for row in connection.execute(
                "SELECT users.id, users.email, users.full_name, seller_profiles.store_name, seller_profiles.status, seller_profiles.created_at FROM seller_profiles JOIN users ON users.id = seller_profiles.user_id ORDER BY seller_profiles.created_at DESC"
            ).fetchall()
        ]


def bootstrap_admin():
    email = os.environ.get("KWAJIBUY_ADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("KWAJIBUY_ADMIN_PASSWORD", "")
    if not email or not password:
        return
    if len(password) < 12:
        raise RuntimeError("KWAJIBUY_ADMIN_PASSWORD must be at least 12 characters.")
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute("BEGIN IMMEDIATE")
        exists = connection.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone()
        if not exists:
            salt, password_digest = hash_password(password)
            connection.execute(
                "INSERT INTO users (email, full_name, password_salt, password_hash, role) VALUES (?, ?, ?, ?, 'admin')",
                (email, "KwajiBuy Administrator", salt, password_digest),
            )


def bootstrap_demo_accounts():
    if os.environ.get("KWAJIBUY_ENABLE_DEMO_ACCOUNTS") != "1":
        return
    demo_accounts = [
        ("demo.shopper@kwajibuy.local", "Demo Shopper", "shopper", ""),
        ("demo.seller@kwajibuy.local", "Demo Seller", "seller", "Kwaji Finds"),
        ("demo.admin@kwajibuy.local", "Demo Administrator", "admin", ""),
    ]
    for email, full_name, role, store_name in demo_accounts:
        with sqlite3.connect(DB_PATH) as connection:
            connection.execute("BEGIN IMMEDIATE")
            exists = connection.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone()
            if exists:
                continue
            salt, password_digest = hash_password(secrets.token_urlsafe(32))
            cursor = connection.execute(
                "INSERT INTO users (email, full_name, password_salt, password_hash, role) VALUES (?, ?, ?, ?, ?)",
                (email, full_name, salt, password_digest, role),
            )
            if role == "seller":
                connection.execute(
                    "INSERT INTO seller_profiles (user_id, store_name, status) VALUES (?, ?, 'approved')",
                    (cursor.lastrowid, store_name),
                )


def authenticate_demo_user(email):
    if os.environ.get("KWAJIBUY_ENABLE_DEMO_ACCOUNTS") != "1":
        return None
    allowed = {
        "demo.shopper@kwajibuy.local",
        "demo.seller@kwajibuy.local",
        "demo.admin@kwajibuy.local",
    }
    normalized_email = (email or "").strip().lower()
    return get_user_by_email(normalized_email) if normalized_email in allowed else None


def list_orders(limit=50, customer_email=None):
    with sqlite3.connect(DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        query = "SELECT order_id, customer_name, phone, delivery_address, customer_email, total_ngn, payment_method, payment_status, order_status, created_at FROM orders"
        parameters = []
        if customer_email is not None:
            query += " WHERE lower(customer_email) = ?"
            parameters.append(customer_email.strip().lower())
        query += " ORDER BY created_at DESC LIMIT ?"
        parameters.append(limit)
        rows = connection.execute(query, parameters).fetchall()
        result = []
        for row in rows:
            order = dict(row)
            order["items"] = [
                dict(item)
                for item in connection.execute(
                    "SELECT product_name, quantity, unit_price_ngn FROM order_items WHERE order_id = ? ORDER BY id",
                    (order["order_id"],),
                ).fetchall()
            ]
            result.append(order)
        return result


def set_order_status(order_id, status):
    if status not in ORDER_STATUSES:
        raise ValueError("Unsupported order status.")
    with sqlite3.connect(DB_PATH) as connection:
        cursor = connection.execute("UPDATE orders SET order_status = ? WHERE order_id = ?", (status, order_id))
        if cursor.rowcount != 1:
            raise ValueError("Order not found.")


def initialize_paystack_payment(order_id, email, total_ngn):
    secret_key = os.environ.get("KWAJIBUY_PAYSTACK_SECRET_KEY", "")
    if not secret_key:
        raise RuntimeError("Online payment is not configured. Use pay on delivery or configure the Paystack secret key.")
    callback_url = os.environ.get("KWAJIBUY_PAYSTACK_CALLBACK_URL", "http://localhost:8550/api/payments/paystack/callback")
    response = httpx.post(
        "https://api.paystack.co/transaction/initialize",
        headers={"Authorization": "Bearer " + secret_key},
        json={"email": email, "amount": total_ngn * 100, "currency": "NGN", "reference": order_id, "callback_url": callback_url},
        timeout=15.0,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("status") or not payload.get("data", {}).get("authorization_url"):
        raise RuntimeError(payload.get("message", "Paystack could not initialize this payment."))
    reference = payload["data"].get("reference")
    if not reference:
        raise RuntimeError("Paystack did not return a transaction reference.")
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute("UPDATE orders SET paystack_reference = ? WHERE order_id = ?", (reference, order_id))
    return payload["data"]["authorization_url"]


def valid_paystack_signature(raw_body, signature):
    secret_key = os.environ.get("KWAJIBUY_PAYSTACK_SECRET_KEY", "")
    if not secret_key or not signature:
        return False
    digest = hmac.new(secret_key.encode("utf-8"), raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(digest, signature)


def apply_paystack_success(event):
    data = event.get("data", {})
    reference = data.get("reference")
    if event.get("event") != "charge.success" or not reference:
        return "ignored"
    event_key = "{}:{}".format(event["event"], reference)
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("BEGIN IMMEDIATE")
        order = connection.execute(
            "SELECT order_id, total_ngn, payment_status, payment_method FROM orders WHERE paystack_reference = ? OR order_id = ?",
            (reference, reference),
        ).fetchone()
        if order is None:
            raise ValueError("No order matches this Paystack reference.")
        if order[3] != "paystack":
            raise ValueError("This order is not configured for online payment.")
        if data.get("status") != "success":
            raise ValueError("Paystack has not confirmed this transaction.")
        if data.get("currency") != "NGN" or data.get("amount") != order[1] * 100:
            raise ValueError("The payment amount or currency does not match the order.")
        inserted = connection.execute(
            "INSERT OR IGNORE INTO payment_events (event_key, paystack_reference) VALUES (?, ?)",
            (event_key, reference),
        ).rowcount
        if inserted:
            connection.execute("UPDATE orders SET payment_status = 'paid' WHERE order_id = ?", (order[0],))
    return "processed" if inserted else "already_processed"


admin_api = FastAPI(title="KwajiBuy admin and payment callbacks")


def require_admin_token(token):
    user = get_user_for_session(token)
    if user and user["role"] == "admin" and user["active"]:
        return
    expected = os.environ.get("KWAJIBUY_ADMIN_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="Admin access is not configured.")
    if not token or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="Invalid admin token.")


class RegistrationPayload(BaseModel):
    email: str
    password: str = Field(min_length=12)
    full_name: str
    role: str = "shopper"
    phone: str = ""
    address: str = ""
    store_name: str = ""


class LoginPayload(BaseModel):
    email: str
    password: str


def bearer_user(authorization):
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return get_user_for_session(authorization[7:].strip())


@admin_api.post("/api/auth/register")
def api_register(payload: RegistrationPayload):
    try:
        user = register_user(
            payload.email,
            payload.password,
            payload.full_name,
            role=payload.role,
            phone=payload.phone,
            address=payload.address,
            store_name=payload.store_name,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    return {"user": user, "message": "Seller access is pending admin approval." if payload.role == "seller" else "Account created."}


@admin_api.post("/api/auth/login")
def api_login(payload: LoginPayload):
    user = authenticate_user(payload.email, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    return {"user": user, "access_token": create_login_session(user["id"]), "token_type": "bearer"}


@admin_api.get("/api/auth/me")
def api_current_user(authorization: str = Header(default="")):
    user = bearer_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Sign-in required.")
    return user


@admin_api.post("/api/auth/logout")
def api_logout(authorization: str = Header(default="")):
    if not bearer_user(authorization):
        raise HTTPException(status_code=401, detail="Sign-in required.")
    revoke_login_session(authorization[7:].strip())
    return {"message": "Signed out."}


@admin_api.get("/api/admin/orders")
def admin_orders(x_admin_token: str = Header(default="")):
    require_admin_token(x_admin_token)
    return list_orders()


@admin_api.patch("/api/admin/orders/{order_id}")
def admin_update_order(order_id: str, status: str, x_admin_token: str = Header(default="")):
    require_admin_token(x_admin_token)
    try:
        set_order_status(order_id, status)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    return {"order_id": order_id, "order_status": status}


@admin_api.get("/api/admin/sellers")
def admin_sellers(x_admin_token: str = Header(default="")):
    require_admin_token(x_admin_token)
    return list_sellers()


@admin_api.patch("/api/admin/sellers/{user_id}")
def admin_update_seller(user_id: int, status: str, x_admin_token: str = Header(default="")):
    require_admin_token(x_admin_token)
    try:
        set_seller_status(user_id, status)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    return {"user_id": user_id, "seller_status": status}


@admin_api.post("/api/payments/paystack/webhook")
async def paystack_webhook(request: Request, x_paystack_signature: str = Header(default="")):
    raw_body = await request.body()
    if not valid_paystack_signature(raw_body, x_paystack_signature):
        raise HTTPException(status_code=401, detail="Invalid Paystack signature.")
    try:
        event = json.loads(raw_body.decode("utf-8"))
        result = apply_paystack_success(event)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error))
    return {"status": result}


@admin_api.get("/api/payments/paystack/callback")
async def paystack_callback(reference: str):
    secret_key = os.environ.get("KWAJIBUY_PAYSTACK_SECRET_KEY", "")
    if not secret_key:
        raise HTTPException(status_code=503, detail="Online payment is not configured.")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                "https://api.paystack.co/transaction/verify/{}".format(reference),
                headers={"Authorization": "Bearer " + secret_key},
            )
            response.raise_for_status()
            payload = response.json()
        transaction = payload.get("data", {})
        if not payload.get("status") or transaction.get("status") != "success":
            raise HTTPException(status_code=400, detail="Paystack has not confirmed this payment.")
        result = apply_paystack_success(
            {"event": "charge.success", "data": transaction}
        )
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Could not verify payment with Paystack.") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    return RedirectResponse(url="/?payment={}".format(result), status_code=303)


def main(page: ft.Page):
    initialize_database()
    bootstrap_admin()
    bootstrap_demo_accounts()
    page.title = "KwajiBuy | Good finds, close to home"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme = ft.Theme(font_family="Trebuchet MS", color_scheme=ft.ColorScheme(primary=GREEN))
    page.bgcolor = PAPER
    page.padding = 0
    page.scroll = ft.ScrollMode.AUTO

    cart = {}
    active_profile_email = ""
    active_category = "All finds"
    search_query = ""
    category_buttons = []
    product_grid = ft.ResponsiveRow(run_spacing=16, spacing=16)
    result_label = ft.Text(color=MUTED, size=13)
    cart_count = ft.Text("0", color=INK, size=12, weight=ft.FontWeight.BOLD)

    def current_user():
        return get_user_for_session(page.session.get("auth_token"))

    def establish_user_session(user):
        page.session.set("auth_token", create_login_session(user["id"]))
        return "/admin" if user["role"] == "admin" else "/seller" if user["role"] == "seller" else "/account"

    def sign_out():
        nonlocal active_profile_email
        auth_token = page.session.get("auth_token")
        if auth_token:
            revoke_login_session(auth_token)
        try:
            if page.session.contains_key("auth_token"):
                page.session.remove("auth_token")
        except KeyError:
            pass
        active_profile_email = ""
        page.go("/account")

    def authorize_admin_view(token):
        user = current_user()
        if user and user["role"] == "admin" and user["active"]:
            return
        raise HTTPException(status_code=401, detail="Sign in with an admin account to continue.")

    def close_dialog():
        if page.dialog:
            page.dialog.open = False
            page.update()

    def show_message(message):
        page.snack_bar = ft.SnackBar(content=ft.Text(message), bgcolor=GREEN)
        page.snack_bar.open = True
        page.update()

    def open_policy(title, body):
        page.dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(title, color=INK, weight=ft.FontWeight.BOLD),
            content=ft.Container(content=ft.Text(body, color=MUTED, size=14), width=460),
            actions=[ft.TextButton("Close", on_click=lambda e: close_dialog())],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.dialog.open = True
        page.update()

    def update_cart_count():
        cart_count.value = str(sum(cart.values()))
        page.update()

    def add_to_cart(product):
        cart[product["id"]] = cart.get(product["id"], 0) + 1
        update_cart_count()
        show_message(product["name"] + " added to your bag")

    def cart_total():
        return sum(
            (get_product(product_id) or {}).get("price", 0) * quantity
            for product_id, quantity in cart.items()
        )

    def remove_from_cart(product_id):
        cart.pop(product_id, None)
        update_cart_count()
        if page.route == "/cart":
            refresh_cart_view()
        else:
            page.go("/cart")

    def change_quantity(product_id, delta):
        new_quantity = cart.get(product_id, 0) + delta
        if new_quantity < 1:
            cart.pop(product_id, None)
        else:
            cart[product_id] = new_quantity
        update_cart_count()
        refresh_cart_view()

    def open_checkout():
        if not cart:
            close_dialog()
            show_message("Your bag is empty. Find something you love first.")
            return
        saved_profile = get_customer_profile(active_profile_email)
        name_field = ft.TextField(label="Full name", value=saved_profile["full_name"] if saved_profile else "", border_radius=8)
        phone_field = ft.TextField(label="Phone number", value=saved_profile["phone"] if saved_profile else "", keyboard_type=ft.KeyboardType.PHONE, border_radius=8)
        email_field = ft.TextField(label="Email for receipt", value=saved_profile["email"] if saved_profile else "", keyboard_type=ft.KeyboardType.EMAIL, border_radius=8)
        address_field = ft.TextField(label="Delivery address", value=saved_profile["delivery_address"] if saved_profile else "", multiline=True, min_lines=2, border_radius=8)
        payment_choice = ft.RadioGroup(
            content=ft.Column(
                [
                    ft.Radio(value="delivery", label="Pay on delivery"),
                    ft.Radio(value="paystack", label="Pay online by card or transfer (Paystack)", disabled=not os.environ.get("KWAJIBUY_PAYSTACK_SECRET_KEY")),
                ],
                spacing=4,
            ),
            value="delivery",
        )

        def place_order(e):
            if not name_field.value or not phone_field.value or not address_field.value:
                show_message("Please complete all delivery details.")
                return
            use_paystack = payment_choice.value == "paystack"
            if use_paystack and not (email_field.value or "").strip():
                show_message("Enter an email address for your payment receipt.")
                return
            payment_method = "paystack" if use_paystack else "pay_on_delivery"
            try:
                order_id, ordered_total = record_order(
                    name_field.value,
                    phone_field.value,
                    address_field.value,
                    cart,
                    payment_method,
                    email_field.value or "",
                )
            except (ValueError, sqlite3.Error) as error:
                show_message("Could not create your order: {}".format(error))
                return
            if use_paystack:
                try:
                    checkout_url = initialize_paystack_payment(order_id, email_field.value.strip(), ordered_total)
                except (RuntimeError, httpx.HTTPError) as error:
                    with sqlite3.connect(DB_PATH) as connection:
                        connection.execute("UPDATE orders SET payment_status = 'initialization_failed' WHERE order_id = ?", (order_id,))
                    show_message("Online payment could not start. Your bag is unchanged; try again or pay on delivery.")
                    return
                cart.clear()
                update_cart_count()
                close_dialog()
                refresh_cart_view()
                page.launch_url(checkout_url)
                return
            cart.clear()
            update_cart_count()
            refresh_cart_view()
            page.dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Order received", color=INK, weight=ft.FontWeight.BOLD),
                content=ft.Text(
                    "Thanks, {}. Order {} for {} is saved. Pay on delivery; the seller will call to confirm.".format(name_field.value.strip(), order_id, naira(ordered_total)),
                    color=MUTED,
                ),
                actions=[ft.TextButton("Done", on_click=lambda event: close_dialog())],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            page.dialog.open = True
            page.update()

        page.dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Delivery details", color=INK, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Column(
                    [name_field, phone_field, email_field, address_field, ft.Text("Payment method", color=INK, weight=ft.FontWeight.BOLD), payment_choice, ft.Text("Order total  " + naira(cart_total()), color=INK, weight=ft.FontWeight.BOLD)],
                    tight=True,
                    spacing=12,
                ),
                width=420,
            ),
            actions=[
                ft.TextButton("Back to bag", on_click=lambda e: return_to_cart()),
                ft.ElevatedButton("Place demo order", on_click=place_order, bgcolor=GREEN, color=WHITE),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.dialog.open = True
        page.update()

    def open_cart(e=None):
        page.go("/cart")

    def return_to_cart():
        close_dialog()
        page.go("/cart")

    def refresh_cart_view():
        if page.route == "/cart":
            route_change(None)

    def cart_view():
        item_rows = []
        for product_id, quantity in list(cart.items()):
            product = get_product(product_id)
            if product is None:
                cart.pop(product_id, None)
                continue
            item_rows.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Image(src=product["image"] or PRODUCTS[0]["image"], width=88, height=88, fit=ft.ImageFit.COVER, border_radius=8),
                            ft.Column(
                                [
                                    ft.Text(product["name"], color=INK, size=14, weight=ft.FontWeight.BOLD),
                                    ft.Text(product["seller"] + "  ·  Verified seller", color=MUTED, size=11),
                                    ft.Text(naira(product["price"]), color=INK, size=14, weight=ft.FontWeight.BOLD),
                                    ft.Row(
                                        [
                                            ft.IconButton(ft.Icons.REMOVE_CIRCLE_OUTLINE, tooltip="Decrease quantity", on_click=lambda e, item_id=product_id: change_quantity(item_id, -1)),
                                            ft.Text(str(quantity), color=INK, size=13),
                                            ft.IconButton(ft.Icons.ADD_CIRCLE_OUTLINE, tooltip="Increase quantity", on_click=lambda e, item_id=product_id: change_quantity(item_id, 1)),
                                        ],
                                        spacing=2,
                                    ),
                                ],
                                expand=True,
                                spacing=4,
                            ),
                            ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Remove item", on_click=lambda e, item_id=product_id: remove_from_cart(item_id)),
                        ],
                        spacing=14,
                    ),
                    bgcolor=WHITE,
                    border=ft.border.all(1, LINE),
                    border_radius=9,
                    padding=12,
                )
            )

        if not item_rows:
            item_content = ft.Container(
                content=ft.Column(
                    [
                        ft.Icon(ft.Icons.SHOPPING_BAG_OUTLINED, size=42, color=MUTED),
                        ft.Text("Your bag is empty", size=18, color=INK, weight=ft.FontWeight.BOLD),
                        ft.Text("Good finds are waiting back at the storefront.", size=13, color=MUTED),
                        ft.ElevatedButton("Continue shopping", icon=ft.Icons.ARROW_BACK, on_click=lambda e: page.go("/"), bgcolor=GREEN, color=WHITE),
                    ],
                    spacing=12,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                bgcolor=WHITE,
                border=ft.border.all(1, LINE),
                border_radius=10,
                padding=32,
            )
        else:
            item_content = ft.Column(
                [
                    *item_rows,
                    ft.Row([ft.Text("Subtotal", color=MUTED), ft.Text(naira(cart_total()), color=INK, size=18, weight=ft.FontWeight.BOLD)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Text("Delivery fee confirmed by your seller at checkout.", color=MUTED, size=11),
                    ft.ElevatedButton("Continue to checkout", icon=ft.Icons.ARROW_FORWARD, on_click=lambda e: open_checkout(), bgcolor=GREEN, color=WHITE, height=46),
                ],
                spacing=14,
            )

        return ft.Container(
            content=ft.Column(
                [
                    ft.TextButton("Continue shopping", icon=ft.Icons.ARROW_BACK, on_click=lambda e: page.go("/")),
                    ft.Row(
                        [
                            ft.Column([ft.Text("Your bag", size=30, color=INK, weight=ft.FontWeight.BOLD), ft.Text("{} item{}".format(sum(cart.values()), "s" if sum(cart.values()) != 1 else ""), color=MUTED, size=13)], spacing=3),
                            ft.Icon(ft.Icons.SHOPPING_BAG_OUTLINED, color=GREEN, size=27),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    item_content,
                ],
                spacing=18,
                width=760,
            ),
            alignment=ft.alignment.top_center,
            padding=ft.padding.symmetric(horizontal=24, vertical=28),
            expand=True,
        )

    def open_admin(e=None):
        page.go("/admin")

    def admin_view():
        dashboard_status = ft.Text("Sign in with an administrator account to load store data.", color=MUTED, size=13)
        summary_cards = ft.ResponsiveRow(spacing=12, run_spacing=12)
        orders_list = ft.Column(spacing=10)
        seller_list = ft.Column(spacing=10)

        def load_dashboard(e=None):
            try:
                authorize_admin_view("")
            except HTTPException as error:
                dashboard_status.value = error.detail
                summary_cards.controls = []
                orders_list.controls = []
                seller_list.controls = []
                page.update()
                return

            orders = list_orders(limit=200)
            sellers = list_sellers()
            paid_total = sum(order["total_ngn"] for order in orders if order["payment_status"] == "paid")
            pending_payments = sum(1 for order in orders if order["payment_status"] == "pending")
            pending_sellers = sum(1 for seller in sellers if seller["status"] == "pending")
            summary_cards.controls = [
                dashboard_metric("Orders", str(len(orders)), ft.Icons.RECEIPT_LONG_OUTLINED, "Latest 200 orders"),
                dashboard_metric("Order value", naira(sum(order["total_ngn"] for order in orders)), ft.Icons.ACCOUNT_BALANCE_WALLET_OUTLINED, "Recorded order totals"),
                dashboard_metric("Paid online", naira(paid_total), ft.Icons.PAYMENTS_OUTLINED, "Confirmed Paystack payments"),
                dashboard_metric("Seller applications", str(pending_sellers), ft.Icons.STORE_OUTLINED, "Awaiting review", ORANGE),
            ]
            dashboard_status.value = "Latest 200 orders · refreshed just now"
            orders_list.controls = []
            seller_list.controls = []
            if not orders:
                orders_list.controls.append(ft.Text("No orders yet.", color=MUTED, size=13))

            for order in orders:
                status_picker = ft.Dropdown(
                    label="Fulfilment status",
                    value=order["order_status"],
                    options=[ft.dropdown.Option(status) for status in ORDER_STATUSES],
                    width=210,
                )

                def save_status(event, order_id=order["order_id"], picker=status_picker):
                    try:
                        authorize_admin_view("")
                        set_order_status(order_id, picker.value)
                    except (HTTPException, ValueError) as error:
                        show_message(error.detail if isinstance(error, HTTPException) else str(error))
                        return
                    show_message("Order {} updated".format(order_id))
                    load_dashboard()

                orders_list.controls.append(
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Row(
                                    [
                                        ft.Text(order["order_id"], color=INK, weight=ft.FontWeight.BOLD),
                                        ft.Text(naira(order["total_ngn"]), color=INK, weight=ft.FontWeight.BOLD),
                                    ],
                                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                ),
                                ft.Text("{}  ·  {}  ·  {}".format(order["customer_name"], order["customer_email"] or "No email", order["phone"]), color=MUTED, size=12),
                                ft.Text("{}  ·  Payment: {} ({})".format(order["created_at"], order["payment_method"], order["payment_status"]), color=MUTED, size=11),
                                ft.Text("Delivery: " + order["delivery_address"], color=MUTED, size=11),
                                ft.Text(", ".join("{} × {}".format(item["product_name"], item["quantity"]) for item in order["items"]), color=INK, size=12),
                                ft.Row(
                                    [
                                        status_picker,
                                        ft.ElevatedButton("Save status", icon=ft.Icons.SAVE_OUTLINED, on_click=save_status, bgcolor=GREEN, color=WHITE),
                                    ],
                                    wrap=True,
                                    spacing=10,
                                ),
                            ],
                            spacing=7,
                        ),
                        bgcolor=WHITE,
                        border=ft.border.all(1, LINE),
                        border_radius=9,
                        padding=14,
                    )
                )

            if not sellers:
                seller_list.controls.append(ft.Text("No seller applications yet.", color=MUTED, size=13))
            for seller in sellers:
                seller_status = ft.Dropdown(
                    label="Application status",
                    value=seller["status"],
                    options=[ft.dropdown.Option(status) for status in SELLER_STATUSES],
                    width=210,
                )

                def save_seller_status(event, user_id=seller["id"], picker=seller_status):
                    try:
                        authorize_admin_view("")
                        set_seller_status(user_id, picker.value)
                    except (HTTPException, ValueError) as error:
                        show_message(error.detail if isinstance(error, HTTPException) else str(error))
                        return
                    show_message("Seller application updated")
                    load_dashboard()

                seller_list.controls.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Column(
                                    [
                                        ft.Text(seller["store_name"], color=INK, weight=ft.FontWeight.BOLD),
                                        ft.Text("{}  ·  {}".format(seller["full_name"], seller["email"]), color=MUTED, size=12),
                                    ],
                                    spacing=4,
                                    expand=True,
                                ),
                                seller_status,
                                ft.ElevatedButton("Save", on_click=save_seller_status, bgcolor=GREEN, color=WHITE),
                            ],
                            wrap=True,
                            spacing=10,
                        ),
                        bgcolor=WHITE,
                        border=ft.border.all(1, LINE),
                        border_radius=9,
                        padding=14,
                    )
                )
            page.update()

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.TextButton("Back to storefront", icon=ft.Icons.ARROW_BACK, on_click=lambda e: page.go("/")),
                            ft.TextButton("Sign out", icon=ft.Icons.LOGOUT, on_click=lambda e: sign_out()),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Row(
                        [
                            ft.Column([ft.Text("Admin dashboard", size=28, color=INK, weight=ft.FontWeight.BOLD), ft.Text("KwajiBuy operations overview", size=13, color=MUTED)], spacing=3),
                            ft.Icon(ft.Icons.ADMIN_PANEL_SETTINGS_OUTLINED, color=GREEN, size=28),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.ElevatedButton("Refresh dashboard", icon=ft.Icons.REFRESH, on_click=load_dashboard, bgcolor=GREEN, color=WHITE),
                    dashboard_status,
                    summary_cards,
                    ft.Text("Recent orders", size=20, color=INK, weight=ft.FontWeight.BOLD),
                    orders_list,
                    ft.Text("Seller applications", size=20, color=INK, weight=ft.FontWeight.BOLD),
                    seller_list,
                ],
                spacing=16,
                width=1040,
            ),
            alignment=ft.alignment.top_center,
            padding=ft.padding.symmetric(horizontal=24, vertical=28),
            expand=True,
        )

    def product_card(product):
        return ft.Container(
            col={"xs": 6, "sm": 6, "md": 4, "lg": 3},
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Stack(
                            [
                                ft.Image(src=product["image"] or PRODUCTS[0]["image"], height=180, width=float("inf"), fit=ft.ImageFit.COVER, border_radius=8),
                                ft.Container(content=ft.Text(product["tag"], size=9, weight=ft.FontWeight.BOLD, color=INK), bgcolor=LIME, padding=ft.padding.symmetric(horizontal=9, vertical=6), border_radius=20, left=10, top=10),
                                ft.IconButton(ft.Icons.FAVORITE_BORDER, tooltip="Save item", icon_color=INK, bgcolor=WHITE, right=8, top=8, on_click=lambda e, item=product: show_message(item["name"] + " saved to your favourites")),
                            ],
                            height=180,
                        ),
                        ft.Column(
                            [
                                ft.Text(product["name"], size=13, color=INK, weight=ft.FontWeight.W_600, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                                ft.Text(product["seller"] + "  ·  ✓ Verified", size=11, color=MUTED),
                                ft.Row([ft.Text(naira(product["price"]), size=15, color=INK, weight=ft.FontWeight.BOLD), ft.Text(naira(product["was"]), size=11, color=MUTED, style=ft.TextStyle(decoration=ft.TextDecoration.LINE_THROUGH))], spacing=8),
                                ft.Row([ft.Icon(ft.Icons.STAR, size=14, color="#E7A32E"), ft.Text(product["rating"], size=11, color=INK), ft.Text("({})".format(product["reviews"]), size=11, color=MUTED)], spacing=3),
                                ft.ElevatedButton("Add to bag", icon=ft.Icons.ADD_SHOPPING_CART, on_click=lambda e, item=product: add_to_cart(item), bgcolor=GREEN, color=WHITE, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)), width=float("inf")),
                            ],
                            spacing=7,
                        ),
                    ],
                    spacing=10,
                ),
                bgcolor=WHITE,
                padding=10,
                border_radius=10,
                border=ft.border.all(1, LINE),
            ),
        )

    def render_products():
        filtered = list_products()
        if active_category != "All finds":
            filtered = [item for item in filtered if item["category"] == active_category]
        if search_query:
            needle = search_query.casefold()
            filtered = [item for item in filtered if needle in item["name"].casefold() or needle in item["category"].casefold() or needle in item["seller"].casefold()]
        product_grid.controls = [product_card(item) for item in filtered]
        result_label.value = "{} find{} picked for you".format(len(filtered), "s" if len(filtered) != 1 else "")
        if not filtered:
            product_grid.controls = [
                ft.Container(col=12, content=ft.Column([ft.Icon(ft.Icons.SEARCH_OFF, size=34, color=MUTED), ft.Text("No finds match that search", color=INK, weight=ft.FontWeight.BOLD), ft.Text("Try another product, seller or category.", color=MUTED)], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8), padding=40)
            ]
        page.update()

    search_field = ft.TextField(
        hint_text="Search products, brands and local sellers",
        border=ft.InputBorder.NONE,
        text_size=14,
        content_padding=ft.padding.symmetric(vertical=12, horizontal=8),
        expand=True,
        on_submit=lambda e: run_search(),
    )

    def run_search():
        nonlocal search_query
        search_query = (search_field.value or "").strip()
        render_products()

    def choose_category(category):
        nonlocal active_category
        active_category = category
        for name, button in category_buttons:
            selected = name == category
            button.style = ft.ButtonStyle(
                color=WHITE if selected else INK,
                bgcolor=GREEN if selected else WHITE,
                padding=ft.padding.symmetric(horizontal=15, vertical=11),
                shape=ft.RoundedRectangleBorder(radius=20),
            )
        render_products()

    def category_button(category):
        selected = category == active_category
        button = ft.TextButton(
            category,
            on_click=lambda e, name=category: choose_category(name),
            style=ft.ButtonStyle(color=WHITE if selected else INK, bgcolor=GREEN if selected else WHITE, padding=ft.padding.symmetric(horizontal=15, vertical=11), shape=ft.RoundedRectangleBorder(radius=20)),
        )
        category_buttons.append((category, button))
        return button

    def toggle_theme(e):
        page.theme_mode = ft.ThemeMode.DARK if page.theme_mode == ft.ThemeMode.LIGHT else ft.ThemeMode.LIGHT
        show_message("Dark mode" if page.theme_mode == ft.ThemeMode.DARK else "Light mode")

    def open_account(e=None):
        page.go("/account")

    def shopper_account_view(user):
        nonlocal active_profile_email
        active_profile_email = user["email"]
        profile = get_customer_profile(active_profile_email)
        shopper_orders = list_orders(limit=50, customer_email=active_profile_email)
        open_orders = sum(1 for order in shopper_orders if order["order_status"] not in ("delivered", "cancelled"))
        profile_email = ft.TextField(
            label="Email address",
            value=profile["email"] if profile else active_profile_email,
            keyboard_type=ft.KeyboardType.EMAIL,
            border_radius=8,
            read_only=True,
        )
        profile_name = ft.TextField(label="Full name", value=profile["full_name"] if profile else "", border_radius=8)
        profile_phone = ft.TextField(label="Phone number", value=profile["phone"] if profile else "", keyboard_type=ft.KeyboardType.PHONE, border_radius=8)
        profile_address = ft.TextField(
            label="Delivery address",
            value=profile["delivery_address"] if profile else "",
            multiline=True,
            min_lines=2,
            border_radius=8,
        )
        profile_message = ft.Text("Edit your details and save this demo profile.", color=MUTED, size=12)
        order_history = ft.Column(spacing=10)

        def render_order_history(email):
            orders = list_orders(limit=20, customer_email=email)
            order_history.controls = []
            if not orders:
                order_history.controls.append(ft.Text("No orders are linked to this email yet.", color=MUTED, size=12))
            for order in orders:
                order_history.controls.append(
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Row(
                                    [
                                        ft.Text(order["order_id"], color=INK, weight=ft.FontWeight.BOLD),
                                        ft.Text(naira(order["total_ngn"]), color=INK, weight=ft.FontWeight.BOLD),
                                    ],
                                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                ),
                                ft.Text(
                                    "{}  ·  {}  ·  {}".format(order["created_at"], order["order_status"], order["payment_status"]),
                                    color=MUTED,
                                    size=11,
                                ),
                                ft.Text(
                                    ", ".join("{} × {}".format(item["product_name"], item["quantity"]) for item in order["items"]),
                                    color=MUTED,
                                    size=12,
                                ),
                            ],
                            spacing=5,
                        ),
                        bgcolor=PAPER,
                        border_radius=8,
                        padding=12,
                    )
                )

        def load_profile(e):
            nonlocal active_profile_email
            email = (profile_email.value or "").strip().lower()
            if "@" not in email:
                profile_message.value = "Enter the email used for your profile or order."
                page.update()
                return
            active_profile_email = email
            saved_profile = get_customer_profile(email)
            if saved_profile:
                profile_name.value = saved_profile["full_name"]
                profile_phone.value = saved_profile["phone"]
                profile_address.value = saved_profile["delivery_address"]
                profile_message.value = "Profile loaded. Update any field and save your changes."
            else:
                profile_message.value = "No saved profile found. Add your details and save to create one."
            render_order_history(email)
            page.update()

        def save_profile(e):
            nonlocal active_profile_email
            try:
                saved_profile = save_customer_profile(
                    profile_email.value or "",
                    profile_name.value or "",
                    profile_phone.value or "",
                    profile_address.value or "",
                )
            except ValueError as error:
                profile_message.value = str(error)
                page.update()
                return
            active_profile_email = saved_profile["email"]
            profile_email.value = active_profile_email
            profile_message.value = "Profile saved on this demo server."
            render_order_history(active_profile_email)
            page.update()

        render_order_history(active_profile_email)
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.TextButton("Back to shopping", icon=ft.Icons.ARROW_BACK, on_click=lambda e: page.go("/")),
                            ft.Row(
                                [
                                    ft.Text(user["full_name"], color=INK, weight=ft.FontWeight.BOLD),
                                    ft.TextButton("Sign out", icon=ft.Icons.LOGOUT, on_click=lambda e: sign_out()),
                                ],
                                spacing=8,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        wrap=True,
                    ),
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Container(content=ft.Text("SHOPPER PROFILE", size=10, color=GREEN, weight=ft.FontWeight.BOLD), bgcolor=LIME, padding=ft.padding.symmetric(horizontal=10, vertical=7), border_radius=20, width=140),
                                ft.Text("Welcome back, {}.".format(user["full_name"].split()[0]), size=28, color=INK, weight=ft.FontWeight.BOLD),
                                ft.Text("Your details prefill checkout and your recent orders stay together here.", size=14, color=MUTED),
                            ],
                            spacing=18,
                            horizontal_alignment=ft.CrossAxisAlignment.START,
                        ),
                        bgcolor=WHITE,
                        border=ft.border.all(1, LINE),
                        border_radius=12,
                        padding=24,
                    ),
                    ft.Text("Account overview", size=18, color=INK, weight=ft.FontWeight.BOLD),
                    ft.ResponsiveRow(
                        [
                            dashboard_metric("Orders", str(len(shopper_orders)), ft.Icons.RECEIPT_LONG_OUTLINED, "Placed from this account"),
                            dashboard_metric("Order value", naira(sum(order["total_ngn"] for order in shopper_orders)), ft.Icons.ACCOUNT_BALANCE_WALLET_OUTLINED, "Across your recent orders"),
                            dashboard_metric("In progress", str(open_orders), ft.Icons.LOCAL_SHIPPING_OUTLINED, "Not yet delivered"),
                            dashboard_metric("Bag", str(sum(cart.values())), ft.Icons.SHOPPING_BAG_OUTLINED, "Items ready for checkout"),
                        ],
                        spacing=12,
                        run_spacing=12,
                    ),
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Text("Profile details", size=19, color=INK, weight=ft.FontWeight.BOLD),
                                ft.Text("Orders placed with this email appear below.", size=12, color=MUTED),
                                profile_email,
                                profile_name,
                                profile_phone,
                                profile_address,
                                ft.Row(
                                    [
                                        ft.OutlinedButton("Load profile & orders", icon=ft.Icons.SEARCH, on_click=load_profile),
                                        ft.ElevatedButton("Save profile", icon=ft.Icons.SAVE_OUTLINED, on_click=save_profile, bgcolor=GREEN, color=WHITE),
                                    ],
                                    wrap=True,
                                    spacing=10,
                                ),
                                profile_message,
                            ],
                            spacing=12,
                        ),
                        bgcolor=WHITE,
                        border=ft.border.all(1, LINE),
                        border_radius=10,
                        padding=20,
                    ),
                    ft.Container(
                        content=ft.Column(
                            [ft.Text("Recent orders", size=19, color=INK, weight=ft.FontWeight.BOLD), order_history],
                            spacing=12,
                        ),
                        bgcolor=WHITE,
                        border=ft.border.all(1, LINE),
                        border_radius=10,
                        padding=20,
                    ),
                    ft.ResponsiveRow(
                        [
                            ft.Container(
                                col={"xs": 12, "md": 6},
                                content=ft.Row([ft.Icon(ft.Icons.SHOPPING_BAG_OUTLINED, color=GREEN, size=23), ft.Column([ft.Text("Your bag", color=INK, weight=ft.FontWeight.BOLD), ft.Text("Review items and continue to checkout.", color=MUTED, size=12)], spacing=4)], spacing=12),
                                bgcolor=WHITE,
                                border=ft.border.all(1, LINE),
                                border_radius=9,
                                padding=16,
                                on_click=lambda e: open_cart(),
                                ink=True,
                            ),
                            ft.Container(
                                col={"xs": 12, "md": 6},
                                content=ft.Row([ft.Icon(ft.Icons.LOCAL_MALL_OUTLINED, color=GREEN, size=23), ft.Column([ft.Text("Keep browsing", color=INK, weight=ft.FontWeight.BOLD), ft.Text("Return to this week’s good finds.", color=MUTED, size=12)], spacing=4)], spacing=12),
                                bgcolor=WHITE,
                                border=ft.border.all(1, LINE),
                                border_radius=9,
                                padding=16,
                                on_click=lambda e: page.go("/"),
                                ink=True,
                            ),
                        ],
                        spacing=12,
                    ),
                ],
                spacing=18,
                width=720,
            ),
            alignment=ft.alignment.top_center,
            padding=ft.padding.symmetric(horizontal=24, vertical=30),
            expand=True,
        )

    def account_view():
        user = current_user()
        if user:
            if user["role"] == "seller":
                page.go("/seller")
                return ft.Container()
            if user["role"] == "admin":
                page.go("/admin")
                return ft.Container()
            return shopper_account_view(user)

        email_field = ft.TextField(label="Email address", keyboard_type=ft.KeyboardType.EMAIL, border_radius=8)
        password_field = ft.TextField(label="Password", password=True, can_reveal_password=True, border_radius=8)
        auth_message = ft.Text("Sign in to your shopper, seller, or admin workspace.", color=MUTED, size=12)

        def advance_login(e):
            user = authenticate_user(email_field.value or "", password_field.value or "")
            if not user:
                auth_message.value = "Email or password is incorrect."
                page.update()
                return
            page.go(establish_user_session(user))

        def load_demo(email):
            user = authenticate_demo_user(email)
            if user is None:
                auth_message.value = "Demo quick access is disabled. Use your password or enable demo accounts on this local server."
                page.update()
                return
            page.go(establish_user_session(user))

        def demo_card(role, email, accent):
            demo_enabled = os.environ.get("KWAJIBUY_ENABLE_DEMO_ACCOUNTS") == "1"
            return ft.Container(
                col={"xs": 12, "sm": 4},
                content=ft.Column(
                    [
                        ft.Container(width=52, height=4, bgcolor=accent, border_radius=4),
                        ft.Text(role, size=14, color=INK, weight=ft.FontWeight.BOLD),
                        ft.Text(email, size=9, color=MUTED, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                        ft.ElevatedButton(
                            "Open demo" if demo_enabled else "Demo disabled",
                            on_click=lambda e, account=email: load_demo(account),
                            disabled=not demo_enabled,
                            bgcolor=GREEN if demo_enabled else "#E9ECE9",
                            color=WHITE if demo_enabled else MUTED,
                            width=float("inf"),
                            style=ft.ButtonStyle(padding=ft.padding.symmetric(horizontal=8, vertical=8), text_style=ft.TextStyle(size=11)),
                        ),
                    ],
                    spacing=6,
                ),
                bgcolor=WHITE,
                border=ft.border.all(1, LINE),
                border_radius=9,
                padding=12,
                on_click=lambda e, account=email: load_demo(account),
                ink=True,
            )

        login_panel = ft.Container(
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Row([ft.Icon(ft.Icons.AUTO_AWESOME, size=16, color=GREEN), ft.Text("KWAJIBUY ACCOUNT", size=10, color=GREEN, weight=ft.FontWeight.BOLD)], spacing=8),
                        bgcolor="#F0F5F1",
                        border_radius=20,
                        padding=ft.padding.symmetric(horizontal=12, vertical=8),
                        width=180,
                    ),
                    ft.Text("Sign in to continue", size=28, color=INK, weight=ft.FontWeight.BOLD),
                    ft.Text("Access your shopper, seller, or admin workspace.", size=13, color=MUTED),
                    email_field,
                    password_field,
                    ft.ElevatedButton("Sign in", icon=ft.Icons.LOGIN, on_click=advance_login, bgcolor=GREEN, color=WHITE, width=float("inf"), height=46),
                    auth_message,
                    ft.Divider(color=LINE),
                    ft.Text("DEMO ACCOUNTS", size=11, color=MUTED, weight=ft.FontWeight.BOLD),
                    ft.ResponsiveRow(
                        [
                            demo_card("Shopper", "demo.shopper@kwajibuy.local", "#16A6BE"),
                            demo_card("Seller", "demo.seller@kwajibuy.local", "#34A878"),
                            demo_card("Administrator", "demo.admin@kwajibuy.local", ORANGE),
                        ],
                        spacing=10,
                        run_spacing=10,
                    ),
                    ft.Row(
                        [
                            ft.Text("New to KwajiBuy?", color=MUTED, size=12),
                            ft.TextButton("Create account", on_click=lambda e: page.go("/register"), style=ft.ButtonStyle(color=GREEN)),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=4,
                    ),
                    ft.TextButton("Back to shopping", icon=ft.Icons.ARROW_BACK, on_click=lambda e: page.go("/")),
                ],
                spacing=13,
            ),
            width=560,
            padding=24,
            bgcolor=WHITE,
            border=ft.border.all(1, LINE),
            border_radius=12,
        )
        return ft.Container(
            content=ft.Column([login_panel], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.padding.symmetric(horizontal=20, vertical=24),
            bgcolor="#F8FAF8",
            expand=True,
        )

    def register_view():
        user = current_user()
        if user:
            page.go(establish_user_session(user))
            return ft.Container()
        name_field = ft.TextField(label="Full name", border_radius=8)
        email_field = ft.TextField(label="Email address", keyboard_type=ft.KeyboardType.EMAIL, border_radius=8)
        password_field = ft.TextField(label="Password (12 characters minimum)", password=True, can_reveal_password=True, border_radius=8)
        phone_field = ft.TextField(label="Phone number", keyboard_type=ft.KeyboardType.PHONE, border_radius=8)
        address_field = ft.TextField(label="Delivery address", multiline=True, min_lines=2, border_radius=8)
        store_name = ft.TextField(label="Store name", border_radius=8, visible=False)
        role_choice = ft.Dropdown(label="Account type", value="shopper", options=[ft.dropdown.Option("shopper"), ft.dropdown.Option("seller")], border_radius=8)
        status = ft.Text("Seller accounts require admin approval.", color=MUTED, size=12)

        def change_role(e):
            store_name.visible = role_choice.value == "seller"
            page.update()

        role_choice.on_change = change_role

        def create_account(e):
            try:
                user = register_user(email_field.value or "", password_field.value or "", name_field.value or "", role=role_choice.value, phone=phone_field.value or "", address=address_field.value or "", store_name=store_name.value or "")
            except (ValueError, sqlite3.Error) as error:
                status.value = str(error)
                page.update()
                return
            page.go(establish_user_session(user))

        return ft.Container(
            content=ft.Column(
                [
                    ft.TextButton("Back to sign in", icon=ft.Icons.ARROW_BACK, on_click=lambda e: page.go("/account")),
                    ft.Container(
                        content=ft.Column(
                            [ft.Text("JOIN KWAJIBUY", size=10, color=GREEN, weight=ft.FontWeight.BOLD), ft.Text("Create your account", size=28, color=INK, weight=ft.FontWeight.BOLD), name_field, email_field, password_field, role_choice, store_name, phone_field, address_field, ft.ElevatedButton("Create account", icon=ft.Icons.PERSON_ADD_ALT_1, on_click=create_account, bgcolor=GREEN, color=WHITE), status],
                            spacing=12,
                        ),
                        width=520,
                        bgcolor=WHITE,
                        border=ft.border.all(1, LINE),
                        border_radius=12,
                        padding=24,
                    ),
                ],
                spacing=18,
            ),
            alignment=ft.alignment.top_center,
            padding=ft.padding.symmetric(horizontal=20, vertical=28),
            expand=True,
        )

    def seller_view(user):
        status = user.get("seller_status", "pending")
        status_color = GREEN if status == "approved" else ORANGE if status == "pending" else MUTED
        status_label = status.replace("_", " ").title()
        seller_products = list_products(seller_id=user["id"], include_inactive=True)
        active_count = sum(1 for product in seller_products if product["active"])
        paused_count = len(seller_products) - active_count
        editing_product_id = None
        form_heading = ft.Text("Add a product", size=18, color=INK, weight=ft.FontWeight.BOLD)
        product_name = ft.TextField(label="Product name", border_radius=8)
        product_category = ft.Dropdown(
            label="Category",
            options=[ft.dropdown.Option(category) for category in CATEGORIES if category != "All finds"],
            border_radius=8,
        )
        product_price = ft.TextField(label="Price (NGN)", keyboard_type=ft.KeyboardType.NUMBER, border_radius=8)
        product_compare = ft.TextField(label="Compare-at price (NGN)", keyboard_type=ft.KeyboardType.NUMBER, border_radius=8)
        product_image = ft.TextField(label="Image URL (optional)", border_radius=8)
        product_tag = ft.TextField(label="Listing tag", value="NEW FIND", border_radius=8)
        form_status = ft.Text(color=MUTED, size=12)
        product_rows = ft.Column(spacing=10)
        save_label = ft.Text("Add product", color=WHITE)

        def reset_product_form():
            nonlocal editing_product_id
            editing_product_id = None
            form_heading.value = "Add a product"
            product_name.value = ""
            product_category.value = None
            product_price.value = ""
            product_compare.value = ""
            product_image.value = ""
            product_tag.value = "NEW FIND"
            save_label.value = "Add product"
            form_status.value = ""

        def render_seller_products():
            nonlocal seller_products, active_count, paused_count
            seller_products = list_products(seller_id=user["id"], include_inactive=True)
            active_count = sum(1 for product in seller_products if product["active"])
            paused_count = len(seller_products) - active_count
            product_rows.controls = []
            if not seller_products:
                product_rows.controls.append(ft.Text("No products yet. Add your first listing above.", color=MUTED, size=13))
            for product in seller_products:
                product_state = "Active" if product["active"] else "Paused"

                def edit_product(event, item=product):
                    nonlocal editing_product_id
                    editing_product_id = item["id"]
                    form_heading.value = "Edit product"
                    product_name.value = item["name"]
                    product_category.value = item["category"]
                    product_price.value = str(item["price"])
                    product_compare.value = str(item["was"])
                    product_image.value = item["image"]
                    product_tag.value = item["tag"]
                    save_label.value = "Save changes"
                    form_status.value = "Editing {}".format(item["name"])
                    page.update()

                def toggle_product(event, item=product):
                    try:
                        set_seller_product_active(user["id"], item["id"], not bool(item["active"]))
                    except ValueError as error:
                        form_status.value = str(error)
                    render_seller_products()
                    page.update()

                product_rows.controls.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Column(
                                    [
                                        ft.Text(product["name"], color=INK, weight=ft.FontWeight.BOLD),
                                        ft.Text("{}  ·  {}  ·  {}".format(product["category"], naira(product["price"]), product_state), color=MUTED, size=12),
                                    ],
                                    spacing=4,
                                    expand=True,
                                ),
                                ft.TextButton("Edit", icon=ft.Icons.EDIT_OUTLINED, on_click=edit_product),
                                ft.TextButton("Pause" if product["active"] else "Republish", icon=ft.Icons.PAUSE_CIRCLE_OUTLINE if product["active"] else ft.Icons.PLAY_CIRCLE_OUTLINE, on_click=toggle_product),
                            ],
                            wrap=True,
                            spacing=8,
                        ),
                        bgcolor=WHITE,
                        border=ft.border.all(1, LINE),
                        border_radius=9,
                        padding=12,
                    )
                )

        def save_product(e):
            nonlocal editing_product_id
            if status != "approved":
                form_status.value = "Admin approval is required before publishing products."
                page.update()
                return
            try:
                if editing_product_id:
                    update_seller_product(
                        user["id"], editing_product_id, product_name.value or "", product_category.value or "",
                        product_price.value or "", product_compare.value or "", product_image.value or "", product_tag.value or "NEW FIND",
                    )
                    form_status.value = "Product updated."
                else:
                    create_seller_product(
                        user["id"], product_name.value or "", product_category.value or "",
                        product_price.value or "", product_compare.value or "", product_image.value or "", product_tag.value or "NEW FIND",
                    )
                    form_status.value = "Product listed in the marketplace."
                editing_product_id = None
                form_heading.value = "Add a product"
                product_name.value = ""
                product_category.value = None
                product_price.value = ""
                product_compare.value = ""
                product_image.value = ""
                product_tag.value = "NEW FIND"
                save_label.value = "Add product"
            except (ValueError, sqlite3.Error) as error:
                form_status.value = str(error)
            render_seller_products()
            page.update()

        render_seller_products()

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.TextButton("Back to storefront", icon=ft.Icons.ARROW_BACK, on_click=lambda e: page.go("/")),
                            ft.TextButton("Sign out", icon=ft.Icons.LOGOUT, on_click=lambda e: sign_out()),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Container(content=ft.Text("SELLER ACCOUNT", size=10, color=GREEN, weight=ft.FontWeight.BOLD), bgcolor=LIME, padding=ft.padding.symmetric(horizontal=10, vertical=7), border_radius=20, width=140),
                                ft.Text("Seller workspace", size=12, color=MUTED, weight=ft.FontWeight.BOLD),
                                ft.Text(user.get("store_name") or "Your store", size=28, color=INK, weight=ft.FontWeight.BOLD),
                                ft.Text("Signed in as {}".format(user["email"]), size=13, color=MUTED),
                            ],
                            spacing=7,
                        ),
                        bgcolor=WHITE,
                        border=ft.border.all(1, LINE),
                        border_radius=12,
                        padding=24,
                    ),
                    ft.Text("Store overview", size=18, color=INK, weight=ft.FontWeight.BOLD),
                    ft.ResponsiveRow(
                        [
                            dashboard_metric("Application", status_label, ft.Icons.VERIFIED_USER_OUTLINED, "Seller review status", status_color),
                            dashboard_metric("Store", user.get("store_name") or "Not set", ft.Icons.STORE_OUTLINED, "Seller profile"),
                            dashboard_metric("Active listings", str(active_count), ft.Icons.INVENTORY_2_OUTLINED, "Visible in the marketplace"),
                            dashboard_metric("Paused listings", str(paused_count), ft.Icons.PAUSE_CIRCLE_OUTLINE, "Hidden from shoppers", ORANGE),
                            dashboard_metric("Payouts", "Not connected", ft.Icons.PAYMENTS_OUTLINED, "No seller payout integration", ORANGE),
                        ],
                        spacing=12,
                        run_spacing=12,
                    ),
                    ft.Text("Catalog", size=18, color=INK, weight=ft.FontWeight.BOLD),
                    ft.Container(
                        content=ft.Column(
                            [
                                form_heading,
                                ft.ResponsiveRow(
                                    [
                                        ft.Container(col={"xs": 12, "md": 6}, content=product_name),
                                        ft.Container(col={"xs": 12, "md": 6}, content=product_category),
                                        ft.Container(col={"xs": 12, "md": 6}, content=product_price),
                                        ft.Container(col={"xs": 12, "md": 6}, content=product_compare),
                                        ft.Container(col={"xs": 12, "md": 6}, content=product_image),
                                        ft.Container(col={"xs": 12, "md": 6}, content=product_tag),
                                    ],
                                    spacing=10,
                                    run_spacing=10,
                                ),
                                ft.Row(
                                    [
                                        ft.ElevatedButton(content=save_label, icon=ft.Icons.SAVE_OUTLINED, on_click=save_product, bgcolor=GREEN, color=WHITE, disabled=status != "approved"),
                                        ft.TextButton("Clear form", icon=ft.Icons.CLEAR, on_click=lambda e: reset_product_form()),
                                        form_status,
                                    ],
                                    wrap=True,
                                    spacing=10,
                                ),
                            ],
                            spacing=12,
                        ),
                        bgcolor=WHITE,
                        border=ft.border.all(1, LINE),
                        border_radius=10,
                        padding=18,
                    ),
                    product_rows,
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Icon(ft.Icons.INFO_OUTLINE, color=status_color, size=22),
                                ft.Column(
                                    [
                                        ft.Text("{} application".format(status_label), color=INK, size=14, weight=ft.FontWeight.BOLD),
                                        ft.Text(
                                            "Your store is in the admin review queue. Product publishing unlocks after approval."
                                            if status == "pending"
                                            else "Your seller account is approved. Payout integration is not enabled in this MVP."
                                            if status == "approved"
                                            else "This application was not approved. Contact KwajiBuy support for next steps.",
                                            color=MUTED,
                                            size=12,
                                        ),
                                    ],
                                    spacing=4,
                                    expand=True,
                                ),
                                ft.ElevatedButton("View storefront", icon=ft.Icons.OPEN_IN_NEW, on_click=lambda e: page.go("/"), bgcolor=GREEN, color=WHITE),
                            ],
                            wrap=True,
                            spacing=12,
                        ),
                        bgcolor=WHITE,
                        border=ft.border.all(1, LINE),
                        border_radius=10,
                        padding=18,
                    ),
                ],
                spacing=18,
                width=760,
            ),
            alignment=ft.alignment.top_center,
            padding=ft.padding.symmetric(horizontal=24, vertical=28),
            expand=True,
        )

    top_strip = ft.Container(
        content=ft.Row(
            [ft.Text("A better way to shop local", size=11, color=WHITE), ft.Row([ft.Text("Sell on KwajiBuy", size=11, color=WHITE), ft.Text("·", size=11, color="#B6C8BD"), ft.Text("Lagos  •  NGN ₦", size=11, color=WHITE)], spacing=10)],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        ),
        bgcolor=GREEN,
        padding=ft.padding.symmetric(horizontal=24, vertical=8),
    )
    header = ft.Container(
        content=ft.ResponsiveRow(
            [
                ft.Container(col={"xs": 7, "md": 3}, content=ft.Row([ft.Container(content=ft.Text("K", size=22, color=INK, weight=ft.FontWeight.BOLD), bgcolor=LIME, width=38, height=38, border_radius=12, alignment=ft.alignment.center), ft.Column([ft.Text("kwajiBuy", size=21, color=INK, weight=ft.FontWeight.BOLD), ft.Text("GOOD FINDS. CLOSE TO HOME.", size=8, color=MUTED, weight=ft.FontWeight.BOLD)], spacing=0)], spacing=9)),
                ft.Container(col={"xs": 12, "md": 6}, content=ft.Container(content=ft.Row([ft.Icon(ft.Icons.SEARCH, color=MUTED, size=20), search_field, ft.IconButton(ft.Icons.ARROW_FORWARD, tooltip="Search", icon_color=WHITE, bgcolor=ORANGE, on_click=lambda e: run_search())], spacing=4), border=ft.border.all(1, LINE), border_radius=10, bgcolor=WHITE, padding=ft.padding.only(left=12, right=6, top=3, bottom=3))),
                ft.Container(col={"xs": 5, "md": 3}, content=ft.Row([ft.IconButton(ft.Icons.BRIGHTNESS_6_OUTLINED, tooltip="Toggle light and dark mode", on_click=toggle_theme), ft.TextButton("Account", icon=ft.Icons.PERSON_OUTLINE, on_click=open_account), ft.Stack([ft.IconButton(ft.Icons.SHOPPING_BAG_OUTLINED, tooltip="Open your bag", on_click=lambda e: open_cart()), ft.Container(content=cart_count, bgcolor=LIME, border_radius=20, padding=ft.padding.symmetric(horizontal=5, vertical=2), right=0, top=0)], width=46, height=44)], alignment=ft.MainAxisAlignment.END, spacing=2)),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=14,
        ),
        padding=ft.padding.symmetric(horizontal=24, vertical=16),
        bgcolor=WHITE,
        border=ft.border.only(bottom=ft.BorderSide(1, LINE)),
    )
    hero = ft.Container(
        content=ft.ResponsiveRow(
            [
                ft.Container(
                    col={"xs": 12, "md": 7},
                    content=ft.Column(
                        [
                            ft.Container(
                                content=ft.Text("THE LOCAL FINDS EDIT  /  01", size=10, color=GREEN, weight=ft.FontWeight.BOLD),
                                bgcolor=LIME,
                                padding=ft.padding.symmetric(horizontal=10, vertical=7),
                                border_radius=20,
                                width=190,
                            ),
                            ft.Text("Good finds.\nFair prices.\nRight here.", size=42, color=INK, weight=ft.FontWeight.BOLD),
                            ft.Text("Shop thoughtful picks from trusted Nigerian sellers, delivered to your door.", size=15, color=INK, max_lines=2),
                            ft.Row(
                                [
                                    ft.ElevatedButton(
                                        "Shop the edit",
                                        icon=ft.Icons.ARROW_DOWNWARD,
                                        on_click=lambda e: page.views[-1].scroll_to(key="catalog", duration=350),
                                        bgcolor=GREEN,
                                        color=WHITE,
                                        height=44,
                                    ),
                                    ft.Row(
                                        [ft.Icon(ft.Icons.VERIFIED_USER_OUTLINED, color=GREEN, size=17), ft.Text("Verified sellers", size=12, color=INK)],
                                        spacing=5,
                                    ),
                                ],
                                spacing=16,
                                wrap=True,
                            ),
                        ],
                        spacing=15,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                ),
                ft.Container(col={"xs": 12, "md": 5}, content=ft.Stack([ft.Image(src="https://images.unsplash.com/photo-1556742049-0cfed4f6a45d?auto=format&fit=crop&w=1100&q=90", height=290, width=float("inf"), fit=ft.ImageFit.COVER, border_radius=12), ft.Container(content=ft.Column([ft.Text("Made for everyday", size=16, color=INK, weight=ft.FontWeight.BOLD), ft.Text("From Nigerian makers & more", size=12, color=MUTED)], spacing=4), bgcolor=WHITE, padding=14, border_radius=10, left=14, bottom=14), ft.Container(content=ft.Text("LOCAL LOVE", size=9, color=INK, weight=ft.FontWeight.BOLD), bgcolor=LIME, padding=ft.padding.symmetric(horizontal=10, vertical=7), border_radius=20, right=14, top=14)], height=290)),
            ],
            spacing=20,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor="#F1F3E9",
        padding=ft.padding.all(24),
        border_radius=14,
    )
    trust_band = ft.ResponsiveRow(
        [
            ft.Container(col={"xs": 12, "md": 4}, content=ft.Row([ft.Icon(icon, color=GREEN, size=23), ft.Column([ft.Text(title, color=INK, size=13, weight=ft.FontWeight.BOLD), ft.Text(description, color=MUTED, size=11)], spacing=3)], spacing=12), padding=16, bgcolor=WHITE, border_radius=9, border=ft.border.all(1, LINE))
            for title, description, icon in [
                ("Verified sellers", "Know who you’re buying from.", ft.Icons.VERIFIED_USER_OUTLINED),
                ("Pay on delivery", "Pay when your order arrives.", ft.Icons.PAYMENTS_OUTLINED),
                ("Easy returns", "A clear 7-day return window.", ft.Icons.REPLAY_OUTLINED),
            ]
        ],
        spacing=12,
    )
    category_row = ft.Row([category_button(category) for category in CATEGORIES], spacing=8, scroll=ft.ScrollMode.AUTO)
    catalog = ft.Column(
        [
            ft.Row([ft.Column([ft.Text("The good finds", size=27, color=INK, weight=ft.FontWeight.BOLD), ft.Text("A little something for every day.", size=13, color=MUTED)], spacing=3), ft.Container(content=ft.Row([ft.Icon(ft.Icons.LOCAL_SHIPPING_OUTLINED, color=GREEN, size=17), ft.Text("Pay on delivery", size=12, color=INK)], spacing=6), bgcolor=WHITE, padding=ft.padding.symmetric(horizontal=12, vertical=9), border_radius=20)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.END, wrap=True),
            category_row,
            ft.Row([result_label, ft.Text("Sorted: featured", size=11, color=MUTED)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            product_grid,
        ],
        spacing=16,
        key="catalog",
    )
    footer = ft.Container(
        content=ft.ResponsiveRow(
            [
                ft.Container(col={"xs": 12, "md": 5}, content=ft.Column([ft.Text("kwajiBuy", size=21, color=WHITE, weight=ft.FontWeight.BOLD), ft.Text("Good finds. Close to home.", size=12, color="#CBD7CF"), ft.Text("An MVP marketplace concept for trusted Nigerian sellers.", size=11, color="#CBD7CF")], spacing=6)),
                ft.Container(col={"xs": 12, "md": 7}, content=ft.Row([ft.TextButton("Admin dashboard", icon=ft.Icons.ADMIN_PANEL_SETTINGS_OUTLINED, on_click=open_admin, style=ft.ButtonStyle(color=WHITE)), ft.TextButton("Returns & refunds", on_click=lambda e: open_policy("Returns & refunds", "You may request a return within 7 days of delivery for an item that is damaged, defective, or materially different from its listing. Keep the item and packaging, and contact the seller through KwajiBuy to start a return. Approved refunds are issued through the original payment method or another agreed method. Demo orders do not trigger real refunds."), style=ft.ButtonStyle(color=WHITE)), ft.TextButton("Privacy", on_click=lambda e: open_policy("Privacy notice", "A production privacy notice should explain what account, order, contact, and device data is collected; why it is used; who receives it; how long it is retained; and how users can exercise their rights. KwajiBuy should comply with Nigeria’s NDPA 2023 and, where applicable, GDPR. This demo stores order delivery details in its local SQLite database."), style=ft.ButtonStyle(color=WHITE)), ft.TextButton("Terms", on_click=lambda e: open_policy("Terms & conditions", "Listings, prices, seller details, delivery estimates, and availability must be accurate. Buyers should review product details before ordering. Sellers remain responsible for lawful products and fulfilment. This coursework MVP stores orders and can initiate Paystack test/live transactions only when configured. It is not a production commerce service."), style=ft.ButtonStyle(color=WHITE))], wrap=True, alignment=ft.MainAxisAlignment.END)),
            ],
            spacing=18,
        ),
        bgcolor=INK,
        padding=ft.padding.symmetric(horizontal=24, vertical=26),
    )
    storefront = ft.Column(
        [
            top_strip,
            header,
            ft.Container(content=ft.Column([hero, trust_band, catalog], spacing=28), padding=ft.padding.symmetric(horizontal=24, vertical=24), expand=True),
            footer,
        ],
        spacing=0,
        expand=True,
    )

    def route_change(e):
        user = current_user()
        if page.route == "/account" and user and user["role"] != "shopper":
            page.go("/admin" if user["role"] == "admin" else "/seller")
            return
        if page.route == "/admin" and (not user or user["role"] != "admin"):
            page.go("/account")
            return
        if page.route == "/seller" and (not user or user["role"] != "seller"):
            page.go("/account")
            return
        page.views.clear()
        page.views.append(ft.View(route="/", controls=[storefront], bgcolor=PAPER, padding=0, scroll=ft.ScrollMode.AUTO))
        if page.route == "/account":
            page.views.append(ft.View(route="/account", controls=[account_view()], bgcolor=PAPER, padding=0, scroll=ft.ScrollMode.AUTO))
        elif page.route == "/register":
            page.views.append(ft.View(route="/register", controls=[register_view()], bgcolor=PAPER, padding=0, scroll=ft.ScrollMode.AUTO))
        elif page.route == "/cart":
            page.views.append(ft.View(route="/cart", controls=[cart_view()], bgcolor=PAPER, padding=0, scroll=ft.ScrollMode.AUTO))
        elif page.route == "/admin":
            page.views.append(ft.View(route="/admin", controls=[admin_view()], bgcolor=PAPER, padding=0, scroll=ft.ScrollMode.AUTO))
        elif page.route == "/seller":
            page.views.append(ft.View(route="/seller", controls=[seller_view(user)], bgcolor=PAPER, padding=0, scroll=ft.ScrollMode.AUTO))
        elif page.route != "/":
            page.go("/")
            return
        page.update()

    def view_pop(e):
        if len(page.views) > 1:
            page.views.pop()
            page.go(page.views[-1].route)

    page.on_route_change = route_change
    page.on_view_pop = view_pop
    page.go(page.route or "/")
    render_products()


flet_app = ft.app(target=main, name="", export_asgi_app=True)
app = FastAPI(title="KwajiBuy")
app.include_router(admin_api.router)
app.mount("/", flet_app)


if __name__ == "__main__":
    uvicorn.run("main:app", host=os.environ.get("KWAJIBUY_HOST", "0.0.0.0"), port=8550)