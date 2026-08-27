# ☁️ Cloud Deals — Full Telegram E-Commerce Bot

A production-ready Telegram digital storefront with cryptocurrency checkout, concurrency-safe inventory reservation, server-side webhook payment verification, automated product delivery, admin panel, support ticket system, and referral tracking.

---

## 🌟 Key Features

* **Storefront Experience:** Dynamic categories, product browsing, live stock counts, and smooth inline keyboard navigation.
* **External Crypto Checkout:** Compliant with Telegram's external checkout guidelines for non-Stars digital commerce. Integrates with NOWPayments hosted checkout (USDT, BTC, ETH, LTC, TON, and 150+ cryptocurrencies).
* **Cryptographic IPN Verification:** Webhooks verified server-side using HMAC-SHA512 with sorted JSON payloads. No client redirects or screenshots are ever trusted.
* **Concurrency-Safe Inventory:** Row-level locking (`SELECT ... FOR UPDATE`) prevents double-spending or over-selling under high concurrency.
* **Automated Product Delivery:** Instant delivery of digital credentials/codes via Telegram once payment reaches confirmed/finished status.
* **Idempotent Webhooks:** Duplicate IPN notifications are safely ignored without re-fulfilling orders or double-crediting balances.
* **Payment Expiration & Auto-Release:** Unpaid reservations automatically expire after a configurable timeout (default 30 min) and release inventory back to the store.
* **Account & Top-up:** Real balance ledger backed by crypto invoices for stored credit purchases.
* **Comprehensive Admin Suite:** Direct Telegram panel (`/admin`) for product CRUD, inventory addition, order inspection, manual fulfillment, user management, statistics, broadcast with rate limits, and maintenance mode toggle.
* **Customer Support & FAQs:** In-bot ticket system with admin reply flow and database-backed dynamic FAQs.

---

## 📂 Project Structure

```text
telegram-shop-bot/
├── app/
│   ├── __init__.py
│   ├── config.py                 # Pydantic Settings configuration & validation
│   ├── logging_config.py         # Structured logging with sensitive data redaction
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py               # FastAPI application factory & health endpoints
│   │   └── webhooks/
│   │       ├── __init__.py
│   │       └── crypto.py         # NOWPayments IPN webhook receiver & verification
│   ├── bot/
│   │   ├── __init__.py
│   │   ├── bot.py                # Telegram bot builder & shared instance registry
│   │   ├── keyboards/
│   │   │   ├── __init__.py
│   │   │   ├── main.py           # Main navigation & back keyboards
│   │   │   ├── products.py       # Categories & product detail keyboards
│   │   │   ├── orders.py         # Crypto payment button & order list keyboards
│   │   │   └── admin.py          # Complete admin panel keyboards
│   │   └── handlers/
│   │       ├── __init__.py
│   │       ├── start.py          # /start, /help, maintenance filter, referral linking
│   │       ├── products.py       # Category browsing, product view, buy order flow
│   │       ├── orders.py         # Payment status check, cancellation, order history
│   │       ├── profile.py        # Profile details, balance top-up, referral links
│   │       ├── support.py        # Ticket creation conversation, my tickets, FAQs
│   │       └── admin.py          # Full admin panel conversations & management
│   ├── database/
│   │   ├── __init__.py
│   │   ├── database.py           # Async SQLAlchemy engine & sessionmaker (SQLite/PG)
│   │   ├── models.py             # Declarative ORM models (User, Order, Inventory, etc.)
│   │   └── repositories/
│   │       ├── __init__.py
│   │       ├── user_repo.py      # User CRUD & balance queries
│   │       ├── category_repo.py  # Category management
│   │       ├── product_repo.py   # Product queries & stock aggregation
│   │       ├── inventory_repo.py # Atomic stock reservation & release
│   │       ├── order_repo.py     # Order lifecycle & public ID generation
│   │       ├── payment_repo.py   # Provider payment tracking & idempotency lookup
│   │       ├── topup_repo.py     # Account credit requests
│   │       ├── support_repo.py   # Ticket logging & admin responses
│   │       └── settings_repo.py  # Store settings & FAQ repository
│   ├── payments/
│   │   ├── __init__.py
│   │   ├── base.py               # Abstract PaymentProvider interface
│   │   └── nowpayments.py        # NOWPayments API v1 integration & HMAC-SHA512
│   └── services/
│       ├── __init__.py
│       ├── user_service.py       # Profile & referral logic
│       ├── product_service.py    # Product/category business layer
│       ├── inventory_service.py  # Stock management & reservation timeouts
│       ├── order_service.py      # Order creation, cancellation, fulfillment
│       ├── payment_service.py    # Payment invoice creation & webhook routing
│       ├── delivery_service.py   # Telegram digital item delivery
│       └── topup_service.py      # Crypto balance credit handling
├── migrations/                   # Alembic database migration scripts
├── scripts/
│   ├── backup.sh                 # Automated SQLite database backup script
│   └── seed.py                   # Initial catalog & demo items seed script
├── tests/
│   ├── conftest.py               # In-memory test database & async fixtures
│   ├── test_models.py            # User, Category, Product model tests
│   ├── test_inventory.py         # Reservation, release, and stock limits
│   ├── test_orders.py            # Lifecycle, duplicate delivery prevention
│   └── test_payments.py          # Webhook HMAC verification & idempotency
├── .env.example                  # Environment variable reference
├── .gitignore
├── alembic.ini
├── Dockerfile                    # Multi-stage production container
├── docker-compose.yml            # Container stack definition
├── requirements.txt              # Pinned Python package dependencies
├── run.py                        # Unified async application runner (Bot + API)
└── bot.py                        # Compatibility entry point
```

