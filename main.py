import os
import re
import json
import time
import logging
import psutil
import asyncio
from threading import Thread
from flask import Flask
from telethon import TelegramClient, events, errors, functions, types
from telethon.sessions import StringSession

# --- 1. Stealth Mode Logging ---
logging.basicConfig(level=logging.ERROR)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# --- 2. Keep-Alive Web Server Node ---
app = Flask('')
@app.route('/')
def server_status():
    return " MASTER OMEGA ENGINE: SYSTEM ONLINE & SECURE"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# --- 3. System Configuration & Database ---
API_ID = 38078790
API_HASH = 'c1b7e324a99544d7a9229ff5324af362'
SESSION_STRING = os.environ.get("SESSION_STRING")

DB_FILE = "master_database.json"
TEMP_DIR = "master_cache"
CONCURRENT_WORKERS = 8  # Elite High-Speed Multi-threading

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {
        "target_channel": None,
        "log_channel": None,
        "sources": [],
        "custom_thumb": None,
        "link_replacer": "",
        "header": "",
        "footer": "",
        "watermark": "",
        "media_filter": "all",
        "engine_state": "ACTIVE",
        "file_registry": []
    }

def save_db():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(DB, f, ensure_ascii=False, indent=4)
    except:
        pass

DB = load_db()
system_start_time = time.time()
upload_queue = asyncio.Queue()

# --- 4. High-Speed Telegram Client ---
bot = TelegramClient(
    StringSession(SESSION_STRING), 
    API_ID, 
    API_HASH,
    connection_retries=15,
    retry_delay=2
)

# --- 5. Core Engine Functions ---
async def send_log(msg):
    log_c = DB.get("log_channel")
    if log_c:
        try:
            await bot.send_message(log_c, f" **SYSTEM LOG:** {msg}")
        except:
            pass

async def payload_worker(worker_id):
    """High-speed asynchronous queue processor for parallel uploads."""
    while True:
        event, final_caption = await upload_queue.get()
        try:
            target = DB.get("target_channel")
            thumb_path = DB.get("custom_thumb")
            os.makedirs(TEMP_DIR, exist_ok=True)

            if not target:
                continue

            if thumb_path and os.path.exists(thumb_path):
                dl_file = await bot.download_media(event.message, file=TEMP_DIR + "/")
                try:
                    await bot.send_file(
                        target, dl_file, caption=final_caption, 
                        thumb=thumb_path, supports_streaming=True, part_size_kb=1024
                    )
                finally:
                    if dl_file and os.path.exists(dl_file):
                        os.remove(dl_file)
            else:
                await bot.send_file(
                    target, event.media, caption=final_caption, 
                    supports_streaming=True, part_size_kb=1024
                )
        except errors.FloodWaitError as e:
            await send_log(f"Worker {worker_id} - FloodWait: Sleeping for {e.seconds}s")
            await asyncio.sleep(e.seconds + 2)
        except Exception as e:
            await send_log(f"Worker {worker_id} Error: `{e}`")
        finally:
            upload_queue.task_done()
            await asyncio.sleep(0.3)

