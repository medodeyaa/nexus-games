# Nexus Games &mdash; Phase 2

A full-stack digital game store built for **Selected Topics in Software Engineering** (Phase 2).
Phase 1 delivered the static front end; Phase 2 (this) adds the full backend, relational data
model, Stripe payments, admin panel, password reset, security hardening, automated tests,
Postman collection, and deployment artifacts.

> Team members: _<fill in here>_

---

## Tech stack

| Layer        | Choice                                            |
|--------------|---------------------------------------------------|
| Backend      | Python 3.11 + Flask 3                             |
| Database     | SQLite (relational, 6 tables, foreign keys ON)    |
| Auth         | Flask sessions + `werkzeug.security` hashing      |
| Payments     | Stripe Checkout (test mode)                       |
| Rate limit   | Flask-Limiter (in-memory)                         |
| Front-end    | Vanilla HTML / CSS / JS (no frameworks)           |
| Tests        | pytest + Flask test client                        |
| WSGI         | gunicorn                                          |
| Deploy       | Render (`render.yaml`) or Railway (`railway.toml`)|

---

## Project layout

```
frontend/
├── app.py                  # Single-file Flask app (sections marked inside)
├── schema.sql              # Relational schema
├── seed.py                 # Loads schema + seeds 8 games + admin/demo users
├── requirements.txt
├── Procfile, runtime.txt, render.yaml, railway.toml
├── postman_collection.json
├── .env, .env.example, .gitignore
├── static/
│   ├── styles.css          # Single global stylesheet (no inline styles)
│   ├── main.js             # Front-end glue (toast, CSRF, fetch wrapper, cart render)
│   └── photos/*.jpg|jfif
├── templates/
│   ├── _nav.html, _footer.html        # Shared partials
│   ├── index.html, login.html, register.html, cart.html, checkout.html,
│   │   product.html, thankyou.html, orders.html,
│   │   forgot_password.html, reset_password.html
│   └── admin/
│       ├── _sidebar.html
│       ├── dashboard.html, products.html, orders.html, users.html
└── tests/
    ├── conftest.py
    ├── test_auth.py, test_products.py, test_cart.py,
    │   test_orders.py, test_admin.py, test_security.py
```

---

## Local setup

```bash
# 1. Create a venv
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy env file and edit values
copy .env.example .env          # Windows
# cp .env.example .env          # macOS/Linux

# 4. Initialize the database (creates schema + seeds products + admin user)
python seed.py

# 5. Run the app
python app.py
# or:  flask --app app run --debug
```

Open <http://localhost:5000/>. You will be redirected to `/login`.

### Default credentials (from `.env.example`)

| Role  | Username | Password   |
|-------|----------|------------|
| Admin | `admin`  | `Admin1234` |
| User  | `demo`   | `Demo1234`  |

Change `ADMIN_SEED_PASSWORD` in `.env` before deploying.

---

## Stripe setup (test mode)

1. Get test keys from <https://dashboard.stripe.com/test/apikeys>.
2. Put them in `.env`:
   ```
   STRIPE_SECRET_KEY=sk_test_...
   STRIPE_PUBLISHABLE_KEY=pk_test_...
   STRIPE_WEBHOOK_SECRET=whsec_...
   APP_BASE_URL=http://localhost:5000
   ```
3. (Optional) Use the Stripe CLI to forward webhooks locally:
   ```
   stripe listen --forward-to http://localhost:5000/api/webhook/stripe
   ```
4. Use test card `4242 4242 4242 4242`, any future expiry, any CVC.

If webhooks aren't configured, the `/thankyou` page also calls
`POST /api/checkout/confirm/<order_id>` which verifies the session with Stripe and
marks the order paid &mdash; so demos work without a public webhook URL.

---

## Database schema

Six tables with the relationships required by the rubric.

```
users ──< orders ──< order_items >── products
   │                                    ▲
   ├──< cart_items >─────────────────────┘
   └──< password_resets
```

