import os
import json
import time
import math
import logging
import traceback
import asyncio
from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession

# --- 1. LOGGING & SYSTEM SETUP ---
LOG_FILE_NAME = "premium_bot.log"

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d] — %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE_NAME, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

API_ID = 38078790
API_HASH = 'c1b7e324a99544d7a9229ff5324af362'
SESSION_STRING = os.environ.get("SESSION_STRING")

DB_FILE = "premium_database.json"
TEMP_DIR = "fast_cache"

def load_database():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                content = f.read()
                if content.strip():
                    return json.loads(content)
        except Exception as e:
            logging.error(f"Database Load Error: {e}\n{traceback.format_exc()}")
    return {
        "target_channel": None,
        "log_channel": None,
        "sources": [],
        "system_active": True,
        "total_processed_files": 0
    }

def save_database(data):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Database Save Error: {e}")

db = load_database()
system_boot_time = time.time()

# --- 2. TELETHON CLIENT WITH MULTI-CONNECTION SPEED BOOST ---
bot = TelegramClient(
    StringSession(SESSION_STRING), 
    API_ID, 
    API_HASH,
    connection_retries=20,
    retry_delay=2,
    request_retries=10
)

# --- 3. HELPER FUNCTIONS FOR PREMIUM UI & PROGRESS BAR ---
def human_readable_size(size_in_bytes):
    if size_in_bytes == 0:
        return "0 B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(math.floor(math.log(size_in_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_in_bytes / p, 2)
    return f"{s} {size_name[i]}"

def human_readable_time(seconds):
    if seconds <= 0:
        return "00:00:00"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

