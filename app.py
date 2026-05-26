"""
Nexus Games — Flask backend (Phase 2)

Single-file app per project preference. Sections:
  1. Imports & config
  2. DB helpers
  3. Validation helpers
  4. Decorators (login_required, admin_required, csrf_protect)
  5. Page routes (HTML)
  6. Auth API
  7. Password reset API
  8. Products API
  9. Cart API
 10. Orders API + Stripe
 11. Admin API
 12. Bootstrap / main
"""
import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, request, jsonify, session, redirect, url_for,
    render_template, send_from_directory, abort, g,
)
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

try:
    import stripe
    STRIPE_AVAILABLE = True
except ImportError:
    STRIPE_AVAILABLE = False

try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    LIMITER_AVAILABLE = True
except ImportError:
    LIMITER_AVAILABLE = False


# ────────────────────────────────────────────────────────────────────
# 1. Config
# ────────────────────────────────────────────────────────────────────
load_dotenv()

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-change-me')
app.config.update(
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.environ.get('SESSION_COOKIE_SECURE', '0') == '1',
    MAX_CONTENT_LENGTH=2 * 1024 * 1024,  # 2 MB request cap
)

DB_PATH = os.environ.get('DATABASE_PATH', 'nexus_games.db')
APP_BASE_URL = os.environ.get('APP_BASE_URL', 'http://localhost:5000')

# Stripe config
if STRIPE_AVAILABLE:
    stripe.api_key = os.environ.get('STRIPE_SECRET_KEY', '')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY', '')

# Rate limiter (login)
if LIMITER_AVAILABLE:
    limiter = Limiter(
        key_func=get_remote_address,
        app=app,
        default_limits=[],
        storage_uri="memory://",
    )
else:
    limiter = None


# ────────────────────────────────────────────────────────────────────
# 2. DB helpers
# ────────────────────────────────────────────────────────────────────
def get_db():
    db = getattr(g, '_db', None)
    if db is None:
        db = g._db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
    return db


@app.teardown_appcontext
def close_db(_exc):
    db = getattr(g, '_db', None)
    if db is not None:
        db.close()


def init_db_if_missing():
    """Auto-create schema + seed on first run if DB doesn't exist."""
    if os.path.exists(DB_PATH):
        return
    print(f"[app] DB not found at {DB_PATH}; running seed.py …")
    import seed
    seed.main()


