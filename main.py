import os
import re
import sys
import json
import time
import logging
import psutil
import asyncio
from datetime import datetime
from threading import Thread
from flask import Flask

# Suppress Werkzeug logs for clean terminal output
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# --- 1. Web Server (Railway Keep-Alive) ---
app = Flask('')

@app.route('/')
def home():
    return " Ultimate Pro Engine v9.0 (Final Big Upgrade) is Live!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# --- Telegram Native Client & Safe Imports ---
from telethon import TelegramClient, events, errors, functions, types
from telethon.sessions import StringSession

# --- 2. Telegram API Credentials ---
API_ID = 38078790
API_HASH = 'c1b7e324a99544d7a9229ff5324af362'
SESSION_STRING = os.environ.get("SESSION_STRING")

# --- 3. Engine Configuration ---
CONCURRENT_WORKERS = 5
DB_FILE = "ultimate_db.json"
TEMP_DIR = "temp_downloads"
THUMB_PATH = "custom_thumb.jpg"

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "target_channel": -1003351682369,
        "log_channel": None,
        "sources": [],
        "duplicates": [],
        "catalog": {},
        "daily_stats": {},
        "crawler_progress": {},
        "header": "",
        "watermark": " **Uploaded by Our Channel**",
        "footer": "",
        "media_filter": "all",
        "replace_link": "",
        "clean_ads": True,
        "auto_tags": False,     # V9.0 Feature
        "delay_seconds": 0,     # V9.0 Feature
        "status": "ON"
    }

def save_db():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(DB, f, ensure_ascii=False, indent=4)
    except Exception:
        pass

DB = load_db()
start_time = time.time()
upload_queue = asyncio.Queue()

# --- Visual Progress Bar Generator ---
def make_progress_bar(percent):
    filled = int(percent // 10)
    bar = "" * filled + "" * (10 - filled)
    return bar

# --- Auto Hashtag Generator ---
def generate_hashtags(text):
    text_lower = text.lower()
    keywords = ['1080p', '720p', '4k', 'action', 'horror', 'comedy', 'romance', 
                'sci-fi', 'thriller', 'drama', 'animation', 'fantasy', 'myanmar', 'sub', 'dub']
    tags = [f"#{kw.replace('-', '')}" for kw in keywords if kw in text_lower]
    return " ".join(tags)

# --- 4. High-Speed Client Setup ---
bot = TelegramClient(
    StringSession(SESSION_STRING), 
    API_ID, 
    API_HASH,
    connection_retries=10,
    retry_delay=1
)

def build_caption(original_text):
    caption = original_text or ""
    rep_link = DB.get("replace_link")
    
    if rep_link:
        caption = re.sub(r'https?://t\.me/\S+', rep_link, caption)
        caption = re.sub(r'@\w+', rep_link, caption)

    if DB.get("clean_ads", True):
        if not rep_link:
            caption = re.sub(r'http\S+', '', caption)
            caption = re.sub(r'@\S+', '', caption)
        caption = re.sub(r'(?i)(join|sub|channel|promo|1xbet|sponsor)', '', caption)
    
    caption = caption.strip()
    
    # Generate Tags if enabled
    tags = ""
    if DB.get("auto_tags"):
        tags = generate_hashtags(caption)
    
    parts = []
    if DB.get("header"): parts.append(DB["header"].strip())
    if caption: parts.append(f"**{caption}**")
    if tags: parts.append(tags)
    if DB.get("watermark"): parts.append(DB["watermark"].strip())
    if DB.get("footer"): parts.append(DB["footer"].strip())
    
    return "\n\n".join(parts)

# ---  ZERO-DISK TRANSFER ENGINE ---
async def safe_upload(message, caption):
    target = DB.get("target_channel")
    if not target: return False

    file_id = str(message.media.document.id) if (message.video or message.document) else None
    if file_id and file_id in DB.get("duplicates", []): return False

    thumb_to_use = THUMB_PATH if os.path.exists(THUMB_PATH) else None

    # V9.0 Anti-Ban Delay System
    delay = DB.get("delay_seconds", 0)
    if delay > 0:
        print(f"[ Delay] Waiting {delay} seconds before sending...")
        await asyncio.sleep(delay)

    try:
        # SPEED MAX Cloud Transfer
        if not thumb_to_use and message.media:
            sent_msg = await bot.send_file(
                target, message.media, caption=caption.strip(), supports_streaming=True
            )
            if sent_msg:
                if file_id: DB["duplicates"].append(file_id)
                today = datetime.now().strftime("%Y-%m-%d")
                DB["daily_stats"][today] = DB["daily_stats"].get(today, 0) + 1
                save_db()
                return True
    except Exception:
        pass

    # FALLBACK Chunk Buffer
    while True:
        try:
            os.makedirs(TEMP_DIR, exist_ok=True)
            temp_path = await bot.download_media(message, file=TEMP_DIR)
            try:
                sent_msg = await bot.send_file(
                    target, temp_path, caption=caption.strip(), thumb=thumb_to_use,
                    supports_streaming=True, part_size_kb=1024
                )
            finally:
                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)

            if sent_msg:
                if file_id: DB["duplicates"].append(file_id)
                today = datetime.now().strftime("%Y-%m-%d")
                DB["daily_stats"][today] = DB["daily_stats"].get(today, 0) + 1
                save_db()
                return True
        except errors.FloodWaitError as e:
            await asyncio.sleep(e.seconds + 2)
        except Exception:
            return False

