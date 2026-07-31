import os
import re
import json
import asyncio
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait, RPCError

# Environment Variables Processing
API_ID_RAW = os.environ.get("API_ID", "").strip()
API_HASH = os.environ.get("API_HASH", "").strip()
SESSION_STRING = os.environ.get("SESSION_STRING", "").strip()
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_ID_RAW = os.environ.get("ADMIN_ID", "").strip()

# Validate essential env variables
if not all([API_ID_RAW, API_HASH, SESSION_STRING, BOT_TOKEN, ADMIN_ID_RAW]):
    print("❌ ERROR: Railway Environment Variables စုံလင်စွာ ထည့်သွင်းထားခြင်း မရှိပါ။")
    print("ကျေးဇူးပြု၍ API_ID, API_HASH, SESSION_STRING, BOT_TOKEN, ADMIN_ID များကို စစ်ဆေးပါ။")

API_ID = int(API_ID_RAW) if API_ID_RAW.isdigit() else 0
ADMIN_ID = int(ADMIN_ID_RAW) if ADMIN_ID_RAW.isdigit() else 0

DATA_FILE = "cloner_database.json"

# Database Manager
def load_db():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "clones": {},          # "src_id": "tgt_id"
        "replacements": {},    # "old": "new"
        "filters": {},         # "src_id": {"media_type": "all", "blacklist": [], "whitelist": [], "remove_links": False}
        "headers": {},         # "src_id": "header text"
        "footers": {}          # "src_id": "footer text"
    }

def save_db(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"[-] DB Save Error: {e}")

db = load_db()

# Pyrogram Clients Setup (in_memory=True fixes Railway session database crashes)
userbot = Client(
    name="userbot_session",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING,
    in_memory=True
)

control_bot = Client(
    name="control_bot_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True
)

# Chat Resolver Helper
async def resolve_chat_id(chat_input: str):
    chat_input = str(chat_input).strip()
    if "/+" in chat_input or "/joinchat/" in chat_input:
        chat = await userbot.join_chat(chat_input)
        return chat.id
    if "t.me/" in chat_input:
        chat_input = chat_input.split("t.me/")[-1].replace("@", "").split("/")[0]
        chat_input = f"@{chat_input}"
    try:
        chat_input = int(chat_input)
    except ValueError:
        pass
    chat = await userbot.get_chat(chat_input)
    return chat.id

# Text Processing Engine
def process_text(text: str, src_id: str):
    if not text:
        return ""

    src_filter = db.get("filters", {}).get(src_id, {})
    
    # 1. Link Removal Engine
    if src_filter.get("remove_links", False):
        text = re.sub(r'https?://\S+|www\.\S+|t\.me/\S+', '', text)

    # 2. Text/Link Replacement Engine
    for old_val, new_val in db.get("replacements", {}).items():
        text = text.replace(old_val, new_val)

    # 3. Add Header & Footer
    header = db.get("headers", {}).get(src_id, "")
    footer = db.get("footers", {}).get(src_id, "")

    if header:
        text = f"{header}\n\n{text}"
    if footer:
        text = f"{text}\n\n{footer}"

    return text.strip()

# Content Filter Engine
def is_content_allowed(message, src_id: str) -> bool:
    src_filter = db.get("filters", {}).get(src_id, {})
    
    # Media Type Filter
    m_type = src_filter.get("media_type", "all")
    if m_type != "all":
        if m_type == "photo" and not message.photo:
            return False
        elif m_type == "video" and not message.video:
            return False
        elif m_type == "document" and not message.document:
            return False
        elif m_type == "audio" and not (message.audio or message.voice):
            return False

    text_to_check = message.text or message.caption or ""
    
    # Blacklist Check
    blacklist = src_filter.get("blacklist", [])
    for word in blacklist:
        if word.lower() in text_to_check.lower():
            return False

    # Whitelist Check
    whitelist = src_filter.get("whitelist", [])
    if whitelist:
        matched = any(word.lower() in text_to_check.lower() for word in whitelist)
        if not matched:
            return False

    return True

