import os
import re
import time
import asyncio
import logging
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Configuration Variables ---
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OWNER_ID = int(os.environ.get("OWNER_ID", 0))

# Dynamic In-Memory Memory Sets (Bot Run နေစဉ် စိတ်ကြိုက် ပြင်ဆင်နိုင်သည်)
SOURCES = set()
DESTS = set()

# Railway မှ တန်ဖိုးများကို စတင် Load လုပ်ခြင်း
env_sources = os.environ.get("SOURCES", "")
if env_sources:
    for x in env_sources.split(","):
        x = x.strip()
        if x:
            SOURCES.add(int(x) if x.lstrip('-').isdigit() else x)

env_dests = os.environ.get("DESTS", "")
if env_dests:
    for x in env_dests.split(","):
        x = x.strip()
        if x:
            DESTS.add(int(x) if x.lstrip('-').isdigit() else x)

# Control Settings
IS_PAUSED = False
REMOVE_LINKS = os.environ.get("REMOVE_LINKS", "False").lower() == "true"
REMOVE_USERNAMES = os.environ.get("REMOVE_USERNAMES", "False").lower() == "true"
CLONED_COUNT = 0
START_TIME = time.time()

# Clients
userbot = Client("userbot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)
bot = Client("controller_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ==========================================
# 🎛 UI CONTROL PANEL BUTTONS
# ==========================================
def get_main_menu():
    pause_btn = "▶️ Resume" if IS_PAUSED else "⏸ Pause"
    link_btn = "🔗 Links: REMOVE" if REMOVE_LINKS else "🔗 Links: KEEP"
    usr_btn = "👤 Usernames: REMOVE" if REMOVE_USERNAMES else "👤 Usernames: KEEP"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Status: {'⏸ Paused' if IS_PAUSED else '▶️ Running'}", callback_data="none")],
        [InlineKeyboardButton(pause_btn, callback_data="toggle_pause")],
        [InlineKeyboardButton(link_btn, callback_data="toggle_links"), InlineKeyboardButton(usr_btn, callback_data="toggle_usernames")],
        [InlineKeyboardButton("📋 List Channels", callback_data="list_channels")],
        [InlineKeyboardButton("📊 Check Stats", callback_data="view_stats")]
    ])

# ==========================================
# 🤖 BOT COMMANDS (အပြည့်အဝ Control ပြုလုပ်ရန်)
# ==========================================

@bot.on_message(filters.command(["start", "menu"]) & filters.user(OWNER_ID))
async def start_cmd(client, message):
    await message.reply_text(
        "🎛 **Master Control Panel**\n\n"
        "အောက်ပါ Buttons များ သို့မဟုတ် Commands များကို သုံး၍ Bot ကို အပြည့်အဝ ထိန်းချုပ်နိုင်ပါသည်။\n\n"
        "📌 **Commands စာရင်း:**\n"
        "• `/add_source <ID or @username>` - Source ထည့်ရန်\n"
        "• `/rm_source <ID or @username>` - Source ဖြုတ်ရန်\n"
        "• `/add_dest <ID or @username>` - Destination ထည့်ရန်\n"
        "• `/rm_dest <ID or @username>` - Destination ဖြုတ်ရန်\n"
        "• `/list` - လက်ရှိ ချိတ်ထားသော Channel များကြည့်ရန်",
        reply_markup=get_main_menu()
    )

# 1. Add Source Channel
@bot.on_message(filters.command("add_source") & filters.user(OWNER_ID))
async def add_source_cmd(client, message):
    if len(message.command) < 2:
        await message.reply("⚠️ သုံးစွဲပုံ: `/add_source -10012345678` သို့မဟုတ် `/add_source @channelname`")
        return
    
    target = message.command[1]
    chat_id = int(target) if target.lstrip('-').isdigit() else target
    
    try:
        # Auto Cache လုပ်ရန် get_chat အသုံးပြုခြင်း
        chat = await userbot.get_chat(chat_id)
        SOURCES.add(chat.id)
        await message.reply(f"✅ **Source Channel ပေါင်းထည့်ပြီးပါပြီ:**\n**Title:** {chat.title}\n**ID:** `{chat.id}`")
    except Exception as e:
        await message.reply(f"❌ **Error:** {e}\n\n*Userbot သည် အဆိုပါ Channel ထဲသို့ ဝင်ထားပြီးဖြစ်ကြောင်း သေချာပါစေ။*")

