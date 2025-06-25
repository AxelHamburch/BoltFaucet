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
from html import escape
from dotenv import load_dotenv
from telegram import Update, InputFile, ParseMode
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackContext,
    DispatcherHandlerStop
)

# === 1. Load & validate environment variables ===
load_dotenv()

LNBITS_API_KEY         = os.getenv("LNBITS_API_KEY")
LNBITS_API_BASE        = os.getenv("LNBITS_API_URL")
TELEGRAM_BOT_TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL            = os.getenv("LNBITS_WEBHOOK_URL")
VOUCHER_TITLE          = os.getenv("VOUCHER_TITLE", "LN Voucher")
VOUCHER_BATCH_SIZE     = int(os.getenv("VOUCHER_BATCH_SIZE", "100"))
MIN_WITHDRAWABLE_SATS  = int(os.getenv("MIN_WITHDRAWABLE_SATS", "21"))
MAX_WITHDRAWABLE_SATS  = int(os.getenv("MAX_WITHDRAWABLE_SATS", "21"))
ADMIN_TELEGRAM_ID      = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))

# === Lucky voucher settings ===
LUCKY_VOUCHER_ENABLED  = os.getenv("LUCKY_VOUCHER_ENABLED", "false").lower() == "true"
LUCKY_VOUCHER_AMOUNT   = int(os.getenv("LUCKY_VOUCHER_AMOUNT", "10000"))
LUCKY_VOUCHER_COUNT    = int(os.getenv("LUCKY_VOUCHER_COUNT", "5"))
_raw_chance            = float(os.getenv("LUCKY_VOUCHER_CHANCE", "0.10"))
LUCKY_VOUCHER_CHANCE   = _raw_chance / 100.0

MIN_WITHDRAWABLE = MIN_WITHDRAWABLE_SATS
MAX_WITHDRAWABLE = MAX_WITHDRAWABLE_SATS

