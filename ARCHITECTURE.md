# Nexus Games &mdash; Architecture

This document is a short reference for the grading presentation. It explains
the data model, request flow, and the reasoning behind the major security
choices.

---

## 1. Data model

Six normalized tables with foreign-key constraints. SQLite enforces
`PRAGMA foreign_keys = ON` in every connection (`get_db()`).

```
┌──────────────┐         ┌──────────────┐         ┌──────────────┐
│    users     │ 1     ∞ │    orders    │ 1     ∞ │ order_items  │
│──────────────│─────────│──────────────│─────────│──────────────│
│ id (PK)      │         │ id (PK)      │         │ id (PK)      │
│ username U   │         │ user_id FK   │         │ order_id FK  │
│ email U      │         │ total        │         │ product_id FK│
│ password_hash│         │ status CHK   │         │ title_snapshot│
│ is_admin     │         │ full_name    │         │ price_at_purchase│
│ is_active    │         │ email        │         │ quantity     │
│ created_at   │         │ shipping_addr│         └──────┬───────┘
└──────┬───────┘         │ stripe_sess  │                │
       │ 1               │ created_at   │                │
       │                 └──────────────┘                │
       │ ∞                                               │
┌──────▼───────┐         ┌──────────────┐                │
│ cart_items   │ ∞     1 │  products    │◄───────────────┘
│──────────────│─────────│──────────────│
│ id (PK)      │         │ id (PK)      │
│ user_id FK   │         │ title        │
│ product_id FK│         │ price CHK≥0  │
│ added_at     │         │ category IDX │
└──────────────┘         │ description  │
                         │ image        │
       ┌─────────────────│ stock CHK≥0  │
       │                 │ created_at   │
       │ ∞               └──────────────┘
┌──────▼─────────┐
│password_resets │
│────────────────│
│ id (PK)        │
│ user_id FK     │
│ token U IDX    │
│ expires_at     │
│ used           │
│ created_at     │
└────────────────┘
```

**Relationships used by the rubric**

* one-to-many: `users → orders`, `orders → order_items`, `users → cart_items`,
  `users → password_resets`
* many-to-one: `cart_items → products`, `order_items → products`

**Snapshotting**: `order_items.title_snapshot` and `price_at_purchase` capture
the product state at purchase time, so editing or deleting a product later does
not alter historical orders.

---

## 2. Request flow

### 2.1. Browsing the store

```
Browser  →  GET /home  →  Flask page route  →  templates/index.html
Browser  →  GET /api/products?category=RPG  →  parameterized SQL  →  JSON
Browser  →  renderProductGrid()
```

Filtering, search, and sort are **all server-side**. The front end debounces
search input by 300 ms and never holds a full product list locally.

### 2.2. Adding to cart

```
Browser  →  POST /api/cart { product_id } + X-CSRF-Token
Server   →  validate session, look up product, check stock > 0
Server   →  INSERT INTO cart_items …
Server   →  200 {success:true}
Browser  →  toast("Added to cart"), refresh cart-count badge
```

### 2.3. Checkout

```
Browser  →  POST /api/checkout/create-session { full_name, email, address } + CSRF
Server   →  read cart_items for user_id
Server   →  recompute total from products.price  (NEVER trusting the client)
Server   →  INSERT orders (status='pending')
Server   →  INSERT order_items with title_snapshot + price_at_purchase
Server   →  stripe.checkout.Session.create(line_items=...)
Server   →  UPDATE orders SET stripe_session_id = ...
Server   →  200 { checkout_url, order_id }
Browser  →  window.location = checkout_url   (redirect to Stripe Checkout)
…user pays on Stripe's hosted page…
Stripe   →  POST /api/webhook/stripe  (signed payload)
Server   →  verify signature → mark order paid + decrement stock + clear cart
Stripe   →  redirect → /thankyou?order_id=…&stripe_session=…
Browser  →  POST /api/checkout/confirm/<order_id>  (fallback if no webhook)
Browser  →  GET /api/orders/<id>  →  render the receipt
```