# ────────────────────────────────────────────────────────────────────
# 3. Validation helpers
# ────────────────────────────────────────────────────────────────────
EMAIL_RE = re.compile(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')
USERNAME_RE = re.compile(r'^[A-Za-z0-9_]{3,20}$')
PASSWORD_LETTER_RE = re.compile(r'[A-Za-z]')
PASSWORD_DIGIT_RE = re.compile(r'\d')

MAX_NAME = 100
MAX_EMAIL = 120
MAX_ADDRESS = 300
MAX_DESC = 2000
MAX_TITLE = 150
MAX_CATEGORY = 50
MAX_IMAGE = 250


def validate_email(value):
    if not isinstance(value, str) or len(value) > MAX_EMAIL or not EMAIL_RE.match(value):
        return False
    return True


def validate_username(value):
    return isinstance(value, str) and bool(USERNAME_RE.match(value))


def validate_password(value):
    if not isinstance(value, str) or len(value) < 8 or len(value) > 128:
        return False
    return bool(PASSWORD_LETTER_RE.search(value) and PASSWORD_DIGIT_RE.search(value))


def clean_text(value, max_len):
    if value is None:
        return ''
    if not isinstance(value, str):
        return ''
    return value.strip()[:max_len]


# ────────────────────────────────────────────────────────────────────
# 4. Decorators
# ────────────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Authentication required'}), 401
        return f(*a, **kw)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Authentication required'}), 401
        row = get_db().execute(
            "SELECT is_admin FROM users WHERE id = ?", (session['user_id'],)
        ).fetchone()
        if not row or row['is_admin'] != 1:
            return jsonify({'success': False, 'message': 'Admin privileges required'}), 403
        return f(*a, **kw)
    return wrapper


def ensure_csrf_token():
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_urlsafe(32)
    return session['csrf_token']


def csrf_protect(f):
    """CSRF check for state-changing endpoints. Skips webhook (verified via Stripe sig)."""
    @wraps(f)
    def wrapper(*a, **kw):
        if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
            token = request.headers.get('X-CSRF-Token') or (
                request.get_json(silent=True) or {}
            ).get('csrf_token')
            if not token or token != session.get('csrf_token'):
                return jsonify({'success': False, 'message': 'CSRF token invalid'}), 403
        return f(*a, **kw)
    return wrapper


@app.after_request
def set_security_headers(resp):
    resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
    resp.headers.setdefault('X-Frame-Options', 'DENY')
    resp.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    return resp


# ────────────────────────────────────────────────────────────────────
# 5. Page routes
# ────────────────────────────────────────────────────────────────────
PUBLIC_PAGES = {'login.html', 'register.html', 'forgot_password.html', 'reset_password.html'}


def _require_login_for_pages():
    return 'user_id' not in session


@app.route('/')
def root():
    if 'user_id' in session:
        return redirect(url_for('page_home'))
    return redirect(url_for('page_login'))


@app.route('/home')
def page_home():
    if _require_login_for_pages():
        return redirect(url_for('page_login'))
    ensure_csrf_token()
    return render_template('index.html', csrf_token=session['csrf_token'])


@app.route('/login')
def page_login():
    ensure_csrf_token()
    return render_template('login.html', csrf_token=session['csrf_token'])


@app.route('/register')
def page_register():
    ensure_csrf_token()
    return render_template('register.html', csrf_token=session['csrf_token'])


@app.route('/forgot-password')
def page_forgot():
    ensure_csrf_token()
    return render_template('forgot_password.html', csrf_token=session['csrf_token'])


@app.route('/reset-password')
def page_reset():
    ensure_csrf_token()
    return render_template('reset_password.html', csrf_token=session['csrf_token'])


@app.route('/cart.html')
@app.route('/cart')
def page_cart():
    if _require_login_for_pages():
        return redirect(url_for('page_login'))
    ensure_csrf_token()
    return render_template('cart.html', csrf_token=session['csrf_token'])


@app.route('/checkout.html')
@app.route('/checkout')
def page_checkout():
    if _require_login_for_pages():
        return redirect(url_for('page_login'))
    ensure_csrf_token()
    return render_template('checkout.html',
                           csrf_token=session['csrf_token'],
                           stripe_publishable_key=STRIPE_PUBLISHABLE_KEY)


@app.route('/product.html')
@app.route('/product')
def page_product():
    if _require_login_for_pages():
        return redirect(url_for('page_login'))
    ensure_csrf_token()
    return render_template('product.html', csrf_token=session['csrf_token'])


@app.route('/thankyou.html')
@app.route('/thankyou')
def page_thankyou():
    if _require_login_for_pages():
        return redirect(url_for('page_login'))
    ensure_csrf_token()
    return render_template('thankyou.html', csrf_token=session['csrf_token'])


@app.route('/orders.html')
@app.route('/orders')
def page_orders():
    if _require_login_for_pages():
        return redirect(url_for('page_login'))
    ensure_csrf_token()
    return render_template('orders.html', csrf_token=session['csrf_token'])


# Admin pages
@app.route('/admin')
@app.route('/admin/')
def page_admin_dashboard():
    if _require_login_for_pages():
        return redirect(url_for('page_login'))
    return render_template('admin/dashboard.html', csrf_token=ensure_csrf_token())


@app.route('/admin/products')
def page_admin_products():
    if _require_login_for_pages():
        return redirect(url_for('page_login'))
    return render_template('admin/products.html', csrf_token=ensure_csrf_token())


@app.route('/admin/orders')
def page_admin_orders():
    if _require_login_for_pages():
        return redirect(url_for('page_login'))
    return render_template('admin/orders.html', csrf_token=ensure_csrf_token())


@app.route('/admin/users')
def page_admin_users():
    if _require_login_for_pages():
        return redirect(url_for('page_login'))
    return render_template('admin/users.html', csrf_token=ensure_csrf_token())


# ────────────────────────────────────────────────────────────────────
# 6. Auth API
# ────────────────────────────────────────────────────────────────────
def _maybe_rate_limit(rule):
    """Apply a rate-limit decorator only if Flask-Limiter is installed."""
    if LIMITER_AVAILABLE:
        return limiter.limit(rule)
    return lambda f: f


@app.route('/api/login', methods=['POST'])
@_maybe_rate_limit("5 per 15 minutes")
def api_login():
    data = request.get_json(silent=True) or {}
    identifier = clean_text(data.get('username'), MAX_EMAIL)
    password = data.get('password', '')

    if not identifier or not password:
        return jsonify({'success': False, 'message': 'Username/email and password required'}), 400

    db = get_db()
    user = db.execute(
        "SELECT id, username, email, password_hash, is_admin, is_active "
        "FROM users WHERE username = ? OR email = ?",
        (identifier, identifier),
    ).fetchone()

    if not user or not check_password_hash(user['password_hash'], password):
        return jsonify({'success': False, 'message': 'Invalid username or password'}), 401
    if user['is_active'] != 1:
        return jsonify({'success': False, 'message': 'Account is deactivated'}), 403

    session.clear()
    session.permanent = True
    session['user_id'] = user['id']
    session['username'] = user['username']
    session['is_admin'] = bool(user['is_admin'])
    ensure_csrf_token()
    return jsonify({
        'success': True,
        'message': 'Login successful',
        'user': {
            'id': user['id'], 'username': user['username'],
            'email': user['email'], 'is_admin': bool(user['is_admin']),
        },
        'csrf_token': session['csrf_token'],
    })


@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json(silent=True) or {}
    username = clean_text(data.get('username'), 20)
    email = clean_text(data.get('email'), MAX_EMAIL).lower()
    password = data.get('password', '')
    confirm = data.get('confirm_password', '')

    if not validate_username(username):
        return jsonify({'success': False,
                        'message': 'Username must be 3–20 chars, letters/numbers/underscore only'}), 400
    if not validate_email(email):
        return jsonify({'success': False, 'message': 'Invalid email address'}), 400
    if not validate_password(password):
        return jsonify({'success': False,
                        'message': 'Password must be 8+ chars and include a letter and a number'}), 400
    if password != confirm:
        return jsonify({'success': False, 'message': 'Passwords do not match'}), 400

    db = get_db()
    existing = db.execute(
        "SELECT id FROM users WHERE username = ? OR email = ?", (username, email)
    ).fetchone()
    if existing:
        return jsonify({'success': False, 'message': 'Username or email already in use'}), 400

    db.execute(
        "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
        (username, email, generate_password_hash(password)),
    )
    db.commit()
    return jsonify({'success': True, 'message': 'Account created. Please log in.'})


@app.route('/logout')
@app.route('/api/logout', methods=['GET', 'POST'])
def api_logout():
    session.clear()
    if request.path.startswith('/api/'):
        return jsonify({'success': True, 'message': 'Logged out'})
    return redirect(url_for('page_login'))


@app.route('/api/user')
def api_user():
    if 'user_id' not in session:
        return jsonify({'logged_in': False, 'csrf_token': ensure_csrf_token()})
    user = get_db().execute(
        "SELECT id, username, email, is_admin FROM users WHERE id = ?",
        (session['user_id'],),
    ).fetchone()
    if not user:
        session.clear()
        return jsonify({'logged_in': False, 'csrf_token': ensure_csrf_token()})
    return jsonify({
        'logged_in': True,
        'user': {
            'id': user['id'], 'username': user['username'],
            'email': user['email'], 'is_admin': bool(user['is_admin']),
        },
        'csrf_token': ensure_csrf_token(),
    })


# ────────────────────────────────────────────────────────────────────
# 7. Password reset
# ────────────────────────────────────────────────────────────────────
@app.route('/api/password-reset/request', methods=['POST'])
def api_password_reset_request():
    data = request.get_json(silent=True) or {}
    email = clean_text(data.get('email'), MAX_EMAIL).lower()
    if not validate_email(email):
        return jsonify({'success': False, 'message': 'Invalid email address'}), 400

    db = get_db()
    user = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    # Always respond success to avoid email enumeration
    if user:
        token = secrets.token_urlsafe(32)
        expires = (datetime.utcnow() + timedelta(hours=1)).isoformat()
        db.execute(
            "INSERT INTO password_resets (user_id, token, expires_at) VALUES (?, ?, ?)",
            (user['id'], token, expires),
        )
        db.commit()
        link = f"{APP_BASE_URL}/reset-password?token={token}"
        print(f"\n[PASSWORD RESET LINK] {link}\n", flush=True)
    return jsonify({'success': True,
                    'message': 'If that email exists, a reset link has been sent (see server console).'})


@app.route('/api/password-reset/confirm', methods=['POST'])
def api_password_reset_confirm():
    data = request.get_json(silent=True) or {}
    token = clean_text(data.get('token'), 200)
    new_password = data.get('new_password', '')
    if not token:
        return jsonify({'success': False, 'message': 'Token required'}), 400
    if not validate_password(new_password):
        return jsonify({'success': False,
                        'message': 'Password must be 8+ chars with a letter and a number'}), 400

    db = get_db()
    row = db.execute(
        "SELECT id, user_id, expires_at, used FROM password_resets WHERE token = ?",
        (token,),
    ).fetchone()
    if not row or row['used']:
        return jsonify({'success': False, 'message': 'Invalid or expired token'}), 400
    if datetime.fromisoformat(row['expires_at']) < datetime.utcnow():
        return jsonify({'success': False, 'message': 'Token expired'}), 400

    db.execute("UPDATE users SET password_hash = ? WHERE id = ?",
               (generate_password_hash(new_password), row['user_id']))
    db.execute("UPDATE password_resets SET used = 1 WHERE id = ?", (row['id'],))
    db.commit()
    return jsonify({'success': True, 'message': 'Password updated. Please log in.'})


# ────────────────────────────────────────────────────────────────────
# 8. Products API
# ────────────────────────────────────────────────────────────────────
SORT_MAP = {
    'price_asc': 'price ASC',
    'price_desc': 'price DESC',
    'title': 'title ASC',
    'newest': 'created_at DESC',
}


@app.route('/api/products')
def api_products():
    search = clean_text(request.args.get('search'), 100)
    category = clean_text(request.args.get('category'), MAX_CATEGORY)
    sort = request.args.get('sort', 'title')
    sort_sql = SORT_MAP.get(sort, 'title ASC')

    try:
        min_price = float(request.args.get('min_price')) if request.args.get('min_price') else None
        max_price = float(request.args.get('max_price')) if request.args.get('max_price') else None
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid price filter'}), 400

    where = []
    params = []
    if search:
        where.append("(LOWER(title) LIKE ? OR LOWER(description) LIKE ?)")
        like = f"%{search.lower()}%"
        params.extend([like, like])
    if category:
        where.append("category = ?")
        params.append(category)
    if min_price is not None:
        where.append("price >= ?")
        params.append(min_price)
    if max_price is not None:
        where.append("price <= ?")
        params.append(max_price)

    sql = "SELECT id, title, price, category, description, image, stock FROM products"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += f" ORDER BY {sort_sql}"

    rows = get_db().execute(sql, params).fetchall()
    return jsonify({'success': True, 'products': [dict(r) for r in rows]})


@app.route('/api/products/categories')
def api_product_categories():
    rows = get_db().execute(
        "SELECT DISTINCT category FROM products ORDER BY category"
    ).fetchall()
    return jsonify({'success': True, 'categories': [r['category'] for r in rows]})


@app.route('/api/products/<int:product_id>')
def api_product_detail(product_id):
    row = get_db().execute(
        "SELECT id, title, price, category, description, image, stock FROM products WHERE id = ?",
        (product_id,),
    ).fetchone()
    if not row:
        return jsonify({'success': False, 'message': 'Product not found'}), 404
    return jsonify({'success': True, 'product': dict(row)})


# ────────────────────────────────────────────────────────────────────
# 9. Cart API
# ────────────────────────────────────────────────────────────────────
def _cart_rows(user_id):
    return get_db().execute(
        """SELECT ci.id AS cart_item_id, ci.added_at,
                  p.id, p.title, p.price, p.category, p.image, p.stock
           FROM cart_items ci
           JOIN products p ON p.id = ci.product_id
           WHERE ci.user_id = ?
           ORDER BY ci.added_at DESC""",
        (user_id,),
    ).fetchall()


@app.route('/api/cart', methods=['GET'])
@login_required
def api_cart_get():
    rows = _cart_rows(session['user_id'])
    items = [dict(r) for r in rows]
    total = round(sum(r['price'] for r in rows), 2)
    return jsonify({'success': True, 'items': items, 'total': total, 'count': len(items)})


@app.route('/api/cart', methods=['POST'])
@login_required
@csrf_protect
def api_cart_add():
    data = request.get_json(silent=True) or {}
    try:
        product_id = int(data.get('product_id'))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'product_id required'}), 400

    db = get_db()
    p = db.execute("SELECT id, stock FROM products WHERE id = ?", (product_id,)).fetchone()
    if not p:
        return jsonify({'success': False, 'message': 'Product not found'}), 404
    if p['stock'] <= 0:
        return jsonify({'success': False, 'message': 'Out of stock'}), 400

    db.execute("INSERT INTO cart_items (user_id, product_id) VALUES (?, ?)",
               (session['user_id'], product_id))
    db.commit()
    return jsonify({'success': True, 'message': 'Added to cart'})


