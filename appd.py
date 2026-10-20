#!/usr/bin/env python3
"""
Premium OSINT Bot — Full Featured v4
+ Color Buttons Everywhere
+ Number Info + Aadhaar Info (Option 3 Format)
+ 30 Second Auto-Delete
+ Force Join + Referral + Buy + Admin Panel
+ Base URL Update from Bot
+ Small Caps + Bold Styling
"""

import os
import telebot
from telebot import types
import requests
import time
import sqlite3
import threading
import random
import string
import re
from datetime import datetime, date, timedelta, timezone

# ===================== CONFIG =====================
DB_PATH = os.getenv('BOT_DB_PATH', 'data.db')
AUTO_DELETE_SECONDS = 30

BOT_TOKEN = '8918692165:AAHFCUdvmTeFR13jVHSpZy6ayXXg1GUYm2M'
ADMIN_USER_ID = 8644816536
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'dimpiiix')

DEFAULT_BASE_URL = "https://sales-carefully-popular-lists.trycloudflare.com"
API_KEY = os.getenv('SEARCH_API_KEY', 'mysecretkey123')

FORCE_JOIN_CHANNEL_URL = os.getenv('FORCE_JOIN_CHANNEL_URL', 'https://t.me/dimpiii_modz')
FORCE_JOIN_CHANNEL_ID = int(os.getenv('FORCE_JOIN_CHANNEL_ID', '-1003855014631'))
DEVELOPER_LINK = f"https://t.me/{ADMIN_USERNAME}"

