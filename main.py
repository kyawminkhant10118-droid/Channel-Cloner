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
LOG_FILE_NAME = "original_copy_bot.log"

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d] — %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE_NAME, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

API_ID = int(os.environ.get("API_ID", 38078790))
API_HASH = os.environ.get("API_HASH", "c1b7e324a99544d7a9229ff5324af362")
SESSION_STRING = os.environ.get("SESSION_STRING")

# Multi-Admin Config
ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip().isdigit()]

DB_FILE = "exact_database.json"
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
        "processed_ids": []
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

# --- 2. UTILITY HELPERS ---
def is_authorized(user_id):
    if not ADMIN_IDS:
        return True
    return user_id in ADMIN_IDS

def get_media_key(msg):
    """Photo, Video နှင့် Document များအတွက် Unique Media Key ရယူခြင်း"""
    if not msg or not (msg.video or msg.photo or msg.document):
        return None
    if hasattr(msg, 'media') and hasattr(msg.media, 'document') and msg.media.document:
        return f"doc_{msg.media.document.id}"
    elif hasattr(msg, 'media') and hasattr(msg.media, 'photo') and msg.media.photo:
        return f"photo_{msg.media.photo.id}"
    elif msg.file:
        return f"file_{msg.file.size}_{msg.file.name}"
    return f"msg_{msg.chat_id}_{msg.id}"

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

# --- 3. EXACT MEDIA PROCESSOR (PHOTO/VIDEO/DOCS) ---
async def process_media_message(msg, status_msg):
    target = db.get("target_channel")
    if not target:
        await status_msg.edit("⚠️ Target Channel သတ်မှတ်ထားခြင်း မရှိသေးပါ။ `/settarget` ဖြင့် အရင် သတ်မှတ်ပေးပါ။")
        return False

    media_key = get_media_key(msg)

    # ORIGINAL CAPTION & FORMATTING ENTITIES
    original_caption = msg.text or ""
    original_entities = msg.entities

    # -------------------------------------------------------------
    # METHOD 1: SERVER-SIDE EXACT COPY (PHOTO/VIDEO အားလုံး အကျုံးဝင်သည်)
    # -------------------------------------------------------------
    try:
        await status_msg.edit("⚡ **Source မူရင်းအတိုင်း Direct Copy တင်နေပါသည်...**")
        
        await bot.send_file(
            target,
            msg.media,
            caption=original_caption,
            formatting_entities=original_entities
        )

        db["total_processed_files"] = db.get("total_processed_files", 0) + 1
        if media_key and media_key not in db.get("processed_ids", []):
            db["processed_ids"].append(media_key)
        save_database(db)

        finish_text = (
            "✅ **EXACT COPY SUCCESS**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 **Target:** `{target}`\n"
            f"⚡ **Status:** Source အတိုင်း ၁၀၀% တစ်ပုံစံတည်း တင်ပြီးပါပြီ။"
        )
        await status_msg.edit(finish_text)
        await dispatch_log(f"✅ **EXACT COPY SUCCESS:** Msg ID `{msg.id}`", "INFO")

        await asyncio.sleep(1.5)
        await status_msg.delete()
        return True

    except Exception as fast_err:
        logging.info(f"Direct copy failed ({fast_err}). Fallback to Download & Upload.")
        await status_msg.edit("⚠️ **Direct Transfer မရပါသဖြင့် Download/Upload နည်းလမ်းသို့ ပြောင်းလဲနေပါသည်။**")
        await asyncio.sleep(1)

    # -------------------------------------------------------------
    # METHOD 2: DOWNLOAD & RE-UPLOAD (RESTRICTED CONTENT FALLBACK)
    # -------------------------------------------------------------
    os.makedirs(TEMP_DIR, exist_ok=True)
    downloaded_path = None
    thumb_path = None
    file_name = "Media_File"

    if msg.file and msg.file.name:
        file_name = msg.file.name
    elif msg.video:
        file_name = f"Video_{msg.id}.mp4"
    elif msg.photo:
        file_name = f"Photo_{msg.id}.jpg"

    try:
        dl_tracker = ProgressTracker("Downloading", status_msg, file_name)
        downloaded_path = await msg.download_media(
            file=TEMP_DIR + "/",
            progress_callback=dl_tracker.callback
        )

        # Video ဖြစ်ပါက Thumbnail ယူမည်
        if msg.video:
            try:
                thumb_path = await msg.download_media(thumb=-1, file=TEMP_DIR + "/")
            except Exception:
                thumb_path = None

        file_actual_name = os.path.basename(downloaded_path)
        ul_tracker = ProgressTracker("Uploading", status_msg, file_actual_name)

        file_lower_ext = downloaded_path.lower()
        is_video_ext = file_lower_ext.endswith(('.mp4', '.mkv', '.avi', '.mov', '.webm', '.m4v', '.flv')) or msg.video

        if is_video_ext:
            duration = 0
            w, h = 1280, 720

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
                    logging.warning(f"Hachoir warning: {ex}")

            video_attribute = DocumentAttributeVideo(
                duration=duration,
                w=w,
                h=h,
                supports_streaming=True
            )

            await bot.send_file(
                target,
                downloaded_path,
                caption=original_caption,
                formatting_entities=original_entities,
                thumb=thumb_path if (thumb_path and os.path.exists(thumb_path)) else None,
                attributes=[video_attribute],
                force_document=False,
                progress_callback=ul_tracker.callback
            )
        else:
            # Photos သို့မဟုတ် အခြား Documents များကို တင်ပေးခြင်း
            await bot.send_file(
                target,
                downloaded_path,
                caption=original_caption,
                formatting_entities=original_entities,
                progress_callback=ul_tracker.callback
            )

        db["total_processed_files"] = db.get("total_processed_files", 0) + 1
        if media_key and media_key not in db.get("processed_ids", []):
            db["processed_ids"].append(media_key)
        save_database(db)

        finish_text = (
            "✅ **TASK COMPLETED SUCCESSFULLY**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📁 **File:** `{file_actual_name}`\n"
            f"🎯 **Target:** `{target}`\n"
            f"🎬 **Status:** Source အတိုင်း Original Captions နှင့် တင်ပြီးပါပြီ။"
        )
        await status_msg.edit(finish_text)
        await dispatch_log(f"✅ **UPLOAD SUCCESS:** `{file_actual_name}`", "INFO")

        await asyncio.sleep(2)
        await status_msg.delete()
        return True

    except Exception as inner_err:
        err_trace = traceback.format_exc()
        logging.error(f"Media Task Error: {inner_err}\n{err_trace}")
        await status_msg.edit(f"❌ **Task Failed:** `{str(inner_err)}`")
        await dispatch_log(f"❌ **Processing Error:** `{str(inner_err)}`", "ERROR")
        return False

    finally:
        for p in [downloaded_path, thumb_path]:
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

