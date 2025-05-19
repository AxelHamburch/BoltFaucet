#!/usr/bin/env python3
import os
import re
import time
import sqlite3
import logging
import requests
import qrcode
import random
import signal
from io import BytesIO
from dotenv import load_dotenv
from telegram import Update, InputFile
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackContext,
    DispatcherHandlerStop
)

# === 1. Load & validate environment variables ===
load_dotenv()

LNBITS_API_KEY         = os.getenv("LNBITS_API_KEY")        # Your Wallet Admin Key
LNBITS_API_BASE        = os.getenv("LNBITS_API_URL")        # e.g. "https://lnbits.de"
TELEGRAM_BOT_TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL            = os.getenv("LNBITS_WEBHOOK_URL")    # optional
VOUCHER_TITLE          = os.getenv("VOUCHER_TITLE", "LN Voucher")
VOUCHER_BATCH_SIZE     = int(os.getenv("VOUCHER_BATCH_SIZE", "100"))
MIN_WITHDRAWABLE_SATS  = int(os.getenv("MIN_WITHDRAWABLE_SATS", "21"))
MAX_WITHDRAWABLE_SATS  = int(os.getenv("MAX_WITHDRAWABLE_SATS", "21"))
ADMIN_TELEGRAM_ID      = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))

# === Lucky voucher settings ===
LUCKY_VOUCHER_ENABLED  = os.getenv("LUCKY_VOUCHER_ENABLED", "false").lower() == "true"
LUCKY_VOUCHER_AMOUNT   = int(os.getenv("LUCKY_VOUCHER_AMOUNT", "10000"))
LUCKY_VOUCHER_COUNT    = int(os.getenv("LUCKY_VOUCHER_COUNT", "5"))
# Interpret the env value as a percentage, then convert to [0,1]:
_raw_chance           = float(os.getenv("LUCKY_VOUCHER_CHANCE", "0.10"))
LUCKY_VOUCHER_CHANCE  = _raw_chance / 100.0

# === Withdraw extension needs the value in SATS ===
MIN_WITHDRAWABLE = MIN_WITHDRAWABLE_SATS
MAX_WITHDRAWABLE = MAX_WITHDRAWABLE_SATS

for var in ("LNBITS_API_KEY", "LNBITS_API_BASE", "TELEGRAM_BOT_TOKEN"):
    if not globals()[var]:
        raise RuntimeError(f"Missing required environment variable: {var}")

HEADERS = {"X-Api-Key": LNBITS_API_KEY}