# Validate required envs
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
        bonus   BOOLEAN DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    ''')
    
    # Add lucky wins tracking
    c.execute('''
      CREATE TABLE IF NOT EXISTS lucky_wins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT NOT NULL,
        username TEXT,
        amount INTEGER NOT NULL,
        won_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    ''')
    conn.commit()
    conn.close()

def clean_database():
    """Remove invalid LNURL entries (HTML fragments) from database"""
    conn = sqlite3.connect("db.sqlite3", timeout=10)
    c = conn.cursor()
    
    # Find and remove invalid entries
    c.execute("SELECT id, lnurl FROM vouchers")
    all_vouchers = c.fetchall()
    
    invalid_count = 0
    for voucher_id, lnurl in all_vouchers:
        # Check if it's a valid LNURL (should start with LNURL and be alphanumeric)
        if not lnurl.startswith('LNURL') or not re.match(r'^LNURL[0-9A-Z]+$', lnurl.upper()):
            c.execute("DELETE FROM vouchers WHERE id = ?", (voucher_id,))
            invalid_count += 1
            logger.info(f"Removed invalid entry: {lnurl[:50]}...")
    
    conn.commit()
    conn.close()
    
    if invalid_count > 0:
        logger.info(f"Cleaned {invalid_count} invalid entries from database")
    else:
        logger.info("No invalid entries found in database")

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

    lnurls = extract_lnurls_from_response(resp.text)
    if lnurls:
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
    else:
        logger.error("No valid LNURLs found in lucky voucher response")

# === 3a. (cont'd) Improved LNURL extraction ===
def extract_lnurls_from_response(response_text):
    """Extract valid LNURLs from response, handling both CSV and HTML responses"""
    text = response_text.strip()
    
    # Check if response looks like HTML
    if "<html" in text.lower() or "<body" in text.lower() or "<script" in text.lower():
        logger.warning("Received HTML response instead of CSV, extracting LNURLs via regex")
        # Use more specific regex to find valid LNURLs
        lnurls = re.findall(r'\b(LNURL[0-9A-Z]{50,})\b', text.upper())
    else:
        # Treat as CSV - split by lines and filter
        lines = text.splitlines()
        lnurls = []
        for line in lines:
            line = line.strip()
            # Check if line looks like a valid LNURL
            if line.startswith('LNURL') and re.match(r'^LNURL[0-9A-Z]+$', line.upper()):
                lnurls.append(line.upper())
    
    # Additional validation - ensure LNURLs are proper length and format
    valid_lnurls = []
    for lnurl in lnurls:
        # LNURL should be at least 50 characters and only contain valid characters
        if len(lnurl) >= 50 and re.match(r'^LNURL[0-9A-Z]+$', lnurl):
            valid_lnurls.append(lnurl)
        else:
            logger.warning(f"Skipping invalid LNURL: {lnurl}")
    
    # Remove duplicates while preserving order
    seen = set()
    unique_lnurls = []
    for lnurl in valid_lnurls:
        if lnurl not in seen:
            seen.add(lnurl)
            unique_lnurls.append(lnurl)
    
    logger.info(f"Extracted {len(unique_lnurls)} valid LNURLs from response")
    return unique_lnurls

def fetch_and_store_lnurls(link_id: str):
    csv_url = f"{LNBITS_API_BASE}/withdraw/csv/{link_id}"
    headers = {**HEADERS, "Accept": "text/csv"}
    resp = requests.get(csv_url, headers=headers, timeout=10)
    if not resp.ok:
        logger.error("Failed to fetch CSV: %s %s", resp.status_code, resp.text)
        return

    lnurls = extract_lnurls_from_response(resp.text)
    if lnurls:
        save_lnurls_to_db(lnurls, link_id)
    else:
        logger.error("No valid LNURLs found in response")

def save_lnurls_to_db(lnurls: list, link_id: str):
    conn = sqlite3.connect("db.sqlite3", timeout=10)
    c = conn.cursor()
    saved_count = 0
    for lnurl in lnurls:
        try:
            c.execute(
                "INSERT INTO vouchers (lnurl, link_id) VALUES (?, ?)",
                (lnurl, link_id)
            )
            saved_count += 1
        except sqlite3.IntegrityError:
            logger.debug(f"LNURL already exists: {lnurl[:20]}...")
    conn.commit()
    conn.close()
    logger.info(f"Saved {saved_count} new LNURLs to database")

# === 4. Claim logic ===
def has_received(chat_id: str) -> bool:
    conn = sqlite3.connect("db.sqlite3", timeout=10)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM vouchers WHERE assigned_to = ?", (chat_id,))
    count = c.fetchone()[0]
    conn.close()
    return count > 0

def get_lucky_stats():
    """Get statistics about lucky wins"""
    conn = sqlite3.connect("db.sqlite3", timeout=10)
    c = conn.cursor()
    c.execute("SELECT COUNT(*), SUM(amount) FROM lucky_wins")
    result = c.fetchone()
    conn.close()
    total_wins = result[0] or 0
    total_amount = result[1] or 0
    return total_wins, total_amount

def record_lucky_win(chat_id: str, username: str, amount: int):
    """Record a lucky win in the database"""
    conn = sqlite3.connect("db.sqlite3", timeout=10)
    c = conn.cursor()
    c.execute(
        "INSERT INTO lucky_wins (chat_id, username, amount) VALUES (?, ?, ?)",
        (chat_id, username, amount)
    )
    conn.commit()
    conn.close()

def assign_voucher(chat_id: str, is_admin: bool = False):
    conn = sqlite3.connect("db.sqlite3", timeout=10)
    c = conn.cursor()

    # 1. Assign normal voucher - only select valid LNURLs
    c.execute(
        "SELECT lnurl, link_id FROM vouchers "
        "WHERE assigned_to IS NULL AND bonus = 0 AND lnurl LIKE 'LNURL%' "
        "LIMIT 1"
    )
    normal = c.fetchone()
    if not normal:
        logger.info("No unassigned normal vouchers, creating new batch")
        conn.close()
        create_voucher_group()
        conn = sqlite3.connect("db.sqlite3", timeout=10)
        c = conn.cursor()
        c.execute(
            "SELECT lnurl, link_id FROM vouchers "
            "WHERE assigned_to IS NULL AND bonus = 0 AND lnurl LIKE 'LNURL%' "
            "LIMIT 1"
        )
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
                "WHERE assigned_to IS NULL AND bonus = 1 AND lnurl LIKE 'LNURL%' "
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

# === 5. Fixed Telegram Handlers ===
def send_voucher(update: Update, lnurl: str, link_id: str, username: str, bonus: bool = False):
    amount = LUCKY_VOUCHER_AMOUNT if bonus else MIN_WITHDRAWABLE_SATS
    
    # Validate LNURL format
    if not lnurl.startswith('LNURL') or not re.match(r'^LNURL[0-9A-Z]+$', lnurl.upper()):
        logger.error(f"Invalid LNURL format: {lnurl}")
        update.message.reply_text("Error: Invalid voucher format. Please contact admin.")
        return
    
    if bonus:
        # Record the lucky win
        record_lucky_win(str(update.effective_chat.id), username, amount)
        
        # Lucky bonus message with clean formatting
        text = (
            f"🍀 <b>Lucky Bonus!</b>\n"
            f"You've won an additional <b>{amount:,} sats</b>, @{username}!\n\n"
            f"<b>Voucher Code:</b>\n"
            f"<code>{lnurl}</code>\n\n"
            f"💡 <i>Tap the code above to copy it, then paste into your Lightning wallet</i>"
        )
        
    else:
        # Regular voucher message
        text = (
            f"Here are your <b>{amount} sats</b>, @{username}.\n\n"
            f"<b>Voucher Code:</b>\n"
            f"<code>{lnurl}</code>\n\n"
            f"💡 <i>Tap the code above to copy it, then paste into your Lightning wallet</i>"
        )
        
        if LUCKY_VOUCHER_ENABLED:
            chance_percent = LUCKY_VOUCHER_CHANCE * 100
            text += f"\n\n🎯 <i>You had a {chance_percent:.2f}% chance for a {LUCKY_VOUCHER_AMOUNT:,} sat bonus</i>"
    
    # Send message with HTML formatting
    update.message.reply_text(text, parse_mode=ParseMode.HTML)

    # Generate and send QR code
    try:
        qr = qrcode.QRCode(box_size=8, border=2)
        qr.add_data(lnurl)
        qr.make(fit=True)
        img = qr.make_image()
        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        buf.name = f"{'lucky_' if bonus else ''}voucher.png"
        
        caption = f"{'🍀 Lucky Bonus' if bonus else '⚡ Lightning'} Voucher QR"
        update.message.reply_photo(photo=InputFile(buf), caption=caption)
        
        logger.info(f"Sent {'lucky ' if bonus else ''}voucher QR for LNURL: {lnurl[:20]}...")
        
    except Exception as e:
        logger.error(f"Failed to generate QR code: {e}")
        update.message.reply_text("QR code generation failed. Please use the voucher code above.")

def start_command(update: Update, context: CallbackContext):
    cid = str(update.effective_chat.id)
    usr = update.effective_user.username or "Anonymous"
    text = update.message.text or ""
    payload = text.split(" ", 1)[1].strip().lower() if " " in text else ""
    is_admin = (update.effective_user.id == ADMIN_TELEGRAM_ID)

    if payload == "claim":
        handle_claim(update, context, usr, cid, is_admin)
    else:
        # Enhanced welcome message
        welcome_text = (
            f"⚡ <b>Lightning Voucher Bot</b>\n\n"
            f"Welcome @{usr}! Get your free <b>{MIN_WITHDRAWABLE_SATS} sats</b> with /getvoucher\n\n"
        )
        
        if LUCKY_VOUCHER_ENABLED:
            chance_percent = LUCKY_VOUCHER_CHANCE * 100
            total_wins, total_amount = get_lucky_stats()
            welcome_text += (
                f"🍀 <b>Lucky Feature Active!</b>\n"
                f"• {chance_percent:.2f}% chance to win <b>{LUCKY_VOUCHER_AMOUNT:,} bonus sats</b>\n"
                f"• {total_wins} lucky winners so far\n"
                f"• {total_amount:,} bonus sats distributed\n\n"
            )
        
        welcome_text += (
            f"<b>Commands:</b>\n"
            f"• /getvoucher - Claim your sats\n"
            f"• /info - About lucky bonuses\n"
            f"• /lucky - Lucky statistics"
        )
        
        update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML)

def handle_claim(update: Update, context: CallbackContext, username: str, chat_id: str, is_admin: bool):
    if not is_admin and has_received(chat_id):
        update.message.reply_text(
            f"You've already claimed your <b>{MIN_WITHDRAWABLE_SATS} sats</b>, @{username}.\n"
            f"Each user can only claim once to keep it fair for everyone.",
            parse_mode=ParseMode.HTML
        )
        return

    normal, lucky = assign_voucher(chat_id, is_admin=is_admin)
    
    if normal:
        lnurl_n, lid_n = normal
        send_voucher(update, lnurl_n, lid_n, username)
        
        if lucky:
            lnurl_l, lid_l = lucky
            send_voucher(update, lnurl_l, lid_l, username, bonus=True)
    else:
        update.message.reply_text(
            "No vouchers available right now.\n"
            "The admin has been notified to refill the supply."
        )
    
    check_voucher_supply()

def getvoucher_command(update: Update, context: CallbackContext):
    cid = str(update.effective_chat.id)
    usr = update.effective_user.username or "Anonymous"
    is_admin = (update.effective_user.id == ADMIN_TELEGRAM_ID)
    handle_claim(update, context, usr, cid, is_admin)

def info_command(update: Update, context: CallbackContext):
    if not LUCKY_VOUCHER_ENABLED:
        update.message.reply_text("Lucky bonuses are currently disabled.")
        return
    
    chance_percent = LUCKY_VOUCHER_CHANCE * 100
    total_wins, total_amount = get_lucky_stats()
    
    info_text = (
        f"🍀 <b>Lucky Bonus Feature</b>\n\n"
        f"<b>How it works:</b>\n"
        f"• {chance_percent:.2f}% chance per claim\n"
        f"• Winners get an extra <b>{LUCKY_VOUCHER_AMOUNT:,} sats</b>\n"
        f"• Completely random and automatic\n\n"
        f"<b>Statistics:</b>\n"
        f"• {total_wins} lucky winners\n"
        f"• {total_amount:,} bonus sats distributed\n"
        f"• Average: {(total_amount / max(total_wins, 1)):,.0f} sats per winner"
    )
    
    update.message.reply_text(info_text, parse_mode=ParseMode.HTML)

def lucky_command(update: Update, context: CallbackContext):
    if not LUCKY_VOUCHER_ENABLED:
        update.message.reply_text("Lucky bonuses are currently disabled.")
        return
    
    total_wins, total_amount = get_lucky_stats()
    chance_percent = LUCKY_VOUCHER_CHANCE * 100
    
    conn = sqlite3.connect("db.sqlite3", timeout=10)
    c = conn.cursor()
    c.execute(
        "SELECT username, amount, won_at FROM lucky_wins "
        "ORDER BY won_at DESC LIMIT 5"
    )
    recent_winners = c.fetchall()
    conn.close()
    
    stats_text = (
        f"🍀 <b>Lucky Statistics</b>\n\n"
        f"<b>Chance:</b> {chance_percent:.2f}% per claim\n"
        f"<b>Bonus:</b> {LUCKY_VOUCHER_AMOUNT:,} sats\n"
        f"<b>Total winners:</b> {total_wins}\n"
        f"<b>Total distributed:</b> {total_amount:,} sats\n\n"
    )
    
    if recent_winners:
        stats_text += "<b>Recent winners:</b>\n"
        for username, amount, won_at in recent_winners:
            won_date = won_at.split()[0] if won_at else "Unknown"
            stats_text += f"• @{username or 'Anonymous'}: {amount:,} sats ({won_date})\n"
    else:
        stats_text += "No lucky winners yet."
    
    update.message.reply_text(stats_text, parse_mode=ParseMode.HTML)

def stats_command(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_TELEGRAM_ID:
        return
    
    conn = sqlite3.connect("db.sqlite3", timeout=10)
    c = conn.cursor()
    
    # Regular voucher stats - only count valid LNURLs
    c.execute("SELECT COUNT(*) FROM vouchers WHERE assigned_to IS NOT NULL AND bonus = 0 AND lnurl LIKE 'LNURL%'")
    used_normal = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM vouchers WHERE assigned_to IS NULL AND bonus = 0 AND lnurl LIKE 'LNURL%'")
    free_normal = c.fetchone()[0]
    
    # Lucky voucher stats
    c.execute("SELECT COUNT(*) FROM vouchers WHERE assigned_to IS NOT NULL AND bonus = 1 AND lnurl LIKE 'LNURL%'")
    used_lucky = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM vouchers WHERE assigned_to IS NULL AND bonus = 1 AND lnurl LIKE 'LNURL%'")
    free_lucky = c.fetchone()[0]
    
    # Count invalid entries
    c.execute("SELECT COUNT(*) FROM vouchers WHERE lnurl NOT LIKE 'LNURL%'")
    invalid_entries = c.fetchone()[0]
    
    # Lucky wins
    c.execute("SELECT COUNT(*), SUM(amount) FROM lucky_wins")
    result = c.fetchone()
    total_lucky_wins = result[0] or 0
    total_lucky_amount = result[1] or 0
    
    conn.close()
    
    stats_text = (
        f"📊 <b>Admin Statistics</b>\n\n"
        f"<b>Regular Vouchers:</b>\n"
        f"• Used: {used_normal}\n"
        f"• Available: {free_normal}\n\n"
        f"<b>Lucky Vouchers:</b>\n"
        f"• Used: {used_lucky}\n"
        f"• Available: {free_lucky}\n\n"
        f"<b>Lucky Wins:</b>\n"
        f"• Total: {total_lucky_wins}\n"
        f"• Amount: {total_lucky_amount:,} sats\n"
        f"• Rate: {(used_lucky / max(used_normal, 1) * 100):.2f}%\n\n"
        f"<b>Database:</b>\n"
        f"• Invalid entries: {invalid_entries}"
    )
    
    if invalid_entries > 0:
        stats_text += f"\n\nUse /cleanup to remove invalid entries"
    
    update.message.reply_text(stats_text, parse_mode=ParseMode.HTML)

def cleanup_command(update: Update, context: CallbackContext):
    """Admin command to clean up invalid database entries"""
    if update.effective_user.id != ADMIN_TELEGRAM_ID:
        return
    
    update.message.reply_text("Cleaning up invalid database entries...")
    clean_database()
    update.message.reply_text("Database cleanup completed.")

def error_handler(update: object, context: CallbackContext):
    logger.exception("Error while handling update: %s", context.error)
    raise DispatcherHandlerStop()

def check_voucher_supply():
    conn = sqlite3.connect("db.sqlite3", timeout=10)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM vouchers WHERE assigned_to IS NULL AND bonus = 0 AND lnurl LIKE 'LNURL%'")
    free_normal = c.fetchone()[0]
    conn.close()
    
    threshold = max(10, VOUCHER_BATCH_SIZE // 10)
    if free_normal < threshold:
        logger.info("Normal voucher supply low (%d), refilling...", free_normal)
        create_voucher_group()

    if LUCKY_VOUCHER_ENABLED:
        conn = sqlite3.connect("db.sqlite3", timeout=10)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM vouchers WHERE assigned_to IS NULL AND bonus = 1 AND lnurl LIKE 'LNURL%'")
        free_lucky = c.fetchone()[0]
        conn.close()
        
        if free_lucky == 0:
            logger.info("Lucky voucher pool empty, refilling...")
            create_lucky_vouchers()

def main():
    init_db()
    
    # Clean up any existing invalid entries
    clean_database()
    
    create_lucky_vouchers()
    create_voucher_group()

    updater = Updater(token=TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start_command))
    dp.add_handler(CommandHandler("getvoucher", getvoucher_command))
    dp.add_handler(CommandHandler("info", info_command))
    dp.add_handler(CommandHandler("lucky", lucky_command))
    dp.add_handler(CommandHandler("stats", stats_command))
    dp.add_handler(CommandHandler("cleanup", cleanup_command))
    dp.add_error_handler(error_handler)

    updater.start_polling()
    logger.info("🤖 Fixed Voucher Bot is running.")

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