# 2. Remove Source Channel
@bot.on_message(filters.command("rm_source") & filters.user(OWNER_ID))
async def rm_source_cmd(client, message):
    if len(message.command) < 2:
        await message.reply("⚠️ သုံးစွဲပုံ: `/rm_source -10012345678` သို့မဟုတ် `/rm_source @channelname`")
        return
    
    target = message.command[1]
    chat_id = int(target) if target.lstrip('-').isdigit() else target
    
    if chat_id in SOURCES:
        SOURCES.remove(chat_id)
        await message.reply(f"🗑 Source Channel `{chat_id}` ကို ဖြုတ်လိုက်ပါပြီ။")
    else:
        await message.reply("❌ ထို Channel သည် Source စာရင်းထဲတွင် မရှိပါ။")

# 3. Add Destination Channel
@bot.on_message(filters.command("add_dest") & filters.user(OWNER_ID))
async def add_dest_cmd(client, message):
    if len(message.command) < 2:
        await message.reply("⚠️ သုံးစွဲပုံ: `/add_dest -10012345678` သို့မဟုတ် `/add_dest @channelname`")
        return
    
    target = message.command[1]
    chat_id = int(target) if target.lstrip('-').isdigit() else target
    
    try:
        chat = await userbot.get_chat(chat_id)
        DESTS.add(chat.id)
        await message.reply(f"✅ **Destination Channel ပေါင်းထည့်ပြီးပါပြီ:**\n**Title:** {chat.title}\n**ID:** `{chat.id}`")
    except Exception as e:
        await message.reply(f"❌ **Error:** {e}\n\n*Userbot သည် အဆိုပါ Channel ထဲတွင် Admin ဖြစ်ကြောင်း သို့မဟုတ် Member ဝင်ထားကြောင်း သေချာပါစေ။*")

# 4. Remove Destination Channel
@bot.on_message(filters.command("rm_dest") & filters.user(OWNER_ID))
async def rm_dest_cmd(client, message):
    if len(message.command) < 2:
        await message.reply("⚠️ သုံးစွဲပုံ: `/rm_dest -10012345678` သို့မဟုတ် `/rm_dest @channelname`")
        return
    
    target = message.command[1]
    chat_id = int(target) if target.lstrip('-').isdigit() else target
    
    if chat_id in DESTS:
        DESTS.remove(chat_id)
        await message.reply(f"🗑 Destination Channel `{chat_id}` ကို ဖြုတ်လိုက်ပါပြီ။")
    else:
        await message.reply("❌ ထို Channel သည် Destination စာရင်းထဲတွင် မရှိပါ။")

# 5. List Channels
@bot.on_message(filters.command("list") & filters.user(OWNER_ID))
async def list_cmd(client, message):
    src_text = "\n".join([f"• `{s}`" for s in SOURCES]) if SOURCES else "မရှိသေးပါ"
    dst_text = "\n".join([f"• `{d}`" for d in DESTS]) if DESTS else "မရှိသေးပါ"
    
    await message.reply(f"📢 **Sources:**\n{src_text}\n\n🎯 **Destinations:**\n{dst_text}")