# Smart Forward/Copy Engine (Bypasses Protected/Restricted Content)
async def send_smart_copy(message, target_id: int, src_id: str):
    if not is_content_allowed(message, src_id):
        return

    text = message.text or message.caption or ""
    processed_caption = process_text(text, src_id)

    # Attempt 1: Standard Copy
    try:
        if message.text:
            await userbot.send_message(target_id, processed_caption)
        else:
            await message.copy(chat_id=target_id, caption=processed_caption)
        return
    except RPCError as e:
        print(f"[!] Standard copy failed ({e}). Attempting download/re-upload bypass...")

    # Attempt 2: Restricted Content Bypass (Download & Re-upload)
    file_path = None
    try:
        file_path = await message.download()
        if not file_path:
            return

        if message.photo:
            await userbot.send_photo(target_id, file_path, caption=processed_caption)
        elif message.video:
            await userbot.send_video(target_id, file_path, caption=processed_caption)
        elif message.document:
            await userbot.send_document(target_id, file_path, caption=processed_caption)
        elif message.audio:
            await userbot.send_audio(target_id, file_path, caption=processed_caption)
        elif message.voice:
            await userbot.send_voice(target_id, file_path, caption=processed_caption)
    except Exception as err:
        print(f"[-] Re-upload Bypass Failed: {err}")
    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

# Real-time Channel Listener
@userbot.on_message(filters.channel)
async def live_channel_listener(client, message):
    src_id = str(message.chat.id)
    clones = db.get("clones", {})
    if src_id in clones:
        target_id = int(clones[src_id])
        await send_smart_copy(message, target_id, src_id)

# UI Keyboards
def get_dashboard_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Active Pair များ", callback_data="cb_list"), InlineKeyboardButton("➕ Add Pair", callback_data="cb_add_help")],
        [InlineKeyboardButton("⚙️ Filter / Settings", callback_data="cb_filter_help"), InlineKeyboardButton("✏️ Text Replacements", callback_data="cb_replace_help")],
        [InlineKeyboardButton("🔄 Batch Clone (Old Posts)", callback_data="cb_batch_help"), InlineKeyboardButton("🗑️ Remove Pair", callback_data="cb_del_help")]
    ])

# Control Bot Handlers
@control_bot.on_message(filters.command("start") & filters.user(ADMIN_ID))
async def cmd_start(client, message):
    await message.reply_text(
        "⚡ **Telegram Ultimate Cloner Control Dashboard** ⚡\n\n"
        "အောက်ပါ Menu များမှတစ်ဆင့် Cloner Bot ကို လွယ်ကူစွာ ထိန်းချုပ်နိုင်ပါသည်။",
        reply_markup=get_dashboard_markup()
    )

