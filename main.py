import os
import re
import json
import time
import logging
import psutil
import asyncio
from threading import Thread
from flask import Flask

# Suppress Werkzeug logs
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# --- Web Server (Railway Keep-Alive) ---
app = Flask('')

@app.route('/')
def home():
    return " ULTRA PRO USERBOT ENGINE v6.0 is Live!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

from telethon import TelegramClient, events, errors, functions, types, Button
from telethon.sessions import StringSession

# --- Credentials ---
API_ID = 38078790
API_HASH = 'c1b7e324a99544d7a9229ff5324af362'
SESSION_STRING = os.environ.get("SESSION_STRING")

DB_FILE = "ultimate_db_v6.json"

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {
        "target_channel": -1003351682369,
        "log_channel": None,
        "sources": [],
        "custom_thumb": None,
        "link_replacer": "",
        "header": "",
        "footer": "",
        "watermark": "",
        "media_filter": "all",
        "status": "ON",
        "file_database": []
    }

def save_db():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(DB, f, ensure_ascii=False, indent=4)
    except:
        pass

DB = load_db()
start_time = time.time()

bot = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

async def main():
    await bot.start()
    print("==================================================")
    print(" ULTRA PRO USERBOT ENGINE v6.0 LIVE ")
    print("==================================================")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./](start|help)$'))
    async def start_cmd(event):
        thumb_mode = "AUTO SCREENSHOT MODE" if not DB.get("custom_thumb") else "CUSTOM THUMBNAIL"
        log_c = DB.get("log_channel") or "None"
        target_c = DB.get("target_channel")
        replacer = DB.get("link_replacer") or "None"
        status_val = DB.get("status", "ON")

        menu_text = (
            "**ULTRA PRO USERBOT ENGINE v6.0**\n"
            "*(Production Grade & Smart Bypass)*\n\n"
            f"Target Channel: `{target_c}`\n"
            f"Log Channel: `{log_c}`\n"
            f"Custom Thumb: `{thumb_mode}`\n"
            f"Link Replacer: `{replacer}`\n"
            f"Status: `{status_val}`\n\n"
            "**1. ADVANCED FEATURES:**\n"
            "/setthumb - ပုံ ပို့ပေးပြီး Custom Poster သတ်မှတ်ရန်\n"
            "/delthumb - Auto Screenshot စနစ် ပြန်သုံးရန်\n"
            "/setlog <ID> - Error/Upload Log ကြည့်မည့် Channel\n"
            "/replacelink <Link> - Link များ Auto အစားထိုးရန်\n"
            "/filter <all/video/document> - Media အမျိုးအစား သတ်မှတ်ရန်\n"
            "/header <စာသား> | /footer <စာသား> | /watermark <စာသား> - စာသားများ ပြင်ဆင်ရန်\n\n"
            "**2. SOURCE & TARGET COMMANDS:**\n"
            "/add <Link/Username> - Source ထည့်ရန်\n"
            "/del <Link/Username> - Source ပြန်ဖြုတ်ရန်\n"
            "/sources - Source ချန်နယ်များ စာရင်းကြည့်ရန်\n"
            "/settarget <ID/Username> - Target Channel ပြောင်းရန်\n"
            "/join <Link> - Channel အလိုအလျောက် Join ရန်\n\n"
            "**3. CONTROL & MONITORING:**\n"
            "/status - Hardware & Server စစ်ဆေးရန်\n"
            "/search <နာမည်> - Database ထဲ ရုပ်ရှင်ပြန်ရှာရန်\n"
            "/backup - DB ဖိုင် ထုတ်ယူရန်\n"
            "/toggle - Bot မောင်းနှင်မှု ခဏရပ်/ပြန်ဖွင့်ရန်"
        )
        await event.respond(menu_text)

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]toggle$'))
    async def toggle_cmd(event):
        current = DB.get("status", "ON")
        DB["status"] = "OFF" if current == "ON" else "ON"
        save_db()
        await event.respond(f" **Bot Status Toggled:** `{DB['status']}`")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]setthumb$'))
    async def setthumb_cmd(event):
        if event.is_reply:
            reply = await event.get_reply_message()
            if reply.media:
                path = await bot.download_media(reply, file="custom_thumb_v6.jpg")
                DB["custom_thumb"] = path
                save_db()
                await event.respond(" **Custom Thumbnail successfully set!**")
                return
        await event.respond(" Please reply to an image with `/setthumb`.")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]delthumb$'))
    async def delthumb_cmd(event):
        DB["custom_thumb"] = None
        if os.path.exists("custom_thumb_v6.jpg"):
            os.remove("custom_thumb_v6.jpg")
        save_db()
        await event.respond(" **Reverted to AUTO SCREENSHOT MODE.**")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]setlog (.+)'))
    async def setlog_cmd(event):
        val = event.pattern_match.group(1).strip()
        DB["log_channel"] = val if val.lower() != "none" else None
        save_db()
        await event.respond(f" **Log Channel updated to:** `{val}`")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]replacelink (.+)'))
    async def replacelink_cmd(event):
        link = event.pattern_match.group(1).strip()
        DB["link_replacer"] = link
        save_db()
        await event.respond(f" **Link Replacer set to:** `{link}`")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]filter (all|video|document)$'))
    async def filter_cmd(event):
        f_type = event.pattern_match.group(1).lower()
        DB["media_filter"] = f_type
        save_db()
        await event.respond(f" **Media Filter updated to:** `{f_type.upper()}`")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]header (.+)'))
    async def header_cmd(event):
        DB["header"] = event.pattern_match.group(1).strip()
        save_db()
        await event.respond(" **Header updated successfully!**")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]footer (.+)'))
    async def footer_cmd(event):
        DB["footer"] = event.pattern_match.group(1).strip()
        save_db()
        await event.respond(" **Footer updated successfully!**")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]watermark (.+)'))
    async def watermark_cmd(event):
        DB["watermark"] = event.pattern_match.group(1).strip()
        save_db()
        await event.respond(" **Watermark updated successfully!**")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]add (.+)'))
    async def add_src(event):
        src = event.pattern_match.group(1).strip()
        if src not in DB["sources"]:
            DB["sources"].append(src)
            save_db()
            await event.respond(f" **Source added:** `{src}`")
        else:
            await event.respond(" Source already exists.")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]del (.+)'))
    async def del_src(event):
        src = event.pattern_match.group(1).strip()
        if src in DB["sources"]:
            DB["sources"].remove(src)
            save_db()
            await event.respond(f" **Source removed:** `{src}`")
        else:
            await event.respond(" Source not found.")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]sources$'))
    async def list_sources(event):
        if not DB["sources"]:
            await event.respond(" **No sources added yet.**")
            return
        msg = " **ACTIVE SOURCES:**\n"
        for i, s in enumerate(DB["sources"], 1):
            msg += f"{i}. `{s}`\n"
        await event.respond(msg)

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]settarget (.+)'))
    async def settarget_cmd(event):
        target = event.pattern_match.group(1).strip()
        try:
            if target.lstrip('-').isdigit():
                DB["target_channel"] = int(target)
            else:
                DB["target_channel"] = target
            save_db()
            await event.respond(f" **Target Channel updated to:** `{target}`")
        except Exception as e:
            await event.respond(f" Error: `{e}`")

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
            await event.respond(" **Successfully joined the channel/chat!**")
        except Exception as e:
            await event.respond(f" Join Error: `{e}`")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]status$'))
    async def status_cmd(event):
        cpu = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory().percent
        uptime = int(time.time() - start_time)
        h, rem = divmod(uptime, 3600)
        m, s = divmod(rem, 60)
        status_msg = (
            " **SERVER & HARDWARE STATUS v6.0**\n"
            f" CPU Usage: `{cpu}%`\n"
            f" RAM Usage: `{ram}%`\n"
            f" Uptime: `{h}h {m}m {s}s`\n"
            f" Bot Status: `{DB.get('status', 'ON')}`\n"
            f" Target: `{DB.get('target_channel')}`"
        )
        await event.respond(status_msg)

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]search (.+)'))
    async def search_cmd(event):
        query = event.pattern_match.group(1).strip().lower()
        results = [f for f in DB.get("file_database", []) if query in f.get("name", "").lower()]
        if not results:
            await event.respond(" No matching files found in database.")
            return
        msg = f" **Search Results for '{query}':**\n"
        for r in results[:10]:
            msg += f" {r.get('name')}\n"
        await event.respond(msg)

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]backup$'))
    async def backup_cmd(event):
        if os.path.exists(DB_FILE):
            await bot.send_file(event.chat_id, DB_FILE, caption=" **ULTRA PRO v6.0 Database Backup**")
        else:
            await event.respond(" Database file not found.")

    @bot.on(events.NewMessage())
    async def forwarder(event):
        if DB.get("status") == "OFF" or not DB.get("sources"):
            return
        try:
            chat = await event.get_chat()
            chat_id_str = str(chat.id)
            username = f"@{chat.username.lower()}" if chat.username else None
            
            matched = False
            for src in DB["sources"]:
                if src.lower() == chat_id_str or (username and src.lower() == username):
                    matched = True
                    break
            
            if matched:
                m_filter = DB.get("media_filter", "all")
                valid_media = False
                if m_filter == "all" and (event.video or event.document):
                    valid_media = True
                elif m_filter == "video" and event.video:
                    valid_media = True
                elif m_filter == "document" and event.document and not event.video:
                    valid_media = True
                    
                if valid_media:
                    fname = event.file.name if event.file and event.file.name else (event.text or "Media File")
                    DB.setdefault("file_database", []).append({"name": fname})
                    save_db()
                    
                    caption = event.text or ""
                    replacer = DB.get("link_replacer")
                    if replacer:
                        caption = re.sub(r'https?://t\.me/\S+', replacer, caption)
                        caption = re.sub(r'@\w+', replacer, caption)
                        
                    parts = []
                    if DB.get("header"): parts.append(DB["header"])
                    if caption: parts.append(f"**{caption}**")
                    if DB.get("watermark"): parts.append(DB["watermark"])
                    if DB.get("footer"): parts.append(DB["footer"])
                    final_caption = "\n\n".join(parts)
                    
                    target = DB.get("target_channel")
                    custom_thumb = DB.get("custom_thumb")
                    
                    os.makedirs("temp_v6", exist_ok=True)
                    if custom_thumb and os.path.exists(custom_thumb):
                        temp_path = await bot.download_media(event.message, file="temp_v6/")
                        try:
                            await bot.send_file(target, temp_path, caption=final_caption, thumb=custom_thumb, supports_streaming=True)
                        finally:
                            if temp_path and os.path.exists(temp_path):
                                os.remove(temp_path)
                    else:
                        await bot.send_file(target, event.media, caption=final_caption, supports_streaming=True)
        except Exception as e:
            log_c = DB.get("log_channel")
            if log_c:
                try:
                    await bot.send_message(log_c, f" Error: `{e}`")
                except:
                    pass

    await bot.run_until_disconnected()

if __name__ == '__main__':
    Thread(target=run_web).start()
    asyncio.run(main())
