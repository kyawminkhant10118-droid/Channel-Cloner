import os
import json
import asyncio
from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession

# --- CONFIGURATION ---
API_ID = 38078790
API_HASH = 'c1b7e324a99544d7a9229ff5324af362'
SESSION_STRING = os.environ.get("SESSION_STRING")

DB_FILE = "bot_config.json"

def load_config():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {
        "target": None,
        "sources": [],
        "active": True
    }

def save_config(cfg):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=4)
    except:
        pass

config = load_config()

bot = TelegramClient(
    StringSession(SESSION_STRING), 
    API_ID, 
    API_HASH,
    connection_retries=10,
    retry_delay=2
)

async def main():
    await bot.start()
    print(" CLEAN & PRACTICAL BOT ONLINE ")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./](start|help)$'))
    async def help_cmd(event):
        msg = (
            " **BOT CONTROL PANEL**\n"
            "\n"
            f" Target: `{config.get('target') or 'Not Set'}`\n"
            f" Sources: `{len(config.get('sources', []))}` active\n"
            f" Status: `{'ACTIVE' if config.get('active') else 'PAUSED'}`\n\n"
            "**Commands:**\n"
            " `/settarget <ID>` - ပို့မယ့်ချန်နယ်သတ်မှတ်ရန်\n"
            " `/addsource <ID/Link>` - ဖမ်းမယ့်ချန်နယ်ထည့်ရန်\n"
            " `/delsource <ID/Link>` - ချန်နယ်ဖြုတ်ရန်\n"
            " `/sources` - ထည့်ထားသောချန်နယ်များကြည့်ရန်\n"
            " `/toggle` - အလုပ်လုပ်ခြင်း ဖွင့်/ပိတ်\n"
            " `/status` - အခြေအနေစစ်ဆေးရန်"
        )
        await event.respond(msg)

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]settarget (.+)'))
    async def set_target(event):
        val = event.pattern_match.group(1).strip()
        target = int(val) if val.lstrip('-').isdigit() else val
        config["target"] = target
        save_config(config)
        await event.respond(f" **Target ချန်နယ်ကို သတ်မှတ်ပြီးပါပြီ:** `{target}`")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]addsource (.+)'))
    async def add_source(event):
        src = event.pattern_match.group(1).strip()
        if src not in config["sources"]:
            config["sources"].append(src)
            save_config(config)
            await event.respond(f" **Source အသစ်ထည့်ပြီးပါပြီ:** `{src}`")
        else:
            await event.respond(" ဒီ Source က ရှိပြီးသားပါ။")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]delsource (.+)'))
    async def del_source(event):
        src = event.pattern_match.group(1).strip()
        if src in config["sources"]:
            config["sources"].remove(src)
            save_config(config)
            await event.respond(f" **Source ကို ဖယ်ရှားလိုက်ပါပြီ:** `{src}`")
        else:
            await event.respond(" ဒီ Source ကို ရှာမတွေ့ပါ။")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]sources$'))
    async def list_sources(event):
        if not config["sources"]:
            await event.respond(" ထည့်ထားသော Source ချန်နယ် မရှိသေးပါ။")
            return
        text = " **Active Sources:**\n"
        for i, s in enumerate(config["sources"], 1):
            text += f"{i}. `{s}`\n"
        await event.respond(text)

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]toggle$'))
    async def toggle_bot(event):
        config["active"] = not config.get("active", True)
        save_config(config)
        state = "ACTIVE " if config["active"] else "PAUSED "
        await event.respond(f" Bot အခြေအနေ: `{state}`")

    @bot.on(events.NewMessage(pattern=r'(?i)^[./]status$'))
    async def status_check(event):
        await event.respond(
            f" **Bot Status:**\n"
            f" Working: `{'Yes' if config.get('active') else 'No'}`\n"
            f" Target: `{config.get('target')}`\n"
            f" Sources Count: `{len(config.get('sources', []))}`"
        )

    # --- REAL-TIME INTERCEPTOR WITH LIVE VISUAL FEEDBACK ---
    @bot.on(events.NewMessage())
    async def handle_messages(event):
        if not config.get("active", True) or not config.get("sources") or not config.get("target"):
            return

        try:
            chat = await event.get_chat()
            if not chat: 
                return

            chat_id = str(chat.id)
            username = f"@{chat.username.lower()}" if chat.username else None

            # Check if message is from configured sources
            matched = any(
                str(s).lower() == chat_id or (username and str(s).lower() == username)
                for s in config["sources"]
            )

            if matched and (event.video or event.document):
                # မျက်စိရှေ့မှာ တကယ်အလုပ်လုပ်နေကြောင်း မြင်ရအောင် Status Message တစ်ခု အရင်ပြမယ်
                status_msg = await event.respond(" **[1/2] ဖိုင်ကို ရယူနေသည် (Downloading)...**")

                target = config["target"]
                caption = event.text or ""

                # Target ထဲသို့ တိုက်ရိုက် လွှဲပြောင်းတင်မည်
                await bot.send_file(
                    target, 
                    event.media, 
                    caption=caption,
                    supports_streaming=True
                )

                # ပြီးသွားရင် Status ကို အောင်မြင်ကြောင်း ပြောင်းမည်
                await status_msg.edit(" **[2/2] Target သို့ အောင်မြင်စွာ တင်ပြီးပါပြီ!**")
                await asyncio.sleep(3)
                await status_msg.delete() # ၃ စက္ကန့်ကြာရင် Message ကို ပြန်ဖျက်မည် (ချန်နယ်မရှုပ်အောင်)

        except Exception as e:
            print(f"Error: {e}")

    await bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
