import os
import re
import time
import asyncio
import logging
import aiosqlite
from pyrogram import Client, filters, idle
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto, InputMediaVideo, InputMediaAudio, InputMediaDocument,
    BotCommand
)
from pyrogram.errors import (
    FloodWait, ChatForwardsRestricted, ChatAdminRequired,
    ChannelPrivate, PeerIdInvalid, UserBannedInChannel
)
from datetime import datetime

# ==========================================
# ⚙️ LOGGING
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

def _parse_int(val, default=0):
    """Parse int from env, strip spaces and handle errors."""
    try:
        return int(str(val).strip().replace(" ", ""))
    except (ValueError, TypeError):
        return default

# ==========================================
# 🔧 ENVIRONMENT VARIABLES
# ==========================================
API_ID = _parse_int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH", "").strip()
SESSION_STRING = os.environ.get("SESSION_STRING", "").strip()
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
OWNER_ID = _parse_int(os.environ.get("OWNER_ID") or os.environ.get("OWNER"))
LOG_CHANNEL = os.environ.get("LOG_CHANNEL", "").strip()

# ==========================================
# 📦 GLOBAL STATE
# ==========================================
DB_FILE = "cloner.db"
CLONED_COUNT = 0
FAILED_COUNT = 0
START_TIME = time.time()
MEDIA_GROUPS = {}
PROCESSED_MSGS = set()  # Duplicate prevention
MAX_CACHE = 5000

