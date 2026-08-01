import os
import re
import sys
import json
import time
import psutil
import asyncio
import traceback
from datetime import datetime
from threading import Thread
from flask import Flask

# --- Telegram Native Client & Safe Imports ---
from telethon import TelegramClient, events, errors, functions
from telethon.sessions import StringSession

# --- 1. Web Server (Railway Keep-Alive Server) ---
app = Flask('')

@app.route('/')
def home():
    return "Next-Level Ultimate Engine is Live and Running Perfectly!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- 2. Telegram API Credentials ---
API_ID = 38078790
API_HASH = 'c1b7e324a99544d7a9229ff5324af362'
TARGET_CHANNEL = -1003351682369  
SESSION_STRING = os.environ.get("SESSION_STRING")

# --- 3. Persistent JSON Database Setup ---
DB_FILE = "ultimate_db.json"

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[-] DB Read Error: {e}")
    return {
        "sources": [],
        "priority_sources": [],
        "duplicates": [],
        "catalog": {},
        "daily_stats": {},
        "watermark": "📥 **Uploaded by Our Channel**",
        "clean_ads": True,
        "status": "ON"
    }

def save_db():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(DB, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"[-] DB Save Error: {e}")

DB = load_db()
start_time = time.time()

# --- 4. Userbot Client Initialization ---
bot = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

# --- Session Refresher Service ---
async def session_refresher():
    while True:
        try:
            await bot.get_me()
            print("[+] Session Keep-Alive Ping Sent.")
        except Exception as e:
            print(f"[-] Session Ping Exception: {e}")
        await asyncio.sleep(1800)

# --- Anti-Flood Safe Upload Processor ---
async def safe_upload(message, caption):
    file_id = None
    if message.video:
        file_id = str(message.media.document.id)
    elif message.document:
        file_id = str(message.media.document.id)

    # Duplicate Prevention Check
    if file_id and file_id in DB.get("duplicates", []):
        print(f"[-] Skipped Duplicate File ID: {file_id}")
        return False

    while True:
        try:
            sent_msg = await bot.send_file(TARGET_CHANNEL, message.media, caption=caption.strip())
            
            if file_id:
                DB["duplicates"].append(file_id)

            title = message.text.split("\n")[0][:50] if message.text else "Unknown Movie"
            msg_link = f"https://t.me/c/{str(TARGET_CHANNEL).replace('-100','')}/{sent_msg.id}"
            DB["catalog"][title.lower()] = {"title": title, "link": msg_link}

            today = datetime.now().strftime("%Y-%m-%d")
            DB["daily_stats"][today] = DB["daily_stats"].get(today, 0) + 1

            save_db()
            print(f"[+] Successfully Uploaded: {title}")
            return True

        except errors.FloodWaitError as e:
            print(f"[!] [Anti-Flood] Limit reached. Waiting for {e.seconds} seconds...")
            await asyncio.sleep(e.seconds + 5)
        except Exception as upload_err:
            print(f"[-] Upload Failed Error: {upload_err}")
            return False

# --- History Movie Crawler Engine ---
async def clone_old_videos(source_chat):
    print(f"[+] History Crawler Started for Source: {source_chat}")
    try:
        async for message in bot.iter_messages(source_chat, reverse=True):
            if DB.get("status") == "OFF":
                print("[-] Bot Engine is Paused. Crawler Stopping.")
                break
            if message.video or message.document:
                caption = message.text or ""
                if DB.get("clean_ads", True):
                    caption = re.sub(r'http\S+', '', caption)
                    caption = re.sub(r'@\S+', '', caption)
                    caption = re.sub(r'(?i)(join|sub|channel|promo|1xbet|sponsor)', '', caption)
                if DB.get("watermark"):
                    caption = f"**{caption.strip()}**\n\n{DB['watermark']}" if caption.strip() else DB["watermark"]

                await safe_upload(message, caption)
                await asyncio.sleep(2.0)
    except Exception as crawler_err:
        print(f"[-] Crawler Execution Error on {source_chat}: {crawler_err}")