@app.route('/api/cart/<int:cart_item_id>', methods=['DELETE'])
@login_required
@csrf_protect
def api_cart_remove(cart_item_id):
    db = get_db()
    cur = db.execute(
        "DELETE FROM cart_items WHERE id = ? AND user_id = ?",
        (cart_item_id, session['user_id']),
    )
    db.commit()
    if cur.rowcount == 0:
        return jsonify({'success': False, 'message': 'Cart item not found'}), 404
    return jsonify({'success': True, 'message': 'Removed'})


@app.route('/api/cart', methods=['DELETE'])
@login_required
@csrf_protect
def api_cart_clear():
    db = get_db()
    db.execute("DELETE FROM cart_items WHERE user_id = ?", (session['user_id'],))
    db.commit()
    return jsonify({'success': True, 'message': 'Cart cleared'})


# ────────────────────────────────────────────────────────────────────
# 10. Orders + Stripe
# ────────────────────────────────────────────────────────────────────
def _create_pending_order(user_id, full_name, email, address):
    db = get_db()
    rows = _cart_rows(user_id)
    if not rows:
        return None, 'Cart is empty', 400
    # Stock check
    for r in rows:
        if r['stock'] <= 0:
            return None, f"'{r['title']}' is out of stock", 400
    total = round(sum(r['price'] for r in rows), 2)
    cur = db.execute(
        """INSERT INTO orders (user_id, total, status, full_name, email, shipping_address)
           VALUES (?, ?, 'pending', ?, ?, ?)""",
        (user_id, total, full_name, email, address),
    )
    order_id = cur.lastrowid
    for r in rows:
        db.execute(
            """INSERT INTO order_items
               (order_id, product_id, title_snapshot, price_at_purchase, quantity)
               VALUES (?, ?, ?, ?, 1)""",
            (order_id, r['id'], r['title'], r['price']),
        )
    db.commit()
    return order_id, None, None