@control_bot.on_callback_query(filters.user(ADMIN_ID))
async def callback_handler(client, query: CallbackQuery):
    data = query.data

    if data == "cb_list":
        clones = db.get("clones", {})
        if not clones:
            await query.answer("မည့်သည့် Channel မျှ မရှိသေးပါ။", show_alert=True)
            return
        msg = "📋 **Active Cloning Pairs:**\n\n"
        for src, tgt in clones.items():
            f_info = db.get("filters", {}).get(src, {})
            m_type = f_info.get("media_type", "all")
            msg += f"• `{src}` ➡️ `{tgt}` (Filter: `{m_type}`)\n"
        await query.message.edit_text(msg, reply_markup=get_dashboard_markup())

    elif data == "cb_add_help":
        await query.message.edit_text(
            "➕ **Channel ချိတ်ဆက်ရန် Command:**\n\n"
            "`/add <source> <target>`\n\n"
            "**ဥပမာ:**\n`/add @source_channel @target_channel`\n"
            "`/add https://t.me/src_chan https://t.me/tgt_chan`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="cb_main")]])
        )

    elif data == "cb_batch_help":
        await query.message.edit_text(
            "🔄 **Batch Clone (ယခင် ပို့စ်ဟောင်းများပါ ကူးယူရန်):**\n\n"
            "`/batch <source> <target>`\n\n"
            "*Restricted / Save ပိတ်ထားသော Channel ပို့စ်များကိုပါ Auto Download ပြုလုပ်၍ ပြန်တင်ပေးပါမည်။*",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="cb_main")]])
        )

    elif data == "cb_filter_help":
        await query.message.edit_text(
            "⚙️ **Filter နှင့် Settings Commands:**\n\n"
            "1. **Media Filter ရွေးရန်:**\n`/filter media <source> <all|photo|video|doc|audio>`\n\n"
            "2. **Blacklist Keyword ထည့်ရန်:**\n`/filter blacklist <source> <word>`\n\n"
            "3. **Link များ Auto ဖျက်ရန်:**\n`/filter removelinks <source> <on|off>`\n\n"
            "4. **Header / Footer တပ်ရန်:**\n`/setheader <source> <text>`\n`/setfooter <source> <text>`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="cb_main")]])
        )

    elif data == "cb_replace_help":
        repls = db.get("replacements", {})
        rep_txt = "\n".join([f"`{k}` ➡️ `{v}`" for k, v in repls.items()]) or "မရှိသေးပါ။"
        await query.message.edit_text(
            "✏️ **Text & Link Replacement:**\n\n"
            "`/replace <old_text> | <new_text>`\n\n"
            f"**လက်ရှိ ထည့်ထားသည်များ:**\n{rep_txt}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="cb_main")]])
        )

    elif data == "cb_del_help":
        await query.message.edit_text(
            "🗑️ **Pair ဖျက်ရန် Command:**\n\n`/del <source_channel>`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="cb_main")]])
        )

    elif data == "cb_main":
        await query.message.edit_text("⚡ **Telegram Ultimate Cloner Control Dashboard** ⚡", reply_markup=get_dashboard_markup())

# Admin Commands
@control_bot.on_message(filters.command("add") & filters.user(ADMIN_ID))
async def cmd_add(client, message):
    try:
        args = message.text.split()
        if len(args) < 3:
            await message.reply_text("❌ **Format အမှားပါဝင်နေပါသည်။**\n\n`/add <source> <target>`")
            return
        status_msg = await message.reply_text("🔄 Channel များကို စစ်ဆေးနေပါသည်...")
        
        src_id = str(await resolve_chat_id(args[1]))
        tgt_id = str(await resolve_chat_id(args[2]))
        
        db["clones"][src_id] = tgt_id
        save_db(db)
        
        await status_msg.edit_text(f"✅ **အောင်မြင်စွာ ချိတ်ဆက်ပြီးပါပြီ!**\n\n`{src_id}` ➡️ `{tgt_id}`", reply_markup=get_dashboard_markup())
    except Exception as e:
        await message.reply_text(f"❌ Error: `{e}`")

@control_bot.on_message(filters.command("del") & filters.user(ADMIN_ID))
async def cmd_del(client, message):
    try:
        args = message.text.split()
        src_id = str(await resolve_chat_id(args[1]))
        if src_id in db["clones"]:
            del db["clones"][src_id]
            save_db(db)
            await message.reply_text(f"🗑️ `{src_id}` ကို ပယ်ဖျက်လိုက်ပါပြီ။", reply_markup=get_dashboard_markup())
        else:
            await message.reply_text("❌ ထို Channel ကို Active List ထဲတွင် မတွေ့ပါ။")
    except Exception as e:
        await message.reply_text(f"❌ Error: `{e}`")

@control_bot.on_message(filters.command("filter") & filters.user(ADMIN_ID))
async def cmd_filter(client, message):
    try:
        args = message.text.split(maxsplit=3)
        sub_cmd = args[1].lower()
        src_id = str(await resolve_chat_id(args[2]))
        
        if src_id not in db["filters"]:
            db["filters"][src_id] = {"media_type": "all", "blacklist": [], "whitelist": [], "remove_links": False}

        if sub_cmd == "media":
            m_type = args[3].lower()
            db["filters"][src_id]["media_type"] = m_type
            save_db(db)
            await message.reply_text(f"✅ Filter Media Type ကို `{m_type}` သို့ ပြောင်းလဲလိုက်ပါပြီ။")

        elif sub_cmd == "blacklist":
            word = args[3]
            db["filters"][src_id]["blacklist"].append(word)
            save_db(db)
            await message.reply_text(f"✅ Blacklist Keyword `{word}` ထည့်သွင်းပြီးပါပြီ။")

        elif sub_cmd == "removelinks":
            status = args[3].lower() == "on"
            db["filters"][src_id]["remove_links"] = status
            save_db(db)
            await message.reply_text(f"✅ Remove Links feature ကို `{status}` သို့ ပြောင်းလိုက်ပါပြီ။")

    except Exception as e:
        await message.reply_text(f"❌ Error: `{e}`")