# --- Main Engine Core Execution ---
async def main():
    await bot.start()
    print("==================================================")
    print("🚀 ULTRA ENGINE USERBOT IS ONLINE & READY!")
    print("==================================================")
    
    asyncio.create_task(session_refresher())

    # --- Commands Handler (Outgoing=True မှန်သမျှ ဆရာကြီး ရိုက်လိုက်သည့် Command များ ဖြစ်သည်) ---
    @bot.on(events.NewMessage(pattern=r'(?i)^/start$', outgoing=True))
    async def start_cmd(event):
        menu_text = (
            "👑 **ULTRA NEXT-LEVEL USERBOT ENGINE** 👑\n\n"
            "• `/add @username` - Source ချန်နယ်အသစ်ထည့်၍ ကားဟောင်းများ Auto တင်ရန်\n"
            "• `/priority @username` - [Priority Watchlist] ဦးစားပေး ချန်နယ်သတ်မှတ်ရန်\n"
            "• `/join Link` - Private/Public Link များဖြင့် Auto Join ရန်\n"
            "• `/search နာမည်` - Catalog Database ထဲတွင် ရုပ်ရှင်ပြန်ရှာရန်\n"
            "• `/status` - Railway CPU, RAM နှင့် ယနေ့ Upload စာရင်းစစ်ရန်\n"
            "• `/backup` - JSON Database Backup ဖိုင်ထုတ်ယူရန်\n"
            "• `/clear` - Source List အားလုံးကို ရှင်းထုတ်ရန်\n"
            "• `/toggle` - Engine မောင်းနှင်မှုကို ခဏရပ်ရန်/ပြန်ဖွင့်ရန်"
        )
        await event.respond(menu_text)

    @bot.on(events.NewMessage(pattern=r'(?i)^/join (.+)', outgoing=True))
    async def join_cmd(event):
        link = event.pattern_match.group(1).strip()
        try:
            if "+" in link or "joinchat" in link:
                hash_code = link.split('/')[-1].replace('+', '')
                await bot(functions.messages.ImportChatInviteRequest(hash_code))
            else:
                await bot(functions.channels.JoinChannelRequest(link))
            await event.respond(f"✅ **အောင်မြင်စွာ Join ပြီးပါပြီ:** {link}")
        except Exception as e:
            await event.respond(f"❌ Join ရန် အဆင်မပြေပါ: `{e}`")

    @bot.on(events.NewMessage(pattern=r'(?i)^/add (.+)', outgoing=True))
    async def add_cmd(event):
        src = event.pattern_match.group(1).strip()
        if src not in DB["sources"]:
            DB["sources"].append(src)
            save_db()
            await event.respond(f"📡 **Source List ထဲထည့်ပြီးပါပြီ:** `{src}`\n🔄 ကားအဟောင်းများကို စတင်ဆွဲတင်နေပါပြီ...")
            asyncio.create_task(clone_old_videos(src))
        else:
            await event.respond("⚠️ ရှိပြီးသား Source ဖြစ်ပါသည် ဆရာကြီး။")

    @bot.on(events.NewMessage(pattern=r'(?i)^/priority (.+)', outgoing=True))
    async def priority_cmd(event):
        src = event.pattern_match.group(1).strip()
        if src not in DB["priority_sources"]:
            DB["priority_sources"].append(src)
            if src not in DB["sources"]:
                DB["sources"].append(src)
            save_db()
            await event.respond(f"⭐ **[Priority] ဦးစားပေး စာရင်းထဲထည့်ပြီးပါပြီ:** `{src}`")
        else:
            await event.respond("⚠️ ဦးစားပေး စာရင်းထဲတွင် ရှိပြီးသားပါ။")

    @bot.on(events.NewMessage(pattern=r'(?i)^/search (.+)', outgoing=True))
    async def search_cmd(event):
        query = event.pattern_match.group(1).strip().lower()
        results = [v for k, v in DB["catalog"].items() if query in k]

        if not results:
            await event.respond("❌ ရှာဖွေမှုရလဒ် မရှိပါ ဆရာကြီး။")
            return

        msg = "🔍 **ရှာဖွေတွေ့ရှိသော ရုပ်ရှင်မှတ်တမ်းများ:**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        for res in results[:15]:
            msg += f"🎬 [{res['title']}]({res['link']})\n"
        await event.respond(msg, link_preview=False)

    @bot.on(events.NewMessage(pattern=r'(?i)^/status$', outgoing=True))
    async def status_cmd(event):
        uptime = f"{int(time.time() - start_time) // 3600}h {int(time.time() - start_time) % 3600 // 60}m"
        ram = psutil.virtual_memory().percent
        cpu = psutil.cpu_percent()
        today = datetime.now().strftime("%Y-%m-%d")
        today_count = DB["daily_stats"].get(today, 0)

        status_msg = (
            "📊 **ULTRA ENGINE HARDWARE MONITOR**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚡ **Status:** `{DB.get('status', 'ON')}`\n"
            f"⏱ **Bot Uptime:** `{uptime}`\n"
            f"🎛 **Railway CPU Usage:** `{cpu}%`\n"
            f"🧠 **Railway RAM Usage:** `{ram}%`\n"
            f"📅 **Today Uploads ({today}):** `{today_count} Movies`\n"
            f"📦 **Total Cataloged:** `{len(DB['catalog'])} Movies`\n"
            f"🚫 **Duplicates Blocked:** `{len(DB['duplicates'])} Files`"
        )
        await event.respond(status_msg)

    @bot.on(events.NewMessage(pattern=r'(?i)^/backup$', outgoing=True))
    async def backup_cmd(event):
        save_db()
        await bot.send_file(event.chat_id, DB_FILE, caption="📦 **Ultimate Bot Engine Database Backup File**")

    @bot.on(events.NewMessage(pattern=r'(?i)^/clear$', outgoing=True))
    async def clear_cmd(event):
        DB["sources"] = []
        DB["priority_sources"] = []
        save_db()
        await event.respond("🗑 **Sources List အားလုံးကို ရှင်းလင်းလိုက်ပါပြီ။**")

    @bot.on(events.NewMessage(pattern=r'(?i)^/toggle$', outgoing=True))
    async def toggle_cmd(event):
        DB["status"] = "OFF" if DB.get("status") == "ON" else "ON"
        save_db()
        await event.respond(f"⚙️ **Engine Status သို့ ပြောင်းလဲလိုက်ပါပြီ:** `{DB['status']}`")

    # Restore Command Handling (Reply to ultimate_db.json file)
    @bot.on(events.NewMessage(outgoing=True))
    async def restore_cmd(event):
        if event.text == "/restore" and event.is_reply:
            reply_msg = await event.get_reply_message()
            if reply_msg.document and reply_msg.document.attributes[0].file_name == DB_FILE:
                global DB
                path = await reply_msg.download_media()
                with open(path, "r", encoding="utf-8") as f:
                    DB = json.load(f)
                save_db()
                os.remove(path)
                await event.respond("✅ **Database/Settings အားလုံးကို Backup ဖိုင်မှတစ်ဆင့် Restore အောင်မြင်ပါပြီ!**")

    # --- Live Real-Time Forwarder Listener ---
    @bot.on(events.NewMessage())
    async def live_forwarder(event):
        if DB.get("status") == "OFF" or not DB.get("sources"):
            return
        try:
            chat = await event.get_chat()
            is_in_list = False
            for src in DB["sources"]:
                if chat and chat.username and f"@{chat.username.lower()}" == src.lower():
                    is_in_list = True
                elif chat and str(chat.id) == src.lstrip('-'):
                    is_in_list = True

            if is_in_list and (event.message.video or event.message.document):
                caption = event.message.text or ""
                if DB.get("clean_ads", True):
                    caption = re.sub(r'http\S+', '', caption)
                    caption = re.sub(r'@\S+', '', caption)
                    caption = re.sub(r'(?i)(join|sub|channel|promo|1xbet|sponsor)', '', caption)
                if DB.get("watermark"):
                    caption = f"**{caption.strip()}**\n\n{DB['watermark']}" if caption.strip() else DB["watermark"]

                await safe_upload(event.message, caption)
        except Exception:
            pass

    await bot.run_until_disconnected()

if __name__ == '__main__':
    Thread(target=run_web).start()
    asyncio.run(main())