# --- Concurrent Parallel Queue Workers ---
async def queue_worker(worker_id):
    while True:
        message, caption = await upload_queue.get()
        try:
            await safe_upload(message, caption)
        except Exception:
            pass
        finally:
            upload_queue.task_done()
            await asyncio.sleep(0.5)

# ---  History Crawler Engine ---
async def clone_old_videos(source_chat):
    try:
        total_res = await bot.get_messages(source_chat, limit=0)
        total_msgs = total_res.total if total_res else 0
        if total_msgs == 0: return

        scanned, media_found = 0, 0
        if "crawler_progress" not in DB: DB["crawler_progress"] = {}

        async for message in bot.iter_messages(source_chat, reverse=True):
            if DB.get("status") == "OFF": break
            scanned += 1
            if message.video or message.document:
                caption = build_caption(message.text)
                await upload_queue.put((message, caption))
                media_found += 1

            pct = round((scanned / total_msgs) * 100, 1)
            DB["crawler_progress"][str(source_chat)] = {
                "total": total_msgs, "scanned": scanned, "media_found": media_found, "percent": pct
            }
            if scanned % 50 == 0 or scanned == total_msgs: save_db()
    except Exception:
        pass

# --- Resolver Helper ---
async def resolve_and_join(link_or_username):
    target_str = link_or_username.strip()
    if "t.me/" in target_str and not ("+" in target_str or "joinchat" in target_str):
        target_str = "@" + target_str.split("t.me/")[-1].replace('/', '')

    if "+" in target_str or "joinchat" in target_str:
        hash_code = target_str.split('/')[-1].replace('+', '')
        chat = await bot(functions.messages.ImportChatInviteRequest(hash_code))
        return chat.chats[0].id, f"Private Channel"
    try:
        entity = await bot.get_entity(target_str)
        try: await bot(functions.channels.JoinChannelRequest(entity))
        except: pass
        identifier = f"@{entity.username}" if entity.username else str(entity.id)
        return identifier, entity.title
    except Exception as e:
        raise Exception(str(e))