# ==========================================
# 🤖 CLIENTS
# ==========================================
userbot = Client(
    "userbot",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING
)
bot = Client(
    "controller_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ==========================================
# 💾 DATABASE CONTROLLER
# ==========================================
async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS routes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER NOT NULL,
                source_name TEXT DEFAULT '',
                dest_id INTEGER NOT NULL,
                dest_name TEXT DEFAULT '',
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(source_id, dest_id)
            );
            CREATE TABLE IF NOT EXISTS forwarded_log (
                msg_id INTEGER,
                source_id INTEGER,
                dest_id INTEGER,
                PRIMARY KEY (msg_id, source_id, dest_id)
            );
            CREATE INDEX IF NOT EXISTS idx_routes_source ON routes(source_id);
            CREATE INDEX IF NOT EXISTS idx_routes_active ON routes(is_active);
            CREATE INDEX IF NOT EXISTS idx_fwd_log_source ON forwarded_log(source_id);
        """)
        defaults = [
            ("is_paused", "false"),
            ("remove_links", "false"),
            ("remove_usernames", "false"),
            ("remove_hashtags", "false"),
            ("skip_forwarded", "true"),
            ("header_text", ""),
            ("footer_text", ""),
            ("clone_delay", "1"),
        ]
        for key, val in defaults:
            await db.execute(
                "INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)",
                (key, val)
            )
        await db.commit()
    logger.info("Database initialized successfully")


async def get_config(key, default=""):
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute(
                "SELECT value FROM config WHERE key = ?", (key,)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else default
    except Exception as e:
        logger.error(f"DB get_config error: {e}")
        return default


async def set_config(key, value):
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
                (key, str(value))
            )
            await db.commit()
    except Exception as e:
        logger.error(f"DB set_config error: {e}")


async def get_routes(source_id=None, active_only=True):
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            if source_id:
                query = (
                    "SELECT dest_id, dest_name FROM routes "
                    "WHERE source_id = ?"
                )
                if active_only:
                    query += " AND is_active = 1"
                async with db.execute(query, (source_id,)) as cursor:
                    rows = await cursor.fetchall()
                    return rows
            else:
                query = "SELECT source_id, source_name, dest_id, dest_name, is_active FROM routes"
                if active_only:
                    query += " WHERE is_active = 1"
                async with db.execute(query) as cursor:
                    return await cursor.fetchall()
    except Exception as e:
        logger.error(f"DB get_routes error: {e}")
        return []


async def add_route(source_id, dest_id, source_name="", dest_name=""):
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                "INSERT OR IGNORE INTO routes (source_id, dest_id, source_name, dest_name) "
                "VALUES (?, ?, ?, ?)",
                (source_id, dest_id, source_name, dest_name)
            )
            await db.commit()
            return True
    except Exception as e:
        logger.error(f"DB add_route error: {e}")
        return False


async def remove_route(source_id, dest_id):
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                "DELETE FROM routes WHERE source_id = ? AND dest_id = ?",
                (source_id, dest_id)
            )
            await db.commit()
            return True
    except Exception as e:
        logger.error(f"DB remove_route error: {e}")
        return False


async def toggle_route(source_id, dest_id):
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                "UPDATE routes SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END "
                "WHERE source_id = ? AND dest_id = ?",
                (source_id, dest_id)
            )
            await db.commit()
            return True
    except Exception as e:
        logger.error(f"DB toggle_route error: {e}")
        return False


async def is_already_forwarded(msg_id, source_id, dest_id):
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute(
                "SELECT 1 FROM forwarded_log WHERE msg_id = ? AND source_id = ? AND dest_id = ?",
                (msg_id, source_id, dest_id)
            ) as cursor:
                row = await cursor.fetchone()
                return row is not None
    except Exception:
        return False


async def log_forwarded(msg_id, source_id, dest_id):
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                "INSERT OR IGNORE INTO forwarded_log (msg_id, source_id, dest_id) VALUES (?, ?, ?)",
                (msg_id, source_id, dest_id)
            )
            await db.commit()
    except Exception:
        pass


# ==========================================
# 🖼 UI CONTROL PANEL
# ==========================================
async def get_main_menu():
    is_paused = (await get_config("is_paused")) == "true"
    rem_links = (await get_config("remove_links")) == "true"
    rem_users = (await get_config("remove_usernames")) == "true"
    rem_tags = (await get_config("remove_hashtags")) == "true"
    skip_fwd = (await get_config("skip_forwarded")) == "true"

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"{'▶' if is_paused else '⏸'} {'RESUME' if is_paused else 'PAUSE'}",
                callback_data="toggle_pause"
            )
        ],
        [
            InlineKeyboardButton(
                f"{'ON' if rem_links else 'OFF'} Links",
                callback_data="toggle_links"
            ),
            InlineKeyboardButton(
                f"{'ON' if rem_users else 'OFF'} @mentions",
                callback_data="toggle_usernames"
            ),
        ],
        [
            InlineKeyboardButton(
                f"{'ON' if rem_tags else 'OFF'} #hashtags",
                callback_data="toggle_hashtags"
            ),
            InlineKeyboardButton(
                f"{'ON' if skip_fwd else 'OFF'} Skip Fwd",
                callback_data="toggle_skip_fwd"
            ),
        ],
        [
            InlineKeyboardButton("Routes", callback_data="view_routes"),
            InlineKeyboardButton("Stats", callback_data="view_stats"),
        ],
        [
            InlineKeyboardButton("Header/Footer", callback_data="edit_header_footer"),
            InlineKeyboardButton("Delay", callback_data="edit_delay"),
        ],
        [
            InlineKeyboardButton("Refresh", callback_data="refresh_menu")
        ],
    ])


async def get_status_text():
    is_paused = (await get_config("is_paused")) == "true"
    routes = await get_routes()
    uptime = time.time() - START_TIME
    hours = int(uptime // 3600)
    mins = int((uptime % 3600) // 60)

    status = "\u2b50 PAUSED" if is_paused else "\u26a1 RUNNING"
    return (
        f"**Channel Cloner Bot**\n\n"
        f"Status: {status}\n"
        f"Uptime: {hours}h {mins}m\n"
        f"Cloned: `{CLONED_COUNT}` messages\n"
        f"Failed: `{FAILED_COUNT}` messages\n"
        f"Active Routes: `{len(routes)}`\n\n"
        f"Use buttons below to control."
    )


# ==========================================
# 🔔 OWNER AUTH CHECK
# ==========================================
def is_owner(func):
    async def wrapper(client, message):
        if message.from_user and message.from_user.id == OWNER_ID:
            await func(client, message)
        else:
            await message.reply("\u274c သင့် Bot မဟုတ်ပါ\u1d40")
    return wrapper


# ==========================================
# 🤖 BOT COMMANDS
# ==========================================

# DEBUG: catch ALL messages to verify bot receives updates
@bot.on_message()
async def catch_all(client, message):
    logger.info(f"[CATCH-ALL] msg_id={message.id} chat={message.chat.id} user={message.from_user.id if message.from_user else 'None'} text={message.text[:50] if message.text else 'no_text'}")


@bot.on_message(filters.command(["start", "menu"]) & filters.private)
async def start_cmd(client, message):
    user_id = message.from_user.id if message.from_user else 0
    logger.info(f"/start from user_id={user_id}, OWNER_ID={OWNER_ID}, match={user_id == OWNER_ID}")
    
    if user_id != OWNER_ID:
        await message.reply_text(
            "\u26a0\ufe0f **Access Denied**\n\n"
            "This is a private bot."
        )
        return
    
    try:
        await message.reply_text(
            await get_status_text(),
            reply_markup=await get_main_menu()
        )
    except Exception as e:
        logger.error(f"start_cmd error: {e}", exc_info=True)
        try:
            await message.reply_text(f"Error: {e}")
        except Exception:
            pass


@bot.on_message(filters.command("route") & filters.user(OWNER_ID))
async def route_cmd(client, message):
    """Add a new clone route: /route <source> <dest>"""
    if len(message.command) < 3:
        await message.reply(
            "\u26a0\ufe0f **Usage:**\n"
            "`/route <Source_ID_or_Username> <Dest_ID_or_Username>`\n\n"
            "Example:\n"
            "`/route @sourcechan @destchan`\n"
            "`/route -1001234567 -1007654321`"
        )
        return

    src_raw, dst_raw = message.command[1], message.command[2]
    src_id = int(src_raw) if src_raw.lstrip("-").isdigit() else src_raw
    dst_id = int(dst_raw) if dst_raw.lstrip("-").isdigit() else dst_raw

    processing_msg = await message.reply("\u23f3 Checking channels...")

    try:
        src_chat = await userbot.get_chat(src_id)
        dst_chat = await userbot.get_chat(dst_id)

        success = await add_route(
            src_chat.id, dst_chat.id,
            src_chat.title or "", dst_chat.title or ""
        )

        if success:
            await processing_msg.edit_text(
                f"\u2705 **Route Added!**\n\n"
                f"\U0001f4e2 Source: {src_chat.title} (`{src_chat.id}`)\n"
                f"\U0001f3af Dest: {dst_chat.title} (`{dst_chat.id}`)\n\n"
                f"Cloning will start automatically."
            )
        else:
            await processing_msg.edit_text(
                "\u26a0\ufe0f This route already exists."
            )
    except (ChannelPrivate, PeerIdInvalid):
        await processing_msg.edit_text(
            "\u274c Cannot access one or both channels. "
            "Make sure the userbot has joined both channels."
        )
    except Exception as e:
        await processing_msg.edit_text(f"\u274c **Error:** `{e}`")
        logger.error(f"Route add error: {e}", exc_info=True)


@bot.on_message(filters.command("unroute") & filters.user(OWNER_ID))
async def unroute_cmd(client, message):
    """Remove a route: /unroute <source_id> <dest_id>"""
    if len(message.command) < 3:
        await message.reply(
            "\u26a0\ufe0f **Usage:** `/unroute <Source_ID> <Dest_ID>`"
        )
        return

    try:
        src_id = int(message.command[1])
        dst_id = int(message.command[2])
        success = await remove_route(src_id, dst_id)
        if success:
            await message.reply(
                f"\U0001f5d1 Route `{src_id}` -> `{dst_id}` removed."
            )
        else:
            await message.reply("\u274c Route not found.")
    except Exception as e:
        await message.reply(f"\u274c Error: `{e}`")


@bot.on_message(filters.command("routes") & filters.user(OWNER_ID))
async def routes_cmd(client, message):
    """List all routes"""
    routes = await get_routes(active_only=False)
    if not routes:
        await message.reply("\u274c No routes configured yet.\nUse `/route <src> <dst>` to add.")
        return

    text = "\U0001f500 **All Routes:**\n\n"
    for i, (s_id, s_name, d_id, d_name, active) in enumerate(routes, 1):
        status = "\u2705" if active else "\u26a0\ufe0f"
        s_label = s_name or f"`{s_id}`"
        d_label = d_name or f"`{d_id}`"
        text += f"{i}. {status} {s_label} -> {d_label}\n"

    text += (
        "\n\nCommands:\n"
        "`/toggle <src_id> <dst_id>` - enable/disable\n"
        "`/unroute <src_id> <dst_id>` - delete"
    )
    await message.reply(text)


@bot.on_message(filters.command("debug") & filters.private)
async def debug_cmd(client, message):
    """Debug command - shows user info"""
    user_id = message.from_user.id if message.from_user else 0
    text = (
        f"**Debug Info**\n\n"
        f"Your ID: `{user_id}`\n"
        f"OWNER_ID: `{OWNER_ID}`\n"
        f"Match: `{user_id == OWNER_ID}`\n"
        f"API_ID: `{API_ID}`\n"
        f"Bot Token: `{BOT_TOKEN[:10]}...`\n"
        f"Session: `{SESSION_STRING[:10]}...`"
    )
    await message.reply_text(text)


@bot.on_message(filters.command("toggle") & filters.user(OWNER_ID))
async def toggle_cmd(client, message):
    """Toggle a route on/off: /toggle <source_id> <dest_id>"""
    if len(message.command) < 3:
        await message.reply(
            "\u26a0\ufe0f **Usage:** `/toggle <Source_ID> <Dest_ID>`"
        )
        return

    try:
        src_id = int(message.command[1])
        dst_id = int(message.command[2])
        success = await toggle_route(src_id, dst_id)
        if success:
            await message.reply(
                f"\U0001f504 Route `{src_id}` -> `{dst_id}` toggled."
            )
        else:
            await message.reply("\u274c Route not found.")
    except Exception as e:
        await message.reply(f"\u274c Error: `{e}`")


@bot.on_message(filters.command("set_header") & filters.user(OWNER_ID))
async def set_header_cmd(client, message):
    header = message.text.split(maxsplit=1)[1] if len(message.command) > 1 else ""
    await set_config("header_text", header)
    await message.reply(f"\u2705 Header set to:\n`{header}`")


@bot.on_message(filters.command("set_footer") & filters.user(OWNER_ID))
async def set_footer_cmd(client, message):
    footer = message.text.split(maxsplit=1)[1] if len(message.command) > 1 else ""
    await set_config("footer_text", footer)
    await message.reply(f"\u2705 Footer set to:\n`{footer}`")


@bot.on_message(filters.command("setdelay") & filters.user(OWNER_ID))
async def set_delay_cmd(client, message):
    if len(message.command) < 2:
        delay = await get_config("clone_delay", "1")
        await message.reply(f"\u23f0 Current delay: `{delay}s`\nUse `/setdelay <seconds>` to change.")
        return
    try:
        delay = max(0, int(message.command[1]))
        await set_config("clone_delay", str(delay))
        await message.reply(f"\u2705 Clone delay set to `{delay}s`.")
    except ValueError:
        await message.reply("\u274c Invalid number.")


@bot.on_message(filters.command("status") & filters.user(OWNER_ID))
async def status_cmd(client, message):
    await message.reply_text(
        await get_status_text(),
        reply_markup=await get_main_menu()
    )


# ==========================================
# \U0001f522 INLINE BUTTON HANDLERS
# ==========================================
@bot.on_callback_query(filters.user(OWNER_ID))
async def cb_handler(client, query):
    data = query.data

    if data == "none":
        await query.answer()
        return

    elif data == "refresh_menu":
        await query.message.edit_text(
            await get_status_text(),
            reply_markup=await get_main_menu()
        )
        await query.answer()

    elif data == "toggle_pause":
        curr = (await get_config("is_paused")) == "true"
        await set_config("is_paused", "false" if curr else "true")
        new_state = "RESUMED" if curr else "PAUSED"
        await query.message.edit_text(
            await get_status_text(),
            reply_markup=await get_main_menu()
        )
        await query.answer(f"Bot {new_state}")

    elif data == "toggle_links":
        curr = (await get_config("remove_links")) == "true"
        await set_config("remove_links", "false" if curr else "true")
        await query.message.edit_reply_markup(reply_markup=await get_main_menu())
        await query.answer(f"Links filter: {'OFF' if curr else 'ON'}")

    elif data == "toggle_usernames":
        curr = (await get_config("remove_usernames")) == "true"
        await set_config("remove_usernames", "false" if curr else "true")
        await query.message.edit_reply_markup(reply_markup=await get_main_menu())
        await query.answer(f"@mentions filter: {'OFF' if curr else 'ON'}")

    elif data == "toggle_hashtags":
        curr = (await get_config("remove_hashtags")) == "true"
        await set_config("remove_hashtags", "false" if curr else "true")
        await query.message.edit_reply_markup(reply_markup=await get_main_menu())
        await query.answer(f"#hashtags filter: {'OFF' if curr else 'ON'}")

    elif data == "toggle_skip_fwd":
        curr = (await get_config("skip_forwarded")) == "true"
        await set_config("skip_forwarded", "false" if curr else "true")
        await query.message.edit_reply_markup(reply_markup=await get_main_menu())
        await query.answer(f"Skip forwarded: {'OFF' if curr else 'ON'}")

    elif data == "view_routes":
        routes = await get_routes(active_only=False)
        if not routes:
            await query.message.reply("No routes configured yet.")
        else:
            text = "\U0001f500 **Routes:**\n\n"
            for s_id, s_name, d_id, d_name, active in routes:
                st = "\u2705" if active else "\u23f8"
                s = s_name or f"`{s_id}`"
                d = d_name or f"`{d_id}`"
                text += f"{st} {s} -> {d}\n"
            await query.message.reply(text)
        await query.answer()

    elif data == "view_stats":
        uptime = time.time() - START_TIME
        hours = int(uptime // 3600)
        mins = int((uptime % 3600) // 60)
        routes = await get_routes()
        text = (
            f"\U0001f4ca **Stats**\n\n"
            f"Cloned: `{CLONED_COUNT}`\n"
            f"Failed: `{FAILED_COUNT}`\n"
            f"Uptime: `{hours}h {mins}m`\n"
            f"Active Routes: `{len(routes)}`\n"
            f"Memory Cache: `{len(PROCESSED_MSGS)}` msgs"
        )
        await query.message.reply(text)
        await query.answer()

    elif data == "edit_header_footer":
        header = await get_config("header_text")
        footer = await get_config("footer_text")
        text = (
            "\U0001f4dd **Header/Footer Settings**\n\n"
            f"Current Header: `{header}`\n"
            f"Current Footer: `{footer}`\n\n"
            "Commands:\n"
            "`/set_header <text>`\n"
            "`/set_footer <text>`\n"
            "`/set_header` (clear)\n"
            "`/set_footer` (clear)"
        )
        await query.message.reply(text)
        await query.answer()

    elif data == "edit_delay":
        delay = await get_config("clone_delay", "1")
        text = (
            f"\u23f0 **Clone Delay: `{delay}s`**\n\n"
            "Use `/setdelay <seconds>` to change."
        )
        await query.message.reply(text)
        await query.answer()

    else:
        await query.answer("Unknown action.", show_alert=True)


# ==========================================
# \U0001f5bc TEXT & MEDIA PROCESSING
# ==========================================
async def process_text(text):
    """Process text: remove links, usernames, hashtags, add header/footer."""
    if not text:
        return text

    rem_links = (await get_config("remove_links")) == "true"
    rem_users = (await get_config("remove_usernames")) == "true"
    rem_tags = (await get_config("remove_hashtags")) == "true"
    header = await get_config("header_text")
    footer = await get_config("footer_text")

    if rem_links:
        text = re.sub(r"https?://\S+", "", text)
    if rem_users:
        text = re.sub(r"@[\w.-]+", "", text)
    if rem_tags:
        text = re.sub(r"#\S+", "", text)

    parts = []
    if header:
        parts.append(header)
    parts.append(text)
    if footer:
        parts.append(footer)

    return "\n\n".join(parts).strip()


async def send_restricted_media(dest, message, caption):
    """Download & re-upload restricted/protected content."""
    file_path = None
    try:
        file_path = await userbot.download_media(message)
        if not file_path:
            logger.warning(f"Failed to download media from msg {message.id}")
            return False

        kwargs = {"caption": caption}
        if message.photo:
            kwargs["photo"] = file_path
            await userbot.send_photo(dest, **kwargs)
        elif message.video:
            kwargs["video"] = file_path
            if message.video.duration:
                kwargs["duration"] = message.video.duration
            if message.video.width:
                kwargs["width"] = message.video.width
            if message.video.height:
                kwargs["height"] = message.video.height
            await userbot.send_video(dest, **kwargs)
        elif message.document:
            kwargs["document"] = file_path
            await userbot.send_document(dest, **kwargs)
        elif message.audio:
            kwargs["audio"] = file_path
            await userbot.send_audio(dest, **kwargs)
        elif message.voice:
            kwargs["voice"] = file_path
            await userbot.send_voice(dest, **kwargs)
        elif message.animation:
            kwargs["animation"] = file_path
            await userbot.send_animation(dest, **kwargs)
        elif message.sticker:
            kwargs["sticker"] = file_path
            await userbot.send_sticker(dest, **kwargs)
        else:
            logger.warning(f"Unknown media type in msg {message.id}")
            return False

        return True
    except Exception as e:
        logger.error(f"Restricted media send error: {e}")
        return False
    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass


# ==========================================
# \U0001f504 CLONER ENGINE
# ==========================================
@userbot.on_message(filters.group | filters.channel)
async def cloner_engine(client, message):
    global CLONED_COUNT, FAILED_COUNT

    # Pause check
    if (await get_config("is_paused")) == "true":
        return

    # Skip if message is from our bot (avoid loops)
    if message.from_user and message.from_user.id == (await bot.get_me()).id:
        return

    # Skip forwarded messages if setting is ON
    if message.forward_from and (await get_config("skip_forwarded")) == "true":
        return

    source_id = message.chat.id

    # Get routes for this source
    dests = await get_routes(source_id)
    if not dests:
        return

    # Skip service messages
    if message.empty or message.service:
        return

    # ---- Album / Media Group Handling ----
    if message.media_group_id:
        mg_id = message.media_group_id
        if mg_id not in MEDIA_GROUPS:
            MEDIA_GROUPS[mg_id] = [message]
            # Wait for all album messages to arrive
            await asyncio.sleep(2.5)
            messages = MEDIA_GROUPS.pop(mg_id, [])

            for dest_id, dest_name in dests:
                # Check duplicate
                if await is_already_forwarded(messages[0].id, source_id, dest_id):
                    continue

                try:
                    # Try normal forward first
                    await userbot.copy_media_group(
                        chat_id=dest_id,
                        from_chat_id=source_id,
                        message_ids=[m.id for m in messages],
                        captions=[await process_text(m.caption or "") for m in messages]
                    )
                    CLONED_COUNT += len(messages)
                    await log_forwarded(messages[0].id, source_id, dest_id)
                    logger.info(f"Album cloned: {len(messages)} items -> {dest_id}")

                except ChatForwardsRestricted:
                    # Fallback: download and re-upload
                    media_list = []
                    files = []
                    try:
                        for m in messages:
                            cap = await process_text(m.caption or "")
                            f = await userbot.download_media(m)
                            files.append(f)
                            if m.photo:
                                media_list.append(InputMediaPhoto(f, caption=cap))
                            elif m.video:
                                media_list.append(InputMediaVideo(f, caption=cap))
                            elif m.audio:
                                media_list.append(InputMediaAudio(f, caption=cap))
                            elif m.document:
                                media_list.append(InputMediaDocument(f, caption=cap))

                        if media_list:
                            await userbot.send_media_group(dest_id, media_list)
                            CLONED_COUNT += len(messages)
                            await log_forwarded(messages[0].id, source_id, dest_id)
                            logger.info(
                                f"Album re-uploaded (restricted): {len(messages)} items -> {dest_id}"
                            )
                    except Exception as e:
                        FAILED_COUNT += len(messages)
                        logger.error(f"Album clone failed -> {dest_id}: {e}")
                    finally:
                        for f in files:
                            if f and os.path.exists(f):
                                try:
                                    os.remove(f)
                                except OSError:
                                    pass

                except FloodWait as e:
                    logger.warning(f"FloodWait album: {e.value}s")
                    await asyncio.sleep(e.value + 2)
                except Exception as e:
                    FAILED_COUNT += len(messages)
                    logger.error(f"Album clone error -> {dest_id}: {e}")
        else:
            MEDIA_GROUPS[mg_id].append(message)
        return

    # ---- Single Message Handling ----
    caption = await process_text(message.text or message.caption or "")
    delay = int(await get_config("clone_delay", "1"))

    for dest_id, dest_name in dests:
        # Duplicate check
        msg_key = (message.id, source_id, dest_id)
        if msg_key in PROCESSED_MSGS:
            continue
        if await is_already_forwarded(message.id, source_id, dest_id):
            continue

        try:
            if message.text and not message.media:
                await userbot.send_message(dest_id, caption)
            elif message.sticker:
                await message.copy(dest_id, caption=caption if caption else None)
            else:
                await message.copy(dest_id, caption=caption if caption else None)

            CLONED_COUNT += 1
            PROCESSED_MSGS.add(msg_key)
            await log_forwarded(message.id, source_id, dest_id)

            # Trim cache if too large
            if len(PROCESSED_MSGS) > MAX_CACHE:
                PROCESSED_MSGS.clear()

            logger.debug(f"Cloned msg {message.id} -> {dest_id}")

        except ChatForwardsRestricted:
            logger.info(
                f"Forward restricted for msg {message.id}, downloading & re-uploading..."
            )
            success = await send_restricted_media(dest_id, message, caption)
            if success:
                CLONED_COUNT += 1
                PROCESSED_MSGS.add(msg_key)
                await log_forwarded(message.id, source_id, dest_id)
            else:
                FAILED_COUNT += 1

        except FloodWait as e:
            logger.warning(f"FloodWait: {e.value}s, sleeping...")
            await asyncio.sleep(e.value + 2)
            # Retry once
            try:
                if message.text and not message.media:
                    await userbot.send_message(dest_id, caption)
                else:
                    await message.copy(dest_id, caption=caption if caption else None)
                CLONED_COUNT += 1
                PROCESSED_MSGS.add(msg_key)
                await log_forwarded(message.id, source_id, dest_id)
            except Exception as retry_e:
                FAILED_COUNT += 1
                logger.error(f"Retry failed for msg {message.id}: {retry_e}")

        except (ChatAdminRequired, UserBannedInChannel) as e:
            logger.error(
                f"Permission denied sending to {dest_id}: {e}"
            )
            FAILED_COUNT += 1

        except Exception as e:
            FAILED_COUNT += 1
            logger.error(f"Clone error msg {message.id} -> {dest_id}: {e}")

        if delay > 0:
            await asyncio.sleep(delay)


# ==========================================
# \U0001f680 MAIN RUNNER
# ==========================================
async def main():
    logger.info(f"Starting bot... OWNER_ID={OWNER_ID}, API_ID={API_ID}")

    if not API_ID or not API_HASH:
        logger.error("API_ID and API_HASH are required!")
        return
    if not SESSION_STRING:
        logger.error("SESSION_STRING is required!")
        return
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is required!")
        return
    if not OWNER_ID:
        logger.error("OWNER_ID is required!")
        return

    await init_db()
    logger.info("Database ready")

    # Start userbot
    try:
        await userbot.start()
        logger.info("Userbot connected")
    except Exception as e:
        logger.error(f"Userbot failed to start: {e}")
        return

    # Start bot - delete webhook first so getUpdates works
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        logger.info("Webhook deleted, using getUpdates")
        await bot.start()
        me = await bot.get_me()
        logger.info(f"Bot @{me.username} connected")
    except Exception as e:
        logger.error(f"Bot failed to start: {e}")
        return

    # Set BotCommand menu
    try:
        commands = [
            BotCommand("start", "Open control panel"),
            BotCommand("route", "Add clone route"),
            BotCommand("unroute", "Remove route"),
            BotCommand("routes", "List all routes"),
            BotCommand("toggle", "Enable/disable route"),
            BotCommand("set_header", "Set header text"),
            BotCommand("set_footer", "Set footer text"),
            BotCommand("setdelay", "Set clone delay"),
            BotCommand("status", "View bot status"),
            BotCommand("debug", "Debug info"),
        ]
        await bot.set_bot_commands(commands)
        logger.info("Bot command menu set")
    except Exception as e:
        logger.warning(f"Could not set bot commands: {e}")

    # Notify owner
    try:
        await bot.send_message(
            OWNER_ID,
            "\u26a1 **Channel Cloner Bot is Online!**\n\n"
            "Use /start to open the control panel."
        )
    except Exception as e:
        logger.warning(f"Could not notify owner: {e}")

    logger.info(f"OWNER_ID = {OWNER_ID}")
    logger.info("Bot is now listening for messages...")

    await idle()

    await userbot.stop()
    await bot.stop()
    logger.info("Bot stopped gracefully.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
