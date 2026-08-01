import os
import re
import sys
import json
import time
import psutil
import asyncio
import traceback
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
    return "Ultra Next-Level Engine v4.0 (High-Speed & Detailed Status) is Live!"

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

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[-] DB Read Error: {e}")
    return {
        "target_channel": -1003351682369,
        "sources": [],
        "priority_sources": [],
        "duplicates": [],
        "catalog": {},
        "daily_stats": {},
        "header": "",
        "watermark": "📥 **Uploaded by Our Channel**",
        "footer": "",
        "media_filter": "all",  # 'all', 'video', 'document'
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

# --- Telegram Official Bot Command Menu Registration ---
async def setup_bot_command_menu():
    try:
        commands = [
            types.BotCommand(command="start", description="📖 Main Command Menu"),
            types.BotCommand(command="add", description="📥 Add Source (Link/Username)"),
            types.BotCommand(command="sources", description="📡 List Active Sources"),
            types.BotCommand(command="status", description="📊 Hardware & Engine Diagnostics"),
            types.BotCommand(command="filter", description="🎞 Set Filter (all/video/document)"),
            types.BotCommand(command="settarget", description="🎯 Set Target Channel ID"),
            types.BotCommand(command="search", description="🔍 Search Cataloged Movies"),
            types.BotCommand(command="toggle", description="⚙️ Pause / Resume Engine"),
            types.BotCommand(command="backup", description="📦 Download Database Backup")
        ]
        await bot(functions.bots.SetBotCommandsRequest(
            scope=types.BotCommandScopeDefault(),
            lang_code='en',
            commands=commands
        ))
        print("[+] Official Telegram Bot Command Menu Registered Successfully!")
    except Exception as e:
        print(f"[!] Command Menu Registration skipped: {e}")

# --- Session Refresher Service ---
async def session_refresher():
    while True:
        try:
            await bot.get_me()
            print("[+] Session Keep-Alive Ping Sent.")
        except Exception:
            pass
        await asyncio.sleep(1800)

# --- Format Caption Helper ---
def build_caption(original_text):
    caption = original_text or ""
    if DB.get("clean_ads", True):
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

# --- Anti-Flood & High-Speed Restricted Bypass Upload Processor ---
async def safe_upload(message, caption):
    target = DB.get("target_channel")
    if not target:
        print("[-] Target Channel စာရင်း မရှိသေးပါ။ /settarget ဖြင့် အရင် သတ်မှတ်ပေးပါ။")
        return False

    # Media Filter Check
    media_mode = DB.get("media_filter", "all")
    if media_mode == "video" and not message.video:
        return False
    elif media_mode == "document" and not (message.document and not message.video):
        return False

    file_id = None
    if message.video or message.document:
        file_id = str(message.media.document.id)

    # Duplicate Prevention Check
    if file_id and file_id in DB.get("duplicates", []):
        print(f"[-] Skipped Duplicate File ID: {file_id}")
        return False

    is_noforward = getattr(message, 'noforward', False) or getattr(getattr(message, 'chat', None), 'noforward', False)

    while True:
        try:
            sent_msg = None
            
            # 1. Direct Forward Send (If not restricted)
            if not is_noforward:
                try:
                    sent_msg = await bot.send_file(target, message.media, caption=caption.strip())
                except Exception as direct_err:
                    print(f"[!] Direct Send Blocked, Switching to Fast Download Mode...")
                    is_noforward = True

            # 2. High-Speed Restricted Bypass Mode (Optimized 512KB Chunking)
            if is_noforward or not sent_msg:
                os.makedirs(TEMP_DIR, exist_ok=True)
                print("[🚀] High-Speed Downloading restricted video to local buffer...")
                
                temp_path = await bot.download_media(message, file=TEMP_DIR)
                
                try:
                    print("[⚡] High-Speed Re-uploading to Target Channel...")
                    sent_msg = await bot.send_file(
                        target, 
                        temp_path, 
                        caption=caption.strip(),
                        part_size_kb=512  # Maximum transfer chunk size for fastest speed
                    )
                finally:
                    # Clean up local temp file immediately
                    if temp_path and os.path.exists(temp_path):
                        os.remove(temp_path)
                        print("[🗑] Temp file cleaned.")

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
                print(f"[+] Successfully Uploaded: {title}")
                return True

        except errors.FloodWaitError as e:
            print(f"[!] [Anti-Flood] Limit reached. Waiting for {e.seconds} seconds...")
            await asyncio.sleep(e.seconds + 5)
        except Exception as upload_err:
            print(f"[-] Upload Failed Error: {upload_err}")
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
    print("🚀 ULTRA ENGINE v4.0 (HIGH-SPEED & STATUS) IS LIVE!")
    print("==================================================")
    
    # Auto Set Command Menu & Session Ping
    await setup_bot_command_menu()
    asyncio.create_task(session_refresher())

    # --- Start & Main Help Menu Command ---
    @bot.on(events.NewMessage(pattern=r'(?i)^/start$', outgoing=True))
    async def start_cmd(event):
        target_info = DB.get("target_channel", "မသတ်မှတ်ရသေးပါ")
        menu_text = (
            "👑 **ULTRA NEXT-LEVEL USERBOT ENGINE v4.0** 👑\n"
            "*(High-Speed Restricted Bypass & Detailed Diagnostics)*\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 **Target Channel:** `{target_info}`\n"
            f"🎞 **Media Filter:** `{DB.get('media_filter', 'all').upper()}`\n"
            f"📡 **Active Sources:** `{len(DB.get('sources', []))}` Channels\n\n"
            
            "📥 **1. SOURCE & LINK COMMANDS:**\n"
            "• `/add <Link/Username>` - Source ထည့်ရန် (Auto Join & Fast Clone)\n"
            "• `/del <Link/Username>` - Source စာရင်းမှ ပြန်ထုတ်ရန်\n"
            "• `/sources` - ထည့်ထားသော Source ချန်နယ်များ စာရင်းကြည့်ရန်\n"
            "• `/join <Link>` - Channel / Group သို့ Auto Join ရန်\n\n"

            "⚙️ **2. CAPTION & FORMATTING:**\n"
            "• `/settarget <ID/Username>` - Target Channel ပြောင်းရန်\n"
            "• `/watermark <စာသား>` - ဗီဒီယို စာသား ပြောင်းရန်\n"
            "• `/header <စာသား>` - ဗီဒီယို ထိပ်ဆုံး စာသား သတ်မှတ်ရန်\n"
            "• `/footer <စာသား>` - ဗီဒီယို အောက်ဆုံး စာသား သတ်မှတ်ရန်\n"
            "• `/filter <all|video|document>` - တင်မည့် ဖိုင်အမျိုးအစား သတ်မှတ်ရန်\n\n"

            "📊 **3. CONTROL & MONITORING:**\n"
            "• `/search <နာမည်>` - Database ထဲ ရုပ်ရှင်ပြန်ရှာရန်\n"
            "• `/status` - Hardware & Server အသေးစိတ် စစ်ဆေးရန်\n"
            "• `/backup` - DB ဖိုင် ထုတ်ယူရန်\n"
            "• `/toggle` - Bot မောင်းနှင်မှု ခဏရပ်/ပြန်ဖွင့်ရန်\n"
            "• `/clear` - Source စာရင်း အကုန် ရှင်းထုတ်ရန်"
        )
        await event.respond(menu_text)

    # --- Ultra Detailed Status Dashboard Command ---
    @bot.on(events.NewMessage(pattern=r'(?i)^/status$', outgoing=True))
    async def status_cmd(event):
        # Time calculations
        uptime_sec = int(time.time() - start_time)
        hours, remainder = divmod(uptime_sec, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s"

        # Hardware metrics
        vram = psutil.virtual_memory()
        ram_used_mb = round(vram.used / (1024 * 1024), 2)
        ram_total_mb = round(vram.total / (1024 * 1024), 2)
        ram_pct = vram.percent

        cpu_pct = psutil.cpu_percent(interval=0.5)

        disk = psutil.disk_usage('.')
        disk_free_gb = round(disk.free / (1024 * 1024 * 1024), 2)
        disk_total_gb = round(disk.total / (1024 * 1024 * 1024), 2)

        # Temp Storage Check
        temp_size_mb = 0
        if os.path.exists(TEMP_DIR):
            for f in os.listdir(TEMP_DIR):
                fp = os.path.join(TEMP_DIR, f)
                if os.path.isfile(fp):
                    temp_size_mb += os.path.getsize(fp)
        temp_size_mb = round(temp_size_mb / (1024 * 1024), 2)

        # DB Statistics
        today = datetime.now().strftime("%Y-%m-%d")
        today_count = DB["daily_stats"].get(today, 0)
        total_catalog = len(DB.get("catalog", {}))
        total_duplicates = len(DB.get("duplicates", []))
        total_sources = len(DB.get("sources", []))

        status_msg = (
            "📊 **ULTRA ENGINE HARDWARE & DIAGNOSTICS v4.0**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚡ **ENGINE STATUS & CONFIG:**\n"
            f"• **System State:** `{DB.get('status', 'ON')}`\n"
            f"• **Target Channel:** `{DB.get('target_channel', 'Not Set')}`\n"
            f"• **Media Mode:** `{DB.get('media_filter', 'all').upper()}`\n"
            f"• **Ad-Cleaner:** `{'ENABLED' if DB.get('clean_ads') else 'DISABLED'}`\n"
            f"• **Active Sources:** `{total_sources} Channels`\n\n"

            "🖥 **RAILWAY HARDWARE MONITOR:**\n"
            f"• **CPU Utilization:** `{cpu_pct}%`\n"
            f"• **RAM Usage:** `{ram_used_mb} MB / {ram_total_mb} MB ({ram_pct}%)`\n"
            f"• **Disk Storage Free:** `{disk_free_gb} GB / {disk_total_gb} GB`\n"
            f"• **Temp File Buffer:** `{temp_size_mb} MB`\n"
            f"• **Engine Uptime:** `{uptime_str}`\n\n"

            "📈 **DATABASE & UPLOAD STATISTICS:**\n"
            f"• **Today Uploads ({today}):** `{today_count} Movies`\n"
            f"• **Total Cataloged Movies:** `{total_catalog} Files`\n"
            f"• **Duplicates Blocked:** `{total_duplicates} Files`\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await event.respond(status_msg)

    # --- Smart Add Command ---
    @bot.on(events.NewMessage(pattern=r'(?i)^/add (.+)', outgoing=True))
    async def add_cmd(event):
        raw_input = event.pattern_match.group(1).strip()
        await event.respond(f"⏳ **Link အား စစ်ဆေး၍ Join နေပါသည်...**\n`{raw_input}`")
        
        try:
            identifier, title = await resolve_and_join(raw_input)
            src_key = str(identifier)
            
            if src_key not in DB["sources"]:
                DB["sources"].append(src_key)
                save_db()
                await event.respond(
                    f"✅ **Source ထည့်သွင်းခြင်း အောင်မြင်ပါသည်!**\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"📌 **Title:** `{title}`\n"
                    f"🆔 **Source:** `{src_key}`\n\n"
                    f"⚡ *Restricted ဖိုင်များပါ High-Speed ဖြင့် အလိုအလျောက် Clone လုပ်ပေးနေပါပြီ...*"
                )
                asyncio.create_task(clone_old_videos(src_key))
            else:
                await event.respond("⚠️ ဤ Source သည် စာရင်းထဲတွင် ရှိပြီးသား ဖြစ်ပါသည်။")
        except Exception as e:
            await event.respond(f"❌ Source ထည့်၍ မရပါ: `{e}`")

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
            await event.respond(f"🗑 **Source ကို စာရင်းမှ ဖျက်ထုတ်ပြီးပါပြီ:** `{raw_input}`")
        else:
            await event.respond("❌ စာရင်းထဲတွင် ရှာမတွေ့ပါ။")

    # --- List Sources Command ---
    @bot.on(events.NewMessage(pattern=r'(?i)^/sources$', outgoing=True))
    async def sources_cmd(event):
        if not DB.get("sources"):
            await event.respond("📡 **လက်ရှိ ချိတ်ဆက်ထားသော Source မရှိသေးပါ။**")
            return
        
        msg = "📡 **လက်ရှိ အလုပ်လုပ်နေသော ACTIVE SOURCES:**\n━━━━━━━━━━━━━━━━━━━━━━\n"
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
            await event.respond(f"🎞 **Media Filter Mode ကို ပြောင်းလဲလိုက်ပါပြီ:** `{mode.upper()}`")
        else:
            await event.respond("⚠️ `/filter all` သို့မဟုတ် `/filter video` သို့မဟုတ် `/filter document` ဟု သုံးပါ။")

    # --- Header / Footer / Watermark Commands ---
    @bot.on(events.NewMessage(pattern=r'(?i)^/header (.+)', outgoing=True))
    async def set_header_cmd(event):
        DB["header"] = event.pattern_match.group(1).strip()
        save_db()
        await event.respond(f"⬆️ **Header Text ပြောင်းလဲပြီးပါပြီ:**\n{DB['header']}")

    @bot.on(events.NewMessage(pattern=r'(?i)^/footer (.+)', outgoing=True))
    async def set_footer_cmd(event):
        DB["footer"] = event.pattern_match.group(1).strip()
        save_db()
        await event.respond(f"⬇️ **Footer Text ပြောင်းလဲပြီးပါပြီ:**\n{DB['footer']}")

    @bot.on(events.NewMessage(pattern=r'(?i)^/watermark (.+)', outgoing=True))
    async def set_watermark_cmd(event):
        DB["watermark"] = event.pattern_match.group(1).strip()
        save_db()
        await event.respond(f"📝 **Watermark Text ပြောင်းလဲပြီးပါပြီ:**\n{DB['watermark']}")

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
            await event.respond(f"🎯 **Target Channel သတ်မှတ်ပြီးပါပြီ:** `{DB['target_channel']}`")
        except Exception as e:
            await event.respond(f"❌ Target Channel သတ်မှတ်ရာတွင် အဆင်မပြေပါ: `{e}`")

    @bot.on(events.NewMessage(pattern=r'(?i)^/join (.+)', outgoing=True))
    async def join_cmd(event):
        link = event.pattern_match.group(1).strip()
        try:
            _, title = await resolve_and_join(link)
            await event.respond(f"✅ **အောင်မြင်စွာ Join ပြီးပါပြီ:** {title}")
        except Exception as e:
            await event.respond(f"❌ Join ရန် အဆင်မပြေပါ: `{e}`")

    @bot.on(events.NewMessage(pattern=r'(?i)^/search (.+)', outgoing=True))
    async def search_cmd(event):
        query = event.pattern_match.group(1).strip().lower()
        results = [v for k, v in DB["catalog"].items() if query in k]

        if not results:
            await event.respond("❌ ရှာဖွေမှုရလဒ် မရှိပါ။")
            return

        msg = "🔍 **ရှာဖွေတွေ့ရှိသော ရုပ်ရှင်မှတ်တမ်းများ:**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        for res in results[:15]:
            msg += f"🎬 [{res['title']}]({res['link']})\n"
        await event.respond(msg, link_preview=False)

    @bot.on(events.NewMessage(pattern=r'(?i)^/backup$', outgoing=True))
    async def backup_cmd(event):
        save_db()
        await event.respond(file=DB_FILE, caption="📦 **Database Backup File**")

    @bot.on(events.NewMessage(pattern=r'(?i)^/clear$', outgoing=True))
    async def clear_cmd(event):
        DB["sources"] = []
        save_db()
        await event.respond("🗑 **Sources စာရင်း အားလုံးကို ရှင်းထုတ်လိုက်ပါပြီ။**")

    @bot.on(events.NewMessage(pattern=r'(?i)^/toggle$', outgoing=True))
    async def toggle_cmd(event):
        DB["status"] = "OFF" if DB.get("status") == "ON" else "ON"
        save_db()
        await event.respond(f"⚙️ **Engine Status:** `{DB['status']}`")

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