# --- Main Engine Loop ---
async def main():
    await bot.start()
    print("==================================================")
    print(" ULTIMATE PRO ENGINE v9.0 (FINAL UPGRADE) LIVE ")
    print("==================================================")
    
    for i in range(1, CONCURRENT_WORKERS + 1):
        asyncio.create_task(queue_worker(i))

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]start$'))
    async def start_cmd(event):
        target_info = DB.get("target_channel", "Not Set")
        tags_status = " ON" if DB.get("auto_tags") else " OFF"
        delay_val = DB.get("delay_seconds", 0)
        
        menu_text = (
            " **ULTIMATE PRO USERBOT v9.0** \n"
            "\n"
            f" **Target:** `{target_info}`\n"
            f" **Auto Tags:** `{tags_status}`\n"
            f" **Upload Delay:** `{delay_val} Secs`\n"
            f" **Queue Pending:** `{upload_queue.qsize()} Files`\n\n"
            
            " **FINAL COMMANDS:**\n"
            " `.status` - Visual Dashboard\n"
            " `.add <Link>` | `.del <Link>`\n"
            " `.autotags` - Toggle Genre Tags\n"
            " `.setdelay <Sec>` - Drip Upload Time\n"
            " `.sources` | `.ping`"
        )
        await event.respond(menu_text)

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]ping$'))
    async def ping_cmd(event):
        await event.respond(" **Pong!** Ultimate Engine is running seamlessly.")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]autotags$'))
    async def autotags_cmd(event):
        DB["auto_tags"] = not DB.get("auto_tags", False)
        save_db()
        status = " ENABLED" if DB["auto_tags"] else " DISABLED"
        await event.respond(f" **Auto Hashtags are now {status}.**")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]setdelay (\d+)'))
    async def setdelay_cmd(event):
        secs = int(event.pattern_match.group(1))
        DB["delay_seconds"] = secs
        save_db()
        await event.respond(f" **Upload Delay set to {secs} seconds per file.**")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]status$'))
    async def status_cmd(event):
        uptime_sec = int(time.time() - start_time)
        hours, remainder = divmod(uptime_sec, 3600)
        minutes, seconds = divmod(remainder, 60)

        vram = psutil.virtual_memory()
        cpu_pct = psutil.cpu_percent(interval=0.5)

        progress_text = ""
        crawler_data = DB.get("crawler_progress", {})
        if crawler_data:
            progress_text += "\n **LIVE CLONING PROGRESS:**\n"
            for src, data in crawler_data.items():
                pct = data['percent']
                p_bar = make_progress_bar(pct)
                progress_text += f" `{src}`\n  `{p_bar}` **{pct}%** ({data['scanned']}/{data['total']})\n"

        status_msg = (
            " **ULTIMATE DASHBOARD v9.0** \n"
            "\n"
            f" **Active Threads:** `{CONCURRENT_WORKERS}`\n"
            f" **Upload Delay:** `{DB.get('delay_seconds')}s`\n"
            f" **Pending Queue:** `{upload_queue.qsize()} Videos`\n"
            f" **CPU:** `{cpu_pct}%` |  **RAM:** `{vram.percent}%`\n"
            f" **Uptime:** `{hours}h {minutes}m`\n"
            f"{progress_text}"
            ""
        )
        await event.respond(status_msg)

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]add (.+)'))
    async def add_cmd(event):
        raw_input = event.pattern_match.group(1).strip()
        await event.respond(f" **Initializing Smart Crawler...**\n`{raw_input}`")
        try:
            identifier, title = await resolve_and_join(raw_input)
            src_key = str(identifier)
            if src_key not in DB["sources"]:
                DB["sources"].append(src_key)
                save_db()
                await event.respond(f" **Source Added & Queue Started:** `{title}`")
                asyncio.create_task(clone_old_videos(src_key))
            else:
                await event.respond(" Source already exists.")
        except Exception as e:
            await event.respond(f" Error: `{e}`")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]del (.+)'))
    async def del_cmd(event):
        raw_input = event.pattern_match.group(1).strip()
        if raw_input in DB["sources"]:
            DB["sources"].remove(raw_input)
            if raw_input in DB.get("crawler_progress", {}):
                del DB["crawler_progress"][raw_input]
            save_db()
            await event.respond(f" **Source Removed:** `{raw_input}`")
        else:
            await event.respond(" Source not found.")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]sources$'))
    async def sources_cmd(event):
        if not DB.get("sources"):
            await event.respond(" **No Active Sources.**")
            return
        msg = " **ACTIVE SOURCES:**\n"
        for idx, src in enumerate(DB["sources"], 1):
            msg += f"{idx}. `{src}`\n"
        await event.respond(msg)

    @bot.on(events.NewMessage())
    async def live_forwarder(event):
        if DB.get("status") == "OFF" or not DB.get("sources"): return
        try:
            chat = await event.get_chat()
            is_in_list = False
            for src in DB["sources"]:
                if chat and chat.username and f"@{chat.username.lower()}" == src.lower():
                    is_in_list = True
                elif chat and str(chat.id) == src:
                    is_in_list = True

            if is_in_list and (event.message.video or event.message.document):
                caption = build_caption(event.message.text)
                await upload_queue.put((event.message, caption))
        except Exception:
            pass

    await bot.run_until_disconnected()

if __name__ == '__main__':
    Thread(target=run_web).start()
    asyncio.run(main())