The fallback `confirm` endpoint matters for the local-grading scenario where
the webhook URL isn't reachable from Stripe's servers. It re-fetches the
checkout session from Stripe and updates the order from `pending → paid` only
if Stripe reports `payment_status == 'paid'` &mdash; so a malicious client cannot
fake a payment by hitting that endpoint.

---

## 3. Front-end glue

A single 250-line `static/main.js` with the `NEXUS` namespace exposes:

* `NEXUS.api(path, {method, body})` &mdash; injects CSRF header automatically
* `NEXUS.checkAuth()` &mdash; called on every protected page; redirects to login if anon
* `NEXUS.toast(msg, type)` &mdash; replaces `alert()` calls
* `NEXUS.setupStoreFilters()` &mdash; debounced search + category/price/sort
* `NEXUS.refreshCartCount()`, `NEXUS.renderCartPage()`, `NEXUS.addToCart()`, etc.

Pages opt into the pieces they need at `DOMContentLoaded`. No build step,
no bundlers, no framework dependencies.

---

## 4. Security choices

| Risk | Mitigation |
|------|-----------|
| SQL injection | 100% parameterized queries. Verified by `test_sql_injection_in_login_safe` and `test_sql_injection_in_search_safe`. |
| Weak passwords | Regex enforces 8+ chars with a letter and a digit. |
| Brute-force login | Flask-Limiter caps `/api/login` at 5 attempts per 15 minutes per IP. |
| Session hijacking | `HttpOnly` cookie (no JS access), `SameSite=Lax`, `Secure` in prod. |
| CSRF | Per-session token, required header on every state-changing API call. Tested. |
| XSS | Front end uses `escapeHtml()` everywhere user data is inserted into HTML. Username regex blocks `<`/`>` outright. |
| Tampered prices | Server recomputes the order total from `products.price` at checkout. The client cannot influence it. |
| Stripe spoofing | `stripe.Webhook.construct_event` verifies the signature with `STRIPE_WEBHOOK_SECRET`. |
| Email enumeration | `/api/password-reset/request` always returns the same success message. |
| Privilege escalation | `@admin_required` re-reads `is_admin` from the DB &mdash; not just the session &mdash; so a demoted admin's existing session loses access immediately. |
| Self-demotion lockout | An admin cannot revoke their own admin flag. |
| Out-of-stock purchase | Stock checked on cart-add **and** at order creation. |

---

## 5. Trade-offs taken

* **Single-file `app.py`** instead of blueprints. The project is small enough
  that a 700-line file with clearly labelled sections is easier to grade than
  a five-package layout. (Section headers in `app.py` mirror the rubric.)
* **SQLite over MySQL/Postgres**. The PDF accepts MySQL; SQLite is
  zero-config and the rubric does not penalize it. Foreign keys are turned on
  per connection so referential integrity still holds.
* **In-memory rate limiter**. Good enough for a single-process demo; for a
  multi-worker prod deploy you'd switch the `storage_uri` to Redis.
* **Cart = one row per item, quantity always 1**. Matches the original
  Phase-1 design (each "Add" appended an item). Adding a quantity column
  would have been a wider change for no grading benefit.

---

## 6. Deployment topology (Render)

```
Internet  →  Render load balancer  →  gunicorn (2 workers)  →  Flask app
                                                                    │
                                                                    ▼
                                                       /var/data/nexus_games.db
                                                       (1 GB persistent disk)

Stripe webhook  →  https://<app>.onrender.com/api/webhook/stripe
                   (verified by STRIPE_WEBHOOK_SECRET)
```

* Build step: `pip install -r requirements.txt && python seed.py`
  (seed is idempotent enough to run once on first deploy &mdash; subsequent
  rebuilds skip it because the schema's `DROP TABLE IF EXISTS` would wipe
  data; for production-style deploys remove `python seed.py` from the build
  command after first run).
* Start step: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 60`.
* Secrets injected via Render dashboard, **never committed**.

---

## 7. What is intentionally out of scope

* Real email delivery (console output instead)
* OAuth / social login
* React/Vue/Next.js rewrite
* Multi-currency / i18n
* Quantity-on-cart and product variants
