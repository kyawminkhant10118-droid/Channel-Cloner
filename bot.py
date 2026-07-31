import os
import asyncio
import logging
import time
from pyrogram import Client, filters
from pyrogram.errors import FloodWait

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "")

SOURCES = [int(x) if x.lstrip('-').isdigit() else x for x in os.environ.get("SOURCES", "").split(",") if x]
DESTS = [int(x) if x.lstrip('-').isdigit() else x for x in os.environ.get("DESTS", "").split(",") if x]

app = Client("my_userbot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)

# --- Global Control Variables ---
is_paused = False
cloned_count = 0
start_time = time.time()

# ==========================================
# 🎮 BOT CONTROL COMMANDS (မိမိ Saved Messages တွင်သာ သုံးရန်)
# ==========================================

# 1. ခဏရပ်ရန် (Pause)
@app.on_message(filters.me & filters.command("pause", prefixes=["/", "."]))
async def pause_bot(client, message):
    global is_paused
    is_paused = True
    await message.edit_text("⏸ **Cloner Bot ကို ခဏရပ်ထားပါသည် (Paused)**.")

# 2. ပြန်စရန် (Resume)
@app.on_message(filters.me & filters.command("resume", prefixes=["/", "."]))
async def resume_bot(client, message):
    global is_paused
    is_paused = False
    await message.edit_text("▶️ **Cloner Bot ပြန်လည် အလုပ်လုပ်နေပါပြီ (Resumed)**.")

# 3. အခြေအနေစစ်ရန် (Status)
@app.on_message(filters.me & filters.command("status", prefixes=["/", "."]))
async def status_bot(client, message):
    state = "Paused ⏸" if is_paused else "Running ▶️"
    uptime = round((time.time() - start_time) / 3600, 2)
    
    text = f"📊 **Bot Status**\n\n"
    text += f"▪️ State: `{state}`\n"
    text += f"▪️ Cloned Messages: `{cloned_count}`\n"
    text += f"▪️ Uptime: `{uptime} Hours`\n"
    text += f"▪️ Sources: `{len(SOURCES)}`\n"
    text += f"▪️ Destinations: `{len(DESTS)}`"
    
    await message.edit_text(text)

# 4. အလုပ်လုပ်/မလုပ် စစ်ရန် (Ping)
@app.on_message(filters.me & filters.command("ping", prefixes=["/", "."]))
async def ping_bot(client, message):
    start = time.time()
    await message.edit_text("Pinging...")
    end = time.time()
    await message.edit_text(f"🏓 **Pong!** \nLatency: `{round((end - start) * 1000, 2)}ms`")

# ==========================================
# 🔄 CLONER LOGIC (မိတ္တူကူးမည့် အပိုင်း)
# ==========================================

@app.on_message(filters.chat(SOURCES))
async def userbot_cloner(client, message):
    global cloned_count
    
    # ⏸ Pause လုပ်ထားရင် အောက်က Code တွေကို ဆက်မလုပ်ဘဲ ရပ်နေမည်
    if is_paused:
        return

    for dest in DESTS:
        try:
            await message.copy(dest)
            cloned_count += 1
            await asyncio.sleep(2) # Anti-ban delay

        except FloodWait as e:
            logger.warning(f"FloodWait: {e.value} စက္ကန့် စောင့်နေပါသည်။")
            await asyncio.sleep(e.value + 2)
            await message.copy(dest)
            cloned_count += 1
        except Exception as e:
            logger.error(f"Error copying to {dest}: {e}")

if __name__ == "__main__":
    logger.info("✅ Userbot Cloner + Control Features စတင်ပါပြီ...")
    app.run()
