import os
import re
import sys
import json
import time
import psutil
import asyncio
import subprocess
from datetime import datetime
from threading import Thread
from flask import Flask

# --- Telegram Native Client & Safe Imports ---
from telethon import TelegramClient, events, errors, functions, types
from telethon.sessions import StringSession

# --- 1. Web Server (Railway Keep-Alive Server) ---
app = Flask('')

@app.route('/')
def home():
    return "Ultra Pro Engine v5.3 (All Commands Registered) is Live!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- 2. Telegram API Credentials ---
API_ID = 38078790
API_HASH = 'c1b7e324a99544d7a9229ff5324af362'
SESSION_STRING = os.environ.get("SESSION_STRING")

# --- 3. Persistent JSON Database Setup ---
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

# --- 4. Userbot Client Initialization ---
bot = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

# --- Admin Log Sender Helper ---
async def send_log(text):
    log_id = DB.get("log_channel")
    if log_id:
        try:
            await bot.send_message(log_id, text)
        except Exception as e:
            print(f"[-] Log Send Failed: {e}")

# --- FFmpeg Auto Screenshot Generator ---
def generate_auto_screenshot(video_path):
    auto_thumb_path = os.path.join(TEMP_DIR, "auto_frame_thumb.jpg")
    try:
        cmd = [
            "ffmpeg", "-y",
            "-ss", "00:00:10",
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "2",
            auto_thumb_path
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        if os.path.exists(auto_thumb_path) and os.path.getsize(auto_thumb_path) > 0:
            print("[] Auto Screenshot Thumbnail Generated Successfully!")
            return auto_thumb_path
    except Exception as e:
        print(f"[-] FFmpeg Screenshot Error: {e}")
    return None

# --- Complete Telegram Command Menu Registration (ALL 18 COMMANDS) ---
async def setup_bot_command_menu():
    try:
        commands = [
            types.BotCommand(command="start", description=" Main Help Menu"),
            types.BotCommand(command="status", description=" Engine Hardware & Diagnostics"),
            types.BotCommand(command="add", description=" Add Source Channel"),
            types.BotCommand(command="del", description=" Remove Source Channel"),
            types.BotCommand(command="sources", description=" List Active Source Channels"),
            types.BotCommand(command="settarget", description=" Set Target Channel"),
            types.BotCommand(command="setthumb", description=" Set Custom Poster Thumbnail"),
            types.BotCommand(command="delthumb", description=" Delete Custom Thumbnail"),
            types.BotCommand(command="setlog", description=" Set Admin Log Channel"),
            types.BotCommand(command="replacelink", description=" Auto Replace External Links"),
            types.BotCommand(command="filter", description=" Set Media Filter (all/video/doc)"),
            types.BotCommand(command="header", description=" Set Caption Header Text"),
            types.BotCommand(command="footer", description=" Set Caption Footer Text"),
            types.BotCommand(command="watermark", description=" Set Caption Watermark"),
            types.BotCommand(command="join", description=" Auto Join Channel by Link"),
            types.BotCommand(command="search", description=" Search Movies in Database"),
            types.BotCommand(command="backup", description=" Download Database Backup File"),
            types.BotCommand(command="toggle", description=" Pause or Resume Engine")
        ]
        await bot(functions.bots.SetBotCommandsRequest(
            scope=types.BotCommandScopeDefault(),
            lang_code='en',
            commands=commands
        ))
        print("[+] Official Telegram Command Menu (18 Commands) Registered Successfully!")
    except Exception as e:
        print(f"[!] Command Menu Error: {e}")

# --- Session Refresher Service ---
async def session_refresher():
    while True:
        try:
            await bot.get_me()
        except Exception:
            pass
        await asyncio.sleep(1800)

# --- Caption Builder with Link Replacement ---
def build_caption(original_text):
    caption = original_text or ""
    
    # Custom Link Replacement
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

# --- High-Speed Restricted Bypass Upload Engine ---
async def safe_upload(message, caption):
    target = DB.get("target_channel")
    if not target:
        print("[-] Target Channel စာရင်း မရှိသေးပါ။ /settarget ဖြင့် အရင် သတ်မှတ်ပေးပါ။")
        return False

    media_mode = DB.get("media_filter", "all")
    if media_mode == "video" and not message.video:
        return False
    elif media_mode == "document" and not (message.document and not message.video):
        return False

    file_id = str(message.media.document.id) if (message.video or message.document) else None

    if file_id and file_id in DB.get("duplicates", []):
        print(f"[-] Duplicate File Skipped: {file_id}")
        return False

    is_noforward = getattr(message, 'noforward', False) or getattr(getattr(message, 'chat', None), 'noforward', False)
    thumb_to_use = THUMB_PATH if os.path.exists(THUMB_PATH) else None

    video_attrs = []
    if message.media and hasattr(message.media, 'document') and message.media.document and hasattr(message.media.document, 'attributes'):
        video_attrs = message.media.document.attributes

    while True:
        try:
            sent_msg = None
            
            # 1. Direct Forward Try
            if not is_noforward and not thumb_to_use:
                try:
                    sent_msg = await bot.send_file(target, message.media, caption=caption.strip())
                except Exception:
                    print("[!] Direct Send Blocked, Switching to Fast Download Mode...")
                    is_noforward = True

            # 2. Fast Restricted / Auto Screenshot Buffer Mode
            if is_noforward or thumb_to_use or not sent_msg:
                os.makedirs(TEMP_DIR, exist_ok=True)
                print("[] Downloading video buffer (High-Speed)...")
                
                temp_path = await bot.download_media(message, file=TEMP_DIR)
                auto_gen_thumb = None
                
                try:
                    if not thumb_to_use:
                        auto_gen_thumb = generate_auto_screenshot(temp_path)
                    
                    final_thumb = thumb_to_use or auto_gen_thumb

                    print("[] Re-uploading to Target Channel as Streaming Video...")
                    sent_msg = await bot.send_file(
                        target, 
                        temp_path, 
                        caption=caption.strip(),
                        thumb=final_thumb,
                        attributes=video_attrs,
                        supports_streaming=True,
                        part_size_kb=512
                    )
                finally:
                    if temp_path and os.path.exists(temp_path):
                        os.remove(temp_path)
                    if auto_gen_thumb and os.path.exists(auto_gen_thumb):
                        os.remove(auto_gen_thumb)

            if sent_msg:
                if file_id:
                    DB["duplicates"].append(file_id)

                title = message.text.split("\n")[0][:50] if message.text else "Unknown Movie"
                clean_target = str(target).replace('-100', '')
                msg_link = f"https://t.me/c/{clean_target}/{sent_msg.id}"
                DB["catalog"][title.lower()] = {"title": title, "link": msg_link}

                today = datetime.now().strftime("%Y-%m-%d")
                DB["daily_stats"][today] = DB["daily_stats"].get(today, 0) + 1
                save_db()

                await send_log(f" **Uploaded Successfully:**\n {title}\n [View Post]({msg_link})")
                print(f"[+] Successfully Uploaded: {title}")
                return True

        except errors.FloodWaitError as e:
            print(f"[!] FloodWait: Waiting {e.seconds}s...")
            await asyncio.sleep(e.seconds + 5)
        except Exception as upload_err:
            print(f"[-] Upload Error: {upload_err}")
            await send_log(f" **Upload Failed:** {upload_err}")
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
                caption = build_caption(message.text)
                await safe_upload(message, caption)
                await asyncio.sleep(2.0)
    except Exception as crawler_err:
        print(f"[-] Crawler Execution Error on {source_chat}: {crawler_err}")

# --- Link & Username Smart Resolver Helper ---
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
        raise Exception(f"Link / Username ကို ဖတ်၍ မရပါ: {e}")

# --- Main Engine Core Execution ---
async def main():
    await bot.start()
    print("==================================================")
    print(" ULTRA PRO ENGINE v5.3 (ALL MENU COMMANDS) IS LIVE!")
    print("==================================================")
    
    await setup_bot_command_menu()
    asyncio.create_task(session_refresher())

    # --- Start & Main Help Menu Command ---
    @bot.on(events.NewMessage(pattern=r'(?i)^/start$', outgoing=True))
    async def start_cmd(event):
        target_info = DB.get("target_channel", "မသတ်မှတ်ရသေးပါ")
        menu_text = (
            " **ULTRA PRO USERBOT ENGINE v5.3** \n"
            "*(Full Menu Integration & Streaming Bypass)*\n"
            "\n"
            f" **Target Channel:** `{target_info}`\n"
            f" **Log Channel:** `{DB.get('log_channel', 'Not Set')}`\n"
            f" **Custom Thumb:** `{'ENABLED' if os.path.exists(THUMB_PATH) else 'AUTO SCREENSHOT MODE'}`\n"
            f" **Link Replacer:** `{DB.get('replace_link', 'Disabled')}`\n\n"
            
            " **1. ADVANCED FEATURES:**\n"
            " `/setthumb` - ပုံ ပို့ပေးပြီး Custom Poster သတ်မှတ်ရန်\n"
            " `/delthumb` - Auto Screenshot စနစ် ပြန်သုံးရန်\n"
            " `/setlog <ID>` - Error/Upload Log ကြည့်မည့် Channel\n"
            " `/replacelink <Link>` - Link များ Auto အစားထိုးရန်\n"
            " `/filter <all/video/document>` - Media အမျိုးအစား သတ်မှတ်ရန်\n"
            " `/header` | `/footer` | `/watermark` - စာသားများ ပြင်ဆင်ရန်\n\n"

            " **2. SOURCE & TARGET COMMANDS:**\n"
            " `/add <Link/Username>` - Source ထည့်ရန်\n"
            " `/del <Link/Username>` - Source ပြန်ဖြုတ်ရန်\n"
            " `/sources` - Source ချန်နယ်များ စာရင်းကြည့်ရန်\n"
            " `/settarget <ID/Username>` - Target Channel ပြောင်းရန်\n"
            " `/join <Link>` - Channel အလိုအလျောက် Join ရန်\n\n"

            " **3. CONTROL & MONITORING:**\n"
            " `/status` - Hardware & Server စစ်ဆေးရန်\n"
            " `/search <နာမည်>` - Database ထဲ ရုပ်ရှင်ပြန်ရှာရန်\n"
            " `/backup` - DB ဖိုင် ထုတ်ယူရန်\n"
            " `/toggle` - Bot မောင်းနှင်မှု ခဏရပ်/ပြန်ဖွင့်ရန်"
        )
        await event.respond(menu_text)

    # --- Ultra Detailed Status Dashboard Command ---
    @bot.on(events.NewMessage(pattern=r'(?i)^/status$', outgoing=True))
    async def status_cmd(event):
        uptime_sec = int(time.time() - start_time)
        hours, remainder = divmod(uptime_sec, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s"

        vram = psutil.virtual_memory()
        ram_used_mb = round(vram.used / (1024 * 1024), 2)
        ram_total_mb = round(vram.total / (1024 * 1024), 2)

        cpu_pct = psutil.cpu_percent(interval=0.5)

        today = datetime.now().strftime("%Y-%m-%d")
        today_count = DB["daily_stats"].get(today, 0)

        status_msg = (
            " **ULTRA ENGINE HARDWARE & DIAGNOSTICS v5.3**\n"
            "\n"
            f" **Status:** `{DB.get('status', 'ON')}` | **Sources:** `{len(DB.get('sources', []))}`\n"
            f" **CPU Utilization:** `{cpu_pct}%`\n"
            f" **RAM Usage:** `{ram_used_mb} MB / {ram_total_mb} MB ({vram.percent}%)`\n"
            f" **Engine Uptime:** `{uptime_str}`\n\n"

            " **UPLOAD STATISTICS:**\n"
            f" **Today Uploads ({today}):** `{today_count} Movies`\n"
            f" **Total Cataloged:** `{len(DB.get('catalog', {}))} Files`\n"
            f" **Duplicates Blocked:** `{len(DB.get('duplicates', []))} Files`\n"
            ""
        )
        await event.respond(status_msg)

    # --- Custom Thumbnail Commands ---
    @bot.on(events.NewMessage(pattern=r'(?i)^/setthumb$', outgoing=True))
    async def setthumb_cmd(event):
        reply = await event.get_reply_message()
        if reply and reply.photo:
            await bot.download_media(reply.photo, file=THUMB_PATH)
            await event.respond(" **Custom Thumbnail Poster သတ်မှတ်လိုက်ပါပြီ!**")
        else:
            await event.respond(" Thumbnail သတ်မှတ်ရန် ပုံကို Reply ပြန်ပြီး `/setthumb` ဟု ရိုက်ပါ။")

    @bot.on(events.NewMessage(pattern=r'(?i)^/delthumb$', outgoing=True))
    async def delthumb_cmd(event):
        if os.path.exists(THUMB_PATH):
            os.remove(THUMB_PATH)
            await event.respond(" **Custom Thumbnail ဖျက်ပြီးပါပြီ (Auto Screenshot Mode သို့ ရောက်ရှိသွားပါပြီ)။**")
        else:
            await event.respond(" Custom Thumbnail မရှိသေးပါ။")

    # --- Set Log Channel Command ---
    @bot.on(events.NewMessage(pattern=r'(?i)^/setlog (.+)', outgoing=True))
    async def setlog_cmd(event):
        log_id = event.pattern_match.group(1).strip()
        try:
            DB["log_channel"] = int(log_id) if (log_id.startswith('-') or log_id.isdigit()) else log_id
            save_db()
            await event.respond(f" **Admin Log Channel သတ်မှတ်ပြီးပါပြီ:** `{DB['log_channel']}`")
        except Exception as e:
            await event.respond(f" Log Channel သတ်မှတ်၍ မရပါ: `{e}`")

    # --- Set Replace Link Command ---
    @bot.on(events.NewMessage(pattern=r'(?i)^/replacelink (.+)', outgoing=True))
    async def replacelink_cmd(event):
        link = event.pattern_match.group(1).strip()
        DB["replace_link"] = link
        save_db()
        await event.respond(f" **Link Auto-Replacer သတ်မှတ်ပြီးပါပြီ:** `{link}`")

    # --- Add Source Command ---
    @bot.on(events.NewMessage(pattern=r'(?i)^/add (.+)', outgoing=True))
    async def add_cmd(event):
        raw_input = event.pattern_match.group(1).strip()
        await event.respond(f" **Link အား စစ်ဆေး၍ Join နေပါသည်...**\n`{raw_input}`")
        
        try:
            identifier, title = await resolve_and_join(raw_input)
            src_key = str(identifier)
            
            if src_key not in DB["sources"]:
                DB["sources"].append(src_key)
                save_db()
                await event.respond(
                    f" **Source ထည့်သွင်းခြင်း အောင်မြင်ပါသည်!**\n"
                    f"\n"
                    f" **Title:** `{title}`\n"
                    f" **Source:** `{src_key}`"
                )
                asyncio.create_task(clone_old_videos(src_key))
            else:
                await event.respond(" ဤ Source သည် စာရင်းထဲတွင် ရှိပြီးသား ဖြစ်ပါသည်။")
        except Exception as e:
            await event.respond(f" Source ထည့်၍ မရပါ: `{e}`")

    # --- Delete Source Command ---
    @bot.on(events.NewMessage(pattern=r'(?i)^/del (.+)', outgoing=True))
    async def del_cmd(event):
        raw_input = event.pattern_match.group(1).strip()
        found = False
        for src in list(DB["sources"]):
            if raw_input in src or src in raw_input:
                DB["sources"].remove(src)
                found = True
        
        if found:
            save_db()
            await event.respond(f" **Source ကို စာရင်းမှ ဖျက်ထုတ်ပြီးပါပြီ:** `{raw_input}`")
        else:
            await event.respond(" စာရင်းထဲတွင် ရှာမတွေ့ပါ။")

    # --- List Sources Command ---
    @bot.on(events.NewMessage(pattern=r'(?i)^/sources$', outgoing=True))
    async def sources_cmd(event):
        if not DB.get("sources"):
            await event.respond(" **လက်ရှိ ချိတ်ဆက်ထားသော Source မရှိသေးပါ။**")
            return
        
        msg = " **လက်ရှိ အလုပ်လုပ်နေသော ACTIVE SOURCES:**\n\n"
        for idx, src in enumerate(DB["sources"], 1):
            msg += f"{idx}. `{src}`\n"
        await event.respond(msg)

    # --- Filter Setup Command ---
    @bot.on(events.NewMessage(pattern=r'(?i)^/filter (.+)', outgoing=True))
    async def set_filter_cmd(event):
        mode = event.pattern_match.group(1).strip().lower()
        if mode in ["all", "video", "document"]:
            DB["media_filter"] = mode
            save_db()
            await event.respond(f" **Media Filter Mode ကို ပြောင်းလဲလိုက်ပါပြီ:** `{mode.upper()}`")
        else:
            await event.respond(" `/filter all` သို့မဟုတ် `/filter video` သို့မဟုတ် `/filter document` ဟု သုံးပါ။")

    # --- Header / Footer / Watermark Commands ---
    @bot.on(events.NewMessage(pattern=r'(?i)^/header (.+)', outgoing=True))
    async def set_header_cmd(event):
        DB["header"] = event.pattern_match.group(1).strip()
        save_db()
        await event.respond(f" **Header Text ပြောင်းလဲပြီးပါပြီ:**\n{DB['header']}")

    @bot.on(events.NewMessage(pattern=r'(?i)^/footer (.+)', outgoing=True))
    async def set_footer_cmd(event):
        DB["footer"] = event.pattern_match.group(1).strip()
        save_db()
        await event.respond(f" **Footer Text ပြောင်းလဲပြီးပါပြီ:**\n{DB['footer']}")

    @bot.on(events.NewMessage(pattern=r'(?i)^/watermark (.+)', outgoing=True))
    async def set_watermark_cmd(event):
        DB["watermark"] = event.pattern_match.group(1).strip()
        save_db()
        await event.respond(f" **Watermark Text ပြောင်းလဲပြီးပါပြီ:**\n{DB['watermark']}")

    # --- Set Target Channel Command ---
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
            await event.respond(f" **Target Channel သတ်မှတ်ပြီးပါပြီ:** `{DB['target_channel']}`")
        except Exception as e:
            await event.respond(f" Target Channel သတ်မှတ်ရာတွင် အဆင်မပြေပါ: `{e}`")

    # --- Join Command ---
    @bot.on(events.NewMessage(pattern=r'(?i)^/join (.+)', outgoing=True))
    async def join_cmd(event):
        link = event.pattern_match.group(1).strip()
        try:
            _, title = await resolve_and_join(link)
            await event.respond(f" **အောင်မြင်စွာ Join ပြီးပါပြီ:** {title}")
        except Exception as e:
            await event.respond(f" Join ရန် အဆင်မပြေပါ: `{e}`")

    # --- Search Catalog Command ---
    @bot.on(events.NewMessage(pattern=r'(?i)^/search (.+)', outgoing=True))
    async def search_cmd(event):
        query = event.pattern_match.group(1).strip().lower()
        results = [v for k, v in DB["catalog"].items() if query in k]

        if not results:
            await event.respond(" ရှာဖွေမှုရလဒ် မရှိပါ။")
            return

        msg = " **ရှာဖွေတွေ့ရှိသော ရုပ်ရှင်မှတ်တမ်းများ:**\n\n"
        for res in results[:15]:
            msg += f" [{res['title']}]({res['link']})\n"
        await event.respond(msg, link_preview=False)

    # --- Database Backup Command ---
    @bot.on(events.NewMessage(pattern=r'(?i)^/backup$', outgoing=True))
    async def backup_cmd(event):
        save_db()
        await event.respond(file=DB_FILE, caption=" **Database Backup File**")

    # --- Toggle Engine Command ---
    @bot.on(events.NewMessage(pattern=r'(?i)^/toggle$', outgoing=True))
    async def toggle_cmd(event):
        DB["status"] = "OFF" if DB.get("status") == "ON" else "ON"
        save_db()
        await event.respond(f" **Engine Status:** `{DB['status']}`")

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
                elif chat and str(chat.id) == src:
                    is_in_list = True

            if is_in_list and (event.message.video or event.message.document):
                caption = build_caption(event.message.text)
                await safe_upload(event.message, caption)
        except Exception:
            pass

    await bot.run_until_disconnected()

if __name__ == '__main__':
    Thread(target=run_web).start()
    asyncio.run(main())
