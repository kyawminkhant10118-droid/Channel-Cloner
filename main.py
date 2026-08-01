import os
import re
import sys
import json
import time
import logging
import psutil
import asyncio
import subprocess
from datetime import datetime
from threading import Thread
from flask import Flask

# Suppress Werkzeug logs for clean terminal output
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# --- 1. Web Server (Railway Keep-Alive) ---
app = Flask('')

@app.route('/')
def home():
    return "Ultra Pro Engine v7.5 (Speed Max + Progress Edition) is Live!"

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

# --- 3. Speed Max Configuration ---
CONCURRENT_WORKERS = 5  # 5 Parallel Workers for Multi-upload
DB_FILE = "ultimate_db.json"
TEMP_DIR = "temp_downloads"
THUMB_PATH = "custom_thumb.jpg"

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[-] DB Read Error: {e}")
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

# --- Async Multi-Worker Task Queue ---
upload_queue = asyncio.Queue()

# --- 4. High-Speed Client Setup ---
bot = TelegramClient(
    StringSession(SESSION_STRING), 
    API_ID, 
    API_HASH,
    connection_retries=10,
    retry_delay=1
)

async def send_log(text):
    log_id = DB.get("log_channel")
    if log_id:
        try:
            await bot.send_message(log_id, text)
        except Exception as e:
            print(f"[-] Log Send Failed: {e}")

async def setup_bot_command_menu():
    try:
        if not await bot.is_bot():
            return
        commands = [
            types.BotCommand(command="start", description=" Main Help Menu"),
            types.BotCommand(command="status", description=" Live Progress & Diagnostics"),
            types.BotCommand(command="add", description=" Add Source Channel"),
            types.BotCommand(command="del", description=" Remove Source Channel"),
            types.BotCommand(command="sources", description=" List Active Sources"),
            types.BotCommand(command="settarget", description=" Set Target Channel"),
            types.BotCommand(command="setthumb", description=" Set Custom Poster"),
            types.BotCommand(command="delthumb", description=" Del Thumb (Max Speed Mode)"),
            types.BotCommand(command="setlog", description=" Set Log Channel"),
            types.BotCommand(command="backup", description=" Download DB Backup"),
            types.BotCommand(command="toggle", description=" Pause or Resume Engine")
        ]
        await bot(functions.bots.SetBotCommandsRequest(
            scope=types.BotCommandScopeDefault(),
            lang_code='en',
            commands=commands
        ))
    except Exception:
        pass

async def session_refresher():
    while True:
        try:
            await bot.get_me()
        except Exception:
            pass
        await asyncio.sleep(1800)

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
    parts = []
    if DB.get("header"): parts.append(DB["header"].strip())
    if caption: parts.append(f"**{caption}**")
    if DB.get("watermark"): parts.append(DB["watermark"].strip())
    if DB.get("footer"): parts.append(DB["footer"].strip())
    
    return "\n\n".join(parts)

# ---  SPEED MAX ZERO-DISK TRANSFER ENGINE ---
async def safe_upload(message, caption):
    target = DB.get("target_channel")
    if not target:
        return False

    media_mode = DB.get("media_filter", "all")
    if media_mode == "video" and not message.video:
        return False
    elif media_mode == "document" and not (message.document and not message.video):
        return False

    file_id = str(message.media.document.id) if (message.video or message.document) else None

    if file_id and file_id in DB.get("duplicates", []):
        return False

    thumb_to_use = THUMB_PATH if os.path.exists(THUMB_PATH) else None

    # LEVEL 1: Direct Cloud Transfer (0.5 - 1s Speed)
    try:
        if not thumb_to_use and message.media:
            sent_msg = await bot.send_file(
                target, 
                message.media, 
                caption=caption.strip(),
                supports_streaming=True
            )
            if sent_msg:
                if file_id: DB["duplicates"].append(file_id)
                save_db()
                print(f"[ SPEED MAX SUCCESS] Instant Cloud Forward Completed!")
                return True
    except Exception as forward_err:
        print(f"[!] Direct Forward Bypass Error: {forward_err} -> Fallback to Chunk Buffer...")

    # LEVEL 2: 1024KB Multi-part Parallel Chunk Buffer
    while True:
        try:
            os.makedirs(TEMP_DIR, exist_ok=True)
            temp_path = await bot.download_media(message, file=TEMP_DIR)
            
            try:
                sent_msg = await bot.send_file(
                    target, 
                    temp_path, 
                    caption=caption.strip(),
                    thumb=thumb_to_use,
                    supports_streaming=True,
                    part_size_kb=1024
                )
            finally:
                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)

            if sent_msg:
                if file_id: DB["duplicates"].append(file_id)
                
                title = message.text.split("\n")[0][:50] if message.text else "Unknown Video"
                clean_target = str(target).replace('-100', '')
                msg_link = f"https://t.me/c/{clean_target}/{sent_msg.id}"
                DB["catalog"][title.lower()] = {"title": title, "link": msg_link}

                today = datetime.now().strftime("%Y-%m-%d")
                DB["daily_stats"][today] = DB["daily_stats"].get(today, 0) + 1
                save_db()

                await send_log(f" **Uploaded:**\n {title}\n [View Post]({msg_link})")
                return True

        except errors.FloodWaitError as e:
            await asyncio.sleep(e.seconds + 2)
        except Exception as upload_err:
            print(f"[-] Upload Error: {upload_err}")
            return False