@app.route('/api/checkout/create-session', methods=['POST'])
@login_required
@csrf_protect
def api_checkout_create_session():
    data = request.get_json(silent=True) or {}
    full_name = clean_text(data.get('full_name'), MAX_NAME)
    email = clean_text(data.get('email'), MAX_EMAIL).lower()
    address = clean_text(data.get('shipping_address'), MAX_ADDRESS)

    if not full_name or len(full_name) < 2:
        return jsonify({'success': False, 'message': 'Full name required'}), 400
    if not validate_email(email):
        return jsonify({'success': False, 'message': 'Valid email required'}), 400
    if not address or len(address) < 5:
        return jsonify({'success': False, 'message': 'Shipping address required'}), 400

    order_id, err, code = _create_pending_order(session['user_id'], full_name, email, address)
    if err:
        return jsonify({'success': False, 'message': err}), code

    if not STRIPE_AVAILABLE or not stripe.api_key or not stripe.api_key.startswith('sk_'):
        return jsonify({
            'success': False,
            'message': 'Stripe is not configured. Set STRIPE_SECRET_KEY in .env (test mode).',
            'order_id': order_id,
        }), 503

    db = get_db()
    items = db.execute(
        "SELECT title_snapshot, price_at_purchase, quantity "
        "FROM order_items WHERE order_id = ?", (order_id,)
    ).fetchall()
    line_items = [{
        'price_data': {
            'currency': 'usd',
            'product_data': {'name': it['title_snapshot']},
            'unit_amount': int(round(it['price_at_purchase'] * 100)),
        },
        'quantity': it['quantity'],
    } for it in items]

    try:
        sess = stripe.checkout.Session.create(
            mode='payment',
            payment_method_types=['card'],
            line_items=line_items,
            customer_email=email,
            success_url=f"{APP_BASE_URL}/thankyou?order_id={order_id}&stripe_session={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{APP_BASE_URL}/checkout?cancelled=1",
            metadata={'order_id': str(order_id), 'user_id': str(session['user_id'])},
        )
    except Exception as e:
        return jsonify({'success': False, 'message': f'Stripe error: {e}'}), 502

    db.execute("UPDATE orders SET stripe_session_id = ? WHERE id = ?", (sess.id, order_id))
    db.commit()
    return jsonify({'success': True, 'order_id': order_id, 'checkout_url': sess.url,
                    'session_id': sess.id})


