# 🔌 Embedding the Telegram Mini App Store into Any Existing Bot

If your client **already has a working Telegram bot** (community bot, support bot, signal bot, or an older keyboard-based shop bot), you **do not need to replace their existing bot**. 

The modern Apple Store Mini App can be embedded directly into their existing bot in **under 2 minutes** using any of the methods below.

---

## ⚡ Method 1: The 1-Minute Zero-Code Method (BotFather Menu Button)

This is the cleanest and most popular method. It attaches a persistent **"🛍️ Store"** button directly to the bottom-left of the user's chat input area next to the attachment icon.

1. Open Telegram and message **[@BotFather](https://t.me/BotFather)**.
2. Send the command:
   ```text
   /setmenubutton
   ```
3. Select your client's existing bot.
4. Send the button label:
   ```text
   🛍️ Shop Now
   ```
   *(or "💎 Digital Store", "⚡ Products", etc.)*
5. Send your hosted WebApp URL:
   ```text
   https://yourdomain.com/webapp
   ```

**Done!** Every user who opens chat with the bot will immediately see the dedicated WebApp launcher button in their chat bar.

---

## 🐍 Method 2: Python Bots

If your client's existing bot is written in Python, add an inline button or reply markup button with the `web_app` parameter.

### A. `aiogram` (v3.x)

```python
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

WEBAPP_URL = "https://yourdomain.com/webapp"

@dp.message(CommandStart())
async def handle_start(message: types.Message):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🛍️ Open Store (Instant Delivery)",
                    web_app=WebAppInfo(url=WEBAPP_URL)
                )
            ],
            [
                InlineKeyboardButton(text="💬 Customer Support", url="https://t.me/YourSupportUsername"),
                InlineKeyboardButton(text="⭐ Verified Vouches", url="https://t.me/YourVouchChannel")
            ]
        ]
    )
    await message.answer(
        f"👋 Welcome {message.from_user.first_name}!\n\n"
        "Explore our verified digital credentials, cloud accounts, and VPN keys with instant automated delivery:",
        reply_markup=keyboard
    )
```

---

### B. `python-telegram-bot` (v20+)

```python
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

WEBAPP_URL = "https://yourdomain.com/webapp"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton(
                "🛍️ Launch Store", 
                web_app=WebAppInfo(url=WEBAPP_URL)
            )
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "⚡ Welcome! Tap below to open our interactive store:",
        reply_markup=reply_markup
    )

app = ApplicationBuilder().token("YOUR_EXISTING_TOKEN").build()
app.add_handler(CommandHandler("start", start))
app.run_polling()
```

---

### C. `telethon`

```python
from telethon import TelegramClient, events
from telethon.tl.types import KeyboardButtonWebView

WEBAPP_URL = "https://yourdomain.com/webapp"

@bot.on(events.NewMessage(pattern="/start"))
async def start_handler(event):
    await event.respond(
        "👋 Welcome! Click below to shop:",
        buttons=[
            [KeyboardButtonWebView("🛍️ Launch Store", WEBAPP_URL)]
        ]
    )
```

---

## 🟢 Method 3: Node.js & TypeScript Bots

### A. `telegraf` (v4.x)

```javascript
const { Telegraf, Markup } = require('telegraf');

const bot = new Telegraf(process.env.BOT_TOKEN);
const WEBAPP_URL = "https://yourdomain.com/webapp";

bot.command('start', (ctx) => {
  return ctx.reply(
    `👋 Welcome ${ctx.from.first_name}! Tap below to access our instant digital store:`,
    Markup.inlineKeyboard([
      [Markup.button.webApp('🛍️ Open Store', WEBAPP_URL)],
      [
        Markup.button.url('💬 Support', 'https://t.me/YourSupportUsername'),
        Markup.button.url('⭐ Vouches', 'https://t.me/YourVouchChannel')
      ]
    ])
  );
});

bot.launch();
```

---

### B. `grammY`

```typescript
import { Bot, InlineKeyboard } from "grammy";

const bot = new Bot(process.env.BOT_TOKEN!);
const WEBAPP_URL = "https://yourdomain.com/webapp";

bot.command("start", (ctx) => {
  const keyboard = new InlineKeyboard()
    .webApp("🛍️ Open Store", WEBAPP_URL)
    .row()
    .url("💬 Support", "https://t.me/YourSupportUsername");

  return ctx.reply("⚡ Welcome! Launch our Mini App to browse products:", {
    reply_markup: keyboard,
  });
});

bot.start();
```

---

## 🔗 Method 4: Telegram Direct Link (No Coding Required)

You can share direct Mini App links anywhere across Telegram (in channel posts, bio descriptions, broadcast messages, or external websites):

```text
https://t.me/<BOT_USERNAME>?startapp=store
```

### In Channel Announcements:
```text
🔥 RESTOCK ALERT: Oracle Cloud & Mullvad VPN keys are now back in stock!
👉 Tap to order instantly: https://t.me/YourBotName?startapp=store
```

When users click the link on mobile or desktop, the sleek Apple Store WebApp opens immediately within Telegram.

---

## 🌐 Connecting Existing Bot Auth to WebApp Backend

When the user launches the Mini App from any Telegram chat, the Telegram SDK automatically passes a cryptographically signed `initData` query string to the WebApp.

The WebApp backend (`POST /api/webapp/auth`) validates the HMAC-SHA256 signature against the bot token configured in `.env`.

> [!TIP]
> **Pro-Tip for Commercial Delivery**:
> When setting up the client's store, configure their existing bot token in `.env`:
> ```env
> BOT_TOKEN=123456789:ABCdefExistingClientBotToken
> ```
> The WebApp will seamlessly authenticate all users from their existing bot, track their balances, and deliver purchased credentials directly to their chat!