# --- Concurrent Parallel Queue Workers ---
async def queue_worker(worker_id):
    print(f"[ Worker-{worker_id}] High-Speed Worker Active.")
    while True:
        message, caption = await upload_queue.get()
        try:
            await safe_upload(message, caption)
        except Exception as e:
            print(f"[-] Worker-{worker_id} Task Error: {e}")
        finally:
            upload_queue.task_done()
            await asyncio.sleep(0.5)

# ---  History Crawler Engine with Progress Tracker (%) ---
async def clone_old_videos(source_chat):
    print(f"[+] History Speed Crawler Started for: {source_chat}")
    try:
        total_res = await bot.get_messages(source_chat, limit=0)
        total_msgs = total_res.total if total_res else 0

        if total_msgs == 0:
            print(f"[-] No messages found in {source_chat}")
            return

        scanned = 0
        media_found = 0

        if "crawler_progress" not in DB:
            DB["crawler_progress"] = {}

        async for message in bot.iter_messages(source_chat, reverse=True):
            if DB.get("status") == "OFF":
                print("[!] Engine paused. Stopping crawler...")
                break

            scanned += 1

            if message.video or message.document:
                caption = build_caption(message.text)
                await upload_queue.put((message, caption))
                media_found += 1

            pct = round((scanned / total_msgs) * 100, 1)

            DB["crawler_progress"][str(source_chat)] = {
                "total": total_msgs,
                "scanned": scanned,
                "media_found": media_found,
                "percent": pct
            }

            if scanned % 50 == 0 or scanned == total_msgs:
                print(f"[ PROGRESS] Channel: {source_chat} | {pct}% Scanned ({scanned}/{total_msgs}) | Found: {media_found} Videos")
                save_db()

        print(f"[ CRAWLE COMPLETED] {source_chat} -> 100% Fully Queued!")

    except Exception as crawler_err:
        print(f"[-] Crawler Error ({source_chat}): {crawler_err}")

# --- Resolver Helper ---
async def resolve_and_join(link_or_username):
    target_str = link_or_username.strip()
    
    if "t.me/" in target_str and not ("+" in target_str or "joinchat" in target_str):
        target_str = "@" + target_str.split("t.me/")[-1].replace('/', '')

    if "+" in target_str or "joinchat" in target_str:
        hash_code = target_str.split('/')[-1].replace('+', '')
        chat = await bot(functions.messages.ImportChatInviteRequest(hash_code))
        entity = chat.chats[0]
        return entity.id, f"Private Channel ({entity.title})"

    try:
        entity = await bot.get_entity(target_str)
        try:
            await bot(functions.channels.JoinChannelRequest(entity))
        except: pass
        
        identifier = f"@{entity.username}" if entity.username else str(entity.id)
        return identifier, entity.title
    except Exception as e:
        raise Exception(f"Link / Username Error: {e}")