def _mark_order_paid(order_id):
    db = get_db()
    o = db.execute("SELECT user_id, status FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not o or o['status'] == 'paid':
        return
    db.execute("UPDATE orders SET status = 'paid' WHERE id = ?", (order_id,))
    # Decrement stock for purchased items
    items = db.execute(
        "SELECT product_id, quantity FROM order_items WHERE order_id = ?", (order_id,)
    ).fetchall()
    for it in items:
        db.execute("UPDATE products SET stock = MAX(stock - ?, 0) WHERE id = ?",
                   (it['quantity'], it['product_id']))
    # Clear the user's cart
    db.execute("DELETE FROM cart_items WHERE user_id = ?", (o['user_id'],))
    db.commit()


@app.route('/api/webhook/stripe', methods=['POST'])
def api_webhook_stripe():
    if not STRIPE_AVAILABLE:
        return jsonify({'success': False, 'message': 'Stripe not installed'}), 503
    payload = request.get_data(as_text=False)
    sig_header = request.headers.get('Stripe-Signature', '')
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        return jsonify({'success': False, 'message': f'Webhook signature invalid: {e}'}), 400

    if event['type'] == 'checkout.session.completed':
        meta = event['data']['object'].get('metadata') or {}
        order_id = meta.get('order_id')
        if order_id:
            _mark_order_paid(int(order_id))
    return jsonify({'success': True})


@app.route('/api/checkout/confirm/<int:order_id>', methods=['POST'])
@login_required
@csrf_protect
def api_checkout_confirm(order_id):
    """
    Fallback confirmation hit by the success URL when no webhook listener is configured
    (e.g., during local grading). Verifies with Stripe before marking paid.
    """
    db = get_db()
    o = db.execute(
        "SELECT id, user_id, stripe_session_id, status FROM orders WHERE id = ?",
        (order_id,),
    ).fetchone()
    if not o or o['user_id'] != session['user_id']:
        return jsonify({'success': False, 'message': 'Order not found'}), 404
    if o['status'] == 'paid':
        return jsonify({'success': True, 'already_paid': True})

    if not STRIPE_AVAILABLE or not stripe.api_key.startswith('sk_'):
        return jsonify({'success': False, 'message': 'Stripe not configured'}), 503
    try:
        sess = stripe.checkout.Session.retrieve(o['stripe_session_id'])
    except Exception as e:
        return jsonify({'success': False, 'message': f'Stripe error: {e}'}), 502
    if sess.payment_status == 'paid':
        _mark_order_paid(order_id)
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'Payment not completed'}), 400


