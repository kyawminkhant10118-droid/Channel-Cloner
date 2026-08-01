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
    return " Ultimate Supreme VIP Engine v13.0 is Live!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# --- Telegram Native Client & Safe Imports ---
from telethon import TelegramClient, events, errors, functions, types, Button
from telethon.sessions import StringSession

# --- 2. Telegram API Credentials ---
API_ID = 38078790
API_HASH = 'c1b7e324a99544d7a9229ff5324af362'
SESSION_STRING = os.environ.get("SESSION_STRING")

# --- 3. Engine Configuration ---
CONCURRENT_WORKERS = 8
DB_FILE = "ultimate_db_v13.json"
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
        "target_channels": [-1003351682369],  # Support multiple targets now
        "log_channel": None,
        "sources": [],
        "duplicates": [],
        "blacklist_words": ["casino", "1xbet", "bet", "18+"],
        "custom_button": {"text": " Join Main Channel", "url": "https://t.me/+0000000000"},
        "daily_stats": {},
        "crawler_progress": {},
        "header": " **[VIP EXCLUSIVE CONTENT]** ",
        "watermark": " **Powered by Supreme VIP Engine**",
        "footer": "",
        "media_filter": "all",
        "replace_link": "",
        "clean_ads": True,
        "auto_tags": True,
        "delay_seconds": 0,
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
                'sci-fi', 'thriller', 'drama', 'animation', 'fantasy', 'myanmar', 'sub', 'dub', 'vip']
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

def check_blacklist(text):
    if not text: return False
    text_lower = text.lower()
    for word in DB.get("blacklist_words", []):
        if word.lower() in text_lower:
            return True
    return False

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
    tags = generate_hashtags(caption) if DB.get("auto_tags") else ""
    
    parts = []
    if DB.get("header"): parts.append(DB["header"].strip())
    if caption: parts.append(f"**{caption}**")
    if tags: parts.append(tags)
    if DB.get("watermark"): parts.append(DB["watermark"].strip())
    if DB.get("footer"): parts.append(DB["footer"].strip())
    
    return "\n\n".join(parts)

async def send_log(text):
    log_chat = DB.get("log_channel")
    if log_chat:
        try:
            await bot.send_message(log_chat, f" **SUPREME LOG:** {text}")
        except:
            pass

