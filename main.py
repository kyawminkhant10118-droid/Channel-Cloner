import os
import json
import time
import math
import shutil
import logging
import asyncio
import subprocess
import traceback
from collections import defaultdict
from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession
from telethon.tl.types import DocumentAttributeVideo
from telethon.utils import get_peer_id

# --- 1. LOGGING & CONFIGURATION ---
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] — %(message)s',
    handlers=[logging.StreamHandler()]
)

API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip().isdigit()]

DB_FILE = "exact_database.json"
TEMP_DIR = "fast_cache"

ALBUM_BUFFERS = defaultdict(list)
ALBUM_LOCKS = set()

# Real-time Task Monitor State
CURRENT_TASK = {
    "action": "Idle (စောင့်ဆိုင်းနေသည်)",
    "file": "-",
    "percentage": "0%",
    "speed": "0 KB/s",
    "eta": "00:00:00",
    "source": "-"
}

# --- 2. DATABASE MANAGEMENT ---
def load_database():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    data = json.loads(content)
                    if "processed_ids" not in data:
                        data["processed_ids"] = []
                    return data
        except Exception as e:
            logging.error(f"Database Load Error: {e}")
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

if SESSION_STRING:
    bot = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
else:
    bot = TelegramClient('bot_session', API_ID, API_HASH)

# --- 3. UTILITY & HELPER FUNCTIONS ---
def is_authorized(user_id):
    if not ADMIN_IDS:
        return True
    return user_id in ADMIN_IDS

def get_media_key(msg):
    if not msg or not (msg.video or msg.photo or msg.document):
        return None
    if hasattr(msg, 'media') and hasattr(msg.media, 'document') and msg.media.document:
        return f"doc_{msg.media.document.id}"
    elif hasattr(msg, 'media') and hasattr(msg.media, 'photo') and msg.media.photo:
        return f"photo_{msg.media.photo.id}"
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

def generate_clean_thumbnail(video_path, output_thumb_path):
    try:
        command = [
            'ffmpeg', '-y',
            '-ss', '00:00:02',
            '-i', video_path,
            '-vframes', '1',
            '-vf', 'scale=320:-1',
            output_thumb_path
        ]
        subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        if os.path.exists(output_thumb_path) and os.path.getsize(output_thumb_path) > 0:
            return output_thumb_path
    except Exception as e:
        logging.warning(f"FFmpeg Thumbnail Warning: {e}")
    return None