@app.route('/api/orders')
@login_required
def api_orders_list():
    rows = get_db().execute(
        """SELECT id, total, status, full_name, email, shipping_address, created_at
           FROM orders WHERE user_id = ? ORDER BY created_at DESC""",
        (session['user_id'],),
    ).fetchall()
    return jsonify({'success': True, 'orders': [dict(r) for r in rows]})


@app.route('/api/orders/<int:order_id>')
@login_required
def api_order_detail(order_id):
    db = get_db()
    o = db.execute(
        """SELECT id, user_id, total, status, full_name, email, shipping_address, created_at
           FROM orders WHERE id = ?""", (order_id,)
    ).fetchone()
    if not o:
        return jsonify({'success': False, 'message': 'Order not found'}), 404
    is_owner = o['user_id'] == session['user_id']
    is_admin_session = session.get('is_admin', False)
    if not (is_owner or is_admin_session):
        return jsonify({'success': False, 'message': 'Forbidden'}), 403
    items = db.execute(
        """SELECT product_id, title_snapshot, price_at_purchase, quantity
           FROM order_items WHERE order_id = ?""", (order_id,)
    ).fetchall()
    out = dict(o)
    out['items'] = [dict(i) for i in items]
    return jsonify({'success': True, 'order': out})


# ────────────────────────────────────────────────────────────────────
# 11. Admin API
# ────────────────────────────────────────────────────────────────────
@app.route('/api/admin/stats')
@admin_required
def api_admin_stats():
    db = get_db()
    stats = {
        'users': db.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        'products': db.execute("SELECT COUNT(*) FROM products").fetchone()[0],
        'orders': db.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
        'paid_orders': db.execute(
            "SELECT COUNT(*) FROM orders WHERE status IN ('paid','shipped','delivered')").fetchone()[0],
        'revenue': db.execute(
            "SELECT COALESCE(SUM(total),0) FROM orders WHERE status IN ('paid','shipped','delivered')"
        ).fetchone()[0],
        'low_stock': [dict(r) for r in db.execute(
            "SELECT id, title, stock FROM products WHERE stock < 10 ORDER BY stock ASC"
        ).fetchall()],
        'recent_orders': [dict(r) for r in db.execute(
            "SELECT id, total, status, full_name, created_at FROM orders "
            "ORDER BY created_at DESC LIMIT 5"
        ).fetchall()],
    }
    return jsonify({'success': True, 'stats': stats})