* **users**: `id, username, email, password_hash, is_admin, is_active, created_at`
* **products**: `id, title, price, category, description, image, stock, created_at`
* **cart_items**: `id, user_id FK, product_id FK, added_at`
* **orders**: `id, user_id FK, total, status, full_name, email, shipping_address,
  stripe_session_id, created_at`
* **order_items**: `id, order_id FK, product_id FK, title_snapshot,
  price_at_purchase, quantity`
* **password_resets**: `id, user_id FK, token, expires_at, used, created_at`

Foreign keys are enforced (`PRAGMA foreign_keys=ON`). Order status is constrained to
`pending|paid|shipped|delivered|cancelled` via a `CHECK` constraint. Indexes exist on
`cart_items(user_id)`, `orders(user_id)`, `order_items(order_id)`,
`products(category)`, and `password_resets(token)`.

---

## API reference

All endpoints return JSON. State-changing endpoints (POST/PUT/DELETE under `/api/`,
except `/api/login`, `/api/register`, `/api/password-reset/*` and the Stripe webhook)
require a CSRF token in the `X-CSRF-Token` header. Fetch it from
`GET /api/user` (returned as `csrf_token`).

### Auth

| Method | Path | Body | Auth | Notes |
|--------|------|------|------|-------|
| POST   | `/api/register` | `{ username, email, password, confirm_password }` | public | Username 3–20 alnum/underscore; password 8+ with letter & number |
| POST   | `/api/login`    | `{ username, password }` | public | Rate-limited: 5/15min per IP. `username` field accepts email too. |
| GET    | `/api/logout`   | — | any | Clears the session |
| GET    | `/api/user`     | — | any | Returns `{logged_in, user?, csrf_token}` |

### Password reset

| Method | Path | Body |
|--------|------|------|
| POST   | `/api/password-reset/request` | `{ email }` |
| POST   | `/api/password-reset/confirm` | `{ token, new_password }` |

Reset links are printed to the server console with the marker
`[PASSWORD RESET LINK] http://localhost:5000/reset-password?token=...`.
The grader follows that link to complete the flow.

### Products (public)

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/products` | Query: `search`, `category`, `min_price`, `max_price`, `sort=price_asc\|price_desc\|title\|newest` |
| GET | `/api/products/categories` | Distinct categories |
| GET | `/api/products/<id>` | Single product |

### Cart (auth)

| Method | Path | Body |
|--------|------|------|
| GET    | `/api/cart` | — |
| POST   | `/api/cart` | `{ product_id }` (rejected when `stock <= 0`) |
| DELETE | `/api/cart/<cart_item_id>` | — |
| DELETE | `/api/cart` | Clear cart |

### Checkout / Orders (auth)

| Method | Path | Body |
|--------|------|------|
| POST | `/api/checkout/create-session` | `{ full_name, email, shipping_address }` &mdash; creates pending order, returns Stripe Checkout URL |
| POST | `/api/checkout/confirm/<order_id>` | Verifies the Stripe session and marks paid (fallback when no webhook) |
| POST | `/api/webhook/stripe` | Stripe signs this. No CSRF. Verified via `STRIPE_WEBHOOK_SECRET`. |
| GET  | `/api/orders` | List own orders |
| GET  | `/api/orders/<id>` | Owner or admin only |

### Admin (auth + `is_admin`)

| Method | Path |
|--------|------|
| GET    | `/api/admin/stats` |
| GET POST | `/api/admin/products` |
| PUT DELETE | `/api/admin/products/<id>` |
| GET    | `/api/admin/orders` (`?status=...`) |
| PUT    | `/api/admin/orders/<id>` (body `{status}`) |
| GET    | `/api/admin/users` |
| PUT    | `/api/admin/users/<id>` (body `{is_admin?, is_active?}`) |

---

## Security

The PDF rubric calls out **"SQL Injection protection and secure input validation"**.

* **All SQL is parameterized** (`?` placeholders). Tested by `test_sql_injection_*`.
* **Input validation** on every endpoint:
  * Email regex (RFC-ish), max 120 chars
  * Username 3–20 chars, `^[A-Za-z0-9_]{3,20}$`
  * Password 8+ chars, must contain a letter AND a digit
  * Length caps on every text field (`MAX_NAME`, `MAX_ADDRESS`, etc.)
  * Numeric fields cast and bounds-checked
* **CSRF protection** via a per-session token; `X-CSRF-Token` required on every
  state-changing API call (except login/register and the Stripe webhook which has its
  own signature check).
* **Secure session cookies**: `HttpOnly=True`, `SameSite=Lax`,
  `Secure=True` in production (set via `SESSION_COOKIE_SECURE=1` env var).
* **Rate-limiting** on `/api/login` &mdash; 5 attempts per 15 minutes per IP.
* **Password hashing**: `werkzeug.security.generate_password_hash` (PBKDF2-SHA256).
* **Stock check** at cart-add and at checkout.
* **Server-recomputed totals** at checkout &mdash; the server never trusts a
  price coming from the client.
* **Order isolation**: a user can only see their own orders; admins can see all.
* **Security headers**: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`.
* **Stripe webhook signature verification** with `STRIPE_WEBHOOK_SECRET`.