# ===================== INIT DB =====================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  first_name TEXT,
                  last_name TEXT,
                  credits INTEGER NOT NULL DEFAULT 0,
                  referred_by INTEGER,
                  total_searches INTEGER DEFAULT 0,
                  join_bonus_claimed INTEGER DEFAULT 0,
                  date_joined TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS banned_users
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  first_name TEXT,
                  last_name TEXT,
                  banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  banned_by INTEGER,
                  reason TEXT DEFAULT 'No reason provided')''')
    c.execute('''CREATE TABLE IF NOT EXISTS bot_settings
                 (setting_key TEXT PRIMARY KEY, setting_value TEXT NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS buy_requests
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  username TEXT,
                  plan TEXT,
                  points INTEGER,
                  price INTEGER,
                  status TEXT DEFAULT 'pending',
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS referral_rewards
                 (user_id INTEGER PRIMARY KEY,
                  referrer_id INTEGER,
                  rewarded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()

    row = c.execute("SELECT setting_value FROM bot_settings WHERE setting_key='base_url'").fetchone()
    if not row:
        c.execute("INSERT INTO bot_settings (setting_key, setting_value) VALUES (?, ?)",
                  ('base_url', DEFAULT_BASE_URL))
        conn.commit()
    conn.close()

init_db()
bot = telebot.TeleBot(BOT_TOKEN)

# ===================== GLOBALS =====================
broadcast_storage = {}
admin_states = {}
buy_pending = {}
join_pending = {}

# ===================== COLOR BUTTON HELPER =====================
def make_button(text, style=None, url=None, callback_data=None, icon_custom_emoji_id=None):
    """Creates a button with style support. Falls back gracefully."""
    try:
        if url:
            btn = types.InlineKeyboardButton(text, url=url)
        elif callback_data:
            btn = types.InlineKeyboardButton(text, callback_data=callback_data)
        else:
            btn = types.KeyboardButton(text)
        if style:
            btn.style = style
        if icon_custom_emoji_id:
            try:
                btn.icon_custom_emoji_id = icon_custom_emoji_id
            except: pass
        return btn
    except:
        # Fallback without style
        if url:
            return types.InlineKeyboardButton(text, url=url)
        elif callback_data:
            return types.InlineKeyboardButton(text, callback_data=callback_data)
        return types.KeyboardButton(text)


def rkb_button(text, style=None):
    """Reply keyboard button with style"""
    try:
        if style:
            return types.KeyboardButton(text, style=style)
        return types.KeyboardButton(text)
    except:
        return types.KeyboardButton(text)


def ikb_button(text, style=None, url=None, callback_data=None):
    """Inline keyboard button with style"""
    try:
        if url:
            return types.InlineKeyboardButton(text, url=url, style=style) if style else types.InlineKeyboardButton(text, url=url)
        if callback_data:
            return types.InlineKeyboardButton(text, callback_data=callback_data, style=style) if style else types.InlineKeyboardButton(text, callback_data=callback_data)
    except:
        if url:
            return types.InlineKeyboardButton(text, url=url)
        return types.InlineKeyboardButton(text, callback_data=callback_data)


# ===================== HELPERS =====================
def get_setting(key, default=None):
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute('SELECT setting_value FROM bot_settings WHERE setting_key = ?', (key,)).fetchone()
        return row[0] if row else default
    finally:
        conn.close()

def set_setting(key, value):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute('INSERT INTO bot_settings(setting_key, setting_value) VALUES (?, ?) ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value', (key, str(value)))
        conn.commit()
    finally:
        conn.close()

def get_base_url():
    return get_setting('base_url', DEFAULT_BASE_URL).rstrip('/')

def save_user(user_id, username, first_name, last_name, referred_by=None):
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute('SELECT user_id FROM users WHERE user_id=?', (user_id,)).fetchone()
        if row:
            conn.execute('UPDATE users SET username=?, first_name=?, last_name=? WHERE user_id=?',
                         (username, first_name, last_name, user_id))
        else:
            conn.execute('INSERT INTO users (user_id, username, first_name, last_name, referred_by) VALUES (?, ?, ?, ?, ?)',
                         (user_id, username, first_name, last_name, referred_by))
        conn.commit()
    finally:
        conn.close()

def get_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def current_balance(user_id):
    user = get_user(user_id)
    return user['credits'] if user else 0

def adjust_credits(user_id, delta):
    conn = sqlite3.connect(DB_PATH, timeout=10, isolation_level='IMMEDIATE')
    try:
        row = conn.execute('SELECT credits FROM users WHERE user_id = ?', (user_id,)).fetchone()
        if not row:
            return None
        new_balance = max(0, row[0] + delta)
        conn.execute('UPDATE users SET credits = ? WHERE user_id = ?', (new_balance, user_id))
        conn.commit()
        return new_balance
    finally:
        conn.close()

def consume_credit(user_id):
    conn = sqlite3.connect(DB_PATH, timeout=10, isolation_level='IMMEDIATE')
    try:
        cur = conn.execute('UPDATE users SET credits = credits - 1 WHERE user_id = ? AND credits > 0', (user_id,))
        if cur.rowcount != 1:
            conn.rollback()
            return None
        conn.execute('UPDATE users SET total_searches = total_searches + 1 WHERE user_id = ?', (user_id,))
        balance = conn.execute('SELECT credits FROM users WHERE user_id = ?', (user_id,)).fetchone()[0]
        conn.commit()
        return balance
    finally:
        conn.close()

def is_user_banned(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute('SELECT * FROM banned_users WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        conn.close()
        return result is not None
    except sqlite3.OperationalError:
        conn.close()
        return False

def ban_user(user_id, username, first_name, last_name, banned_by, reason=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO banned_users 
                 (user_id, username, first_name, last_name, banned_by, reason) 
                 VALUES (?, ?, ?, ?, ?, ?)''',
              (user_id, username, first_name, last_name, banned_by, reason))
    conn.commit()
    conn.close()

def unban_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM banned_users WHERE user_id = ?', (user_id,))
    conn.commit()
    affected = c.rowcount
    conn.close()
    return affected > 0

def get_all_users():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT user_id FROM users')
    users = [row[0] for row in c.fetchall()]
    conn.close()
    return users

def format_address(address_string):
    if not address_string or address_string == "N/A":
        return "N/A"
    return (address_string.replace('!!!!', ', ').replace('!!!', ', ')
            .replace('!!', ', ').replace('!', ', '))

def is_member(user_id):
    try:
        status = bot.get_chat_member(FORCE_JOIN_CHANNEL_ID, user_id).status
        return status in ['member', 'administrator', 'creator']
    except Exception as e:
        print(f"Channel check error: {e}")
        return False

# ===================== AUTO DELETE =====================
def auto_delete_message(chat_id, message_id):
    def delete():
        time.sleep(AUTO_DELETE_SECONDS)
        try:
            bot.delete_message(chat_id, message_id)
        except Exception:
            pass
    threading.Thread(target=delete, daemon=True).start()

def wrapped_send_message(chat_id, text, *args, **kwargs):
    is_announcement = kwargs.pop('is_announcement', False)
    is_admin_log = (chat_id == ADMIN_USER_ID)
    msg = bot.send_message(chat_id, text, *args, **kwargs)
    if not is_announcement and not is_admin_log:
        auto_delete_message(chat_id, msg.message_id)
    return msg

# ===================== API =====================
def fetch_number_info(mobile_number):
    try:
        url = f"{get_base_url()}/search/number?number={mobile_number}&key={API_KEY}"
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if data.get("status") == "success":
                results = data.get("result", [])
                if results:
                    seen = set()
                    transformed = []
                    for item in results:
                        if isinstance(item, dict):
                            key = f"{item.get('num','')}_{item.get('aadhar','')}"
                            if key not in seen:
                                seen.add(key)
                                transformed.append(item)
                    if transformed:
                        return {"status": "success", "results": transformed, "count": len(transformed)}
                return {"status": "no_data"}
        return {"status": "error"}
    except Exception as e:
        print(f"Number API Error: {e}")
        return {"status": "error"}

def fetch_aadhaar_info(aadhaar_number):
    try:
        url = f"{get_base_url()}/search/aadhar?aadhar={aadhaar_number}&key={API_KEY}"
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if data.get("status") == "success":
                results = data.get("result", [])
                if results:
                    main_info = results[0]
                    mobiles = []
                    seen = set()
                    for item in results:
                        m = item.get("num", "N/A")
                        if m != "N/A" and m not in seen:
                            seen.add(m)
                            mobiles.append({
                                "mobile": m,
                                "alt": item.get("alt", "N/A"),
                                "circle": item.get("circle", "N/A")
                            })
                    return {
                        "status": "success",
                        "name": main_info.get("name", "N/A"),
                        "fname": main_info.get("fname", "N/A"),
                        "address": format_address(main_info.get("address", "N/A")),
                        "mobiles": mobiles
                    }
                return {"status": "no_data"}
        return {"status": "error"}
    except Exception as e:
        print(f"Aadhaar API Error: {e}")
        return {"status": "error"}

# ===================== FONT =====================
SMALL_CAPS_MAP = {
    'a': 'ᴀ', 'b': 'ʙ', 'c': 'ᴄ', 'd': 'ᴅ', 'e': 'ᴇ', 'f': 'ꜰ', 'g': 'ɢ',
    'h': 'ʜ', 'i': 'ɪ', 'j': 'ᴊ', 'k': 'ᴋ', 'l': 'ʟ', 'm': 'ᴍ', 'n': 'ɴ',
    'o': 'ᴏ', 'p': 'ᴘ', 'q': 'ǫ', 'r': 'ʀ', 's': 's', 't': 'ᴛ', 'u': 'ᴜ',
    'v': 'ᴠ', 'w': 'ᴡ', 'x': 'x', 'y': 'ʏ', 'z': 'ᴢ',
    'A': 'ᴀ', 'B': 'ʙ', 'C': 'ᴄ', 'D': 'ᴅ', 'E': 'ᴇ', 'F': 'ꜰ', 'G': 'ɢ',
    'H': 'ʜ', 'I': 'ɪ', 'J': 'ᴊ', 'K': 'ᴋ', 'L': 'ʟ', 'M': 'ᴍ', 'N': 'ɴ',
    'O': 'ᴏ', 'P': 'ᴘ', 'Q': 'ǫ', 'R': 'ʀ', 'S': 's', 'T': 'ᴛ', 'U': 'ᴜ',
    'V': 'ᴠ', 'W': 'ᴡ', 'X': 'x', 'Y': 'ʏ', 'Z': 'ᴢ',
}

def scp(text):
    return ''.join(SMALL_CAPS_MAP.get(ch, ch) for ch in str(text))

# ===================== UI =====================
LINE = "━━━━━━━━━━━━━━━━━━━━━━━━━"
LINE_THIN = "─────────────────────"

E_FIRE = "🔥"; E_CROWN = "👑"; E_SPARKLES = "✨"; E_MSG = "💬"
E_PIN = "📌"; E_MONEY = "💰"; E_BOLT = "⚡"; E_TICK = "✔️"
E_CROSS = "❌"; E_WARN = "⚠️"; E_REFRESH = "🔄"; E_STAR = "⭐"
E_GEM = "💎"; E_LOCK = "🔒"; E_SHIELD = "🛡️"; E_HEART_P = "💜"
E_FILE = "📄"; E_SEARCH = "🔍"; E_GEAR = "⚙️"; E_GIFT = "🎁"
E_ARROW = "➡️"; E_MOBILE = "📱"; E_ID = "🆔"; E_MEGA = "📣"
E_USERS = "👥"; E_STATS = "📊"; E_OK = "✅"; E_MENU = "🏠"
E_CART = "🛒"; E_LINK = "🔗"; E_BAN = "🚫"

# ===================== KEYBOARDS =====================
BTN_NUM_INFO     = "📱 ɴᴜᴍʙᴇʀ ɪɴꜰᴏ"
BTN_AADHAAR_INFO = "🆔 ᴀᴀᴅʜᴀᴀʀ ɪɴꜰᴏ"
BTN_BALANCE      = "💰 ʙᴀʟᴀɴᴄᴇ"
BTN_BUY_POINTS   = "🛒 ʙᴜʏ ᴄʀᴇᴅɪᴛs"
BTN_REFERRAL     = "🔗 ʀᴇꜰᴇʀʀᴀʟ"
BTN_ADMIN_PANEL  = "👑 ᴀᴅᴍɪɴ ᴘᴀɴᴇʟ"
BTN_CANCEL       = "🚫 ᴄᴀɴᴄᴇʟ"
BTN_MAIN_MENU    = "🏠 ᴍᴀɪɴ ᴍᴇɴᴜ"


def get_main_keyboard(user_id):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(
        rkb_button(BTN_NUM_INFO, 'primary'),
        rkb_button(BTN_AADHAAR_INFO, 'primary')
    )
    kb.row(
        rkb_button(BTN_BALANCE, 'success'),
        rkb_button(BTN_BUY_POINTS, 'success')
    )
    kb.row(rkb_button(BTN_REFERRAL, 'primary'))
    if user_id == ADMIN_USER_ID:
        kb.row(rkb_button(BTN_ADMIN_PANEL, 'danger'))
    return kb


def get_cancel_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(rkb_button(BTN_CANCEL, 'danger'))
    return kb


def get_join_button_kb():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.row(ikb_button("📢 ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ 📢", style='primary', url=FORCE_JOIN_CHANNEL_URL))
    kb.row(ikb_button("✅ ɪ'ᴠᴇ ᴊᴏɪɴᴇᴅ ✅", style='success', callback_data="check_join"))
    return kb


def get_admin_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(rkb_button("📣 ʙʀᴏᴀᴅᴄᴀsᴛ", 'primary'), rkb_button("📊 sᴛᴀᴛs", 'success'))
    kb.row(rkb_button("👥 ᴜsᴇʀs ʟɪsᴛ", 'primary'), rkb_button("🚫 ʙᴀɴɴᴇᴅ ʟɪsᴛ", 'danger'))
    kb.row(rkb_button("💎 ᴀᴅᴅ ᴘᴏɪɴᴛs", 'success'), rkb_button("❌ ʀᴇᴍᴏᴠᴇ ᴘᴏɪɴᴛs", 'danger'))
    kb.row(rkb_button("🚫 ʙᴀɴ ᴜsᴇʀ", 'danger'), rkb_button("✅ ᴜɴʙᴀɴ ᴜsᴇʀ", 'success'))
    kb.row(rkb_button("🔗 ᴜᴘᴅᴀᴛᴇ ʙᴀsᴇ ᴜʀʟ", 'primary'), rkb_button("💰 ᴘᴇɴᴅɪɴɢ ʙᴜʏs", 'success'))
    kb.row(rkb_button("📢 ᴜᴘᴅᴀᴛᴇ ᴄʜᴀɴɴᴇʟ", 'primary'), rkb_button("🎁 ɢɪᴠᴇ ᴘʀᴇᴍɪᴜᴍ", 'success'))
    kb.row(rkb_button("📨 ᴍsɢ ᴜsᴇʀ", 'primary'), rkb_button("📢 ᴄʜᴀɴɴᴇʟ ʙʀᴏᴀᴅᴄᴀsᴛ", 'primary'))
    kb.row(rkb_button("🔍 ᴄʜᴇᴄᴋ ᴜsᴇʀ", 'primary'), rkb_button("💾 ʙᴀᴄᴋᴜᴘ ᴅʙ", 'success'))
    kb.row(rkb_button("📊 ᴛᴏᴘ ᴜsᴇʀs", 'success'), rkb_button("📈 ᴛᴏᴅᴀʏ sᴛᴀᴛs", 'success'))
    kb.row(rkb_button("🧹 ᴄʟᴇᴀʀ ᴘᴇɴᴅɪɴɢ", 'danger'), rkb_button("🔄 ᴘɪɴɢ ᴀᴘɪ", 'success'))
    kb.row(rkb_button(BTN_MAIN_MENU, 'success'))
    return kb

# ===================== FORCE JOIN =====================
def send_force_join(chat_id, referrer_id=None):
    if referrer_id:
        join_pending[chat_id] = referrer_id

    text = (
        f"╭━━━━━━━━━━━━━━━━━━╮\n"
        f"   {E_LOCK} *{scp('JOIN REQUIRED')}* {E_LOCK}\n"
        f"╰━━━━━━━━━━━━━━━━━━╯\n\n"
        f"{E_WARN} *{scp('Please join our channel to use this bot')}*\n\n"
        f"{E_GIFT} *{scp('Get 2 Free Credits on join!')}*\n"
        f"{E_LINK} *{scp('Get 1 Credit per referral')}*\n\n"
        f"{LINE}\n"
        f"{E_CROWN} *{scp('Owner')}:* @{ADMIN_USERNAME}\n"
        f"{LINE}\n\n"
        f"{E_ARROW} {scp('Click join button, then verify')}"
    )
    bot.send_message(chat_id, text, reply_markup=get_join_button_kb(), parse_mode="Markdown")

# ===================== /start =====================
@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if is_user_banned(user_id):
        bot.send_message(chat_id,
            f"╭━━━━━━━━━━━━━━━━━━╮\n"
            f"   {E_BAN} *{scp('YOU ARE BANNED')}* {E_BAN}\n"
            f"╰━━━━━━━━━━━━━━━━━━╯\n\n"
            f"{E_WARN} {scp('Contact owner to unban')}\n"
            f"{E_CROWN} @{ADMIN_USERNAME}",
            parse_mode="Markdown")
        return

    referrer_id = None
    if len(message.text.split()) > 1:
        try:
            referrer_id = int(message.text.split()[1])
            if referrer_id == user_id:
                referrer_id = None
        except:
            referrer_id = None

    save_user(user_id, message.from_user.username or '',
              message.from_user.first_name or '', message.from_user.last_name or '',
              referrer_id)

    if not is_member(user_id):
        send_force_join(chat_id, referrer_id)
        return

    process_join_bonus(user_id)
    process_referral_bonus(user_id, referrer_id)

    user = get_user(user_id)
    balance = user['credits'] if user else 0

    text = (
        f"╭━━━━━━━━━━━━━━━━━━╮\n"
        f"   {E_FIRE} *{scp('PREMIUM OSINT BOT')}* {E_FIRE}\n"
        f"╰━━━━━━━━━━━━━━━━━━╯\n\n"
        f"{E_SPARKLES} *{scp('Welcome')}, {message.from_user.first_name}!*\n\n"
        f"{E_STAR} *{scp('User ID')}:* `{user_id}`\n"
        f"{E_GEM} *{scp('Credits')}:* {balance}\n"
        f"{E_GEAR} *{scp('Owner')}:* @{ADMIN_USERNAME}\n\n"
        f"{LINE}\n"
        f"{E_SHIELD} *{scp('Services')}:*\n"
        f"• {E_MOBILE} {scp('Number Information')}\n"
        f"• {E_ID} {scp('Aadhaar Information')}\n\n"
        f"{LINE}\n"
        f"{E_BOLT} *{scp('Cost')}:* 1 {scp('Credit per search')}\n"
        f"{E_LINK} *{scp('Referral')}:* 1 {scp('Credit per friend')}\n\n"
        f"{E_HEART_P} _{scp('Use buttons below')}_"
    )
    bot.send_message(chat_id, text, reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")


def process_join_bonus(user_id):
    user = get_user(user_id)
    if not user or user.get('join_bonus_claimed'):
        return
    adjust_credits(user_id, 2)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('UPDATE users SET join_bonus_claimed=1 WHERE user_id=?', (user_id,))
    conn.commit()
    conn.close()
    try:
        bot.send_message(user_id,
            f"╭━━━━━━━━━━━━━━━━━━╮\n"
            f"   {E_GIFT} *{scp('WELCOME BONUS')}* {E_GIFT}\n"
            f"╰━━━━━━━━━━━━━━━━━━╯\n\n"
            f"{E_TICK} *{scp('You got 2 Free Credits!')}*\n\n"
            f"{E_GEM} *{scp('Credits')}:* {current_balance(user_id)}",
            parse_mode="Markdown")
    except: pass

def process_referral_bonus(user_id, referrer_id):
    if not referrer_id or referrer_id == user_id:
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT referred_by FROM users WHERE user_id=?', (user_id,))
    row = c.fetchone()
    if not row or row[0] != referrer_id:
        conn.close()
        return
    c.execute('SELECT 1 FROM referral_rewards WHERE user_id=?', (user_id,))
    if c.fetchone():
        conn.close()
        return
    c.execute('INSERT INTO referral_rewards (user_id, referrer_id) VALUES (?, ?)', (user_id, referrer_id))
    c.execute('UPDATE users SET credits = credits + 1 WHERE user_id=?', (referrer_id,))
    conn.commit()
    conn.close()
    try:
        new_bal = current_balance(referrer_id)
        bot.send_message(referrer_id,
            f"╭━━━━━━━━━━━━━━━━━━╮\n"
            f"   {E_GIFT} *{scp('NEW REFERRAL!')}* {E_GIFT}\n"
            f"╰━━━━━━━━━━━━━━━━━━╯\n\n"
            f"{E_TICK} {scp('Someone joined using your link!')}\n\n"
            f"{E_GEM} *{scp('You Earned')}:* +1 Credit\n"
            f"{E_MONEY} *{scp('Total Credits')}:* {new_bal}\n\n"
            f"{E_SPARKLES} _{scp('Keep sharing to earn more!')}_",
            parse_mode="Markdown")
    except: pass

# ===================== CHECK JOIN =====================
@bot.callback_query_handler(func=lambda call: call.data == "check_join")
def check_join_callback(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id

    try:
        bot.answer_callback_query(call.id)
    except: pass

    if is_member(user_id):
        referrer_id = join_pending.pop(chat_id, None)
        process_join_bonus(user_id)
        process_referral_bonus(user_id, referrer_id)

        try:
            bot.delete_message(chat_id, call.message.message_id)
        except: pass

        balance = current_balance(user_id)
        text = (
            f"╭━━━━━━━━━━━━━━━━━━╮\n"
            f"   {E_TICK} *{scp('VERIFIED')}* {E_TICK}\n"
            f"╰━━━━━━━━━━━━━━━━━━╯\n\n"
            f"{E_SPARKLES} *{scp('Welcome to Premium OSINT Bot!')}*\n\n"
            f"{E_GEM} *{scp('Credits')}:* {balance}\n"
            f"{E_HEART_P} _{scp('Use buttons below')}_"
        )
        bot.send_message(chat_id, text, reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")
    else:
        try:
            bot.answer_callback_query(call.id, "❌ Please join first!", show_alert=True)
        except: pass

# ===================== BALANCE =====================
def show_balance(chat_id, user_id):
    balance = current_balance(user_id)
    user = get_user(user_id)
    ref_count = 0
    if user:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM referral_rewards WHERE referrer_id=?', (user_id,))
        ref_count = c.fetchone()[0]
        conn.close()

    text = (
        f"╭━━━━━━━━━━━━━━━━━━╮\n"
        f"   {E_MONEY} *{scp('MY BALANCE')}* {E_MONEY}\n"
        f"╰━━━━━━━━━━━━━━━━━━╯\n\n"
        f"{E_GEM} *{scp('Credits')}:* {balance}\n"
        f"{E_STATS} *{scp('Total Searches')}:* {user.get('total_searches', 0) if user else 0}\n"
        f"{E_USERS} *{scp('Referrals')}:* {ref_count}\n\n"
        f"{LINE}\n"
        f"{E_BOLT} *{scp('Cost')}:* 1 {scp('Credit per search')}\n\n"
        f"{E_WARN} _{scp('Buy more credits from Buy Credits')}_"
    )
    wrapped_send_message(chat_id, text, reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")

# ===================== BUY CREDITS =====================
def show_buy_points(chat_id, user_id):
    bot_info = bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"

    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.row(
        ikb_button("💎 10 ᴄʀ - ₹100", style='primary', callback_data="buy_10"),
        ikb_button("💎 25 ᴄʀ - ₹220", style='primary', callback_data="buy_25")
    )
    kb.row(
        ikb_button("💎 50 ᴄʀ - ₹400", style='primary', callback_data="buy_50"),
        ikb_button("💎 100 ᴄʀ - ₹700", style='primary', callback_data="buy_100")
    )
    kb.row(ikb_button("💎 500 ᴄʀ - ₹3000", style='primary', callback_data="buy_500"))
    kb.row(ikb_button("📞 ᴄᴏɴᴛᴀᴄᴛ ᴏᴡɴᴇʀ", style='success', url=DEVELOPER_LINK))

    text = (
        f"╭━━━━━━━━━━━━━━━━━━╮\n"
        f"   {E_CART} *{scp('BUY CREDITS')}* {E_CART}\n"
        f"╰━━━━━━━━━━━━━━━━━━╯\n\n"
        f"{E_STAR} *{scp('Available Plans')}:*\n\n"
        f"{E_GEM} *10 ᴄʀᴇᴅɪᴛs* - ₹100\n"
        f"{E_GEM} *25 ᴄʀᴇᴅɪᴛs* - ₹220\n"
        f"{E_GEM} *50 ᴄʀᴇᴅɪᴛs* - ₹400\n"
        f"{E_GEM} *100 ᴄʀᴇᴅɪᴛs* - ₹700\n"
        f"{E_GEM} *500 ᴄʀᴇᴅɪᴛs* - ₹3000\n\n"
        f"{LINE}\n"
        f"{E_BOLT} *1 {scp('Credit')} = 1 {scp('Search')}*\n"
        f"{E_TICK} {scp('Instant activation')}\n\n"
        f"{LINE}\n"
        f"{E_LINK} *{scp('Your Referral Link')}:*\n"
        f"`{ref_link}`\n\n"
        f"{E_GIFT} *{scp('Share to earn 1 credit per friend!')}*\n\n"
        f"{E_WARN} _{scp('Select a plan below')}_"
    )
    wrapped_send_message(chat_id, text, reply_markup=kb, parse_mode="Markdown")


@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def buy_plan_callback(call):
    plan_id = call.data.replace("buy_", "")
    plans = {"10": 100, "25": 220, "50": 400, "100": 700, "500": 3000}

    if plan_id not in plans:
        bot.answer_callback_query(call.id, "Invalid plan!")
        return

    points = int(plan_id)
    price = plans[plan_id]
    user_id = call.from_user.id
    username = call.from_user.username or "N/A"
    first_name = call.from_user.first_name or "User"

    try:
        bot.answer_callback_query(call.id, "✅ Request Sent!")
    except: pass

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO buy_requests (user_id, username, plan, points, price)
                 VALUES (?, ?, ?, ?, ?)''',
              (user_id, username, f"{points} Credits", points, price))
    req_id = c.lastrowid
    conn.commit()
    conn.close()

    text_user = (
        f"╭━━━━━━━━━━━━━━━━━━╮\n"
        f"   {E_TICK} *{scp('REQUEST SENT')}* {E_TICK}\n"
        f"╰━━━━━━━━━━━━━━━━━━╯\n\n"
        f"{E_GEM} *{scp('Plan')}:* {points} Credits\n"
        f"{E_MONEY} *{scp('Price')}:* ₹{price}\n\n"
        f"{LINE}\n"
        f"{E_MSG} *{scp('Contact owner for payment')}:*\n"
        f"{E_CROWN} @{ADMIN_USERNAME}\n\n"
        f"{E_WARN} _{scp('Send screenshot after payment')}_"
    )
    kb = types.InlineKeyboardMarkup()
    kb.row(ikb_button("📞 ᴄᴏɴᴛᴀᴄᴛ ᴏᴡɴᴇʀ", style='success', url=DEVELOPER_LINK))
    wrapped_send_message(call.message.chat.id, text_user, reply_markup=kb, parse_mode="Markdown")

    try:
        admin_kb = types.InlineKeyboardMarkup()
        admin_kb.row(
            ikb_button("✅ ᴀᴘᴘʀᴏᴠᴇ", style='success', callback_data=f"approve_{req_id}"),
            ikb_button("❌ ʀᴇᴊᴇᴄᴛ", style='danger', callback_data=f"reject_{req_id}")
        )
        admin_kb.row(ikb_button("💬 ᴍsɢ ᴜsᴇʀ", style='primary', url=f"tg://user?id={user_id}"))

        bot.send_message(ADMIN_USER_ID,
            f"╭━━━━━━━━━━━━━━━━━━╮\n"
            f"   {E_CART} *{scp('NEW PURCHASE REQUEST')}* {E_CART}\n"
            f"╰━━━━━━━━━━━━━━━━━━╯\n\n"
            f"{E_ID} *{scp('Request ID')}:* `#{req_id}`\n"
            f"{E_STAR} *{scp('User ID')}:* `{user_id}`\n"
            f"{E_USERS} *{scp('Name')}:* {first_name}\n"
            f"{E_MSG} *{scp('Username')}:* @{username}\n\n"
            f"{LINE}\n"
            f"{E_GEM} *{scp('Plan')}:* {points} Credits\n"
            f"{E_MONEY} *{scp('Price')}:* ₹{price}\n"
            f"{LINE}\n\n"
            f"{E_TICK} {scp('Approve or Reject below')}",
            reply_markup=admin_kb, parse_mode="Markdown")
    except Exception as e:
        print(f"Admin notify failed: {e}")


@bot.callback_query_handler(func=lambda call: call.data.startswith(("approve_", "reject_")))
def approve_reject_callback(call):
    if call.from_user.id != ADMIN_USER_ID:
        bot.answer_callback_query(call.id, "❌ Unauthorized", show_alert=True)
        return

    action, req_id = call.data.split("_", 1)
    req_id = int(req_id)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT * FROM buy_requests WHERE id=?', (req_id,))
    req = c.fetchone()

    if not req:
        conn.close()
        bot.answer_callback_query(call.id, "❌ Not found!")
        return

    if req['status'] != 'pending':
        conn.close()
        bot.answer_callback_query(call.id, f"❌ Already {req['status']}!")
        return

    if action == "approve":
        c.execute('UPDATE buy_requests SET status="approved" WHERE id=?', (req_id,))
        c.execute('UPDATE users SET credits = credits + ? WHERE user_id=?', (req['points'], req['user_id']))
        conn.commit()
        conn.close()

        bot.answer_callback_query(call.id, "✅ Approved!")
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except: pass

        try:
            new_bal = current_balance(req['user_id'])
            bot.send_message(req['user_id'],
                f"╭━━━━━━━━━━━━━━━━━━╮\n"
                f"   {E_TICK} *{scp('PURCHASE APPROVED')}* {E_TICK}\n"
                f"╰━━━━━━━━━━━━━━━━━━╯\n\n"
                f"{E_GEM} *{scp('Credits Added')}:* +{req['points']}\n"
                f"{E_MONEY} *{scp('New Balance')}:* {new_bal}\n\n"
                f"{E_SPARKLES} _{scp('Thank you!')}_",
                parse_mode="Markdown")
        except: pass
        bot.send_message(ADMIN_USER_ID, f"✅ Approved #{req_id}")
    else:
        c.execute('UPDATE buy_requests SET status="rejected" WHERE id=?', (req_id,))
        conn.commit()
        conn.close()

        bot.answer_callback_query(call.id, "❌ Rejected!")
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except: pass

        try:
            bot.send_message(req['user_id'],
                f"╭━━━━━━━━━━━━━━━━━━╮\n"
                f"   {E_CROSS} *{scp('REQUEST REJECTED')}* {E_CROSS}\n"
                f"╰━━━━━━━━━━━━━━━━━━╯\n\n"
                f"{E_WARN} {scp('Contact owner for info.')}\n"
                f"{E_CROWN} @{ADMIN_USERNAME}",
                parse_mode="Markdown")
        except: pass
        bot.send_message(ADMIN_USER_ID, f"❌ Rejected #{req_id}")

# ===================== NUMBER INFO =====================
@bot.message_handler(func=lambda m: m.text == BTN_NUM_INFO)
def num_info_start(message):
    user_id = message.from_user.id
    if is_user_banned(user_id): return

    if not is_member(user_id):
        send_force_join(message.chat.id); return

    balance = current_balance(user_id)
    if balance <= 0:
        kb = types.InlineKeyboardMarkup()
        kb.row(ikb_button("🛒 ʙᴜʏ ᴄʀᴇᴅɪᴛs", style='success', callback_data="open_buy"))
        kb.row(ikb_button("📢 ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ", style='primary', url=FORCE_JOIN_CHANNEL_URL))
        text = (
            f"╭━━━━━━━━━━━━━━━━━━╮\n"
            f"   {E_CROSS} *{scp('NO CREDITS')}* {E_CROSS}\n"
            f"╰━━━━━━━━━━━━━━━━━━╯\n\n"
            f"{E_WARN} {scp('You have 0 credits.')}\n\n"
            f"{E_GIFT} {scp('Buy credits or refer friends')}"
        )
        wrapped_send_message(message.chat.id, text, reply_markup=kb, parse_mode="Markdown")
        return

    text = (
        f"╭━━━━━━━━━━━━━━━━━━╮\n"
        f"   {E_MOBILE} *{scp('NUMBER INFO')}* {E_MOBILE}\n"
        f"╰━━━━━━━━━━━━━━━━━━╯\n\n"
        f"{E_GEM} *{scp('Credits')}:* {balance}\n"
        f"{E_MONEY} *{scp('Cost')}:* 1 Credit\n\n"
        f"{LINE}\n"
        f"{E_MSG} {scp('Send the mobile number')}\n"
        f"{E_PIN} {scp('Example')}: `9876543210`\n\n"
        f"{E_WARN} _{scp('Send 10 digit number')}_"
    )
    msg = bot.send_message(message.chat.id, text, reply_markup=get_cancel_keyboard(), parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_num_info)


def process_num_info(message):
    user_id = message.from_user.id
    text = message.text.strip()

    if text == BTN_CANCEL or text in [BTN_NUM_INFO, BTN_AADHAAR_INFO, BTN_BALANCE,
                                       BTN_BUY_POINTS, BTN_REFERRAL, BTN_ADMIN_PANEL]:
        bot.send_message(message.chat.id, f"{E_CROSS} *{scp('Cancelled')}*",
                        reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")
        return

    if not re.fullmatch(r'\d{10,13}', text):
        msg = bot.send_message(message.chat.id,
            f"{E_CROSS} *{scp('Invalid number. Send 10-13 digits.')}*",
            reply_markup=get_cancel_keyboard(), parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_num_info)
        return

    remaining = consume_credit(user_id)
    if remaining is None:
        bot.send_message(message.chat.id, f"{E_CROSS} *{scp('Insufficient credits')}*",
                        reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")
        return

    loading = bot.send_message(message.chat.id,
        f"╭━━━━━━━━━━━━━━━━━━╮\n"
        f"   {E_REFRESH} *{scp('SEARCHING')}* {E_REFRESH}\n"
        f"╰━━━━━━━━━━━━━━━━━━╯\n\n"
        f"{E_SEARCH} {scp('Please wait...')}",
        parse_mode="Markdown")

    result = fetch_number_info(text)

    try:
        bot.delete_message(message.chat.id, loading.message_id)
    except: pass

    if result.get("status") == "success":
        results = result.get("results", [])
        total = len(results)

        text_out = (
            f"╭━━━━━━━━━━━━━━━━━━╮\n"
            f"   📱 *{scp('NUMBER INFO')}* 📱\n"
            f"╰━━━━━━━━━━━━━━━━━━╯\n\n"
            f"📌 *{scp('Number')}:* `{text}`\n"
            f"📊 *{scp('Records')}:* *{total}*\n\n"
            f"{LINE}\n\n"
        )

        for i, rec in enumerate(results[:5], 1):
            text_out += (
                f"⭐ *{scp('RECORD')} #{i}*\n"
                f"{LINE_THIN}\n"
                f"🆔 *{scp('Aadhaar')}:* `{rec.get('aadhar', 'N/A')}`\n"
                f"👤 *{scp('Name')}:* *{rec.get('name', 'N/A')}*\n"
                f"👨 *{scp('Father')}:* *{rec.get('fname', 'N/A')}*\n"
                f"📱 *{scp('Alt Mobile')}:* `{rec.get('alt', 'N/A')}`\n"
                f"🛡️ *{scp('Circle')}:* *{rec.get('circle', 'N/A')}*\n"
                f"📧 *{scp('Email')}:* `{rec.get('email', 'N/A')}`\n"
                f"📍 *{scp('Address')}:* _{format_address(rec.get('address', 'N/A'))}_\n\n"
            )

        text_out += (
            f"{LINE}\n"
            f"💎 *{scp('Credits Left')}:* *{remaining}*\n\n"
            f"⏱️ _This message will self-destruct in 30 seconds_"
        )

        wrapped_send_message(message.chat.id, text_out,
                            reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")
    elif result.get("status") == "no_data":
        adjust_credits(user_id, 1)
        wrapped_send_message(message.chat.id,
            f"╭━━━━━━━━━━━━━━━━━━╮\n"
            f"   {E_CROSS} *{scp('NO DATA')}* {E_CROSS}\n"
            f"╰━━━━━━━━━━━━━━━━━━╯\n\n"
            f"{E_WARN} {scp('No data found for this number.')}\n\n"
            f"{E_TICK} _{scp('Credit refunded')}_",
            reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")
    else:
        adjust_credits(user_id, 1)
        wrapped_send_message(message.chat.id,
            f"╭━━━━━━━━━━━━━━━━━━╮\n"
            f"   {E_CROSS} *{scp('ERROR')}* {E_CROSS}\n"
            f"╰━━━━━━━━━━━━━━━━━━╯\n\n"
            f"{E_WARN} {scp('API error occurred.')}\n\n"
            f"{E_TICK} _{scp('Credit refunded')}_",
            reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")

# ===================== AADHAAR INFO =====================
@bot.message_handler(func=lambda m: m.text == BTN_AADHAAR_INFO)
def aadhaar_info_start(message):
    user_id = message.from_user.id
    if is_user_banned(user_id): return

    if not is_member(user_id):
        send_force_join(message.chat.id); return

    balance = current_balance(user_id)
    if balance <= 0:
        kb = types.InlineKeyboardMarkup()
        kb.row(ikb_button("🛒 ʙᴜʏ ᴄʀᴇᴅɪᴛs", style='success', callback_data="open_buy"))
        kb.row(ikb_button("📢 ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ", style='primary', url=FORCE_JOIN_CHANNEL_URL))
        text = (
            f"╭━━━━━━━━━━━━━━━━━━╮\n"
            f"   {E_CROSS} *{scp('NO CREDITS')}* {E_CROSS}\n"
            f"╰━━━━━━━━━━━━━━━━━━╯\n\n"
            f"{E_WARN} {scp('You have 0 credits.')}\n\n"
            f"{E_GIFT} {scp('Buy credits or refer friends')}"
        )
        wrapped_send_message(message.chat.id, text, reply_markup=kb, parse_mode="Markdown")
        return

    text = (
        f"╭━━━━━━━━━━━━━━━━━━╮\n"
        f"   {E_ID} *{scp('AADHAAR INFO')}* {E_ID}\n"
        f"╰━━━━━━━━━━━━━━━━━━╯\n\n"
        f"{E_GEM} *{scp('Credits')}:* {balance}\n"
        f"{E_MONEY} *{scp('Cost')}:* 1 Credit\n\n"
        f"{LINE}\n"
        f"{E_MSG} {scp('Send the Aadhaar number')}\n"
        f"{E_PIN} {scp('Example')}: `123456789012`\n\n"
        f"{E_WARN} _{scp('Send 12 digit Aadhaar')}_"
    )
    msg = bot.send_message(message.chat.id, text, reply_markup=get_cancel_keyboard(), parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_aadhaar_info)


def process_aadhaar_info(message):
    user_id = message.from_user.id
    text = message.text.strip()

    if text == BTN_CANCEL or text in [BTN_NUM_INFO, BTN_AADHAAR_INFO, BTN_BALANCE,
                                       BTN_BUY_POINTS, BTN_REFERRAL, BTN_ADMIN_PANEL]:
        bot.send_message(message.chat.id, f"{E_CROSS} *{scp('Cancelled')}*",
                        reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")
        return

    if not re.fullmatch(r'\d{12}', text):
        msg = bot.send_message(message.chat.id,
            f"{E_CROSS} *{scp('Invalid Aadhaar. Send 12 digits.')}*",
            reply_markup=get_cancel_keyboard(), parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_aadhaar_info)
        return

    remaining = consume_credit(user_id)
    if remaining is None:
        bot.send_message(message.chat.id, f"{E_CROSS} *{scp('Insufficient credits')}*",
                        reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")
        return

    loading = bot.send_message(message.chat.id,
        f"╭━━━━━━━━━━━━━━━━━━╮\n"
        f"   {E_REFRESH} *{scp('SEARCHING')}* {E_REFRESH}\n"
        f"╰━━━━━━━━━━━━━━━━━━╯\n\n"
        f"{E_SEARCH} {scp('Please wait...')}",
        parse_mode="Markdown")

    result = fetch_aadhaar_info(text)

    try:
        bot.delete_message(message.chat.id, loading.message_id)
    except: pass

    if result.get("status") == "success":
        mobiles = result.get("mobiles", [])
        name = result.get("name", "N/A")
        fname = result.get("fname", "N/A")
        address = result.get("address", "N/A")

        text_out = (
            f"╭━━━━━━━━━━━━━━━━━━╮\n"
            f"   🆔 *{scp('AADHAAR INFO')}* 🆔\n"
            f"╰━━━━━━━━━━━━━━━━━━╯\n\n"
            f"🔒 *{scp('Aadhaar')}:* `{text[:4]}XXXX{text[-4:]}`\n"
            f"📊 *{scp('Linked Mobiles')}:* *{len(mobiles)}*\n\n"
            f"{LINE}\n"
            f"👤 *{scp('Name')}:* *{name}*\n"
            f"👨 *{scp('Father')}:* *{fname}*\n"
            f"📍 *{scp('Address')}:* _{address}_\n\n"
            f"{LINE}\n"
            f"📱 *{scp('LINKED NUMBERS')}:*\n\n"
        )

        for i, m in enumerate(mobiles[:10], 1):
            mob = m.get('mobile', 'N/A')
            circle = m.get('circle', 'N/A')
            alt = m.get('alt', 'N/A')
            text_out += (
                f"⭐ *#{i}* `{mob}`\n"
                f"   🛡️ *{scp('Circle')}:* *{circle}*\n"
            )
            if alt != "N/A":
                text_out += f"   📱 *{scp('Alt')}:* `{alt}`\n"
            text_out += "\n"

        text_out += (
            f"{LINE}\n"
            f"💎 *{scp('Credits Left')}:* *{remaining}*\n\n"
            f"⏱️ _This message will self-destruct in 30 seconds_"
        )

        wrapped_send_message(message.chat.id, text_out,
                            reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")

    elif result.get("status") == "no_data":
        adjust_credits(user_id, 1)
        wrapped_send_message(message.chat.id,
            f"╭━━━━━━━━━━━━━━━━━━╮\n"
            f"   {E_CROSS} *{scp('NO DATA')}* {E_CROSS}\n"
            f"╰━━━━━━━━━━━━━━━━━━╯\n\n"
            f"{E_WARN} {scp('No data found for this Aadhaar.')}\n\n"
            f"{E_TICK} _{scp('Credit refunded')}_",
            reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")
    else:
        adjust_credits(user_id, 1)
        wrapped_send_message(message.chat.id,
            f"╭━━━━━━━━━━━━━━━━━━╮\n"
            f"   {E_CROSS} *{scp('ERROR')}* {E_CROSS}\n"
            f"╰━━━━━━━━━━━━━━━━━━╯\n\n"
            f"{E_WARN} {scp('API error occurred.')}\n\n"
            f"{E_TICK} _{scp('Credit refunded')}_",
            reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")

# ===================== REFERRAL =====================
@bot.message_handler(func=lambda m: m.text == BTN_REFERRAL)
def referral_handler(message):
    user_id = message.from_user.id
    if is_user_banned(user_id): return
    if not is_member(user_id):
        send_force_join(message.chat.id); return

    bot_info = bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM referral_rewards WHERE referrer_id=?', (user_id,))
    ref_count = c.fetchone()[0]
    conn.close()

    text = (
        f"╭━━━━━━━━━━━━━━━━━━╮\n"
        f"   {E_USERS} *{scp('REFERRAL SYSTEM')}* {E_USERS}\n"
        f"╰━━━━━━━━━━━━━━━━━━╯\n\n"
        f"{E_LINK} *{scp('Your Referral Link')}:*\n"
        f"`{ref_link}`\n\n"
        f"{E_STAR} *{scp('Your ID')}:* `{user_id}`\n"
        f"{E_USERS} *{scp('Total Referrals')}:* {ref_count}\n"
        f"{E_GEM} *{scp('Credits Earned')}:* {ref_count}\n\n"
        f"{LINE}\n"
        f"{E_SPARKLES} *{scp('How it works')}:*\n"
        f"• {scp('Share your link with friends')}\n"
        f"• {scp('They join & verify channel')}\n"
        f"• {scp('You get 1 credit per referral')}\n"
        f"• {scp('Credits added automatically')}\n\n"
        f"{E_GIFT} *{scp('Share more')} → {scp('Earn more!')}*"
    )
    wrapped_send_message(message.chat.id, text, parse_mode="Markdown")

# ===================== ADMIN PANEL =====================
@bot.message_handler(func=lambda m: m.text == BTN_ADMIN_PANEL and m.from_user.id == ADMIN_USER_ID)
def admin_panel(message):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    total_users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_banned = c.execute("SELECT COUNT(*) FROM banned_users").fetchone()[0]
    total_credits = c.execute("SELECT COALESCE(SUM(credits),0) FROM users").fetchone()[0]
    total_searches = c.execute("SELECT COALESCE(SUM(total_searches),0) FROM users").fetchone()[0]
    pending_buys = c.execute("SELECT COUNT(*) FROM buy_requests WHERE status='pending'").fetchone()[0]
    total_referrals = c.execute("SELECT COUNT(*) FROM referral_rewards").fetchone()[0]
    conn.close()

    current_url = get_base_url()

    text = (
        f"╭━━━━━━━━━━━━━━━━━━╮\n"
        f"   {E_CROWN} *{scp('ADMIN PANEL')}* {E_CROWN}\n"
        f"╰━━━━━━━━━━━━━━━━━━╯\n\n"
        f"{E_USERS} *{scp('Total Users')}:* {total_users}\n"
        f"{E_BAN} *{scp('Banned Users')}:* {total_banned}\n"
        f"{E_GEM} *{scp('Total Credits')}:* {total_credits}\n"
        f"{E_SEARCH} *{scp('Total Searches')}:* {total_searches}\n"
        f"{E_LINK} *{scp('Total Referrals')}:* {total_referrals}\n"
        f"{E_CART} *{scp('Pending Buys')}:* {pending_buys}\n\n"
        f"{LINE}\n"
        f"{E_LINK} *{scp('Base URL')}:*\n"
        f"`{current_url}`\n"
        f"{LINE}\n\n"
        f"{E_GEAR} *{scp('Admin Tools')}:*\n"
        f"Use buttons below"
    )
    bot.send_message(message.chat.id, text, reply_markup=get_admin_keyboard(), parse_mode="Markdown")

# ============ ADMIN BUTTON HANDLERS ============
@bot.message_handler(func=lambda m: m.text == "📣 ʙʀᴏᴀᴅᴄᴀsᴛ" and m.from_user.id == ADMIN_USER_ID)
def admin_broadcast_start(message):
    msg = bot.send_message(message.chat.id,
        f"{E_MEGA} *{scp('Broadcast Mode')}*\n\n"
        f"{E_MSG} {scp('Send the message to broadcast')}\n"
        f"{E_MSG} {scp('Or send photo with caption')}\n\n"
        f"{E_CROSS} {scp('Send')} /cancel {scp('to abort')}",
        reply_markup=get_cancel_keyboard(), parse_mode="Markdown")
    bot.register_next_step_handler(msg, admin_broadcast_process)

def admin_broadcast_process(message):
    if message.text == BTN_CANCEL:
        bot.send_message(message.chat.id, f"{E_CROSS} *{scp('Cancelled')}*",
                        reply_markup=get_admin_keyboard(), parse_mode="Markdown")
        return
    user_ids = get_all_users()
    sent = 0; failed = 0
    status = bot.send_message(message.chat.id,
        f"{E_REFRESH} {scp('Sending to')} {len(user_ids)} {scp('users...')}",
        parse_mode="Markdown")
    for uid in user_ids:
        try:
            if message.photo:
                bot.send_photo(uid, message.photo[-1].file_id, caption=message.caption or "", parse_mode="Markdown")
            elif message.text:
                bot.send_message(uid, message.text, parse_mode="Markdown")
            elif message.video:
                bot.send_video(uid, message.video.file_id, caption=message.caption or "", parse_mode="Markdown")
            sent += 1
        except:
            failed += 1
        time.sleep(0.05)
    bot.edit_message_text(
        f"╭━━━━━━━━━━━━━━━━━━╮\n"
        f"   {E_TICK} *{scp('BROADCAST DONE')}* {E_TICK}\n"
        f"╰━━━━━━━━━━━━━━━━━━╯\n\n"
        f"{E_TICK} {scp('Sent')}: {sent}\n"
        f"{E_CROSS} {scp('Failed')}: {failed}",
        chat_id=message.chat.id, message_id=status.message_id, parse_mode="Markdown")
    bot.send_message(message.chat.id, "✅ Done", reply_markup=get_admin_keyboard())


@bot.message_handler(func=lambda m: m.text == "📊 sᴛᴀᴛs" and m.from_user.id == ADMIN_USER_ID)
def admin_stats(message):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    total_users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_credits = c.execute("SELECT COALESCE(SUM(credits),0) FROM users").fetchone()[0]
    total_searches = c.execute("SELECT COALESCE(SUM(total_searches),0) FROM users").fetchone()[0]
    total_banned = c.execute("SELECT COUNT(*) FROM banned_users").fetchone()[0]
    pending_buys = c.execute("SELECT COUNT(*) FROM buy_requests WHERE status='pending'").fetchone()[0]
    total_referrals = c.execute("SELECT COUNT(*) FROM referral_rewards").fetchone()[0]
    conn.close()
    text = (
        f"╭━━━━━━━━━━━━━━━━━━╮\n"
        f"   {E_STATS} *{scp('BOT STATISTICS')}* {E_STATS}\n"
        f"╰━━━━━━━━━━━━━━━━━━╯\n\n"
        f"{E_USERS} {scp('Total Users')}: {total_users}\n"
        f"{E_GEM} {scp('Total Credits')}: {total_credits}\n"
        f"{E_SEARCH} {scp('Total Searches')}: {total_searches}\n"
        f"{E_LINK} {scp('Total Referrals')}: {total_referrals}\n"
        f"{E_BAN} {scp('Banned Users')}: {total_banned}\n"
        f"{E_CART} {scp('Pending Buys')}: {pending_buys}\n\n"
        f"{E_BOLT} {scp('Status')}: {E_TICK} {scp('Online')}"
    )
    bot.send_message(message.chat.id, text, reply_markup=get_admin_keyboard(), parse_mode="Markdown")


@bot.message_handler(func=lambda m: m.text == "👥 ᴜsᴇʀs ʟɪsᴛ" and m.from_user.id == ADMIN_USER_ID)
def admin_users_list(message):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT user_id, first_name, credits FROM users ORDER BY credits DESC LIMIT 50')
    users = c.fetchall()
    conn.close()
    text = f"╭━━━━━━━━━━━━━━━━━━╮\n   {E_USERS} *{scp('USERS LIST')}* {E_USERS}\n╰━━━━━━━━━━━━━━━━━━╯\n\n"
    for u in users:
        text += f"• `{u['user_id']}` — *{u['first_name'] or 'User'}* ({u['credits']}c)\n"
    bot.send_message(message.chat.id, text, parse_mode="Markdown")


@bot.message_handler(func=lambda m: m.text == "🚫 ʙᴀɴɴᴇᴅ ʟɪsᴛ" and m.from_user.id == ADMIN_USER_ID)
def admin_banned_list(message):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT user_id, first_name, reason FROM banned_users')
    users = c.fetchall()
    conn.close()
    if not users:
        bot.send_message(message.chat.id, f"{E_TICK} {scp('No banned users')}",
                        reply_markup=get_admin_keyboard()); return
    text = f"╭━━━━━━━━━━━━━━━━━━╮\n   {E_BAN} *{scp('BANNED USERS')}* {E_BAN}\n╰━━━━━━━━━━━━━━━━━━╯\n\n"
    for u in users:
        text += f"• `{u[0]}` — *{u[1] or 'User'}*\n   _{u[2] or 'No reason'}_\n\n"
    bot.send_message(message.chat.id, text, parse_mode="Markdown")


@bot.message_handler(func=lambda m: m.text == "💎 ᴀᴅᴅ ᴘᴏɪɴᴛs" and m.from_user.id == ADMIN_USER_ID)
def admin_add_points_start(message):
    msg = bot.send_message(message.chat.id,
        f"{E_GEM} *{scp('Add Credits')}*\n\n{E_MSG} Format: `user_id amount`",
        reply_markup=get_cancel_keyboard(), parse_mode="Markdown")
    bot.register_next_step_handler(msg, admin_add_points_process)

def admin_add_points_process(message):
    if message.text == BTN_CANCEL:
        bot.send_message(message.chat.id, f"{E_CROSS} *{scp('Cancelled')}*",
                        reply_markup=get_admin_keyboard(), parse_mode="Markdown"); return
    parts = message.text.split()
    if len(parts) != 2:
        bot.send_message(message.chat.id, f"{E_CROSS} {scp('Invalid format')}",
                        reply_markup=get_admin_keyboard()); return
    try:
        uid = int(parts[0]); amt = int(parts[1])
    except:
        bot.send_message(message.chat.id, f"{E_CROSS} {scp('Invalid values')}",
                        reply_markup=get_admin_keyboard()); return
    new_bal = adjust_credits(uid, amt)
    if new_bal is None:
        bot.send_message(message.chat.id, f"{E_CROSS} {scp('User not found')}",
                        reply_markup=get_admin_keyboard()); return
    bot.send_message(message.chat.id,
        f"{E_TICK} {scp('Added')} {amt} {scp('credits to')} `{uid}`\n"
        f"{E_GEM} {scp('New balance')}: {new_bal}",
        reply_markup=get_admin_keyboard(), parse_mode="Markdown")
    try:
        bot.send_message(uid, f"💎 *{scp('Credits Added')}*\n+{amt}\nBalance: {new_bal}",
                        parse_mode="Markdown")
    except: pass


@bot.message_handler(func=lambda m: m.text == "❌ ʀᴇᴍᴏᴠᴇ ᴘᴏɪɴᴛs" and m.from_user.id == ADMIN_USER_ID)
def admin_remove_points_start(message):
    msg = bot.send_message(message.chat.id,
        f"{E_CROSS} *{scp('Remove Credits')}*\n\n{E_MSG} Format: `user_id amount`",
        reply_markup=get_cancel_keyboard(), parse_mode="Markdown")
    bot.register_next_step_handler(msg, admin_remove_points_process)

def admin_remove_points_process(message):
    if message.text == BTN_CANCEL:
        bot.send_message(message.chat.id, f"{E_CROSS} *{scp('Cancelled')}*",
                        reply_markup=get_admin_keyboard(), parse_mode="Markdown"); return
    parts = message.text.split()
    if len(parts) != 2:
        bot.send_message(message.chat.id, f"{E_CROSS} {scp('Invalid format')}",
                        reply_markup=get_admin_keyboard()); return
    try:
        uid = int(parts[0]); amt = int(parts[1])
    except:
        bot.send_message(message.chat.id, f"{E_CROSS} {scp('Invalid values')}",
                        reply_markup=get_admin_keyboard()); return
    new_bal = adjust_credits(uid, -amt)
    if new_bal is None:
        bot.send_message(message.chat.id, f"{E_CROSS} {scp('User not found')}",
                        reply_markup=get_admin_keyboard()); return
    bot.send_message(message.chat.id,
        f"{E_TICK} {scp('Removed')} {amt} {scp('credits from')} `{uid}`\n"
        f"{E_GEM} {scp('New balance')}: {new_bal}",
        reply_markup=get_admin_keyboard(), parse_mode="Markdown")


@bot.message_handler(func=lambda m: m.text == "🚫 ʙᴀɴ ᴜsᴇʀ" and m.from_user.id == ADMIN_USER_ID)
def admin_ban_start(message):
    msg = bot.send_message(message.chat.id,
        f"{E_BAN} *{scp('Ban User')}*\n\n{E_MSG} Format: `user_id reason`",
        reply_markup=get_cancel_keyboard(), parse_mode="Markdown")
    bot.register_next_step_handler(msg, admin_ban_process)

def admin_ban_process(message):
    if message.text == BTN_CANCEL:
        bot.send_message(message.chat.id, f"{E_CROSS} *{scp('Cancelled')}*",
                        reply_markup=get_admin_keyboard(), parse_mode="Markdown"); return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 1:
        bot.send_message(message.chat.id, f"{E_CROSS} {scp('Invalid format')}",
                        reply_markup=get_admin_keyboard()); return
    try:
        uid = int(parts[0])
    except:
        bot.send_message(message.chat.id, f"{E_CROSS} {scp('Invalid user ID')}",
                        reply_markup=get_admin_keyboard()); return
    reason = parts[1] if len(parts) > 1 else "Violation of rules"
    user = get_user(uid)
    if not user:
        bot.send_message(message.chat.id, f"{E_CROSS} {scp('User not found')}",
                        reply_markup=get_admin_keyboard()); return
    ban_user(uid, user.get('username', ''), user.get('first_name', ''),
             user.get('last_name', ''), ADMIN_USER_ID, reason)
    bot.send_message(message.chat.id,
        f"{E_TICK} {scp('Banned')} `{uid}`\n{E_WARN} {scp('Reason')}: {reason}",
        reply_markup=get_admin_keyboard(), parse_mode="Markdown")
    try:
        bot.send_message(uid, f"🚫 *{scp('You are banned')}*\nReason: {reason}",
                        parse_mode="Markdown")
    except: pass


@bot.message_handler(func=lambda m: m.text == "✅ ᴜɴʙᴀɴ ᴜsᴇʀ" and m.from_user.id == ADMIN_USER_ID)
def admin_unban_start(message):
    msg = bot.send_message(message.chat.id,
        f"{E_OK} *{scp('Unban User')}*\n\n{E_MSG} Send user ID",
        reply_markup=get_cancel_keyboard(), parse_mode="Markdown")
    bot.register_next_step_handler(msg, admin_unban_process)

def admin_unban_process(message):
    if message.text == BTN_CANCEL:
        bot.send_message(message.chat.id, f"{E_CROSS} *{scp('Cancelled')}*",
                        reply_markup=get_admin_keyboard(), parse_mode="Markdown"); return
    try:
        uid = int(message.text.strip())
    except:
        bot.send_message(message.chat.id, f"{E_CROSS} {scp('Invalid ID')}",
                        reply_markup=get_admin_keyboard()); return
    if unban_user(uid):
        bot.send_message(message.chat.id, f"{E_TICK} {scp('Unbanned')} `{uid}`",
                        reply_markup=get_admin_keyboard(), parse_mode="Markdown")
        try:
            bot.send_message(uid, f"✅ *{scp('You have been unbanned!')}*", parse_mode="Markdown")
        except: pass
    else:
        bot.send_message(message.chat.id, f"{E_CROSS} {scp('User not banned')}",
                        reply_markup=get_admin_keyboard())


@bot.message_handler(func=lambda m: m.text == "🔗 ᴜᴘᴅᴀᴛᴇ ʙᴀsᴇ ᴜʀʟ" and m.from_user.id == ADMIN_USER_ID)
def admin_update_url_start(message):
    current = get_base_url()
    msg = bot.send_message(message.chat.id,
        f"{E_LINK} *{scp('Update Base URL')}*\n\n"
        f"{E_MSG} Current:\n`{current}`\n\n"
        f"{E_PIN} Send new URL",
        reply_markup=get_cancel_keyboard(), parse_mode="Markdown")
    bot.register_next_step_handler(msg, admin_update_url_process)

def admin_update_url_process(message):
    if message.text == BTN_CANCEL:
        bot.send_message(message.chat.id, f"{E_CROSS} *{scp('Cancelled')}*",
                        reply_markup=get_admin_keyboard(), parse_mode="Markdown"); return
    new_url = message.text.strip()
    if not new_url.startswith("http"):
        bot.send_message(message.chat.id, f"{E_CROSS} {scp('Invalid URL')}",
                        reply_markup=get_admin_keyboard()); return
    set_setting('base_url', new_url)
    bot.send_message(message.chat.id,
        f"{E_TICK} *{scp('Base URL Updated')}*\n\n`{new_url}`",
        reply_markup=get_admin_keyboard(), parse_mode="Markdown")


@bot.message_handler(func=lambda m: m.text == "💰 ᴘᴇɴᴅɪɴɢ ʙᴜʏs" and m.from_user.id == ADMIN_USER_ID)
def admin_pending_buys(message):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, user_id, username, plan, points, price, created_at FROM buy_requests WHERE status="pending" ORDER BY created_at DESC LIMIT 20')
    rows = c.fetchall()
    conn.close()
    if not rows:
        bot.send_message(message.chat.id, f"{E_TICK} {scp('No pending buys')}",
                        reply_markup=get_admin_keyboard()); return
    text = f"╭━━━━━━━━━━━━━━━━━━╮\n   {E_MONEY} *{scp('PENDING BUYS')}* {E_MONEY}\n╰━━━━━━━━━━━━━━━━━━╯\n\n"
    for r in rows:
        text += (f"{E_STAR} *ID:* `#{r[0]}`\n"
                 f"{E_USERS} *User:* `{r[1]}` (@{r[2]})\n"
                 f"{E_GEM} *Plan:* {r[3]}\n"
                 f"{E_MONEY} *Price:* ₹{r[5]}\n"
                 f"{LINE}\n")
    bot.send_message(message.chat.id, text, parse_mode="Markdown")


@bot.message_handler(func=lambda m: m.text == "📢 ᴜᴘᴅᴀᴛᴇ ᴄʜᴀɴɴᴇʟ" and m.from_user.id == ADMIN_USER_ID)
def admin_update_channel(message):
    msg = bot.send_message(message.chat.id,
        f"{E_MEGA} *{scp('Update Channel')}*\n\n"
        f"Current: `{FORCE_JOIN_CHANNEL_URL}`\n\n"
        f"Send new channel URL",
        reply_markup=get_cancel_keyboard(), parse_mode="Markdown")
    bot.register_next_step_handler(msg, admin_update_channel_process)

def admin_update_channel_process(message):
    if message.text == BTN_CANCEL:
        bot.send_message(message.chat.id, f"{E_CROSS} *{scp('Cancelled')}*",
                        reply_markup=get_admin_keyboard(), parse_mode="Markdown"); return
    set_setting('channel_url', message.text.strip())
    bot.send_message(message.chat.id, f"{E_TICK} {scp('Channel updated')}",
                    reply_markup=get_admin_keyboard())


@bot.message_handler(func=lambda m: m.text == "🎁 ɢɪᴠᴇ ᴘʀᴇᴍɪᴜᴍ" and m.from_user.id == ADMIN_USER_ID)
def admin_give_premium(message):
    msg = bot.send_message(message.chat.id,
        f"{E_GIFT} *{scp('Give Credits')}*\n\nFormat: `user_id amount`",
        reply_markup=get_cancel_keyboard(), parse_mode="Markdown")
    bot.register_next_step_handler(msg, admin_give_premium_process)

def admin_give_premium_process(message):
    if message.text == BTN_CANCEL:
        bot.send_message(message.chat.id, f"{E_CROSS} *{scp('Cancelled')}*",
                        reply_markup=get_admin_keyboard(), parse_mode="Markdown"); return
    parts = message.text.split()
    if len(parts) != 2:
        bot.send_message(message.chat.id, f"{E_CROSS} {scp('Invalid format')}",
                        reply_markup=get_admin_keyboard()); return
    try:
        uid = int(parts[0]); amt = int(parts[1])
    except:
        bot.send_message(message.chat.id, f"{E_CROSS} {scp('Invalid values')}",
                        reply_markup=get_admin_keyboard()); return
    new_bal = adjust_credits(uid, amt)
    if new_bal is None:
        bot.send_message(message.chat.id, f"{E_CROSS} {scp('User not found')}",
                        reply_markup=get_admin_keyboard()); return
    bot.send_message(message.chat.id, f"{E_TICK} {scp('Gave')} {amt} {scp('to')} `{uid}`",
                    reply_markup=get_admin_keyboard(), parse_mode="Markdown")
    try:
        bot.send_message(uid, f"🎁 *{scp('Gift Credits')}*\n+{amt}\nBalance: {new_bal}",
                        parse_mode="Markdown")
    except: pass


@bot.message_handler(func=lambda m: m.text == "📨 ᴍsɢ ᴜsᴇʀ" and m.from_user.id == ADMIN_USER_ID)
def admin_msg_user(message):
    msg = bot.send_message(message.chat.id,
        f"{E_MSG} *{scp('Message User')}*\n\nFormat: `user_id message`",
        reply_markup=get_cancel_keyboard(), parse_mode="Markdown")
    bot.register_next_step_handler(msg, admin_msg_user_process)

def admin_msg_user_process(message):
    if message.text == BTN_CANCEL:
        bot.send_message(message.chat.id, f"{E_CROSS} *{scp('Cancelled')}*",
                        reply_markup=get_admin_keyboard(), parse_mode="Markdown"); return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.send_message(message.chat.id, f"{E_CROSS} {scp('Invalid format')}",
                        reply_markup=get_admin_keyboard()); return
    try:
        uid = int(parts[0])
    except:
        bot.send_message(message.chat.id, f"{E_CROSS} {scp('Invalid user ID')}",
                        reply_markup=get_admin_keyboard()); return
    try:
        bot.send_message(uid, f"{E_MEGA} *{scp('Message from Admin')}*\n\n{parts[1]}",
                        parse_mode="Markdown")
        bot.send_message(message.chat.id, f"{E_TICK} {scp('Message sent')}",
                        reply_markup=get_admin_keyboard())
    except Exception as e:
        bot.send_message(message.chat.id, f"{E_CROSS} {scp('Failed')}: {e}",
                        reply_markup=get_admin_keyboard())


@bot.message_handler(func=lambda m: m.text == "📢 ᴄʜᴀɴɴᴇʟ ʙʀᴏᴀᴅᴄᴀsᴛ" and m.from_user.id == ADMIN_USER_ID)
def admin_channel_broadcast(message):
    msg = bot.send_message(message.chat.id,
        f"{E_MEGA} *{scp('Channel Broadcast')}*\n\nFormat: `channel_id message`",
        reply_markup=get_cancel_keyboard(), parse_mode="Markdown")
    bot.register_next_step_handler(msg, admin_channel_broadcast_process)

def admin_channel_broadcast_process(message):
    if message.text == BTN_CANCEL:
        bot.send_message(message.chat.id, f"{E_CROSS} *{scp('Cancelled')}*",
                        reply_markup=get_admin_keyboard(), parse_mode="Markdown"); return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.send_message(message.chat.id, f"{E_CROSS} {scp('Invalid format')}",
                        reply_markup=get_admin_keyboard()); return
    try:
        cid = int(parts[0])
        bot.send_message(cid, parts[1], parse_mode="Markdown")
        bot.send_message(message.chat.id, f"{E_TICK} {scp('Sent to channel')}",
                        reply_markup=get_admin_keyboard())
    except Exception as e:
        bot.send_message(message.chat.id, f"{E_CROSS} {scp('Failed')}: {e}",
                        reply_markup=get_admin_keyboard())


@bot.message_handler(func=lambda m: m.text == "🔍 ᴄʜᴇᴄᴋ ᴜsᴇʀ" and m.from_user.id == ADMIN_USER_ID)
def admin_check_user(message):
    msg = bot.send_message(message.chat.id,
        f"{E_SEARCH} *{scp('Check User')}*\n\nSend user ID",
        reply_markup=get_cancel_keyboard(), parse_mode="Markdown")
    bot.register_next_step_handler(msg, admin_check_user_process)

def admin_check_user_process(message):
    if message.text == BTN_CANCEL:
        bot.send_message(message.chat.id, f"{E_CROSS} *{scp('Cancelled')}*",
                        reply_markup=get_admin_keyboard(), parse_mode="Markdown"); return
    try:
        uid = int(message.text.strip())
    except:
        bot.send_message(message.chat.id, f"{E_CROSS} {scp('Invalid ID')}",
                        reply_markup=get_admin_keyboard()); return
    user = get_user(uid)
    if not user:
        bot.send_message(message.chat.id, f"{E_CROSS} {scp('User not found')}",
                        reply_markup=get_admin_keyboard()); return
    text = (
        f"╭━━━━━━━━━━━━━━━━━━╮\n"
        f"   {E_USERS} *{scp('USER INFO')}* {E_USERS}\n"
        f"╰━━━━━━━━━━━━━━━━━━╯\n\n"
        f"{E_ID} ID: `{user['user_id']}`\n"
        f"{E_MSG} Username: @{user.get('username', 'N/A')}\n"
        f"{E_USERS} Name: *{user.get('first_name', 'User')}*\n"
        f"{E_GEM} Credits: {user.get('credits', 0)}\n"
        f"{E_SEARCH} Searches: {user.get('total_searches', 0)}\n"
        f"{E_LINK} Referred By: `{user.get('referred_by', 'N/A')}`\n"
        f"{E_STATS} Joined: {user.get('date_joined', 'N/A')}"
    )
    bot.send_message(message.chat.id, text, reply_markup=get_admin_keyboard(), parse_mode="Markdown")


@bot.message_handler(func=lambda m: m.text == "💾 ʙᴀᴄᴋᴜᴘ ᴅʙ" and m.from_user.id == ADMIN_USER_ID)
def admin_backup_db(message):
    try:
        with open(DB_PATH, 'rb') as f:
            bot.send_document(message.chat.id, f, caption=f"{E_FILE} Database Backup")
    except Exception as e:
        bot.send_message(message.chat.id, f"{E_CROSS} {scp('Backup failed')}: {e}",
                        reply_markup=get_admin_keyboard())


@bot.message_handler(func=lambda m: m.text == "📊 ᴛᴏᴘ ᴜsᴇʀs" and m.from_user.id == ADMIN_USER_ID)
def admin_top_users(message):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT user_id, first_name, credits, total_searches FROM users ORDER BY total_searches DESC LIMIT 10')
    rows = c.fetchall()
    conn.close()
    text = f"╭━━━━━━━━━━━━━━━━━━╮\n   {E_STATS} *{scp('TOP USERS')}* {E_STATS}\n╰━━━━━━━━━━━━━━━━━━╯\n\n"
    for i, r in enumerate(rows, 1):
        text += f"{i}. `{r[0]}` — *{r[1] or 'User'}* ({r[3]} searches)\n"
    bot.send_message(message.chat.id, text, parse_mode="Markdown")


@bot.message_handler(func=lambda m: m.text == "📈 ᴛᴏᴅᴀʏ sᴛᴀᴛs" and m.from_user.id == ADMIN_USER_ID)
def admin_today_stats(message):
    today = date.today().isoformat()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("SELECT COUNT(*) FROM users WHERE DATE(date_joined) = ?", (today,))
        new_users = c.fetchone()[0]
    except:
        new_users = 0
    total_users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    text = (
        f"╭━━━━━━━━━━━━━━━━━━╮\n"
        f"   {E_STATS} *{scp('TODAY STATS')}* {E_STATS}\n"
        f"╰━━━━━━━━━━━━━━━━━━╯\n\n"
        f"{E_USERS} New Users: {new_users}\n"
        f"{E_USERS} Total Users: {total_users}\n"
        f"{E_STAR} Date: {today}"
    )
    bot.send_message(message.chat.id, text, reply_markup=get_admin_keyboard(), parse_mode="Markdown")


@bot.message_handler(func=lambda m: m.text == "🧹 ᴄʟᴇᴀʀ ᴘᴇɴᴅɪɴɢ" and m.from_user.id == ADMIN_USER_ID)
def admin_clear_pending(message):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM buy_requests WHERE status="pending"')
    count = c.rowcount
    conn.commit()
    conn.close()
    bot.send_message(message.chat.id, f"{E_TICK} {scp('Cleared')} {count} pending requests",
                    reply_markup=get_admin_keyboard(), parse_mode="Markdown")


@bot.message_handler(func=lambda m: m.text == "🔄 ᴘɪɴɢ ᴀᴘɪ" and m.from_user.id == ADMIN_USER_ID)
def admin_ping_api(message):
    try:
        url = get_base_url()
        r = requests.get(url, timeout=10)
        bot.send_message(message.chat.id,
            f"{E_TICK} *{scp('API Status')}*\n\n"
            f"{E_LINK} URL: `{url}`\n"
            f"{E_BOLT} Status: {r.status_code}\n"
            f"{E_STATS} Time: {r.elapsed.total_seconds():.2f}s",
            reply_markup=get_admin_keyboard(), parse_mode="Markdown")
    except Exception as e:
        bot.send_message(message.chat.id, f"{E_CROSS} {scp('API unreachable')}: {e}",
                        reply_markup=get_admin_keyboard())

# ===================== OTHER HANDLERS =====================
@bot.message_handler(func=lambda m: m.text == BTN_BALANCE)
def balance_handler(message):
    if is_user_banned(message.from_user.id): return
    if not is_member(message.from_user.id):
        send_force_join(message.chat.id); return
    show_balance(message.chat.id, message.from_user.id)


@bot.message_handler(func=lambda m: m.text == BTN_BUY_POINTS)
def buy_points_handler(message):
    if is_user_banned(message.from_user.id): return
    if not is_member(message.from_user.id):
        send_force_join(message.chat.id); return
    show_buy_points(message.chat.id, message.from_user.id)


@bot.callback_query_handler(func=lambda call: call.data == "open_buy")
def open_buy_callback(call):
    try:
        bot.answer_callback_query(call.id)
    except: pass
    show_buy_points(call.message.chat.id, call.from_user.id)


@bot.message_handler(func=lambda m: m.text == BTN_MAIN_MENU)
def main_menu_handler(message):
    start_command(message)


@bot.message_handler(func=lambda m: m.text == BTN_CANCEL)
def cancel_handler(message):
    bot.send_message(message.chat.id, f"{E_CROSS} *{scp('Cancelled')}*",
                    reply_markup=get_main_keyboard(message.from_user.id), parse_mode="Markdown")


@bot.message_handler(commands=['cancel'])
def cancel_command(message):
    bot.send_message(message.chat.id, f"{E_CROSS} *{scp('Cancelled')}*",
                    reply_markup=get_main_keyboard(message.from_user.id), parse_mode="Markdown")


# ===================== RUN =====================
if __name__ == "__main__":
    print("=" * 60)
    print("  Premium OSINT Bot — Started v4")
    print("=" * 60)
    print(f"  Owner: @{ADMIN_USERNAME}")
    print(f"  Admin ID: {ADMIN_USER_ID}")
    print(f"  Base URL: {get_base_url()}")
    print(f"  Auto-delete: {AUTO_DELETE_SECONDS}s")
    print("=" * 60)
    bot.infinity_polling(timeout=60, long_polling_timeout=60)