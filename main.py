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

# --- LOGGING & CONFIGURATION ---
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

# --- DATABASE MANAGEMENT ---
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

# --- UTILITIES ---
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

def generate_clean_thumbnail(video_path, output_thumb_path):
    """FFmpeg သုံး၍ ဗီဒီယို၏ ၂ စက္ကန့်မြောက် Frame မှ Thumbnail ထုတ်ယူခြင်း (အဖြူရောင်ဖြစ်ခြင်းမှ ကာကွယ်ရန်)"""
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
        logging.warning(f"FFmpeg Thumbnail Error: {e}")
    return None

def get_video_metadata(video_path):
    """FFprobe သုံး၍ Duration, Width, Height ကို ယူခြင်း"""
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

# --- MEDIA PROCESSOR ---
async def process_media_message(msg, status_msg=None):
    target = db.get("target_channel")
    if not target:
        if status_msg:
            await status_msg.edit("⚠️ Target Channel မသတ်မှတ်ရသေးပါ။ `/settarget` သုံးပါ။")
        return False

    media_key = get_media_key(msg)
    original_caption = msg.text or ""
    original_entities = msg.entities

    # Direct Transfer စမ်းသပ်ခြင်း
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

        if status_msg:
            await status_msg.edit("✅ **DIRECT COPY SUCCESS**")
            await asyncio.sleep(1)
            await status_msg.delete()
        return True

    except Exception:
        if status_msg:
            await status_msg.edit("⚠️ **Restricted Content ဖြစ်သောကြောင့် Fast Download/Upload ပြုလုပ်နေပါသည်။**")

    # Forward ပိတ်ထားသော Restricted Channel များအတွက် Download & Re-upload ပြုလုပ်ခြင်း
    os.makedirs(TEMP_DIR, exist_ok=True)
    downloaded_path = None
    thumb_path = None

    try:
        downloaded_path = await msg.download_media(file=TEMP_DIR + "/")
        if not downloaded_path or not os.path.exists(downloaded_path):
            raise Exception("Download ယူ၍ မရရှိပါ။")

        file_lower = downloaded_path.lower()
        is_video = file_lower.endswith(('.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.m4v')) or msg.video

        if is_video:
            if status_msg:
                await status_msg.edit("🎬 **Video Streaming & Thumbnail ပြင်ဆင်နေပါသည်...**")

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
                force_document=False
            )
        else:
            await bot.send_file(
                target,
                downloaded_path,
                caption=original_caption,
                formatting_entities=original_entities
            )

        db["total_processed_files"] = db.get("total_processed_files", 0) + 1
        if media_key and media_key not in db.get("processed_ids", []):
            db["processed_ids"].append(media_key)
        save_database(db)

        if status_msg:
            await status_msg.edit("✅ **SUCCESSFULLY COPIED & STREAM READY**")
            await asyncio.sleep(1)
            await status_msg.delete()
        return True

    except Exception as inner_err:
        logging.error(f"Media Task Error: {inner_err}\n{traceback.format_exc()}")
        if status_msg:
            await status_msg.edit(f"❌ **Task Failed:** `{str(inner_err)}`")
        return False

    finally:
        for p in [downloaded_path, thumb_path]:
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

# --- ALBUM PROCESSOR ---
async def process_album_group(grouped_id):
    if grouped_id in ALBUM_LOCKS:
        return
    ALBUM_LOCKS.add(grouped_id)
    await asyncio.sleep(2)

    messages = ALBUM_BUFFERS.pop(grouped_id, [])
    ALBUM_LOCKS.discard(grouped_id)

    if not messages:
        return

    messages.sort(key=lambda x: x.id)
    target = db.get("target_channel")
    if not target:
        return

    album_caption = ""
    album_entities = None
    for m in messages:
        if m.text:
            album_caption = m.text
            album_entities = m.entities
            break

    try:
        await bot.send_file(
            target,
            [m.media for m in messages if m.media],
            caption=album_caption,
            formatting_entities=album_entities
        )
        for m in messages:
            k = get_media_key(m)
            if k and k not in db.get("processed_ids", []):
                db["processed_ids"].append(k)
        db["total_processed_files"] = db.get("total_processed_files", 0) + len(messages)
        save_database(db)
    except Exception as e:
        logging.error(f"Album Error: {e}")

# --- COMMANDS ---
def auth_check(func):
    async def wrapper(event):
        if not is_authorized(event.sender_id):
            await event.respond("🚫 Admin သာ သုံးစွဲခွင့်ရှိပါသည်။")
            return
        await func(event)
    return wrapper

@bot.on(events.NewMessage(pattern=r'(?i)^[./](start|help|dashboard)$'))
@auth_check
async def dashboard_command(event):
    uptime_sec = int(time.time() - system_boot_time)
    hrs, rem = divmod(uptime_sec, 3600)
    mins, secs = divmod(rem, 60)

    panel_text = (
        "💎 **CHANNEL CLONER BOT (SPEED & STREAM OPTIMIZED)**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 Target Channel: `{db.get('target_channel') or 'Not Configured'}`\n"
        f"🛡 Log Channel: `{db.get('log_channel') or 'Not Configured'}`\n"
        f"📡 Active Sources: `{len(db.get('sources', []))}` active\n"
        f"⚙️ Engine Status: `{'ONLINE 🟢' if db.get('system_active') else 'PAUSED 🔴'}`\n"
        f"📦 Total Processed: `{db.get('total_processed_files', 0)}` items\n"
        f"⏱ System Uptime: `{hrs}h {mins}m {secs}s`\n\n"
        "**Commands:**\n"
        "• `/addsource <ID>` - Source ထည့်ရန်\n"
        "• `/settarget <ID>` - Target သတ်မှတ်ရန်\n"
        "• `/setlog <ID>` - Log Channel သတ်မှတ်ရန်\n"
        "• `/delsource <ID>` - Source ဖျက်ရန်\n"
        "• `/sources` - Source စာရင်းကြည့်ရန်\n"
        "• `/toggle` - Bot ဖွင့်/ပိတ် ပြုလုပ်ရန်"
    )
    await event.respond(panel_text)

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

@bot.on(events.NewMessage(pattern=r'(?i)^[./]addsource (.+)'))
@auth_check
async def add_source(event):
    src_raw = event.pattern_match.group(1).strip()
    src_str = src_raw
    if src_raw.lstrip('-').isdigit():
        src_str = str(int(src_raw))

    if src_str not in db["sources"]:
        db["sources"].append(src_str)
        save_database(db)
        await event.respond(f"✅ **Source Added Successfully:** `{src_str}`")
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

# --- REAL-TIME EVENT INTERCEPTOR ---
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

        if is_matched and (event.video or event.photo or event.document):
            media_key = get_media_key(event.message)
            if media_key and media_key in db.get("processed_ids", []):
                return

            if event.grouped_id:
                gid = event.grouped_id
                ALBUM_BUFFERS[gid].append(event.message)
                asyncio.create_task(process_album_group(gid))
            else:
                status_msg = await event.respond("💎 **New Media Detected! Copying...**")
                await process_media_message(event.message, status_msg)

    except errors.FloodWaitError as flood_err:
        await asyncio.sleep(flood_err.seconds)
    except Exception as outer_err:
        logging.error(f"Interceptor Error: {outer_err}")

# --- MAIN ENGINE LOOP ---
async def main():
    if SESSION_STRING:
        await bot.start()
    else:
        await bot.start(bot_token=BOT_TOKEN)
        
    logging.info("⚡ TELEGRAM CHANNEL CLONER BOT IS ONLINE ⚡")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot stopped.")