---

## Running the tests

```bash
pytest -v
```

42 tests covering auth, products, cart, orders, admin, and security
(SQLi, XSS-rejection, weak passwords, CSRF, session cookie flags, password reset).
Each test gets a fresh in-memory schema + minimal seed.

```bash
# With coverage
pip install pytest-cov
pytest --cov=app --cov-report=term-missing
```

---

## Postman

Import `postman_collection.json` in Postman. The collection has the
`{{base_url}}` variable (defaults to `http://localhost:5000`) and a
`{{csrf_token}}` variable that the "Login" requests auto-populate via a test
script. Cookies are kept by Postman's cookie jar automatically, so you can run
the requests in order: **Login → Add to cart → Checkout → Confirm → Get order**.

---

## Deployment (Render)

1. Push the repo to GitHub.
2. In Render, **New → Blueprint**, point at the repo. It will read `render.yaml`.
3. Set the secret env vars in the dashboard:
   `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`,
   `ADMIN_SEED_PASSWORD`, `APP_BASE_URL` (the Render URL).
4. The 1 GB disk mounts at `/var/data` so SQLite survives restarts;
   `DATABASE_PATH` is set to `/var/data/nexus_games.db`.
5. The build step runs `pip install -r requirements.txt && python seed.py`.
6. Configure the Stripe webhook in the Stripe dashboard to point at
   `https://<your-app>.onrender.com/api/webhook/stripe`.

A `railway.toml` is also included for Railway deployments.

---

## How the password reset link is surfaced

Real email delivery is intentionally out of scope. When a user posts to
`/api/password-reset/request`, the backend creates a token row in
`password_resets`, then **prints the link to the server console** with the
marker `[PASSWORD RESET LINK]`. Example log line:

```
[PASSWORD RESET LINK] http://localhost:5000/reset-password?token=abc123…
```

The grader copies this link into the browser, sets a new password, and logs in.

---

## What changed since Phase 1

* Hardcoded `games` array in `main.js` replaced by `GET /api/products`.
* `localStorage` cart replaced by server-side `cart_items` table.
* Single `users` table replaced by a 6-table relational schema.
* Fake card inputs on the checkout page replaced by Stripe Checkout redirect.
* All inline styles moved into `static/styles.css`.
* `assasin` typo fixed to `assassin` in the AC Mirage description.
* Removed broken `hero-bg.jpg` reference and orphan extensionless `checkout` file.
* Added: admin panel, password reset, security hardening, tests, Postman,
  deployment files, README + ARCHITECTURE docs.
