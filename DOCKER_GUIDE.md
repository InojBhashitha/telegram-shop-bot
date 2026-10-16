# 🐳 1-Click Docker Compose & Auto-SSL Deployment Guide

This guide explains how to deploy the entire **Telegram Mini App Storefront & Bot** in production with **automatic Let's Encrypt / ZeroSSL HTTPS certificates** in under 3 minutes.

---

## 🏗️ Architecture Overview

```text
[ Telegram App / Browser ]
           │
           ▼ (HTTPS :443 / HTTP :80)
┌────────────────────────────────────────────────────────┐
│ Caddy Reverse Proxy (Auto-SSL via Let's Encrypt)       │
│ - Automatic TLS issuance & 60-day background renewal   │
│ - HTTP to HTTPS forced redirect                        │
│ - Zstandard & Gzip high-performance compression        │
│ - HTTP/3 (QUIC) support                                │
└──────────────────────────┬─────────────────────────────┘
                           │ (Internal Docker Network)
                           ▼ (:8000)
┌────────────────────────────────────────────────────────┐
│ Python 3.12 Shop Container (telegram-shop-app)         │
│ - FastAPI WebApp Storefront & Webhook API Server       │
│ - Telegram Bot Polling Engine                          │
│ - Background Expiring Orders & Auto-Payment Polling    │
│ - SQLite Persistent Volume (/app/data/shop.db)         │
└────────────────────────────────────────────────────────┘
```

---

## ⚡ 3-Minute Quick Start on Any Linux VPS

### 1. Requirements
- A VPS with Ubuntu 22.04 / 24.04 or Debian (e.g. $4–$5/mo on Hetzner, DigitalOcean, Vultr, Contabo).
- A domain or subdomain pointing to your VPS IP address (DNS `A` Record, e.g. `shop.yourdomain.com` -> `123.45.67.89`).

---

### 2. Install Docker in 1 Command
If your VPS does not have Docker yet, install the official release:
```bash
curl -fsSL https://get.docker.com | sh
```

---

### 3. Clone Repository & Run Setup Wizard
```bash
git clone https://github.com/InojBhashitha/telegram-shop-bot.git
cd telegram-shop-bot

# Run the interactive configuration wizard
python3 setup_wizard.py
```

The wizard will ask for:
- Your Telegram Bot Token (verified live via Telegram API)
- Store name, custom logo, theme accent color, and currency
- **Public Domain for Auto-SSL** (e.g. `shop.yourdomain.com`)
- Admin Telegram ID(s) and crypto payment gateway

---

### 4. Deploy with 1 Click
Run the automated deployment script:
```bash
./deploy.sh
```

*(Alternatively, run `docker compose up -d --build` directly)*

**That's it!** Caddy will immediately:
1. Verify DNS for your domain.
2. Obtain a valid SSL/TLS certificate from Let's Encrypt.
3. Start serving your Apple Store WebApp at `https://shop.yourdomain.com/webapp`.
4. Launch your Telegram bot with instant delivery and cart checkout.

---

## 🛠️ Management & Operational Commands

### View Live Container Logs
```bash
# View all logs in real-time
docker compose logs -f

# View only shop application logs
docker compose logs -f shop-app

# View only Caddy SSL reverse proxy logs
docker compose logs -f caddy
```

### Inspect or Seed Inventory Inside Docker
```bash
# Inspect current stock levels
docker compose exec shop-app python seed_catalog.py --status

# Seed high-converting demo categories & products
docker compose exec shop-app python seed_catalog.py

# Wipe demo catalog
docker compose exec shop-app python seed_catalog.py --wipe
```

### Update Code to Latest Version
```bash
git pull
docker compose up -d --build
```
*Zero downtime: existing database and SSL certificates are preserved across rebuilds.*

### Stop or Restart Services
```bash
# Restart all containers
docker compose restart

# Stop services safely
docker compose down
```

---

## 💾 Database Persistence & Backups

Your SQLite database is stored in a dedicated persistent Docker volume named `telegram_shop_data` at `/app/data/shop.db`.

To create an instant backup of your database:
```bash
# Copy database out of the container to your host
docker compose cp shop-app:/app/data/shop.db ./backup_shop_$(date +%Y%m%d).db
```

To restore from a backup:
```bash
docker compose cp ./backup_shop.db shop-app:/app/data/shop.db
docker compose restart shop-app
```

---

## 🔌 Running in API-Only Mode (External Bot Embedding)

If you already have an existing Telegram bot and only want Docker to host the WebApp storefront, set:
```env
MODE=api
```
in your `.env` file and run `docker compose up -d`. The container will run only the FastAPI WebApp server with 2 workers, freeing up resources.

---

## ❓ Troubleshooting

| Issue | Solution |
| :--- | :--- |
| **SSL certificate fails to issue** | Ensure your domain's DNS `A` record points to your VPS IP, and ports `80` and `443` are open in your firewall (`ufw allow 80/tcp && ufw allow 443/tcp`). |
| **Port 80/443 already in use** | If Apache or Nginx is running on the host, stop it: `sudo systemctl stop nginx && sudo systemctl disable nginx`. |
| **Bot not responding** | Check bot logs with `docker compose logs -f shop-app`. Ensure `BOT_TOKEN` in `.env` is valid. |
| **Mini App blank screen** | Verify that `WEBAPP_URL` in `.env` uses `https://` (Telegram Mini Apps require HTTPS). |