def get_video_metadata(video_path):
    duration, width, height = 0, 1280, 720
    try:
        cmd = [
            'ffprobe', '-v', 'error',
            '-show_entries', 'format=duration:stream=width,height',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            video_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        lines = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
        if len(lines) >= 3:
            width = int(lines[0])
            height = int(lines[1])
            duration = int(float(lines[2]))
    except Exception as e:
        logging.warning(f"FFprobe Metadata Error: {e}")
    return duration, width, height

async def dispatch_log(log_msg, level="INFO"):
    log_chat_id = db.get("log_channel")
    if log_chat_id:
        try:
            icon = "🟢" if level == "INFO" else "❌" if level == "ERROR" else "⚠️"
            await bot.send_message(log_chat_id, f"{icon} **SYSTEM LOG [{level}]**\n{log_msg}")
        except Exception as e:
            logging.error(f"Log Dispatch Failed: {e}")

def reset_current_task():
    global CURRENT_TASK
    CURRENT_TASK = {
        "action": "Idle (စောင့်ဆိုင်းနေသည်)",
        "file": "-",
        "percentage": "0%",
        "speed": "0 KB/s",
        "eta": "00:00:00",
        "source": "-"
    }

# --- 4. PROGRESS TRACKER CLASS ---
class ProgressTracker:
    def __init__(self, action_name, message, file_name, source_info="Unknown"):
        self.action_name = action_name
        self.message = message
        self.file_name = file_name
        self.source_info = str(source_info)
        self.start_time = time.time()
        self.last_update_time = time.time()

    async def callback(self, current, total):
        now = time.time()
        if now - self.last_update_time < 2.5 and current != total:
            return

        self.last_update_time = now
        elapsed = now - self.start_time
        percentage = (current / total) * 100 if total > 0 else 0
        speed = current / elapsed if elapsed > 0 else 0
        eta = (total - current) / speed if speed > 0 else 0

        filled_blocks = int(percentage // 10)
        progress_bar = "█" * filled_blocks + "░" * (10 - filled_blocks)

        global CURRENT_TASK
        CURRENT_TASK = {
            "action": self.action_name,
            "file": self.file_name,
            "percentage": f"{percentage:.1f}%",
            "speed": f"{human_readable_size(speed)}/s",
            "eta": human_readable_time(eta),
            "source": self.source_info
        }

        status_text = (
            f"⚡ **{self.action_name.upper()} IN PROGRESS**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 **Source:** `{self.source_info}`\n"
            f"📁 **File:** `{self.file_name}`\n"
            f"📊 **Progress:** `[{progress_bar}] {percentage:.1f}%`\n"
            f"🚀 **Speed:** `{human_readable_size(speed)}/s`\n"
            f"📦 **Size:** `{human_readable_size(current)} / {human_readable_size(total)}`\n"
            f"⏱ **ETA:** `{human_readable_time(eta)}`"
        )

        try:
            if self.message:
                await self.message.edit(status_text)
        except Exception:
            pass

# --- 5. MEDIA PROCESSOR ---
async def process_media_message(msg, status_msg=None, source_info="Unknown"):
    target = db.get("target_channel")
    if not target:
        if status_msg:
            await status_msg.edit("⚠️ Target Channel/Group မသတ်မှတ်ရသေးပါ။ `/settarget` သုံးပါ။")
        return False

    media_key = get_media_key(msg)
    original_caption = msg.text or ""
    original_entities = msg.entities

    # Direct Copy
    try:
        if status_msg:
            await status_msg.edit("⚡ **Direct Copy စတင်နေပါသည်...**")

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

        await dispatch_log(f"✅ **DIRECT COPY SUCCESS:** Copied from `{source_info}`", "INFO")

        if status_msg:
            await status_msg.edit("✅ **DIRECT COPY SUCCESS**")
            await asyncio.sleep(1)
            await status_msg.delete()
        reset_current_task()
        return True

    except Exception:
        if status_msg:
            await status_msg.edit("⚠️ **Restricted Content ဖြစ်သောကြောင့် Fast Download/Upload ပြုလုပ်နေပါသည်။**")

    # Fast Download & Upload Fallback
    os.makedirs(TEMP_DIR, exist_ok=True)
    downloaded_path = None
    thumb_path = None

    file_name = "Media_File"
    if msg.file and msg.file.name:
        file_name = msg.file.name
    elif msg.video:
        file_name = f"Video_{msg.id}.mp4"

    try:
        dl_tracker = ProgressTracker("Downloading", status_msg, file_name, source_info)
        downloaded_path = await msg.download_media(
            file=TEMP_DIR + "/",
            progress_callback=dl_tracker.callback
        )

        if not downloaded_path or not os.path.exists(downloaded_path):
            raise Exception("Download ယူ၍ မရရှိပါ။")

        file_actual_name = os.path.basename(downloaded_path)
        ul_tracker = ProgressTracker("Uploading", status_msg, file_actual_name, source_info)

        file_lower = downloaded_path.lower()
        is_video = file_lower.endswith(('.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.m4v')) or msg.video

        if is_video:
            duration, w, h = get_video_metadata(downloaded_path)
            generated_thumb = f"{downloaded_path}_thumb.jpg"
            thumb_path = generate_clean_thumbnail(downloaded_path, generated_thumb)

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

        await dispatch_log(f"✅ **RE-UPLOAD SUCCESS:** `{file_actual_name}` from `{source_info}`", "INFO")

        if status_msg:
            await status_msg.edit("✅ **SUCCESSFULLY COPIED & STREAM READY**")
            await asyncio.sleep(1)
            await status_msg.delete()
        reset_current_task()
        return True

    except Exception as inner_err:
        logging.error(f"Media Task Error: {inner_err}\n{traceback.format_exc()}")
        await dispatch_log(f"❌ **TASK FAILED:** `{str(inner_err)}`", "ERROR")
        if status_msg:
            await status_msg.edit(f"❌ **Task Failed:** `{str(inner_err)}`")
        reset_current_task()
        return False

    finally:
        for p in [downloaded_path, thumb_path]:
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

# --- 6. COMMAND HANDLERS & HISTORY BACKFILL ---
def auth_check(func):
    async def wrapper(event):
        if not is_authorized(event.sender_id):
            await event.respond("🚫 Admin သာ သုံးစွဲခွင့်ရှိပါသည်။")
            return
        await func(event)
    return wrapper

# 🔥 အဟောင်းများ အကုန် လိုက်ကူးပေးမည့် FEATURE
@bot.on(events.NewMessage(pattern=r'(?i)^[./](cloneold|copyall)(?:\s+(.+))?$'))
@auth_check
async def clone_old_history(event):
    target = db.get("target_channel")
    if not target:
        await event.respond("⚠️ **Target Channel/Group မသတ်မှတ်ရသေးပါ။** `/settarget` အရင်လုပ်ပါ။")
        return

    arg = event.pattern_match.group(2)
    sources_to_clone = []

    if arg:
        sources_to_clone.append(arg.strip())
    else:
        sources_to_clone = db.get("sources", [])

    if not sources_to_clone:
        await event.respond("⚠️ **Source မရှိသေးပါ။** `/addsource` ဖြင့် Source အရင်ထည့်ပါ သို့မဟုတ် `/copyall <Source_ID>` ဟု ရိုက်ထည့်ပါ။")
        return

    status_msg = await event.respond("⏳ **ယခင် တက်ခဲ့ပြီးသား Media အဟောင်းများကို စတင် ရှာဖွေနေပါသည်...**")

    for src in sources_to_clone:
        try:
            entity_arg = int(src) if str(src).lstrip('-').isdigit() else src
            entity = await bot.get_entity(entity_arg)
            title = getattr(entity, 'title', getattr(entity, 'first_name', 'Source'))

            await status_msg.edit(f"🔍 **`{title}` မှ မက်ဆေ့ချ် အဟောင်းများကို စစ်ဆေးနေပါသည်...**")

            scanned_count = 0
            copied_count = 0

            # reverse=True ကြောင့် အဟောင်းဆုံး မက်ဆေ့ချ်မှ အသစ်ဆုံး မက်ဆေ့ချ်သို့ စီ၍ ကူးပေးမည်
            async for message in bot.iter_messages(entity, reverse=True):
                scanned_count += 1

                if message.video or message.photo or message.document:
                    media_key = get_media_key(message)

                    # ကူးပြီးသား ဖိုင်ဖြစ်ပါက ကျော်မည်
                    if media_key and media_key in db.get("processed_ids", []):
                        continue

                    # Message တစ်ခုချင်းစီကို Process လုပ်ခြင်း
                    progress_info = f"`{title}` (Scanned: {scanned_count} | Copied: {copied_count})"
                    task_msg = await event.respond(f"📦 **အဟောင်းများ ကူးယူနေပါသည်:** {progress_info}")
                    
                    success = await process_media_message(message, task_msg, source_info=title)
                    if success:
                        copied_count += 1

                    # Telegram FloodWait မမိစေရန် ၁ စက္ကန့် နားမည်
                    await asyncio.sleep(1)

            await event.respond(f"✅ **`{title}` ၏ အဟောင်းများ ကူးယူခြင်း ပြီးစီးပါပြီ!**\n📊 Total Copied: `{copied_count}` items")

        except errors.FloodWaitError as flood:
            await event.respond(f"⏳ **Telegram Rate Limit ကြောင့် {flood.seconds} စက္ကန့် စောင့်ဆိုင်းနေပါသည်...**")
            await asyncio.sleep(flood.seconds)
        except Exception as e:
            logging.error(f"Clone History Error for {src}: {e}")
            await event.respond(f"❌ **Error copying history from `{src}`:** `{str(e)}`")

    await status_msg.edit("🎉 **သတ်မှတ်ထားသော Source များမှ မက်ဆေ့ချ် အဟောင်းများ အားလုံး ကူးယူပြီးပါပြီ။**")

@bot.on(events.NewMessage(pattern=r'(?i)^[./]ping$'))
@auth_check
async def ping_command(event):
    start = time.time()
    msg = await event.respond("🏓 **Pinging System...**")
    delta = round((time.time() - start) * 1000, 2)
    await msg.edit(f"🏓 **PONG!**\n⚡ **Latency:** `{delta} ms`\n🟢 **Engine State:** `Running 24/7`")

@bot.on(events.NewMessage(pattern=r'(?i)^[./](live|activity|task)$'))
@auth_check
async def live_task_command(event):
    report = (
        "📊 **LIVE BOT ACTIVITY MONITOR**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚙️ **Status:** `{CURRENT_TASK['action']}`\n"
        f"📍 **Source:** `{CURRENT_TASK['source']}`\n"
        f"📁 **File:** `{CURRENT_TASK['file']}`\n"
        f"📊 **Progress:** `{CURRENT_TASK['percentage']}`\n"
        f"🚀 **Speed:** `{CURRENT_TASK['speed']}`\n"
        f"⏱ **ETA:** `{CURRENT_TASK['eta']}`\n"
    )
    await event.respond(report)

@bot.on(events.NewMessage(pattern=r'(?i)^[./](start|help|dashboard|status)$'))
@auth_check
async def dashboard_command(event):
    uptime_sec = int(time.time() - system_boot_time)
    hrs, rem = divmod(uptime_sec, 3600)
    mins, secs = divmod(rem, 60)

    total, used, free = shutil.disk_usage(".")

    panel_text = (
        "💎 **CHANNEL & GROUP CLONER BOT**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🟢 **Engine State:** `{'ONLINE (ACTIVE)' if db.get('system_active') else 'PAUSED 🔴'}`\n"
        f"⚙️ **Current Action:** `{CURRENT_TASK['action']}`\n"
        f"🎯 **Target Channel/Group:** `{db.get('target_channel') or 'Not Configured'}`\n"
        f"🛡 **Log Channel:** `{db.get('log_channel') or 'Not Configured'}`\n"
        f"📡 **Active Sources:** `{len(db.get('sources', []))}` active\n"
        f"📦 **Total Processed:** `{db.get('total_processed_files', 0)}` items\n"
        f"💾 **Free Disk Space:** `{human_readable_size(free)}` / `{human_readable_size(total)}`\n"
        f"⏱ **System Uptime:** `{hrs}h {mins}m {secs}s`\n\n"
        "**Available Commands:**\n"
        "• `/copyall` - Source ထဲရှိ **အဟောင်းများ အားလုံး** လိုက်ကူးရန်\n"
        "• `/addsource <Link/ID>` - Source ထည့်ရန် (Name ပြပေးမည်)\n"
        "• `/settarget <Link/ID>` - Target သတ်မှတ်ရန်\n"
        "• `/setlog <Link/ID>` - Log Channel သတ်မှတ်ရန်\n"
        "• `/live` - လက်ရှိ ဘာလုပ်နေလဲ ကြည့်ရန်\n"
        "• `/ping` - Bot စစ်ရန်\n"
        "• `/delsource <ID>` - Source ဖျက်ရန်\n"
        "• `/sources` - Source စာရင်းကြည့်ရန်\n"
        "• `/toggle` - Bot ဖွင့်/ပိတ် လုပ်ရန်"
    )
    await event.respond(panel_text)

@bot.on(events.NewMessage(pattern=r'(?i)^[./]settarget (.+)'))
@auth_check
async def set_target(event):
    val = event.pattern_match.group(1).strip()
    status_msg = await event.respond("🔍 **Target Group/Channel အချက်အလက် စစ်ဆေးနေပါသည်...**")
    try:
        entity = await bot.get_entity(int(val) if val.lstrip('-').isdigit() else val)
        peer_id = get_peer_id(entity)
        title = getattr(entity, 'title', getattr(entity, 'first_name', 'Unknown Name'))
        
        db["target_channel"] = peer_id
        save_database(db)
        await status_msg.edit(f"✅ **TARGET SET SUCCESSFULLY!**\n📌 **အမည်:** `{title}`\n🆔 **ID:** `{peer_id}`")
        await dispatch_log(f"🎯 **Target Set:** **{title}** (`{peer_id}`)", "INFO")
    except Exception as e:
        target = int(val) if val.lstrip('-').isdigit() else val
        db["target_channel"] = target
        save_database(db)
        await status_msg.edit(f"✅ **Target Channel Updated:** `{target}`")

@bot.on(events.NewMessage(pattern=r'(?i)^[./]setlog (.+)'))
@auth_check
async def set_log(event):
    val = event.pattern_match.group(1).strip()
    log_id = int(val) if val.lstrip('-').isdigit() else val
    db["log_channel"] = log_id
    save_database(db)
    await event.respond(f"✅ **Log Channel Updated:** `{log_id}`")
    await dispatch_log("Log channel configured successfully.", "INFO")

@bot.on(events.NewMessage(pattern=r'(?i)^[./]addsource (.+)'))
@auth_check
async def add_source(event):
    src_raw = event.pattern_match.group(1).strip()
    status_msg = await event.respond("🔍 **Source Group/Channel အချက်အလက် စစ်ဆေးနေပါသည်...**")

    try:
        entity_arg = int(src_raw) if src_raw.lstrip('-').isdigit() else src_raw
        entity = await bot.get_entity(entity_arg)
        
        peer_id = str(get_peer_id(entity))
        title = getattr(entity, 'title', getattr(entity, 'first_name', 'Unknown Name'))
        username = f"@{entity.username}" if getattr(entity, 'username', None) else "Private Group/Channel"

        if peer_id not in db["sources"]:
            db["sources"].append(peer_id)
            save_database(db)
            
            success_text = (
                "✅ **SOURCE ADDED SUCCESSFULLY!**\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📌 **အမည် (Name):** `{title}`\n"
                f"🆔 **ID:** `{peer_id}`\n"
                f"🔗 **Username/Link:** `{username}`\n\n"
                "⚡ *ဒီ Group/Channel မှာ တက်လာသမျှ ဖိုင်များကို စတင် စောင့်ကြည့် ကူးယူပေးနေပါပြီ။*\n"
                "👉 *အဟောင်းများကိုပါ အကုန်ကူးလိုပါက `/copyall` ဟု ရိုက်ထည့်ပါ။*"
            )
            await status_msg.edit(success_text)
            await dispatch_log(f"📡 **New Source Added:** **{title}** (`{peer_id}`)", "INFO")
        else:
            await status_msg.edit(f"⚠️ **{title}** (`{peer_id}`) သည် စာရင်းထဲတွင် ရှိပြီးသား ဖြစ်ပါသည်။")

    except Exception as e:
        await status_msg.edit(
            f"❌ **Source ရှာမတွေ့ပါ။**\n"
            f"ID သို့မဟုတ် Link မှန်မမှန် ပြန်စစ်ပါ။\n\n"
            f"Error Details: `{str(e)}`"
        )

@bot.on(events.NewMessage(pattern=r'(?i)^[./]delsource (.+)'))
@auth_check
async def del_source(event):
    src = event.pattern_match.group(1).strip()
    if src in db["sources"]:
        db["sources"].remove(src)
        save_database(db)
        await event.respond(f"🗑 **Source Removed:** `{src}`")
        await dispatch_log(f"🗑 Source Removed: `{src}`", "INFO")

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

# --- 7. REAL-TIME EVENT INTERCEPTOR ---
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

        chat_peer_id = str(get_peer_id(chat))
        chat_id = str(chat.id)
        username = f"@{chat.username.lower()}" if chat.username else None

        is_matched = any(
            str(s) == chat_peer_id or str(s) == chat_id or (username and str(s).lower() == username)
            for s in sources
        )

        if is_matched and (event.video or event.photo or event.document):
            media_key = get_media_key(event.message)
            if media_key and media_key in db.get("processed_ids", []):
                return

            source_name = getattr(chat, 'title', username or chat_id)

            if event.grouped_id:
                gid = event.grouped_id
                ALBUM_BUFFERS[gid].append(event.message)
                asyncio.create_task(process_album_group(gid))
            else:
                status_msg = await event.respond("💎 **New Media Detected! Processing...**")
                await process_media_message(event.message, status_msg, source_info=source_name)

    except errors.FloodWaitError as flood_err:
        await asyncio.sleep(flood_err.seconds)
    except Exception as outer_err:
        logging.error(f"Interceptor Error: {outer_err}")

# --- 8. MAIN ENGINE LOOP ---
async def main():
    if SESSION_STRING:
        await bot.start()
    else:
        await bot.start(bot_token=BOT_TOKEN)
        
    logging.info("⚡ TELEGRAM CHANNEL & GROUP CLONER IS ONLINE ⚡")
    await dispatch_log("🚀 **Bot System Started & Running 24/7!**", "INFO")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot stopped.")