# === Logging setup ===
logging.basicConfig(
    format="%(asctime)s %(levelname)s: %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === 2. Database initialization ===
def init_db():
    conn = sqlite3.connect("db.sqlite3", timeout=10)
    c = conn.cursor()
    c.execute('''
      CREATE TABLE IF NOT EXISTS vouchers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lnurl TEXT     NOT NULL UNIQUE,
        link_id TEXT   NOT NULL,
        assigned_to TEXT UNIQUE,
        used    BOOLEAN DEFAULT 0,
        bonus   BOOLEAN DEFAULT 0
      )
    ''')
    conn.commit()
    conn.close()

# === 3a. Create normal voucher group & import ===
def create_voucher_group():
    logger.info(f"Creating voucher group ({VOUCHER_BATCH_SIZE} uses)...")
    url = f"{LNBITS_API_BASE}/withdraw/api/v1/links"
    payload = {
        "title": VOUCHER_TITLE,
        "min_withdrawable": MIN_WITHDRAWABLE,
        "max_withdrawable": MAX_WITHDRAWABLE,
        "uses": VOUCHER_BATCH_SIZE,
        "wait_time": 1,
        "is_unique": True,
        "webhook_url": WEBHOOK_URL
    }
    resp = requests.post(url, json=payload, headers=HEADERS, timeout=10)
    if not resp.ok:
        logger.error("Failed to create voucher group: %s %s", resp.status_code, resp.text)
        return
    link_id = resp.json().get("id")
    logger.info("Voucher group created: %s", link_id)
    fetch_and_store_lnurls(link_id)

def fetch_and_store_lnurls(link_id: str):
    csv_url = f"{LNBITS_API_BASE}/withdraw/csv/{link_id}"
    headers = {**HEADERS, "Accept": "text/csv"}
    resp = requests.get(csv_url, headers=headers, timeout=10)
    if not resp.ok:
        logger.error("Failed to fetch CSV: %s %s", resp.status_code, resp.text)
        return

    text = resp.text.strip()
    if "<html" in text.lower():
        logger.warning("Received HTML instead of CSV, extracting via regex")
        lnurls = re.findall(r"(LNURL[0-9A-Za-z]+)", text)
    else:
        lnurls = text.splitlines()

    seen, unique = set(), []
    for u in lnurls:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    logger.info("Imported %d unique vouchers", len(unique))
    save_lnurls_to_db(unique, link_id)

def save_lnurls_to_db(lnurls: list, link_id: str):
    conn = sqlite3.connect("db.sqlite3", timeout=10)
    c = conn.cursor()
    for lnurl in lnurls:
        try:
            c.execute(
                "INSERT INTO vouchers (lnurl, link_id) VALUES (?, ?)",
                (lnurl, link_id)
            )
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    conn.close()

# === 3b. Create lucky bonus vouchers ===
def create_lucky_vouchers():
    if not LUCKY_VOUCHER_ENABLED:
        return
    logger.info(f"Creating {LUCKY_VOUCHER_COUNT} lucky vouchers ({LUCKY_VOUCHER_AMOUNT} sats each)...")
    url = f"{LNBITS_API_BASE}/withdraw/api/v1/links"
    payload = {
        "title": "Lucky Voucher",
        "min_withdrawable": LUCKY_VOUCHER_AMOUNT,
        "max_withdrawable": LUCKY_VOUCHER_AMOUNT,
        "uses": LUCKY_VOUCHER_COUNT,
        "wait_time": 1,
        "is_unique": True,
        "webhook_url": WEBHOOK_URL
    }
    resp = requests.post(url, json=payload, headers=HEADERS, timeout=10)
    if not resp.ok:
        logger.error("Failed to create lucky vouchers: %s %s", resp.status_code, resp.text)
        return
    link_id = resp.json().get("id")

    csv_url = f"{LNBITS_API_BASE}/withdraw/csv/{link_id}"
    headers = {**HEADERS, "Accept": "text/csv"}
    resp = requests.get(csv_url, headers=headers, timeout=10)
    if not resp.ok:
        logger.error("Failed to fetch lucky vouchers CSV: %s %s", resp.status_code, resp.text)
        return

    lnurls = resp.text.strip().splitlines()
    conn = sqlite3.connect("db.sqlite3", timeout=10)
    c = conn.cursor()
    for lnurl in lnurls:
        try:
            c.execute(
                "INSERT INTO vouchers (lnurl, link_id, bonus) VALUES (?, ?, 1)",
                (lnurl, link_id)
            )
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    conn.close()
    logger.info(f"Stored {len(lnurls)} lucky vouchers.")

# === 4. Claim logic ===
def has_received(chat_id: str) -> bool:
    conn = sqlite3.connect("db.sqlite3", timeout=10)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM vouchers WHERE assigned_to = ?", (chat_id,))
    count = c.fetchone()[0]
    conn.close()
    return count > 0

def assign_voucher(chat_id: str, is_admin: bool = False):
    conn = sqlite3.connect("db.sqlite3", timeout=10)
    c = conn.cursor()

    # 1. Assign normal voucher
    c.execute("SELECT lnurl, link_id FROM vouchers WHERE assigned_to IS NULL AND bonus = 0 LIMIT 1")
    normal = c.fetchone()
    if not normal:
        logger.info("No unassigned normal vouchers, creating new batch")
        conn.close()
        create_voucher_group()
        conn = sqlite3.connect("db.sqlite3", timeout=10)
        c = conn.cursor()
        c.execute("SELECT lnurl, link_id FROM vouchers WHERE assigned_to IS NULL AND bonus = 0 LIMIT 1")
        normal = c.fetchone()

    lucky = None
    if normal:
        lnurl_n, link_id_n = normal
        assign_tag = f"{chat_id}-{time.time_ns()}" if is_admin else chat_id
        c.execute("UPDATE vouchers SET assigned_to = ? WHERE lnurl = ?", (assign_tag, lnurl_n))

        # 2. Possibly assign a lucky bonus voucher
        if LUCKY_VOUCHER_ENABLED and random.random() < LUCKY_VOUCHER_CHANCE:
            c.execute(
                "SELECT lnurl, link_id FROM vouchers "
                "WHERE assigned_to IS NULL AND bonus = 1 "
                "ORDER BY RANDOM() LIMIT 1"
            )
            lucky_row = c.fetchone()
            if lucky_row:
                lnurl_l, link_id_l = lucky_row
                c.execute(
                    "UPDATE vouchers SET assigned_to = ? WHERE lnurl = ?",
                    (assign_tag + "-bonus", lnurl_l)
                )
                lucky = (lnurl_l, link_id_l)

        conn.commit()
        conn.close()
        return (lnurl_n, link_id_n), lucky

    conn.close()
    return None, None

# === 5. Telegram Handlers ===
def send_voucher(update: Update, lnurl: str, link_id: str, username: str, bonus: bool = False):
    amount = LUCKY_VOUCHER_AMOUNT if bonus else MIN_WITHDRAWABLE_SATS
    bonus_note = "\n🍀 LUCKY BONUS! 🍀" if bonus else ""
    text = (
        f"Hey @{username}, here are your {amount} sats 🎁{bonus_note}\n\n"
        f"<code>{lnurl}</code>\n\n"
        "👉 Press to copy the voucher if needed!"
    )
    update.message.reply_text(text, parse_mode="HTML")

    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(lnurl)
    qr.make(fit=True)
    img = qr.make_image()
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    buf.name = "voucher.png"
    update.message.reply_photo(photo=InputFile(buf))

def start_command(update: Update, context: CallbackContext):
    cid = str(update.effective_chat.id)
    usr = update.effective_user.username or "Anonymous"
    text = update.message.text or ""
    payload = text.split(" ", 1)[1].strip().lower() if " " in text else ""
    is_admin = (update.effective_user.id == ADMIN_TELEGRAM_ID)

    if payload == "claim":
        if not is_admin and has_received(cid):
            update.message.reply_text(
                f"Hey @{usr}, you’ve already claimed {MIN_WITHDRAWABLE_SATS} sats 🎉"
            )
        else:
            normal, lucky = assign_voucher(cid, is_admin=is_admin)
            if normal:
                lnurl_n, lid_n = normal
                send_voucher(update, lnurl_n, lid_n, usr)
                if lucky:
                    lnurl_l, lid_l = lucky
                    send_voucher(update, lnurl_l, lid_l, usr, bonus=True)
            else:
                update.message.reply_text("Sorry, no vouchers available right now.")
        check_voucher_supply()
    else:
        update.message.reply_text(
            "⚡ Welcome!\n"
            "To claim your sats, use /getvoucher."
        )

def getvoucher_command(update: Update, context: CallbackContext):
    cid = str(update.effective_chat.id)
    usr = update.effective_user.username or "Anonymous"
    is_admin = (update.effective_user.id == ADMIN_TELEGRAM_ID)

    if not is_admin and has_received(cid):
        update.message.reply_text(
            f"Hey @{usr}, you’ve already claimed {MIN_WITHDRAWABLE_SATS} sats 🎉"
        )
    else:
        normal, lucky = assign_voucher(cid, is_admin=is_admin)
        if normal:
            lnurl_n, lid_n = normal
            send_voucher(update, lnurl_n, lid_n, usr)
            if lucky:
                lnurl_l, lid_l = lucky
                send_voucher(update, lnurl_l, lid_l, usr, bonus=True)
        else:
            update.message.reply_text("Sorry, no vouchers available right now.")
        check_voucher_supply()

def stats_command(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_TELEGRAM_ID:
        return
    conn = sqlite3.connect("db.sqlite3", timeout=10)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM vouchers WHERE assigned_to IS NOT NULL")
    used = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM vouchers WHERE assigned_to IS NULL")
    free = c.fetchone()[0]
    conn.close()
    update.message.reply_text(f"📊 Used: {used}, Free: {free}")

def error_handler(update: object, context: CallbackContext):
    logger.exception("Error while handling update: %s", context.error)
    raise DispatcherHandlerStop()

def check_voucher_supply():
    conn = sqlite3.connect("db.sqlite3", timeout=10)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM vouchers WHERE assigned_to IS NULL AND bonus = 0")
    free_normal = c.fetchone()[0]
    conn.close()
    threshold = max(10, VOUCHER_BATCH_SIZE // 10)
    if free_normal < threshold:
        logger.info("Normal voucher supply low (%d), refilling...", free_normal)
        create_voucher_group()

def main():
    init_db()
    create_lucky_vouchers()
    create_voucher_group()

    updater = Updater(token=TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start_command))
    dp.add_handler(CommandHandler("getvoucher", getvoucher_command))
    dp.add_handler(CommandHandler("stats", stats_command))
    dp.add_error_handler(error_handler)

    updater.start_polling()
    logger.info("🤖 Voucher Bot is running.")

    def stop(signum, frame):
        logger.info("📉 Shutting down…")
        updater.stop()
        updater.is_idle = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    updater.idle()
    logger.info("⏹️ Bot stopped.")

if __name__ == "__main__":
    main()