# ---  MULTI-TARGET ZERO-DISK TRANSFER ENGINE ---
async def safe_upload(message, caption):
    targets = DB.get("target_channels", [])
    if not targets: return False

    if check_blacklist(message.text):
        return False

    file_id = str(message.media.document.id) if (message.video or message.document) else None
    if file_id and file_id in DB.get("duplicates", []): return False

    thumb_to_use = THUMB_PATH if os.path.exists(THUMB_PATH) else None
    delay = DB.get("delay_seconds", 0)
    if delay > 0:
        await asyncio.sleep(delay)

    # Prepare custom inline buttons if configured
    buttons = None
    c_btn = DB.get("custom_button")
    if c_btn and c_btn.get("text") and c_btn.get("url"):
        buttons = [[Button.url(c_btn["text"], c_btn["url"])]]

    success_any = False
    for target in targets:
        try:
            if not thumb_to_use and message.media:
                sent_msg = await bot.send_file(
                    target, message.media, caption=caption.strip(), 
                    buttons=buttons, supports_streaming=True
                )
                if sent_msg: success_any = True
                continue
        except Exception:
            pass

        while True:
            try:
                os.makedirs(TEMP_DIR, exist_ok=True)
                temp_path = await bot.download_media(message, file=TEMP_DIR)
                try:
                    sent_msg = await bot.send_file(
                        target, temp_path, caption=caption.strip(), thumb=thumb_to_use,
                        buttons=buttons, supports_streaming=True, part_size_kb=1024
                    )
                finally:
                    if temp_path and os.path.exists(temp_path):
                        os.remove(temp_path)

                if sent_msg:
                    success_any = True
                    break
            except errors.FloodWaitError as e:
                await asyncio.sleep(e.seconds + 2)
            except Exception:
                break

    if success_any:
        if file_id: DB["duplicates"].append(file_id)
        today = datetime.now().strftime("%Y-%m-%d")
        DB["daily_stats"][today] = DB["daily_stats"].get(today, 0) + 1
        save_db()
        return True
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
            await asyncio.sleep(0.3)

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
            
            m_filter = DB.get("media_filter", "all")
            match_filter = False
            if m_filter == "all" and (message.video or message.document): match_filter = True
            elif m_filter == "video" and message.video: match_filter = True
            elif m_filter == "document" and message.document and not message.video: match_filter = True

            if match_filter and not check_blacklist(message.text):
                caption = build_caption(message.text)
                await upload_queue.put((message, caption))
                media_found += 1

            pct = round((scanned / total_msgs) * 100, 1)
            DB["crawler_progress"][str(source_chat)] = {
                "total": total_msgs, "scanned": scanned, "media_found": media_found, "percent": pct
            }
            if scanned % 50 == 0 or scanned == total_msgs: save_db()
        await send_log(f"Finished Supreme cloning source: `{source_chat}`")
    except Exception as e:
        await send_log(f"Error in Supreme crawler for `{source_chat}`: `{e}`")

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
    print(" ULTIMATE SUPREME VIP v13.0 LIVE ")
    print("==================================================")
    
    for i in range(1, CONCURRENT_WORKERS + 1):
        asyncio.create_task(queue_worker(i))

    @bot.on(events.NewMessage(pattern=r'(?i)^[./](start|panel)$'))
    async def panel_cmd(event):
        targets_count = len(DB.get("target_channels", []))
        status_val = DB.get("status", "ON")
        tags_status = "" if DB.get("auto_tags") else ""
        ads_status = "" if DB.get("clean_ads") else ""
        
        panel_text = (
            " **SUPREME VIP CONTROL PANEL v13.0** \n"
            "\n"
            f" **Status:** `{status_val}` |  **Targets:** `{targets_count} Channels`\n"
            f" **Threads:** `{CONCURRENT_WORKERS} Threads`\n"
            f" **Auto Tags:** `{tags_status}` |  **Clean Ads:** `{ads_status}`\n"
            f" **Filter:** `{DB.get('media_filter').upper()}` |  **Delay:** `{DB.get('delay_seconds')}s`\n"
            f" **Queue Pending:** `{upload_queue.qsize()} Files`"
        )
        
        buttons = [
            [Button.inline(" Turn ON", b"engine_on"), Button.inline(" Turn OFF", b"engine_off")],
            [Button.inline(" Dashboard Status", b"btn_status"), Button.inline(" Daily Stats", b"btn_stats")],
            [Button.inline(" Toggle Tags", b"toggle_tags"), Button.inline(" Toggle Ads", b"toggle_ads")],
            [Button.inline(" View Sources", b"btn_sources")]
        ]
        await event.respond(panel_text, buttons=buttons)

    @bot.on(events.CallbackQuery)
    async def callback_handler(event):
        data = event.data.decode('utf-8')
        if data == "engine_on":
            DB["status"] = "ON"
            save_db()
            await event.answer(" Engine Activated!", alert=True)
        elif data == "engine_off":
            DB["status"] = "OFF"
            save_db()
            await event.answer(" Engine Deactivated!", alert=True)
        elif data == "toggle_tags":
            DB["auto_tags"] = not DB.get("auto_tags", False)
            save_db()
            await event.answer(f"Tags: {'ENABLED' if DB['auto_tags'] else 'DISABLED'}", alert=True)
        elif data == "toggle_ads":
            DB["clean_ads"] = not DB.get("clean_ads", True)
            save_db()
            await event.answer(f"Ad Cleaner: {'ENABLED' if DB['clean_ads'] else 'DISABLED'}", alert=True)
        elif data == "btn_status":
            uptime_sec = int(time.time() - start_time)
            hours, remainder = divmod(uptime_sec, 3600)
            minutes, seconds = divmod(remainder, 60)
            vram = psutil.virtual_memory()
            cpu_pct = psutil.cpu_percent(interval=0.5)
            await event.answer(f"CPU: {cpu_pct}% | RAM: {vram.percent}% | Uptime: {hours}h {minutes}m", alert=True)
        elif data == "btn_stats":
            stats = DB.get("daily_stats", {})
            total_u = sum(stats.values())
            await event.answer(f"Total Uploaded Files Recorded: {total_u}", alert=True)
        elif data == "btn_sources":
            sources = DB.get("sources", [])
            await event.answer(f"Active Sources Count: {len(sources)}", alert=True)

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]ping$'))
    async def ping_cmd(event):
        await event.respond(" **Supreme Pong!** Ultra-responsive server running smoothly.")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]setthumb$'))
    async def setthumb_cmd(event):
        if event.is_reply:
            reply_msg = await event.get_reply_message()
            if reply_msg.media:
                await bot.download_media(reply_msg, file=THUMB_PATH)
                await event.respond(" **Supreme Custom Thumbnail successfully saved!**")
                return
        await event.respond(" Please reply to an image/photo with `.setthumb` to set it as custom thumbnail.")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]addtarget$'))
    async def addtarget_cmd(event):
        chat_id = event.chat_id
        if chat_id not in DB["target_channels"]:
            DB["target_channels"].append(chat_id)
            save_db()
            await event.respond(f" **This chat added as a Target Channel.** (Total: {len(DB['target_channels'])})")
        else:
            await event.respond(" This chat is already in target channels list.")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]setbtn (.+) \| (.+)'))
    async def setbtn_cmd(event):
        btn_text = event.pattern_match.group(1).strip()
        btn_url = event.pattern_match.group(2).strip()
        DB["custom_button"] = {"text": btn_text, "url": btn_url}
        save_db()
        await event.respond(f" **Custom Inline Button updated:** [{btn_text}]({btn_url})")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]setlog$'))
    async def setlog_cmd(event):
        DB["log_channel"] = event.chat_id
        save_db()
        await event.respond(f" **This chat has been set as the Supreme Log Channel.**")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]on$'))
    async def on_cmd(event):
        DB["status"] = "ON"
        save_db()
        await event.respond(" **Engine Activated:** Live forwarding & cloning resumed.")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]off$'))
    async def off_cmd(event):
        DB["status"] = "OFF"
        save_db()
        await event.respond(" **Engine Deactivated:** Live forwarding & cloning paused.")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]autotags$'))
    async def autotags_cmd(event):
        DB["auto_tags"] = not DB.get("auto_tags", False)
        save_db()
        await event.respond(f" **Auto Tags:** `{'ENABLED' if DB['auto_tags'] else 'DISABLED'}`")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]cleanads$'))
    async def cleanads_cmd(event):
        DB["clean_ads"] = not DB.get("clean_ads", True)
        save_db()
        await event.respond(f" **Ad Cleaner:** `{'ENABLED' if DB['clean_ads'] else 'DISABLED'}`")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]setdelay (\d+)'))
    async def setdelay_cmd(event):
        secs = int(event.pattern_match.group(1))
        DB["delay_seconds"] = secs
        save_db()
        await event.respond(f" **Drip Delay set to {secs} seconds.**")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]filter (all|video|document)$'))
    async def filter_cmd(event):
        ftype = event.pattern_match.group(1).lower()
        DB["media_filter"] = ftype
        save_db()
        await event.respond(f" **Media Filter updated to:** `{ftype.upper()}`")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]setheader (.+)'))
    async def setheader_cmd(event):
        DB["header"] = event.pattern_match.group(1).strip()
        save_db()
        await event.respond(" **Header updated successfully!**")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]setwatermark (.+)'))
    async def setwatermark_cmd(event):
        DB["watermark"] = event.pattern_match.group(1).strip()
        save_db()
        await event.respond(" **Watermark updated successfully!**")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]setfooter (.+)'))
    async def setfooter_cmd(event):
        DB["footer"] = event.pattern_match.group(1).strip()
        save_db()
        await event.respond(" **Footer updated successfully!**")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]setlink (.+)'))
    async def setlink_cmd(event):
        DB["replace_link"] = event.pattern_match.group(1).strip()
        save_db()
        await event.respond(" **Link Replacement updated successfully!**")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]stats$'))
    async def stats_cmd(event):
        stats = DB.get("daily_stats", {})
        msg = " **DAILY UPLOAD STATISTICS:**\n"
        if not stats:
            msg += "No uploads recorded yet."
        else:
            for date, count in sorted(stats.items())[-7:]:
                msg += f" `{date}` : **{count} files**\n"
        await event.respond(msg)

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
            progress_text += "\n **CLONING PROGRESS:**\n"
            for src, data in crawler_data.items():
                pct = data['percent']
                p_bar = make_progress_bar(pct)
                progress_text += f" `{src}`\n  `{p_bar}` **{pct}%** ({data['scanned']}/{data['total']})\n"

        status_msg = (
            " **SUPREME DASHBOARD v13.0** \n"
            "\n"
            f" **Threads:** `{CONCURRENT_WORKERS}` |  **Uptime:** `{hours}h {minutes}m`\n"
            f" **CPU:** `{cpu_pct}%` |  **RAM:** `{vram.percent}%`\n"
            f" **Queue Pending:** `{upload_queue.qsize()} Files`\n"
            f"{progress_text}"
            ""
        )
        await event.respond(status_msg)

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]add (.+)'))
    async def add_cmd(event):
        raw_input = event.pattern_match.group(1).strip()
        await event.respond(f" **Initializing Supreme Crawler...**\n`{raw_input}`")
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

            if is_in_list:
                m_filter = DB.get("media_filter", "all")
                match_filter = False
                if m_filter == "all" and (event.message.video or event.message.document): match_filter = True
                elif m_filter == "video" and event.message.video: match_filter = True
                elif m_filter == "document" and event.message.document and not event.message.video: match_filter = True

                if match_filter and not check_blacklist(event.message.text):
                    caption = build_caption(event.message.text)
                    await upload_queue.put((event.message, caption))
        except Exception:
            pass

    await bot.run_until_disconnected()

if __name__ == '__main__':
    Thread(target=run_web).start()
    asyncio.main(main())