# --- 4. COMMANDS & CONTROLS ---
async def main():
    await bot.start()
    logging.info("⚡ EXACT COPY BOT ONLINE (PHOTOS, VIDEOS & DOCUMENTS) ⚡")

    def auth_check(func):
        async def wrapper(event):
            if not is_authorized(event.sender_id):
                await event.respond("🚫 **Access Denied!** Admin သာ သုံးစွဲခွင့်ရှိပါသည်။")
                return
            await func(event)
        return wrapper

    @bot.on(events.NewMessage(pattern=r'(?i)^[./](start|help|dashboard|menu)$'))
    @auth_check
    async def dashboard_command(event):
        uptime_sec = int(time.time() - system_boot_time)
        hrs, rem = divmod(uptime_sec, 3600)
        mins, secs = divmod(rem, 60)

        panel_text = (
            "💎 **EXACT COPY BOT DASHBOARD**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 Target Channel: `{db.get('target_channel') or 'Not Configured'}`\n"
            f"🛡 Log Channel: `{db.get('log_channel') or 'Not Configured'}`\n"
            f"📡 Active Sources: `{len(db.get('sources', []))}` active\n"
            f"⚙️ Engine Status: `{'ONLINE 🟢' if db.get('system_active') else 'PAUSED 🔴'}`\n"
            f"📦 Total Processed: `{db.get('total_processed_files', 0)}` files\n"
            f"⏱ System Uptime: `{hrs}h {mins}m {secs}s`\n\n"
            "**Control Commands:**\n"
            "• `/settarget <ID>` - Target Channel သတ်မှတ်ရန်\n"
            "• `/setlog <ID>` - Log Channel သတ်မှတ်ရန်\n"
            "• `/addsource <ID>` - Source ထည့်ပြီး Auto Copy လုပ်ရန်\n"
            "• `/range <Source> <Start_ID> <End_ID>` - ID အလိုက် အဟောင်းများ ကူးရန်\n"
            "• `/status` - စနစ် Status ကြည့်ရန်"
        )
        await event.respond(panel_text)

    # --- RANGE BATCH COPY (PHOTOS, VIDEOS, DOCS) ---
    @bot.on(events.NewMessage(pattern=r'(?i)^[./]range (\S+) (\d+) (\d+)'))
    @auth_check
    async def range_fetch(event):
        src_raw = event.pattern_match.group(1)
        start_id = int(event.pattern_match.group(2))
        end_id = int(event.pattern_match.group(3))

        if start_id > end_id:
            await event.respond("⚠️ Start ID သည် End ID ထက် ပိုမကြီးရပါ။")
            return

        status_msg = await event.respond(f"🚀 **Range Processing Started:** ID `{start_id}` to `{end_id}`...")
        success, skipped = 0, 0

        for msg_id in range(start_id, end_id + 1):
            try:
                msg = await bot.get_messages(int(src_raw) if src_raw.lstrip('-').isdigit() else src_raw, ids=msg_id)
                if msg and (msg.video or msg.photo or msg.document):
                    media_key = get_media_key(msg)
                    if media_key and media_key in db.get("processed_ids", []):
                        skipped += 1
                        continue

                    info_msg = await event.respond(f"📥 **Processing ID: `{msg_id}`...**")
                    res = await process_media_message(msg, info_msg)
                    if res:
                        success += 1
                    await asyncio.sleep(1)
            except Exception as e:
                logging.error(f"Error fetching ID {msg_id}: {e}")

        await status_msg.edit(
            "✅ **RANGE TASK COMPLETED**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 Total Success: `{success}`\n"
            f"⏩ Total Skipped: `{skipped}`"
        )

    # --- STANDARD COMMANDS ---
    @bot.on(events.NewMessage(pattern=r'(?i)^[./]status$'))
    @auth_check
    async def status_command(event):
        total, used, free = shutil.disk_usage(".")
        uptime_sec = int(time.time() - system_boot_time)
        hrs, rem = divmod(uptime_sec, 3600)
        mins, secs = divmod(rem, 60)

        status_report = (
            "📊 **DETAILED SYSTEM STATUS**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚙️ **Engine Status:** `{'ONLINE 🟢' if db.get('system_active') else 'PAUSED 🔴'}`\n"
            f"🎯 **Target Channel:** `{db.get('target_channel') or 'Not Configured'}`\n"
            f"🛡 **Log Channel:** `{db.get('log_channel') or 'Not Configured'}`\n"
            f"📡 **Active Sources:** `{len(db.get('sources', []))}` channels\n"
            f"📦 **Processed Media:** `{db.get('total_processed_files', 0)}` files\n"
            f"⏱ **System Uptime:** `{hrs}h {mins}m {secs}s`\n"
            f"💾 **Disk Free Space:** `{human_readable_size(free)} / {human_readable_size(total)}`\n"
        )
        await event.respond(status_report)

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]settarget (.+)'))
    @auth_check
    async def set_target(event):
        val = event.pattern_match.group(1).strip()
        target = int(val) if val.lstrip('-').isdigit() else val
        db["target_channel"] = target
        save_database(db)
        await event.respond(f"✅ **Target Channel Updated:** `{target}`")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]setlog (.+)'))
    @auth_check
    async def set_log(event):
        val = event.pattern_match.group(1).strip()
        log_id = int(val) if val.lstrip('-').isdigit() else val
        db["log_channel"] = log_id
        save_database(db)
        await event.respond(f"✅ **Log Channel Updated:** `{log_id}`")
        await dispatch_log("Log Channel linked successfully.", "INFO")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]addsource (.+)'))
    @auth_check
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
            await event.respond(f"✅ **Source Added Successfully:** `{src_str}`")

            status_msg = await event.respond("🔍 **Source ၏ ဖိုင်အဟောင်းများကို စတင် ကူးယူနေပါပြီ...**")
            try:
                fetched_count, skipped_count = 0, 0
                async for msg in bot.iter_messages(entity if 'entity' in locals() else src_str, limit=None, reverse=True):
                    if msg and (msg.video or msg.photo or msg.document):
                        media_key = get_media_key(msg)
                        if media_key and media_key in db.get("processed_ids", []):
                            skipped_count += 1
                            continue

                        fetched_count += 1
                        info_msg = await event.respond(f"📥 **[ဖိုင်အမှတ် {fetched_count}] ဖိုင်အဟောင်း (ID: `{msg.id}`) ကို တင်နေပါပြီ...**")
                        await process_media_message(msg, info_msg)
                        await asyncio.sleep(1)

                await status_msg.edit(
                    "✅ **SOURCE FETCHING COMPLETED**\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"📦 **မီဒီယာသစ် တင်ပြီး:** `{fetched_count}` ခု\n"
                    f"⏩ **ရှိပြီးသားမို့ ကျော်ခဲ့:** `{skipped_count}` ခု"
                )
            except Exception as e:
                await status_msg.edit(f"⚠️ Source ဖိုင်အဟောင်းများ ယူရာတွင် Error တက်ခဲ့ပါသည်: `{e}`")
        else:
            await event.respond("⚠️ ဒီ Source က စာရင်းထဲတွင် ရှိပြီးသား ဖြစ်ပါသည်။")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]delsource (.+)'))
    @auth_check
    async def del_source(event):
        src = event.pattern_match.group(1).strip()
        if src in db["sources"]:
            db["sources"].remove(src)
            save_database(db)
            await event.respond(f"🗑 **Source Removed:** `{src}`")
        else:
            await event.respond("⚠️ Source not found.")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]sources$'))
    @auth_check
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
    @auth_check
    async def toggle_system(event):
        db["system_active"] = not db.get("system_active", True)
        save_database(db)
        state = "ONLINE 🟢" if db["system_active"] else "PAUSED 🔴"
        await event.respond(f"🔄 **Engine State:** `{state}`")

    # --- REAL-TIME LISTENER (PHOTOS, VIDEOS, DOCUMENTS) ---
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

            # Photos, Videos နှင့် Documents များကို ဖမ်းယူခြင်း
            if is_matched and (event.video or event.photo or event.document):
                media_key = get_media_key(event.message)
                if media_key and media_key in db.get("processed_ids", []):
                    return

                status_msg = await event.respond("💎 **New Media Detected! Copying exact content...**")
                await process_media_message(event.message, status_msg)

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