@control_bot.on_message(filters.command("replace") & filters.user(ADMIN_ID))
async def cmd_replace(client, message):
    try:
        text = message.text.split(" ", 1)[1]
        old_val, new_val = text.split("|")
        old_val, new_val = old_val.strip(), new_val.strip()
        
        db["replacements"][old_val] = new_val
        save_db(db)
        
        await message.reply_text(f"✅ **Text Replacement ထည့်ပြီးပါပြီ:**\n\n`{old_val}` ➡️ `{new_val}`")
    except Exception:
        await message.reply_text("❌ Format အမှားပါဝင်နေပါသည်။\n\nဥပမာ - `/replace @old_link | @my_link`")

@control_bot.on_message(filters.command("setheader") & filters.user(ADMIN_ID))
async def cmd_setheader(client, message):
    try:
        args = message.text.split(" ", 2)
        src_id = str(await resolve_chat_id(args[1]))
        header_text = args[2]
        db["headers"][src_id] = header_text
        save_db(db)
        await message.reply_text(f"✅ Header စာသား ထည့်သွင်းပြီးပါပြီ။")
    except Exception as e:
        await message.reply_text(f"❌ Error: `{e}`")

@control_bot.on_message(filters.command("setfooter") & filters.user(ADMIN_ID))
async def cmd_setfooter(client, message):
    try:
        args = message.text.split(" ", 2)
        src_id = str(await resolve_chat_id(args[1]))
        footer_text = args[2]
        db["footers"][src_id] = footer_text
        save_db(db)
        await message.reply_text(f"✅ Footer စာသား ထည့်သွင်းပြီးပါပြီ။")
    except Exception as e:
        await message.reply_text(f"❌ Error: `{e}`")

@control_bot.on_message(filters.command("batch") & filters.user(ADMIN_ID))
async def cmd_batch(client, message):
    try:
        args = message.text.split()
        if len(args) < 3:
            await message.reply_text("❌ **Format အမှားပါဝင်နေပါသည်။**\n\n`/batch <source> <target>`")
            return
        status_msg = await message.reply_text("🔄 Batch Clone စတင်ရန် ပြင်ဆင်နေပါသည်...")
        
        src_id = await resolve_chat_id(args[1])
        tgt_id = await resolve_chat_id(args[2])
        
        count = 0
        await status_msg.edit_text("📦 ပို့စ်ဟောင်းများကို စတင် ကူးယူနေပါပြီ...")
        
        async for msg in userbot.get_chat_history(src_id, reverse=True):
            try:
                await send_smart_copy(msg, tgt_id, str(src_id))
                count += 1
                await asyncio.sleep(1.2)  # FloodWait Protection
                
                if count % 20 == 0:
                    await status_msg.edit_text(f"📦 ပို့စ်ပေါင်း **{count}** ခု ကူးယူပြီးပါပြီ...")
            except FloodWait as f:
                await asyncio.sleep(f.value)
            except Exception as err:
                print(f"Batch Item Error: {err}")
                
        await status_msg.edit_text(f"🎉 **Batch Clone ပြီးစီးပါပြီ!**\n\nစုစုပေါင်း ပို့စ်: **{count}** ခု")
    except Exception as e:
        await message.reply_text(f"❌ Error: `{e}`")

# Main Startup Function
async def main():
    print("=== Cloner Bot စတင်နေပါပြီ ===")
    await userbot.start()
    await control_bot.start()
    print("=== Bot အောင်မြင်စွာ Run သွားပါပြီ ===")
    await idle()
    await userbot.stop()
    await control_bot.stop()

if __name__ == "__main__":
    asyncio.run(main())