---

## ⚙️ Technology Stack

* **Language:** Python 3.12+
* **Telegram Framework:** `python-telegram-bot` 22.8 (async/await)
* **Web Framework:** `FastAPI` 0.141 & `Uvicorn` 0.52
* **ORM & Database:** `SQLAlchemy` 2.0 (asyncio) with `aiosqlite` (development/small VPS) and ready for `asyncpg` (PostgreSQL)
* **Migrations:** `Alembic` 1.19
* **HTTP Client:** `httpx` 0.28 with connection timeouts
* **Settings & Schemas:** `pydantic-settings` 2.15 & `pydantic` 2.13
* **Test Suite:** `pytest` 9.1 & `pytest-asyncio` 1.4

---

## 🚀 Quick Start (Local Development)

### 1. Prerequisites
* Python 3.12+
* Telegram account to create a bot via `@BotFather`
* [NOWPayments](https://nowpayments.io) account (or sandbox account at [account-sandbox.nowpayments.io](https://account-sandbox.nowpayments.io))

### 2. Setup Virtual Environment
```bash
git clone <repo-url> telegram-shop-bot
cd telegram-shop-bot

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Edit `.env` with your credentials:
```env
BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
DATABASE_URL=sqlite+aiosqlite:///./cloud_deals.db
ADMIN_TELEGRAM_IDS=123456789,987654321

CRYPTO_PROVIDER=nowpayments
NOWPAYMENTS_API_KEY=your_sandbox_or_live_api_key
NOWPAYMENTS_IPN_SECRET=your_ipn_secret_key
NOWPAYMENTS_SANDBOX=true

WEBHOOK_BASE_URL=https://your-domain-or-tunnel.ngrok-free.app
API_HOST=0.0.0.0
API_PORT=8000
STORE_NAME=Cloud Deals
SUPPORT_USERNAME=your_telegram_support_handle
ORDER_EXPIRY_MINUTES=30
LOG_LEVEL=INFO
```

### 4. Run Migrations & Seed Sample Data
```bash
# Run database migrations
alembic upgrade head

# (Optional) Seed initial demo categories, products, and FAQs
python scripts/seed.py
```

### 5. Run the Application
```bash
python run.py
```
This concurrently starts:
1. **FastAPI Webhook Server** on `http://0.0.0.0:8000`
2. **Telegram Polling Bot**
3. **Background Order Expiration Loop** (releasing expired reservations every 5 minutes)

---

## 💳 Payment Integration & Webhook Flow

### How the Payment Flow Works
```
Customer                    Telegram Bot                Backend / API             NOWPayments
   |                             |                           |                         |
   |-- 1. [🛒 Buy Now] --------->|                           |                         |
   |                             |-- 2. create_order() ----->|                         |
   |                             |      (Reserves Stock)     |-- 3. POST /v1/invoice ->|
   |                             |                           |<-- Returns URL & ID ----|
   |                             |<-- 4. Order & URL --------|                         |
   |<-- 5. [💳 Pay with Crypto] -|                                                     |
   |                                                                                   |
   |-- 6. Opens checkout link in browser and sends crypto ---------------------------->|
   |                                                                                   |
   |                                                         |<-- 7. IPN Webhook (HMAC)|
   |                                                         |    POST /webhooks/crypto|
   |                                                         |-- 8. Verify HMAC-SHA512 |
   |                                                         |-- 9. Check Idempotency  |
   |                                                         |-- 10. Mark SOLD & PAID  |
   |                             |<-- 11. Trigger Delivery --|                         |
   |<-- 12. Digital Code Sent ---|                           |                         |
```

### Webhook Verification Rules
1. Every incoming webhook payload from `POST /webhooks/crypto/nowpayments` is verified using **HMAC-SHA512**.
2. The payload keys are sorted alphabetically and hashed with your `NOWPAYMENTS_IPN_SECRET`.
3. The computed signature is compared with constant-time equality (`hmac.compare_digest`) against the `x-nowpayments-sig` header.
4. Orders are marked `PAID` and fulfilled **only** when `payment_status` is `finished`.

### Local Webhook Testing with ngrok
To receive callbacks on your local machine:
```bash
ngrok http 8000
```
Copy the generated HTTPS URL (e.g., `https://abc1234.ngrok-free.app`) and set it in your `.env`:
```env
WEBHOOK_BASE_URL=https://abc1234.ngrok-free.app
```

---

## 🔒 Concurrency & Inventory Protection

* **Row-Level Locking:** Inventory reservation queries utilize database-level locks (`with_for_update`) to ensure that if two customers attempt to purchase the exact same remaining item simultaneously, only one succeeds; the second receives an "Out of stock" notice.
* **Double-Delivery Prevention:** Fulfillment logic asserts that orders can only be transitioned from `PAID` to `FULFILLED` once. Duplicate webhook deliveries detect the terminal state and exit early without re-executing delivery.
* **Access Control:** All order retrieval callbacks verify that `order.user_id == current_user.id`, preventing unauthorized order enumeration.

---

## 🤖 Bot Commands & Navigation

### User Commands
* `/start` — Register user, process referral link, and display main storefront menu.
* `/help` — Display bot usage instructions and store support contact.
* `/profile` — View account details, order count, balance, and referral link.
* `/orders` — View paginated personal order history and delivery statuses.
* `/support` — Create customer support tickets and review past tickets.

### Admin Commands (`/admin`)
Only Telegram IDs specified in `ADMIN_TELEGRAM_IDS` can access the admin control center:
* **📦 Products:** Add, edit, deactivate, or review active products.
* **📁 Categories:** Create new categories, configure icons, and manage descriptions.
* **📥 Inventory:** Bulk upload deliverable stock codes/credentials per product.
* **💰 Orders:** Inspect recent orders, track payment state, or trigger manual delivery.
* **💳 Payments:** View payment audit trails and provider payment identifiers.
* **👥 Users:** View total registered users and manage user access.
* **📊 Statistics:** Real-time revenue, paid orders, pending items, and open tickets.
* **📢 Broadcast:** Send mass announcements to all registered customers with safe rate-limiting.
* **🎫 Tickets:** Review user support requests, respond directly from Telegram, or close tickets.
* **⚙️ Settings:** Toggle store maintenance mode and configure store defaults.

---

## 🧪 Running Automated Tests

The repository includes a comprehensive `pytest` test suite covering models, atomic inventory reservations, order lifecycle, webhook HMAC verification, and idempotency guarantees.

```bash
# Run all tests
pytest -v

# Run with coverage report
pytest --cov=app tests/
```

---

## 🐳 Docker Deployment

### 1. Build and Run with Docker Compose
```bash
docker compose up -d --build
```

### 2. View Logs
```bash
docker compose logs -f
```

### 3. Check Health
```bash
curl http://localhost:8000/health
# {"status":"ok","service":"cloud-deals"}
```

---

## 🌐 Production Linux VPS Deployment (Ubuntu/Debian)

### Step 1: System Preparation
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv git sqlite3 nginx certbot python3-certbot-nginx
```

### Step 2: Clone & Configure
```bash
cd /opt
sudo git clone <your-repo-url> cloud-deals
cd cloud-deals
sudo chown -R $USER:$USER /opt/cloud-deals

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

cp .env.example .env
nano .env  # Add live BOT_TOKEN, NOWPAYMENTS keys, domain, etc.
```

### Step 3: Run Database Migrations
```bash
alembic upgrade head
```

### Step 4: Configure Systemd Service
Create `/etc/systemd/system/cloud-deals.service`:
```ini
[Unit]
Description=Cloud Deals Telegram Shop Bot & Webhook Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/cloud-deals
EnvironmentFile=/opt/cloud-deals/.env
ExecStart=/opt/cloud-deals/venv/bin/python /opt/cloud-deals/run.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable cloud-deals
sudo systemctl start cloud-deals
sudo systemctl status cloud-deals
```

### Step 5: Configure Nginx & SSL
Create `/etc/nginx/sites-available/cloud-deals`:
```nginx
server {
    server_name store.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable the site and obtain a free Let's Encrypt SSL certificate:
```bash
sudo ln -s /etc/nginx/sites-available/cloud-deals /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

sudo certbot --nginx -d store.yourdomain.com
```

Your webhook endpoint will be live at:
`https://store.yourdomain.com/webhooks/crypto/nowpayments`

---

## 💾 Database Backups

### Automated SQLite Backup Script
The included backup script uses SQLite's non-blocking `.backup` API to create consistent point-in-time snapshots and removes files older than 30 days:
```bash
./scripts/backup.sh /opt/cloud-deals/backups
```

### Set up Automated Daily Cron Job
```bash
crontab -e
```
Add the following entry:
```cron
0 3 * * * /opt/cloud-deals/scripts/backup.sh /opt/cloud-deals/backups >> /var/log/cloud_deals_backup.log 2>&1
```

---

## 🛡️ Security Checklist

- [x] **No Secrets in Source Code:** All tokens and API keys are strictly loaded via environment variables and `.env`.
- [x] **Log Masking:** `logging_config.py` automatically filters and redacts API keys, bot tokens, and payment secrets from output logs.
- [x] **HMAC-SHA512 Verification:** Webhooks reject all unauthenticated or tampered payloads with constant-time comparison.
- [x] **Strict Server-Side Fulfillment:** Orders only fulfill on verified `finished` status callbacks.
- [x] **Inventory Race Prevention:** Concurrency-safe atomic reservation prevents duplicate sales.
- [x] **Authorization Checks:** Admin endpoints check `ADMIN_TELEGRAM_IDS` and order endpoints verify ownership.
- [x] **Floating-Point Avoidance:** Monetary calculations use `Decimal` to avoid rounding errors.