# ==========================================
# 🔘 INLINE BUTTON HANDLER
# ==========================================
@bot.on_callback_query(filters.user(OWNER_ID))
async def callback_handler(client, query):
    global IS_PAUSED, REMOVE_LINKS, REMOVE_USERNAMES
    
    data = query.data
    
    if data == "toggle_pause":
        IS_PAUSED = not IS_PAUSED
        state = "ခဏရပ်ထားပါသည်" if IS_PAUSED else "ပြန်လည်စတင်ပါပြီ"
        await query.answer(f"Bot ကို {state}။", show_alert=True)
        await query.message.edit_reply_markup(reply_markup=get_main_menu())
        
    elif data == "toggle_links":
        REMOVE_LINKS = not REMOVE_LINKS
        state = "Link များ ဖြုတ်မည်" if REMOVE_LINKS else "Link များ မဖြုတ်ပါ"
        await query.answer(f"Setting: {state}")
        await query.message.edit_reply_markup(reply_markup=get_main_menu())

    elif data == "toggle_usernames":
        REMOVE_USERNAMES = not REMOVE_USERNAMES
        state = "Usernames များ ဖြုတ်မည်" if REMOVE_USERNAMES else "Usernames များ မဖြုတ်ပါ"
        await query.answer(f"Setting: {state}")
        await query.message.edit_reply_markup(reply_markup=get_main_menu())

    elif data == "list_channels":
        src_text = "\n".join([f"• `{s}`" for s in SOURCES]) if SOURCES else "မရှိသေးပါ"
        dst_text = "\n".join([f"• `{d}`" for d in DESTS]) if DESTS else "မရှိသေးပါ"
        await query.message.reply(f"📢 **Active Sources:**\n{src_text}\n\n🎯 **Active Destinations:**\n{dst_text}")
        await query.answer()

    elif data == "view_stats":
        uptime = round((time.time() - START_TIME) / 3600, 2)
        state_text = "Paused ⏸" if IS_PAUSED else "Running ▶️"
        
        text = f"📊 **Bot Statistics**\n\n"
        text += f"▪️ State: `{state_text}`\n"
        text += f"▪️ Cloned Messages: `{CLONED_COUNT}`\n"
        text += f"▪️ Uptime: `{uptime} Hours`\n"
        text += f"▪️ Sources Count: `{len(SOURCES)}`\n"
        text += f"▪️ Dests Count: `{len(DESTS)}`"
        
        await query.answer()
        await query.message.reply(text)

# ==========================================
# 🔄 DYNAMIC USERBOT CLONER LOGIC
# ==========================================

# Text processing function
def process_caption(text):
    if not text:
        return text
    if REMOVE_LINKS:
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
    if REMOVE_USERNAMES:
        text = re.sub(r'@[a-zA-Z0-9_]+', '', text)
    return text

# Custom Filter to dynamically match active SOURCES
async def dynamic_sources_filter(_, __, message):
    if IS_PAUSED or not SOURCES:
        return False
    chat_id = message.chat.id
    username = f"@{message.chat.username}" if message.chat.username else None
    return (chat_id in SOURCES) or (username in SOURCES)

source_filter = filters.create(dynamic_sources_filter)

@userbot.on_message(source_filter)
async def userbot_cloner(client, message):
    global CLONED_COUNT

    original_text = message.text or message.caption or ""
    new_text = process_caption(original_text)

    for dest in list(DESTS):
        try:
            if message.text:
                await userbot.send_message(dest, new_text)
            else:
                await message.copy(dest, caption=new_text)
                
            CLONED_COUNT += 1
            await asyncio.sleep(2.5) # Anti-flood delay

        except FloodWait as e:
            logger.warning(f"FloodWait: {e.value} စက္ကန့် စောင့်ပါမည်...")
            await asyncio.sleep(e.value + 2)
            await message.copy(dest, caption=new_text)
            CLONED_COUNT += 1
        except Exception as e:
            logger.error(f"Error copying to {dest}: {e}")

# ==========================================
# 🚀 MAIN RUNNER WITH AUTO-CACHE
# ==========================================
async def main():
    logger.info("Userbot စတင်နေပါသည်...")
    await userbot.start()
    
    logger.info("Controller Bot စတင်နေပါသည်...")
    await bot.start()

    # Pre-cache Sources and Destinations
    logger.info("Channels များကို Auto-Cache လုပ်နေပါသည်...")
    all_chats = list(SOURCES) + list(DESTS)
    for c_id in all_chats:
        try:
            await userbot.get_chat(c_id)
            logger.info(f"✅ Chat Cached: {c_id}")
        except Exception as e:
            logger.error(f"❌ Cache Error ({c_id}): {e}")

    logger.info("✅ Full Control Cloner Bot အဆင်သင့်ဖြစ်ပါပြီ!")
    await idle()
    
    await userbot.stop()
    await bot.stop()

if __name__ == "__main__":
    asyncio.run(main())