# --- Main Engine Loop ---
async def main():
    await bot.start()
    print("==================================================")
    print(" ULTRA PRO ENGINE v7.5 (PROGRESS EDITION) LIVE ")
    print("==================================================")
    
    await setup_bot_command_menu()
    
    for i in range(1, CONCURRENT_WORKERS + 1):
        asyncio.create_task(queue_worker(i))

    asyncio.create_task(session_refresher())

    # --- Commands ---
    @bot.on(events.NewMessage(pattern=r'(?i)^/start$', outgoing=True))
    async def start_cmd(event):
        target_info = DB.get("target_channel", "Not Set")
        speed_status = " SPEED MAX (Zero-Disk Cloud Copy)" if not os.path.exists(THUMB_PATH) else " NORMAL (Custom Poster Active)"
        
        menu_text = (
            " **ULTRA PRO USERBOT v7.5 (PROGRESS EDITION)** \n"
            "\n"
            f" **Target Channel:** `{target_info}`\n"
            f" **Engine Mode:** `{speed_status}`\n"
            f" **Active Workers:** `{CONCURRENT_WORKERS} Parallel Workers`\n"
            f" **Queue Pending:** `{upload_queue.qsize()} Files`\n\n"

            " **COMMANDS:**\n"
            " `/status` - Live Progress (%) & Diagnostic\n"
            " `/add <Link>` - Add Source & Auto-Clone\n"
            " `/del <Link>` - Remove Source Channel\n"
            " `/sources` - View Active Source List\n"
            " `/delthumb` - Switch to Speed Max Mode\n"
            " `/backup` - Download Database Backup"
        )
        await event.respond(menu_text)

    @bot.on(events.NewMessage(pattern=r'(?i)^/status$', outgoing=True))
    async def status_cmd(event):
        uptime_sec = int(time.time() - start_time)
        hours, remainder = divmod(uptime_sec, 3600)
        minutes, seconds = divmod(remainder, 60)

        vram = psutil.virtual_memory()
        cpu_pct = psutil.cpu_percent(interval=0.5)
        today = datetime.now().strftime("%Y-%m-%d")

        progress_text = ""
        crawler_data = DB.get("crawler_progress", {})
        if crawler_data:
            progress_text += "\n **CHANNEL CLONING PROGRESS:**\n"
            for src, data in crawler_data.items():
                progress_text += (
                    f" `{src}`: **{data['percent']}%** "
                    f"({data['scanned']}/{data['total']} msgs) "
                    f"-  `{data['media_found']} Videos`\n"
                )

        status_msg = (
            " **SPEED MAX DIAGNOSTICS v7.5** \n"
            "\n"
            f" **Parallel Workers:** `{CONCURRENT_WORKERS} Active Threads`\n"
            f" **Queue Pending:** `{upload_queue.qsize()} Videos in Queue`\n"
            f" **CPU Usage:** `{cpu_pct}%`\n"
            f" **RAM Usage:** `{vram.percent}%`\n"
            f" **Uptime:** `{hours}h {minutes}m`\n"
            f"{progress_text}\n"
            f" **Today Uploads:** `{DB['daily_stats'].get(today, 0)} Files`\n"
            ""
        )
        await event.respond(status_msg)

    @bot.on(events.NewMessage(pattern=r'(?i)^/setthumb$', outgoing=True))
    async def setthumb_cmd(event):
        reply = await event.get_reply_message()
        if reply and reply.photo:
            await bot.download_media(reply.photo, file=THUMB_PATH)
            await event.respond(" Custom Poster Set!")
        else:
            await event.respond(" Reply to an image with `/setthumb`")

    @bot.on(events.NewMessage(pattern=r'(?i)^/delthumb$', outgoing=True))
    async def delthumb_cmd(event):
        if os.path.exists(THUMB_PATH):
            os.remove(THUMB_PATH)
            await event.respond(" **Poster Removed! Switched to Speed Max Zero-Disk Mode!**")
        else:
            await event.respond(" Custom Thumbnail does not exist.")

    @bot.on(events.NewMessage(pattern=r'(?i)^/add (.+)', outgoing=True))
    async def add_cmd(event):
        raw_input = event.pattern_match.group(1).strip()
        await event.respond(f" **Adding Source & Starting Crawler...**\n`{raw_input}`")
        try:
            identifier, title = await resolve_and_join(raw_input)
            src_key = str(identifier)
            if src_key not in DB["sources"]:
                DB["sources"].append(src_key)
                save_db()
                await event.respond(f" **Source Added:** `{title}`")
                asyncio.create_task(clone_old_videos(src_key))
            else:
                await event.respond(" Source already exists.")
        except Exception as e:
            await event.respond(f" Error: `{e}`")

    @bot.on(events.NewMessage(pattern=r'(?i)^/del (.+)', outgoing=True))
    async def del_cmd(event):
        raw_input = event.pattern_match.group(1).strip()
        if raw_input in DB["sources"]:
            DB["sources"].remove(raw_input)
            if raw_input in DB.get("crawler_progress", {}):
                del DB["crawler_progress"][raw_input]
            save_db()
            await event.respond(f" **Removed Source:** `{raw_input}`")
        else:
            await event.respond(" Source not found in DB.")

    @bot.on(events.NewMessage(pattern=r'(?i)^/sources$', outgoing=True))
    async def sources_cmd(event):
        if not DB.get("sources"):
            await event.respond(" **No Active Sources.**")
            return
        msg = " **ACTIVE SOURCES:**\n\n"
        for idx, src in enumerate(DB["sources"], 1):
            msg += f"{idx}. `{src}`\n"
        await event.respond(msg)

    @bot.on(events.NewMessage(pattern=r'(?i)^/settarget (.+)', outgoing=True))
    async def settarget_cmd(event):
        raw_target = event.pattern_match.group(1).strip()
        try:
            if raw_target.startswith('-') or raw_target.lstrip('-').isdigit():
                DB["target_channel"] = int(raw_target)
            else:
                entity = await bot.get_entity(raw_target)
                DB["target_channel"] = entity.id
            save_db()
            await event.respond(f" **Target Set:** `{DB['target_channel']}`")
        except Exception as e:
            await event.respond(f" Error: `{e}`")

    @bot.on(events.NewMessage(pattern=r'(?i)^/backup$', outgoing=True))
    async def backup_cmd(event):
        save_db()
        await event.respond(file=DB_FILE, caption=" **Database Backup File**")

    @bot.on(events.NewMessage(pattern=r'(?i)^/toggle$', outgoing=True))
    async def toggle_cmd(event):
        DB["status"] = "OFF" if DB.get("status") == "ON" else "ON"
        save_db()
        await event.respond(f" **Engine Status:** `{DB['status']}`")

    # Live Real-Time Forward Listener
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
