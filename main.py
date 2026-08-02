import os
import json
import time
import math
import shutil
import logging
import traceback
import asyncio
from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession
from telethon.tl.types import DocumentAttributeVideo

# Hachoir Metadata Parser
try:
    from hachoir.metadata import extractMetadata
    from hachoir.parser import createParser
    HACHOIR_AVAILABLE = True
except ImportError:
    HACHOIR_AVAILABLE = False

# --- 1. LOGGING & CONFIGURATION ---
LOG_FILE_NAME = "premium_bot.log"

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d]  %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE_NAME, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

API_ID = int(os.environ.get("API_ID", 38078790))
API_HASH = os.environ.get("API_HASH", "c1b7e324a99544d7a9229ff5324af362")
SESSION_STRING = os.environ.get("SESSION_STRING")

DB_FILE = "premium_database.json"
TEMP_DIR = "fast_cache"

def load_database():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                content = f.read()
                if content.strip():
                    data = json.loads(content)
                    if "processed_ids" not in data:
                        data["processed_ids"] = []
                    return data
        except Exception as e:
            logging.error(f"Database Load Error: {e}\n{traceback.format_exc()}")
    return {
        "target_channel": None,
        "log_channel": None,
        "sources": [],
        "system_active": True,
        "total_processed_files": 0,
        "processed_ids": [] # တင်ပြီးသား ဗီဒီယို ID များ မှတ်ရန်
    }

def save_database(data):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Database Save Error: {e}")

db = load_database()
system_boot_time = time.time()

bot = TelegramClient(
    StringSession(SESSION_STRING), 
    API_ID, 
    API_HASH,
    connection_retries=20,
    retry_delay=2,
    request_retries=10
)

# --- 2. UNIQUE MEDIA KEY GENERATOR (DUPLICATE CHECK) ---
def get_media_key(msg):
    """ဗီဒီယို/ဖိုင်တစ်ခုစီ၏ သီးသန့် ID ကို ထုတ်ပေးသည့် Function"""
    if not msg or not (msg.video or msg.document):
        return None
    if hasattr(msg, 'media') and hasattr(msg.media, 'document') and msg.media.document:
        return f"doc_{msg.media.document.id}"
    elif msg.file:
        return f"file_{msg.file.size}_{msg.file.name}"
    return f"msg_{msg.chat_id}_{msg.id}"