# --- 6. Command Center (Bot Commands) ---
async def main():
    await bot.start()
    print("==================================================")
    print(" MASTER OMEGA ALL-IN-ONE ENGINE ONLINE ")
    print("==================================================")

    for i in range(1, CONCURRENT_WORKERS + 1):
        asyncio.create_task(payload_worker(i))

    @bot.on(events.NewMessage(pattern=r'(?i)^[./](start|help|panel)$'))
    async def control_panel(event):
        thumb_status = " CUSTOM" if DB.get("custom_thumb") else " AUTO SCREENSHOT"
        panel_text = (
            " **MASTER OMEGA CONTROL PANEL** \n"
            "\n"
            f" Target Node: `{DB.get('target_channel') or 'NOT SET'}`\n"
            f" Log Node: `{DB.get('log_channel') or 'NOT SET'}`\n"
            f" Status: `{DB.get('engine_state')}` | Threads: `{CONCURRENT_WORKERS}`\n"
            f" Link Mask: `{DB.get('link_replacer') or 'None'}`\n"
            f" Filter: `{DB.get('media_filter').upper()}` | Thumb: `{thumb_status}`\n\n"
            "**[ COMMAND MATRIX ]**\n"
            " `/settarget <ID>` / `/setlog <ID>` - ချန်နယ်သတ်မှတ်ရန်\n"
            " `/add <Link>` / `/del <Link>` - Source အတိုးအလျှော့လုပ်ရန်\n"
            " `/sources` - Source List ကြည့်ရန်\n"
            " `/join <Link>` - Channel / Chat Join ရန်\n"
            " `/setthumb` (Reply) / `/delthumb` - Custom ပုံ ပြင်ရန်\n"
            " `/filter <all/video/document>` - Media အမျိုးအစားခွဲရန်\n"
            " `/replacelink <Text>` - လင့်ခ်များ အစားထိုးရန်\n"
            " `/header <Txt>` / `/footer <Txt>` / `/watermark <Txt>`\n"
            " `/status` - Server Hardware & RAM စစ်ဆေးရန်\n"
            " `/backup` - Database ထုတ်ယူရန်\n"
            " `/search <Name>` - Database ထဲရှာရန်\n"
            " `/toggle` - Engine ဖွင့်/ပိတ် လုပ်ရန်"
        )
        await event.respond(panel_text)

    # --- System State & Monitors ---
    @bot.on(events.NewMessage(pattern=r'(?i)^[./]toggle$'))
    async def toggle_cmd(event):
        DB["engine_state"] = "PAUSED" if DB.get("engine_state") == "ACTIVE" else "ACTIVE"
        save_db()
        await event.respond(f" **System State Shifted:** `{DB['engine_state']}`")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]status$'))
    async def status_cmd(event):
        cpu = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory().percent
        uptime = int(time.time() - system_start_time)
        h, rem = divmod(uptime, 3600)
        m, s = divmod(rem, 60)
        await event.respond(
            " **OMEGA HARDWARE DIAGNOSTICS** \n"
            f" CPU Load: `{cpu}%`\n"
            f" RAM Load: `{ram}%`\n"
            f" Uptime: `{h}h {m}m {s}s`\n"
            f" Pending Tasks: `{upload_queue.qsize()}` Files"
        )

    # --- Formatting & Settings ---
    @bot.on(events.NewMessage(pattern=r'(?i)^[./]setthumb$'))
    async def set_thumb_cmd(event):
        if event.is_reply:
            msg = await event.get_reply_message()
            if msg.media:
                os.makedirs(TEMP_DIR, exist_ok=True)
                path = await bot.download_media(msg, file=os.path.join(TEMP_DIR, "master_thumb.jpg"))
                DB["custom_thumb"] = path
                save_db()
                await event.respond(" **Master Custom Thumbnail Activated.**")
                return
        await event.respond(" Reply to an image with `/setthumb`.")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]delthumb$'))
    async def del_thumb_cmd(event):
        DB["custom_thumb"] = None
        if os.path.exists(os.path.join(TEMP_DIR, "master_thumb.jpg")):
            os.remove(os.path.join(TEMP_DIR, "master_thumb.jpg"))
        save_db()
        await event.respond(" **Reverted to Auto Screenshot Mode.**")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]settarget (.+)'))
    async def set_target_cmd(event):
        val = event.pattern_match.group(1).strip()
        DB["target_channel"] = int(val) if val.lstrip('-').isdigit() else val
        save_db()
        await event.respond(f" **Target Node Secured:** `{val}`")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]setlog (.+)'))
    async def set_log_cmd(event):
        val = event.pattern_match.group(1).strip()
        DB["log_channel"] = int(val) if val.lstrip('-').isdigit() else val
        save_db()
        await event.respond(f" **Log Node Secured:** `{val}`")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]replacelink (.+)'))
    async def replace_link_cmd(event):
        DB["link_replacer"] = event.pattern_match.group(1).strip()
        save_db()
        await event.respond(f" **Link Masker Active:** `{DB['link_replacer']}`")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]filter (all|video|document)$'))
    async def filter_cmd(event):
        DB["media_filter"] = event.pattern_match.group(1).lower()
        save_db()
        await event.respond(f" **Media Filter:** `{DB['media_filter'].upper()}`")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]header (.+)'))
    async def header_cmd(event):
        DB["header"] = event.pattern_match.group(1).strip()
        save_db()
        await event.respond(" **Header Set.**")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]footer (.+)'))
    async def footer_cmd(event):
        DB["footer"] = event.pattern_match.group(1).strip()
        save_db()
        await event.respond(" **Footer Set.**")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]watermark (.+)'))
    async def watermark_cmd(event):
        DB["watermark"] = event.pattern_match.group(1).strip()
        save_db()
        await event.respond(" **Watermark Set.**")

    # --- Source Management ---
    @bot.on(events.NewMessage(pattern=r'(?i)^[./]add (.+)'))
    async def add_src_cmd(event):
        src = event.pattern_match.group(1).strip()
        if src not in DB["sources"]:
            DB["sources"].append(src)
            save_db()
            await event.respond(f" **Source Added:** `{src}`")
        else:
            await event.respond(" Source already in matrix.")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]del (.+)'))
    async def del_src_cmd(event):
        src = event.pattern_match.group(1).strip()
        if src in DB["sources"]:
            DB["sources"].remove(src)
            save_db()
            await event.respond(f" **Source Terminated:** `{src}`")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]sources$'))
    async def list_src_cmd(event):
        if not DB["sources"]:
            await event.respond(" **No Active Sources.**")
            return
        msg = " **ACTIVE SOURCE NODES:**\n"
        for i, s in enumerate(DB["sources"], 1):
            msg += f"{i}. `{s}`\n"
        await event.respond(msg)

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]join (.+)'))
    async def join_cmd(event):
        link = event.pattern_match.group(1).strip()
        try:
            if "+" in link or "joinchat" in link:
                hash_code = link.split('/')[-1].replace('+', '')
                await bot(functions.messages.ImportChatInviteRequest(hash_code))
            else:
                entity = await bot.get_entity(link)
                await bot(functions.channels.JoinChannelRequest(entity))
            await event.respond(" **Channel infiltration successful!**")
        except Exception as e:
            await event.respond(f" Join Error: `{e}`")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]backup$'))
    async def backup_cmd(event):
        if os.path.exists(DB_FILE):
            await bot.send_file(event.chat_id, DB_FILE, caption=" **OMEGA Database Backup**")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]search (.+)'))
    async def search_cmd(event):
        q = event.pattern_match.group(1).strip().lower()
        res = [f for f in DB.get("file_registry", []) if q in f.get("name", "").lower()]
        if not res:
            await event.respond(" No matching payloads found.")
            return
        msg = f" **Search Results ({len(res)}):**\n"
        for r in res[:15]:
            msg += f" {r.get('name')}\n"
        await event.respond(msg)

    # --- Core Interceptor (Payload Catcher) ---
    @bot.on(events.NewMessage())
    async def message_interceptor(event):
        if DB.get("engine_state") == "PAUSED" or not DB.get("sources"):
            return
        try:
            chat = await event.get_chat()
            if not chat: return

            chat_id = str(chat.id)
            username = f"@{chat.username.lower()}" if chat.username else None

            matched = any(
                src.lower() == chat_id or (username and src.lower() == username) 
                for src in DB["sources"]
            )

            if matched:
                media_filter = DB.get("media_filter", "all")
                valid = False
                if media_filter == "all" and (event.video or event.document): valid = True
                elif media_filter == "video" and event.video: valid = True
                elif media_filter == "document" and event.document and not event.video: valid = True

                if valid:
                    # Save to DB for tracking
                    fname = event.file.name if event.file and event.file.name else "Encrypted_Payload"
                    DB.setdefault("file_registry", []).append({"name": fname})
                    save_db()

                    # Process Caption
                    caption = event.text or ""
                    rep_link = DB.get("link_replacer")
                    if rep_link:
                        caption = re.sub(r'https?://t\.me/\S+', rep_link, caption)
                        caption = re.sub(r'@\w+', rep_link, caption)

                    parts = []
                    if DB.get("header"): parts.append(DB["header"])
                    if caption: parts.append(f"**{caption}**")
                    if DB.get("watermark"): parts.append(DB["watermark"])
                    if DB.get("footer"): parts.append(DB["footer"])
                    
                    final_cap = "\n\n".join(parts)
                    await upload_queue.put((event, final_cap))
        except Exception as e:
            await send_log(f"Interceptor Alert: `{e}`")

    await bot.run_until_disconnected()

if __name__ == '__main__':
    Thread(target=run_web_server).start()
    asyncio.run(main())
