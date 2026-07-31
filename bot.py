import os
import asyncio
import logging
import time
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Railway Variables ---
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OWNER_ID = int(os.environ.get("OWNER_ID", 0)) # ထိန်းချုပ်မည့် သင့်ရဲ့ User ID

SOURCES = [int(x) if x.lstrip('-').isdigit() else x for x in os.environ.get("SOURCES", "").split(",") if x]
DESTS = [int(x) if x.lstrip('-').isdigit() else x for x in os.environ.get("DESTS", "").split(",") if x]

# --- Global Control Variables ---
is_paused = False
cloned_count = 0
start_time = time.time()

# 1. Userbot Client (ပိတ်ထားသော Channel များမှ ကူးပေးမည့် အကောင့်အစစ်)
userbot = Client("userbot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)

# 2. Controller Bot Client (သင့်ကို Control လုပ်ခွင့်ပေးမည့် Bot)
bot = Client("controller_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)


# ==========================================
# 🤖 BOT CONTROLLER LOGIC (Bot ဖြင့် ထိန်းချုပ်ခြင်း)
# ==========================================

# Control Panel ခလုတ်များ
def get_control_panel():
    state = "⏸ Paused" if is_paused else "▶️ Running"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Status: {state}", callback_data="none")],
        [InlineKeyboardButton("▶️ Resume", callback_data="resume"), InlineKeyboardButton("⏸ Pause", callback_data="pause")],
        [InlineKeyboardButton("📊 Check Stats", callback_data="stats")]
    ])

@bot.on_message(filters.command("start") & filters.user(OWNER_ID))
async def start_cmd(client, message):
    await message.reply_text(
        "🎛 **Userbot Controller Panel**\n\nအောက်ပါ ခလုတ်များကို နှိပ်၍ Userbot ကို အပြည့်အဝ ထိန်းချုပ်နိုင်ပါသည်။",
        reply_markup=get_control_panel()
    )

@bot.on_callback_query(filters.user(OWNER_ID))
async def callback_handler(client, query):
    global is_paused
    
    data = query.data
    
    if data == "pause":
        is_paused = True
        await query.answer("Userbot ကို ခဏရပ်ထားလိုက်ပါပြီ။", show_alert=True)
        await query.message.edit_reply_markup(reply_markup=get_control_panel())
        
    elif data == "resume":
        is_paused = False
        await query.answer("Userbot ပြန်လည် အလုပ်လုပ်နေပါပြီ။", show_alert=True)
        await query.message.edit_reply_markup(reply_markup=get_control_panel())
        
    elif data == "stats":
        uptime = round((time.time() - start_time) / 3600, 2)
        state_text = "Paused ⏸" if is_paused else "Running ▶️"
        
        text = f"📊 **Bot Statistics**\n\n"
        text += f"▪️ State: `{state_text}`\n"
        text += f"▪️ Cloned Messages: `{cloned_count}`\n"
        text += f"▪️ Uptime: `{uptime} Hours`\n"
        text += f"▪️ Sources: `{len(SOURCES)}`\n"
        text += f"▪️ Destinations: `{len(DESTS)}`"
        
        await query.answer("Stats updated!")
        await query.message.edit_text(text, reply_markup=get_control_panel())


# ==========================================
# 🔄 USERBOT CLONER LOGIC (မိတ္တူကူးမည့် အပိုင်း)
# ==========================================

@userbot.on_message(filters.chat(SOURCES))
async def userbot_cloner(client, message):
    global cloned_count
    
    # ⏸ Pause လုပ်ထားလျှင် ကျော်သွားမည်
    if is_paused:
        return

    for dest in DESTS:
        try:
            await message.copy(dest)
            cloned_count += 1
            await asyncio.sleep(2.5) # Anti-ban delay
            
        except FloodWait as e:
            logger.warning(f"FloodWait: {e.value} စက္ကန့် စောင့်နေပါသည်။")
            await asyncio.sleep(e.value + 2)
            await message.copy(dest)
            cloned_count += 1
        except Exception as e:
            logger.error(f"Error copying to {dest}: {e}")

# ==========================================
# 🚀 MAIN RUNNER (Client နှစ်ခုလုံးကို တစ်ပြိုင်နက် Run ခြင်း)
# ==========================================
async def main():
    logger.info("Starting Userbot...")
    await userbot.start()
    
    logger.info("Starting Controller Bot...")
    await bot.start()
    
    logger.info("✅ Dual Clients အောင်မြင်စွာ Run နေပါပြီ။")
    await idle()
    
    await userbot.stop()
    await bot.stop()

if __name__ == "__main__":
    asyncio.run(main())