@app.route('/api/admin/products', methods=['GET'])
@admin_required
def api_admin_products_list():
    rows = get_db().execute(
        "SELECT id, title, price, category, description, image, stock, created_at "
        "FROM products ORDER BY id"
    ).fetchall()
    return jsonify({'success': True, 'products': [dict(r) for r in rows]})


@app.route('/api/admin/products', methods=['POST'])
@admin_required
@csrf_protect
def api_admin_products_create():
    d = request.get_json(silent=True) or {}
    title = clean_text(d.get('title'), MAX_TITLE)
    category = clean_text(d.get('category'), MAX_CATEGORY)
    description = clean_text(d.get('description'), MAX_DESC)
    image = clean_text(d.get('image'), MAX_IMAGE)
    try:
        price = float(d.get('price'))
        stock = int(d.get('stock', 100))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Invalid price or stock'}), 400
    if not title or not category or price < 0 or stock < 0:
        return jsonify({'success': False, 'message': 'Invalid product fields'}), 400
    cur = get_db().execute(
        "INSERT INTO products (title, price, category, description, image, stock) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (title, price, category, description, image, stock),
    )
    get_db().commit()
    return jsonify({'success': True, 'id': cur.lastrowid})


@app.route('/api/admin/products/<int:pid>', methods=['PUT'])
@admin_required
@csrf_protect
def api_admin_products_update(pid):
    d = request.get_json(silent=True) or {}
    fields, params = [], []
    if 'title' in d:
        fields.append("title = ?"); params.append(clean_text(d['title'], MAX_TITLE))
    if 'category' in d:
        fields.append("category = ?"); params.append(clean_text(d['category'], MAX_CATEGORY))
    if 'description' in d:
        fields.append("description = ?"); params.append(clean_text(d['description'], MAX_DESC))
    if 'image' in d:
        fields.append("image = ?"); params.append(clean_text(d['image'], MAX_IMAGE))
    if 'price' in d:
        try:
            fields.append("price = ?"); params.append(float(d['price']))
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': 'Invalid price'}), 400
    if 'stock' in d:
        try:
            fields.append("stock = ?"); params.append(int(d['stock']))
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': 'Invalid stock'}), 400
    if not fields:
        return jsonify({'success': False, 'message': 'No fields to update'}), 400
    params.append(pid)
    cur = get_db().execute(f"UPDATE products SET {', '.join(fields)} WHERE id = ?", params)
    get_db().commit()
    if cur.rowcount == 0:
        return jsonify({'success': False, 'message': 'Product not found'}), 404
    return jsonify({'success': True})