# --- 3. PROGRESS & FORMATTING HELPERS ---
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
    def __init__(self, action_name, message, file_name):
        self.action_name = action_name
        self.message = message
        self.file_name = file_name
        self.start_time = time.time()
        self.last_update_time = time.time()

    async def callback(self, current, total):
        now = time.time()
        if now - self.last_update_time < 2.0 and current != total:
            return

        self.last_update_time = now
        elapsed = now - self.start_time
        percentage = (current / total) * 100 if total > 0 else 0
        
        speed = current / elapsed if elapsed > 0 else 0
        eta = (total - current) / speed if speed > 0 else 0

        filled_blocks = int(percentage // 10)
        progress_bar = "" * filled_blocks + "" * (10 - filled_blocks)

        status_text = (
            f" **{self.action_name.upper()} IN PROGRESS**\n"
            "\n"
            f" **File:** `{self.file_name}`\n"
            f" **Progress:** `[{progress_bar}] {percentage:.1f}%`\n"
            f" **Speed:** `{human_readable_size(speed)}/s`\n"
            f" **Size:** `{human_readable_size(current)} / {human_readable_size(total)}`\n"
            f" **ETA:** `{human_readable_time(eta)}`"
        )

        try:
            await self.message.edit(status_text)
        except Exception:
            pass

async def dispatch_log(log_msg, level="INFO"):
    log_chat_id = db.get("log_channel")
    if log_chat_id:
        try:
            icon = "" if level == "INFO" else "" if level == "ERROR" else ""
            await bot.send_message(log_chat_id, f"{icon} **SYSTEM LOG [{level}]**\n{log_msg}")
        except Exception as e:
            logging.error(f"Failed to dispatch log: {e}")

# --- 4. CORE MEDIA PROCESSOR WITH DUPLICATE RECORDING ---
async def process_media_message(msg, status_msg):
    target = db.get("target_channel")
    if not target:
        await status_msg.edit(" Target Channel သတ်မှတ်ထားခြင်း မရှိသေးပါ။ `/settarget` ဖြင့် အရင် သတ်မှတ်ပေးပါ။")
        return False

    os.makedirs(TEMP_DIR, exist_ok=True)
    downloaded_path = None
    file_name = "Unknown_Media"

    if msg.file and msg.file.name:
        file_name = msg.file.name
    elif msg.video:
        file_name = f"Video_{msg.id}.mp4"

    caption_text = msg.text or ""
    media_key = get_media_key(msg)

    try:
        # Download Phase
        dl_tracker = ProgressTracker("Downloading", status_msg, file_name)
        downloaded_path = await msg.download_media(
            file=TEMP_DIR + "/",
            progress_callback=dl_tracker.callback
        )

        file_actual_name = os.path.basename(downloaded_path)
        ul_tracker = ProgressTracker("Uploading", status_msg, file_actual_name)

        file_lower_ext = downloaded_path.lower()
        is_video_ext = file_lower_ext.endswith(('.mp4', '.mkv', '.avi', '.mov', '.webm', '.m4v', '.flv')) or msg.video

        if is_video_ext:
            duration = 0
            w = 1280
            h = 720

            if msg and msg.media and hasattr(msg.media, 'document') and msg.media.document:
                for attr in msg.media.document.attributes:
                    if isinstance(attr, DocumentAttributeVideo):
                        duration = attr.duration or 0
                        w = attr.w or 1280
                        h = attr.h or 720
                        break

            if (duration == 0 or w == 0) and HACHOIR_AVAILABLE and downloaded_path:
                try:
                    parser = createParser(downloaded_path)
                    if parser:
                        with parser:
                            metadata = extractMetadata(parser)
                            if metadata:
                                if metadata.has('duration'):
                                    duration = int(metadata.get('duration').seconds)
                                if metadata.has('width'):
                                    w = int(metadata.get('width'))
                                if metadata.has('height'):
                                    h = int(metadata.get('height'))
                except Exception as ex:
                    logging.warning(f"Hachoir extraction warning: {ex}")

            video_attribute = DocumentAttributeVideo(
                duration=duration,
                w=w,
                h=h,
                supports_streaming=True
            )

            await bot.send_file(
                target,
                downloaded_path,
                caption=caption_text,
                attributes=[video_attribute],
                force_document=False,
                progress_callback=ul_tracker.callback
            )
        else:
            await bot.send_file(
                target,
                downloaded_path,
                caption=caption_text,
                progress_callback=ul_tracker.callback
            )

        # DB တွင် ဖိုင် တင်ပြီးကြောင်း မှတ်သားခြင်း
        db["total_processed_files"] = db.get("total_processed_files", 0) + 1
        if media_key and media_key not in db.get("processed_ids", []):
            db["processed_ids"].append(media_key)
        save_database(db)

        finish_text = (
            " **TASK COMPLETED SUCCESSFULLY**\n"
            "\n"
            f" **File:** `{file_actual_name}`\n"
            f" **Target:** `{target}`\n"
            f" **Status:** Force Streamable Video Player Mode"
        )
        await status_msg.edit(finish_text)
        await dispatch_log(f" **UPLOAD SUCCESS:** `{file_actual_name}`", "INFO")

        await asyncio.sleep(2)
        await status_msg.delete()
        return True

    except Exception as inner_err:
        err_trace = traceback.format_exc()
        logging.error(f"Media Task Error: {inner_err}\n{err_trace}")
        await status_msg.edit(f" **Task Failed:** `{str(inner_err)}`")
        await dispatch_log(f" **Processing Error:** `{str(inner_err)}`", "ERROR")
        return False

    finally:
        if downloaded_path and os.path.exists(downloaded_path):
            try:
                os.remove(downloaded_path)
                logging.info(f"Cache cleared: {downloaded_path}")
            except Exception as c_err:
                logging.warning(f"Failed cache clear: {c_err}")

# --- 5. MAIN BOT COMMANDS & HANDLERS ---
async def main():
    await bot.start()
    logging.info(" ULTIMATE HIGH-SPEED OMEGA ENGINE FULLY ONLINE ")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./](start|help|dashboard|menu)$'))
    async def dashboard_command(event):
        uptime_sec = int(time.time() - system_boot_time)
        hrs, rem = divmod(uptime_sec, 3600)
        mins, secs = divmod(rem, 60)

        panel_text = (
            " **PREMIUM HIGH-SPEED CONTROL PANEL**\n"
            "\n"
            f" Target Channel: `{db.get('target_channel') or 'Not Configured'}`\n"
            f" Log Channel: `{db.get('log_channel') or 'Not Configured'}`\n"
            f" Active Sources: `{len(db.get('sources', []))}` active\n"
            f" Engine Status: `{'ONLINE ' if db.get('system_active') else 'PAUSED '}`\n"
            f" Total Processed: `{db.get('total_processed_files', 0)}` files\n"
            f" System Uptime: `{hrs}h {mins}m {secs}s`\n\n"
            "**Control Commands:**\n"
            " `/status` - စနစ်၏ လက်ရှိ အခြေအနေ ကြည့်ရန်\n"
            " `/settarget <ID>` - Set Target Channel\n"
            " `/setlog <ID>` - Set System Log Channel\n"
            " `/addsource <ID/Link>` - Add Source & Auto Fetch All Past Videos\n"
            " `/delsource <ID/Link>` - Remove Source Monitor\n"
            " `/sources` - View Active Sources\n"
            " `/toggle` - Pause / Resume Engine"
        )
        await event.respond(panel_text)

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]status$'))
    async def status_command(event):
        total, used, free = shutil.disk_usage(".")
        uptime_sec = int(time.time() - system_boot_time)
        hrs, rem = divmod(uptime_sec, 3600)
        mins, secs = divmod(rem, 60)

        cache_files_count = 0
        if os.path.exists(TEMP_DIR):
            cache_files_count = len(os.listdir(TEMP_DIR))

        status_report = (
            " **SYSTEM DETAILED STATUS REPORT**\n"
            "\n"
            f" **Engine Status:** `{'ONLINE ' if db.get('system_active') else 'PAUSED '}`\n"
            f" **Target Channel:** `{db.get('target_channel') or 'Not Configured'}`\n"
            f" **Log Channel:** `{db.get('log_channel') or 'Not Configured'}`\n"
            f" **Active Sources:** `{len(db.get('sources', []))}` channels\n"
            f" **Processed Media:** `{db.get('total_processed_files', 0)}` files\n"
            f" **System Uptime:** `{hrs}h {mins}m {secs}s`\n"
            f" **Disk Free Space:** `{human_readable_size(free)} / {human_readable_size(total)}`\n"
            f" **Active Cache Files:** `{cache_files_count}` files\n"
        )
        await event.respond(status_report)

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]settarget (.+)'))
    async def set_target(event):
        val = event.pattern_match.group(1).strip()
        target = int(val) if val.lstrip('-').isdigit() else val
        db["target_channel"] = target
        save_database(db)
        await event.respond(f" **Target Channel Updated:** `{target}`")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]setlog (.+)'))
    async def set_log(event):
        val = event.pattern_match.group(1).strip()
        log_id = int(val) if val.lstrip('-').isdigit() else val
        db["log_channel"] = log_id
        save_database(db)
        await event.respond(f" **Log Channel Updated:** `{log_id}`")
        await dispatch_log("Log Channel linked successfully.", "INFO")

    # --- SOURCE ထည့်သည်နှင့် အဟောင်းမှ အသစ်သို့ ALL FETCH + DUPLICATE SKIP HANDLER ---
    @bot.on(events.NewMessage(pattern=r'(?i)^[./]addsource (.+)'))
    async def add_source(event):
        src_raw = event.pattern_match.group(1).strip()

        try:
            entity = await bot.get_entity(int(src_raw) if src_raw.lstrip('-').isdigit() else src_raw)
            src_str = str(entity.id)
        except Exception:
            src_str = src_raw

        if src_str not in db["sources"]:
            db["sources"].append(src_str)
            save_database(db)
            await event.respond(f" **Source Added Successfully:** `{src_str}`")
            await dispatch_log(f"Source Added: `{src_str}`", "INFO")

            status_msg = await event.respond(" **Source ၏ ဖိုင်အဟောင်းအားလုံးကို စတင် စစ်ဆေးနေပါပြီ...**")
            
            try:
                fetched_count = 0
                skipped_count = 0
                
                # limit=None ဖြင့် အရင် ဗီဒီယို အကုန်လုံးကို အဟောင်းမှ အသစ်သို့ စစ်မည်
                async for msg in bot.iter_messages(entity if 'entity' in locals() else src_str, limit=None, reverse=True):
                    if msg and (msg.video or msg.document):
                        media_key = get_media_key(msg)
                        
                        # Target ထဲ တင်ပြီးသား ဖိုင်ဖြစ်နေပါက မလိုအပ်ဘဲ ထပ်မဒေါင်းဘဲ ကျော်မည်
                        if media_key and media_key in db.get("processed_ids", []):
                            skipped_count += 1
                            continue

                        fetched_count += 1
                        info_msg = await event.respond(f" **[ဖိုင်အမှတ် {fetched_count}] ဖိုင်အဟောင်း (ID: `{msg.id}`) ကို စတင် တင်နေပါပြီ...**")
                        await process_media_message(msg, info_msg)
                        await asyncio.sleep(1) # Telegram Rate Limit ကာကွယ်ရန်

                summary_text = (
                    " **SOURCE FETCHING COMPLETED**\n"
                    "\n"
                    f" **တင်ပြီးခဲ့သော ဗီဒီယိုသစ်:** `{fetched_count}` ခု\n"
                    f" **ရှိပြီးသားမို့ ကျော်ခဲ့သော ဗီဒီယို:** `{skipped_count}` ခု"
                )
                await status_msg.edit(summary_text)

            except Exception as e:
                await status_msg.edit(f" Source ထည့်ပြီးသော်လည်း ဖိုင်အဟောင်းများ ယူရာတွင် Error တက်ခဲ့ပါသည်: `{e}`")
        else:
            await event.respond(" ဒီ Source က စာရင်းထဲတွင် ရှိပြီးသား ဖြစ်ပါသည်။")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]delsource (.+)'))
    async def del_source(event):
        src = event.pattern_match.group(1).strip()
        if src in db["sources"]:
            db["sources"].remove(src)
            save_database(db)
            await event.respond(f" **Source Removed:** `{src}`")
            await dispatch_log(f"Source Removed: `{src}`", "INFO")
        else:
            await event.respond(" Source not found.")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]sources$'))
    async def list_sources(event):
        sources = db.get("sources", [])
        if not sources:
            await event.respond(" No active sources configured.")
            return
        text = " **Active Monitored Sources:**\n"
        for idx, s in enumerate(sources, 1):
            text += f"{idx}. `{s}`\n"
        await event.respond(text)

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]toggle$'))
    async def toggle_system(event):
        db["system_active"] = not db.get("system_active", True)
        save_database(db)
        state = "ONLINE " if db["system_active"] else "PAUSED "
        await event.respond(f" **Engine State:** `{state}`")

    # --- REAL-TIME NEW MESSAGE INTERCEPTOR ---
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
                media_key = get_media_key(event.message)
                if media_key and media_key in db.get("processed_ids", []):
                    return # တင်ပြီးသားဖြစ်ပါက ကျော်မည်

                status_msg = await event.respond(" **Real-time Media Detected...**")
                await process_media_message(event.message, status_msg)

        except errors.FloodWaitError as flood_err:
            wait_time = flood_err.seconds
            logging.warning(f"FloodWait Triggered: Waiting {wait_time}s")
            await dispatch_log(f" FloodWait Warning: Waiting `{wait_time}` seconds.", "WARNING")
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
