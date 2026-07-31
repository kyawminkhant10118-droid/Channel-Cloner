import os
import re
import time
import asyncio
import logging
import aiosqlite
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, InputMediaVideo
from pyrogram.errors import FloodWait, ChatForwardsRestricted

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# --- Environment Variables ---
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OWNER_ID = int(os.environ.get("OWNER_ID", 0))

# --- Global Variables & Caches ---
DB_FILE = "cloner_god.db"
CLONED_COUNT = 0
START_TIME = time.time()
MEDIA_GROUPS = {} # Media Group/Album များကို ထိန်းချုပ်ရန်

# Clients
userbot = Client("userbot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)
bot = Client("controller_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ==========================================
# 💾 DATABASE CONTROLLER (SQLite)
# ==========================================
async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS routes (
                source_id INTEGER,
                dest_id INTEGER,
                PRIMARY KEY (source_id, dest_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS replacements (
                old_text TEXT PRIMARY KEY,
                new_text TEXT
            )
        """)
        # Default Settings
        defaults = [
            ("is_paused", "false"),
            ("remove_links", "false"),
            ("remove_usernames", "false"),
            ("header_text", ""),
            ("footer_text", "")
        ]
        for key, val in defaults:
            await db.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", (key, val))
        await db.commit()

async def get_config(key, default=""):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT value FROM config WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else default

async def set_config(key, value):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, str(value)))
        await db.commit()

async def get_routes(source_id=None):
    async with aiosqlite.connect(DB_FILE) as db:
        if source_id:
            async with db.execute("SELECT dest_id FROM routes WHERE source_id = ?", (source_id,)) as cursor:
                rows = await cursor.fetchall()
                return [r[0] for r in rows]
        else:
            async with db.execute("SELECT source_id, dest_id FROM routes") as cursor:
                return await cursor.fetchall()

async def add_route(source_id, dest_id):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT OR IGNORE INTO routes (source_id, dest_id) VALUES (?, ?)", (source_id, dest_id))
        await db.commit()

async def remove_route(source_id, dest_id):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM routes WHERE source_id = ? AND dest_id = ?", (source_id, dest_id))
        await db.commit()

# ==========================================
# 🎛 UI CONTROL PANEL
# ==========================================
async def get_main_menu():
    is_paused = (await get_config("is_paused")) == "true"
    rem_links = (await get_config("remove_links")) == "true"
    rem_users = (await get_config("remove_usernames")) == "true"

    pause_btn = "▶️ Resume Bot" if is_paused else "⏸ Pause Bot"
    link_btn = "✅ Remove Links" if rem_links else "❌ Remove Links"
    usr_btn = "✅ Remove Usernames" if rem_users else "❌ Remove Usernames"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"State: {'⏸ PAUSED' if is_paused else '▶️ RUNNING'}", callback_data="none")],
        [InlineKeyboardButton(pause_btn, callback_data="toggle_pause")],
        [InlineKeyboardButton(link_btn, callback_data="toggle_links"), InlineKeyboardButton(usr_btn, callback_data="toggle_usernames")],
        [InlineKeyboardButton("🔀 Route Manager", callback_data="view_routes"), InlineKeyboardButton("📊 Statistics", callback_data="view_stats")]
    ])

# ==========================================
# 🤖 BOT COMMANDS
# ==========================================
@bot.on_message(filters.command(["start", "menu"]) & filters.user(OWNER_ID))
async def start_cmd(client, message):
    await message.reply_text(
        "⚡️ **GOD LEVEL CLONER DASHBOARD** ⚡️\n\n"
        "အောက်ပါ Panel မှတစ်ဆင့် Bot ၏ Settings များကို တိုက်ရိုက် ထိန်းချုပ်နိုင်ပါသည်။\n\n"
        "🛠 **Routing Commands:**\n"
        "• `/route <Source_ID> <Dest_ID>` - Route သစ် ချိတ်ရန်\n"
        "• `/unroute <Source_ID> <Dest_ID>` - Route ဖြုတ်ရန်\n"
        "• `/routes` - ချိတ်ထားသော Route များ ကြည့်ရန်\n"
        "• `/set_header <စာသား>` - စာသားထိပ်တွင် တပ်မည့် စာ\n"
        "• `/set_footer <စာသား>` - စာသားအောက်တွင် တပ်မည့် စာ",
        reply_markup=await get_main_menu()
    )

@bot.on_message(filters.command("route") & filters.user(OWNER_ID))
async def route_cmd(client, message):
    if len(message.command) < 3:
        await message.reply("⚠️ **Usage:** `/route <Source_ID_or_Username> <Dest_ID_or_Username>`")
        return
    
    src, dst = message.command[1], message.command[2]
    src_id = int(src) if src.lstrip('-').isdigit() else src
    dst_id = int(dst) if dst.lstrip('-').isdigit() else dst

    try:
        src_chat = await userbot.get_chat(src_id)
        dst_chat = await userbot.get_chat(dst_id)
        
        await add_route(src_chat.id, dst_chat.id)
        await message.reply(f"✅ **Route ချိတ်ဆက်ပြီးပါပြီ!**\n\n📢 **Source:** {src_chat.title} (`{src_chat.id}`)\n🎯 **Dest:** {dst_chat.title} (`{dst_chat.id}`)")
    except Exception as e:
        await message.reply(f"❌ **Error:** {e}")

@bot.on_message(filters.command("unroute") & filters.user(OWNER_ID))
async def unroute_cmd(client, message):
    if len(message.command) < 3:
        await message.reply("⚠️ **Usage:** `/unroute <Source_ID> <Dest_ID>`")
        return
    src_id = int(message.command[1])
    dst_id = int(message.command[2])
    await remove_route(src_id, dst_id)
    await message.reply(f"🗑 Route ({src_id} ➔ {dst_id}) ကို ဖြုတ်လိုက်ပါပြီ။")

@bot.on_message(filters.command("routes") & filters.user(OWNER_ID))
async def routes_cmd(client, message):
    routes = await get_routes()
    if not routes:
        await message.reply("❌ ချိတ်ဆက်ထားသော Route မရှိသေးပါ။")
        return
    text = "🔀 **Active Channel Routes:**\n\n"
    for s, d in routes:
        text += f"• `{s}` ➔ `{d}`\n"
    await message.reply(text)

@bot.on_message(filters.command("set_header") & filters.user(OWNER_ID))
async def set_header_cmd(client, message):
    header = message.text.split(maxsplit=1)[1] if len(message.command) > 1 else ""
    await set_config("header_text", header)
    await message.reply(f"✅ Header စာသား ပြင်ဆင်ပြီးပါပြီ:\n`{header}`")

@bot.on_message(filters.command("set_footer") & filters.user(OWNER_ID))
async def set_footer_cmd(client, message):
    footer = message.text.split(maxsplit=1)[1] if len(message.command) > 1 else ""
    await set_config("footer_text", footer)
    await message.reply(f"✅ Footer စာသား ပြင်ဆင်ပြီးပါပြီ:\n`{footer}`")

# ==========================================
# 🔘 INLINE BUTTON HANDLERS
# ==========================================
@bot.on_callback_query(filters.user(OWNER_ID))
async def cb_handler(client, query):
    data = query.data
    
    if data == "toggle_pause":
        curr = await get_config("is_paused") == "true"
        await set_config("is_paused", "false" if curr else "true")
        await query.message.edit_reply_markup(reply_markup=await get_main_menu())
        
    elif data == "toggle_links":
        curr = await get_config("remove_links") == "true"
        await set_config("remove_links", "false" if curr else "true")
        await query.message.edit_reply_markup(reply_markup=await get_main_menu())

    elif data == "toggle_usernames":
        curr = await get_config("remove_usernames") == "true"
        await set_config("remove_usernames", "false" if curr else "true")
        await query.message.edit_reply_markup(reply_markup=await get_main_menu())

    elif data == "view_routes":
        routes = await get_routes()
        text = "🔀 **Active Routes:**\n" + "\n".join([f"• `{s}` ➔ `{d}`" for s, d in routes]) if routes else "မရှိသေးပါ"
        await query.message.reply(text)
        await query.answer()

    elif data == "view_stats":
        uptime = round((time.time() - START_TIME) / 3600, 2)
        routes = await get_routes()
        text = f"📊 **God Level Stats**\n\n• Cloned: `{CLONED_COUNT}`\n• Uptime: `{uptime} Hours`\n• Active Routes: `{len(routes)}`"
        await query.message.reply(text)
        await query.answer()

# ==========================================
# 🖼 ADVANCED TEXT & MEDIA PROCESSING
# ==========================================
async def process_text(text):
    if not text:
        return text
    
    rem_links = (await get_config("remove_links")) == "true"
    rem_users = (await get_config("remove_usernames")) == "true"
    header = await get_config("header_text")
    footer = await get_config("footer_text")

    if rem_links:
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
    if rem_users:
        text = re.sub(r'@[a-zA-Z0-9_]+', '', text)

    if header:
        text = f"{header}\n\n{text}"
    if footer:
        text = f"{text}\n\n{footer}"
        
    return text.strip()

# Bypass Restricted Content (Download & Re-upload Engine)
async def send_restricted_media(dest, message, caption):
    file_path = await userbot.download_media(message)
    try:
        if message.photo:
            await userbot.send_photo(dest, photo=file_path, caption=caption)
        elif message.video:
            await userbot.send_video(dest, video=file_path, caption=caption)
        elif message.document:
            await userbot.send_document(dest, document=file_path, caption=caption)
        elif message.audio:
            await userbot.send_audio(dest, audio=file_path, caption=caption)
        elif message.voice:
            await userbot.send_voice(dest, voice=file_path, caption=caption)
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)

# ==========================================
# 🔄 CLONER ENGINE (ALBUM & ROUTING)
# ==========================================
@userbot.on_message(filters.group | filters.channel)
async def god_cloner_engine(client, message):
    global CLONED_COUNT
    
    if (await get_config("is_paused")) == "true":
        return

    # Check Route Exists
    dests = await get_routes(message.chat.id)
    if not dests:
        return

    # Album (Media Group) Handling
    if message.media_group_id:
        mg_id = message.media_group_id
        if mg_id not in MEDIA_GROUPS:
            MEDIA_GROUPS[mg_id] = [message]
            await asyncio.sleep(2) # Album ၏ Media အားလုံး ရောက်အောင် စောင့်ခြင်း
            
            messages = MEDIA_GROUPS.pop(mg_id, [])
            for dest in dests:
                try:
                    # Direct Copying Album
                    await userbot.copy_media_group(dest, message.chat.id, messages[0].id)
                    CLONED_COUNT += len(messages)
                except ChatForwardsRestricted:
                    # Download & Re-upload Restricted Album
                    media_list = []
                    files = []
                    for m in messages:
                        f = await userbot.download_media(m)
                        files.append(f)
                        cap = await process_text(m.caption or "")
                        if m.photo:
                            media_list.append(InputMediaPhoto(f, caption=cap))
                        elif m.video:
                            media_list.append(InputMediaVideo(f, caption=cap))
                    
                    await userbot.send_media_group(dest, media_list)
                    for f in files:
                        if os.path.exists(f): os.remove(f)
                    CLONED_COUNT += len(messages)
                except Exception as e:
                    logger.error(f"Album Error: {e}")
        else:
            MEDIA_GROUPS[mg_id].append(message)
        return

    # Single Message Handling
    caption = await process_text(message.text or message.caption or "")
    for dest in dests:
        try:
            if message.text:
                await userbot.send_message(dest, caption)
            else:
                await message.copy(dest, caption=caption)
            CLONED_COUNT += 1
            await asyncio.sleep(2)

        except ChatForwardsRestricted:
            # Restricted/Protected Content တွေ့ပါက Auto Download လုပ်၍ တင်ပေးခြင်း
            logger.info("Restricted Content တွေ့ရှိသဖြင့် Download/Upload စနစ်ဖြင့် ကူးပါမည်...")
            await send_restricted_media(dest, message, caption)
            CLONED_COUNT += 1
        except FloodWait as e:
            await asyncio.sleep(e.value + 2)
            await message.copy(dest, caption=caption)
            CLONED_COUNT += 1
        except Exception as e:
            logger.error(f"Cloning Error: {e}")

# ==========================================
# 🚀 MAIN RUNNER
# ==========================================
async def main():
    await init_db()
    logger.info("💾 SQLite Database စတင်ပါပြီ...")
    
    await userbot.start()
    await bot.start()
    
    # Auto-Cache Active Routes
    routes = await get_routes()
    for s, d in routes:
        try:
            await userbot.get_chat(s)
            await userbot.get_chat(d)
        except Exception as e:
            logger.error(f"Cache Error ({s} -> {d}): {e}")

    logger.info("🚀 GOD LEVEL CLONER IS ONLINE!")
    await idle()
    
    await userbot.stop()
    await bot.stop()

if __name__ == "__main__":
    asyncio.run(main())