@app.route('/api/admin/products/<int:pid>', methods=['DELETE'])
@admin_required
@csrf_protect
def api_admin_products_delete(pid):
    cur = get_db().execute("DELETE FROM products WHERE id = ?", (pid,))
    get_db().commit()
    if cur.rowcount == 0:
        return jsonify({'success': False, 'message': 'Product not found'}), 404
    return jsonify({'success': True})


@app.route('/api/admin/orders')
@admin_required
def api_admin_orders_list():
    status = clean_text(request.args.get('status'), 20)
    sql = ("SELECT o.id, o.user_id, u.username, o.total, o.status, "
           "o.full_name, o.email, o.created_at "
           "FROM orders o JOIN users u ON u.id = o.user_id")
    params = []
    if status:
        sql += " WHERE o.status = ?"; params.append(status)
    sql += " ORDER BY o.created_at DESC"
    rows = get_db().execute(sql, params).fetchall()
    return jsonify({'success': True, 'orders': [dict(r) for r in rows]})


@app.route('/api/admin/orders/<int:order_id>', methods=['PUT'])
@admin_required
@csrf_protect
def api_admin_order_update(order_id):
    d = request.get_json(silent=True) or {}
    status = clean_text(d.get('status'), 20)
    if status not in ('pending', 'paid', 'shipped', 'delivered', 'cancelled'):
        return jsonify({'success': False, 'message': 'Invalid status'}), 400
    cur = get_db().execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
    get_db().commit()
    if cur.rowcount == 0:
        return jsonify({'success': False, 'message': 'Order not found'}), 404
    return jsonify({'success': True})


@app.route('/api/admin/users')
@admin_required
def api_admin_users_list():
    rows = get_db().execute(
        "SELECT id, username, email, is_admin, is_active, created_at FROM users ORDER BY id"
    ).fetchall()
    return jsonify({'success': True, 'users': [dict(r) for r in rows]})


@app.route('/api/admin/users/<int:uid>', methods=['PUT'])
@admin_required
@csrf_protect
def api_admin_user_update(uid):
    d = request.get_json(silent=True) or {}
    fields, params = [], []
    if 'is_admin' in d:
        fields.append("is_admin = ?"); params.append(1 if d['is_admin'] else 0)
    if 'is_active' in d:
        fields.append("is_active = ?"); params.append(1 if d['is_active'] else 0)
    if not fields:
        return jsonify({'success': False, 'message': 'No fields to update'}), 400
    if uid == session['user_id'] and 'is_admin' in d and not d['is_admin']:
        return jsonify({'success': False, 'message': 'Cannot demote yourself'}), 400
    params.append(uid)
    cur = get_db().execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", params)
    get_db().commit()
    if cur.rowcount == 0:
        return jsonify({'success': False, 'message': 'User not found'}), 404
    return jsonify({'success': True})


# ────────────────────────────────────────────────────────────────────
# 12. Bootstrap
# ────────────────────────────────────────────────────────────────────
@app.errorhandler(404)
def not_found(_e):
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'message': 'Not found'}), 404
    return redirect(url_for('root'))


@app.errorhandler(413)
def too_large(_e):
    return jsonify({'success': False, 'message': 'Payload too large'}), 413


if __name__ == '__main__':
    init_db_if_missing()
    host = os.environ.get('FLASK_HOST', '127.0.0.1')
    port = int(os.environ.get('FLASK_PORT', '5000'))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() in ('1', 'true', 'yes')
    print(f"Nexus Games starting on http://{host}:{port}")
    print(f"Login at http://{host}:{port}/login")
    app.run(host=host, port=port, debug=debug)