class ProgressTracker:
    """Live Progress Bar, MB/s Speed နှင့် ETA ကို အနီးစပ်ဆုံး တိကျစွာ တွက်ချက်ပေးမည့် Class"""
    def __init__(self, action_name, message, file_name):
        self.action_name = action_name
        self.message = message
        self.file_name = file_name
        self.start_time = time.time()
        self.last_update_time = time.time()

    async def callback(self, current, total):
        now = time.time()
        # Telegram Rate Limit မမိစေရန် ၂ စက္ကန့်လျှင် ၁ ကြိမ်သာ UI ကို Update ပြုလုပ်မည်
        if now - self.last_update_time < 2.0 and current != total:
            return

        self.last_update_time = now
        elapsed = now - self.start_time
        percentage = (current / total) * 100 if total > 0 else 0
        
        # Speed Calculation (MB/s)
        speed = current / elapsed if elapsed > 0 else 0
        eta = (total - current) / speed if speed > 0 else 0

        # Progress Bar Construction [████████░░]
        filled_blocks = int(percentage // 10)
        progress_bar = "█" * filled_blocks + "░" * (10 - filled_blocks)

        status_text = (
            f"⚡ **{self.action_name.upper()} IN PROGRESS**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📁 **File:** `{self.file_name}`\n"
            f"📊 **Progress:** `[{progress_bar}] {percentage:.1f}%`\n"
            f"🚀 **Speed:** `{human_readable_size(speed)}/s`\n"
            f"📦 **Size:** `{human_readable_size(current)} / {human_readable_size(total)}`\n"
            f"⏱ **ETA:** `{human_readable_time(eta)}`"
        )

        try:
            await self.message.edit(status_text)
        except Exception:
            pass

async def dispatch_log(log_msg, level="INFO"):
    log_chat_id = db.get("log_channel")
    if log_chat_id:
        try:
            icon = "🟢" if level == "INFO" else "❌" if level == "ERROR" else "⚠️"
            await bot.send_message(log_chat_id, f"{icon} **SYSTEM LOG [{level}]**\n{log_msg}")
        except Exception as e:
            logging.error(f"Failed to dispatch log: {e}")

# --- 4. MAIN ENGINE CODE ---
async def main():
    await bot.start()
    logging.info("⚡ ULTIMATE HIGH-SPEED OMEGA ENGINE FULLY ONLINE ⚡")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./](start|help|dashboard|menu)$'))
    async def dashboard_command(event):
        uptime_sec = int(time.time() - system_boot_time)
        hrs, rem = divmod(uptime_sec, 3600)
        mins, secs = divmod(rem, 60)

        panel_text = (
            "💎 **PREMIUM HIGH-SPEED CONTROL PANEL**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 Target Channel: `{db.get('target_channel') or 'Not Configured'}`\n"
            f"🛡 Log Channel: `{db.get('log_channel') or 'Not Configured'}`\n"
            f"📡 Active Sources: `{len(db.get('sources', []))}` active\n"
            f"⚙️ Engine Status: `{'ONLINE 🟢' if db.get('system_active') else 'PAUSED 🔴'}`\n"
            f"📦 Total Processed: `{db.get('total_processed_files', 0)}` files\n"
            f"⏱ System Uptime: `{hrs}h {mins}m {secs}s`\n\n"
            "**Control Commands:**\n"
            "• `/settarget <ID>` - Set Target Channel\n"
            "• `/setlog <ID>` - Set System Log Channel\n"
            "• `/addsource <ID/Link>` - Add Source Monitor\n"
            "• `/delsource <ID/Link>` - Remove Source Monitor\n"
            "• `/sources` - View Active Sources\n"
            "• `/toggle` - Pause / Resume Engine"
        )
        await event.respond(panel_text)

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]settarget (.+)'))
    async def set_target(event):
        val = event.pattern_match.group(1).strip()
        target = int(val) if val.lstrip('-').isdigit() else val
        db["target_channel"] = target
        save_database(db)
        await event.respond(f"✅ **Target Channel Updated:** `{target}`")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]setlog (.+)'))
    async def set_log(event):
        val = event.pattern_match.group(1).strip()
        log_id = int(val) if val.lstrip('-').isdigit() else val
        db["log_channel"] = log_id
        save_database(db)
        await event.respond(f"✅ **Log Channel Updated:** `{log_id}`")
        await dispatch_log("Log Channel linked successfully.", "INFO")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]addsource (.+)'))
    async def add_source(event):
        src = event.pattern_match.group(1).strip()
        if src not in db["sources"]:
            db["sources"].append(src)
            save_database(db)
            await event.respond(f"✅ **Source Added:** `{src}`")
            await dispatch_log(f"Source Added: `{src}`", "INFO")
        else:
            await event.respond("⚠️ Source already exists in database.")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]delsource (.+)'))
    async def del_source(event):
        src = event.pattern_match.group(1).strip()
        if src in db["sources"]:
            db["sources"].remove(src)
            save_database(db)
            await event.respond(f"🗑 **Source Removed:** `{src}`")
            await dispatch_log(f"Source Removed: `{src}`", "INFO")
        else:
            await event.respond("⚠️ Source not found.")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]sources$'))
    async def list_sources(event):
        sources = db.get("sources", [])
        if not sources:
            await event.respond("📡 No active sources configured.")
            return
        text = "📡 **Active Monitored Sources:**\n"
        for idx, s in enumerate(sources, 1):
            text += f"{idx}. `{s}`\n"
        await event.respond(text)

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]toggle$'))
    async def toggle_system(event):
        db["system_active"] = not db.get("system_active", True)
        save_database(db)
        state = "ONLINE 🟢" if db["system_active"] else "PAUSED 🔴"
        await event.respond(f"🔄 **Engine State:** `{state}`")

    # --- 5. HIGH-SPEED INTERCEPTOR WITH FAST PARALLEL PROCESSING ---
    @bot.on(events.NewMessage())
    async def message_interceptor(event):
        if not db.get("system_active", True):
            return

        sources = db.get("sources", [])
        target = db.get("target_channel")

        if not sources or not target:
            return

        try:
            chat = await event.get_chat()
            if not chat:
                return

            chat_id = str(chat.id)
            username = f"@{chat.username.lower()}" if chat.username else None

            is_matched = any(
                str(s).lower() == chat_id or (username and str(s).lower() == username)
                for s in sources
            )

            if is_matched and (event.video or event.document):
                status_msg = await event.respond("💎 **[1/2] Initiating High-Speed Download...**")
                
                os.makedirs(TEMP_DIR, exist_ok=True)
                downloaded_path = None
                file_name = "Unknown_Media"

                if event.file and event.file.name:
                    file_name = event.file.name
                elif event.video:
                    file_name = f"Video_{event.id}.mp4"

                caption_text = event.text or ""

                try:
                    # --- FAST DOWNLOAD WITH REAL-TIME PROGRESS BAR ---
                    dl_tracker = ProgressTracker("Downloading", status_msg, file_name)
                    
                    downloaded_path = await event.download_media(
                        file=TEMP_DIR + "/",
                        progress_callback=dl_tracker.callback
                    )

                    file_actual_name = os.path.basename(downloaded_path)

                    # --- FAST UPLOAD WITH REAL-TIME PROGRESS BAR ---
                    ul_tracker = ProgressTracker("Uploading", status_msg, file_actual_name)
                    
                    file_lower_ext = downloaded_path.lower()
                    is_video_ext = file_lower_ext.endswith(('.mp4', '.mkv', '.avi', '.mov', '.webm', '.m4v', '.flv'))

                    if is_video_ext:
                        # Video Player အဖြစ် အမှန်တကယ် ပေါ်စေရန်နှင့် Fast Upload ရစေရန်
                        await bot.send_file(
                            target,
                            downloaded_path,
                            caption=caption_text,
                            supports_streaming=True,
                            force_document=False,
                            progress_callback=ul_tracker.callback
                        )
                    else:
                        await bot.send_file(
                            target,
                            downloaded_path,
                            caption=caption_text,
                            supports_streaming=True,
                            progress_callback=ul_tracker.callback
                        )

                    # အောင်မြင်စွာ တင်ပြီးစီးကြောင်း တိကျစွာ ပြသခြင်း
                    db["total_processed_files"] = db.get("total_processed_files", 0) + 1
                    save_database(db)

                    finish_text = (
                        "✅ **TASK COMPLETED SUCCESSFULLY**\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"📁 **File:** `{file_actual_name}`\n"
                        f"🎯 **Target:** `{target}`\n"
                        f"⚡ **Status:** Uploaded in Video Player Mode"
                    )
                    await status_msg.edit(finish_text)
                    await dispatch_log(f"✅ **UPLOAD SUCCESS:** `{file_actual_name}` from `{chat.title or chat_id}`", "INFO")

                    await asyncio.sleep(5)
                    await status_msg.delete()

                except Exception as inner_err:
                    err_trace = traceback.format_exc()
                    logging.error(f"Media Task Error: {inner_err}\n{err_trace}")
                    await status_msg.edit(f"❌ **Task Failed:** `{str(inner_err)}`")
                    await dispatch_log(f"❌ **Processing Error:** `{str(inner_err)}`", "ERROR")

                finally:
                    if downloaded_path and os.path.exists(downloaded_path):
                        try:
                            os.remove(downloaded_path)
                            logging.info(f"Cache cleared: {downloaded_path}")
                        except Exception as c_err:
                            logging.warning(f"Failed cache clear: {c_err}")

        except errors.FloodWaitError as flood_err:
            wait_time = flood_err.seconds
            logging.warning(f"FloodWait Triggered: Waiting {wait_time}s")
            await dispatch_log(f"⏳ FloodWait Warning: Waiting `{wait_time}` seconds.", "WARNING")
            await asyncio.sleep(wait_time)

        except Exception as outer_err:
            logging.critical(f"Critical Exception: {outer_err}\n{traceback.format_exc()}")

    await bot.run_until_disconnected()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot manually terminated.")
    except Exception as boot_err:
        logging.critical(f"Fatal Boot Error: {boot_err}")
