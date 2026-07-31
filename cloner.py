import os
import json
import asyncio
import re
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait, RPCError

# ---------------------------------------------------------------------------------
# 1. ENVIRONMENT VARIABLES & CONFIGURATION
# ---------------------------------------------------------------------------------
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

DATA_FILE = "cloner_database.json"

# ---------------------------------------------------------------------------------
# 2. DATABASE MANAGEMENT (DATA PERSISTENCE)
# ---------------------------------------------------------------------------------
def load_db():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[-] DB Load Error: {e}")
    return {
        "pairs": {},            # { "source_id": "target_id" }
        "replacements": {},     # { "old_text": "new_text" }
        "filters": {
            "allow_photo": True,
            "allow_video": True,
            "allow_document": True,
            "allow_audio": True,
            "allow_text": True,
            "remove_links": False,
            "blacklisted_words": []
        },
        "header": "",
        "footer": ""
    }

def save_db(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

db = load_db()

# ---------------------------------------------------------------------------------
# 3. CLIENT INITIALIZATION
# ---------------------------------------------------------------------------------
userbot = Client("userbot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)
control_bot = Client("control_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ---------------------------------------------------------------------------------
# 4. HELPER & PROCESSING FUNCTIONS
# ---------------------------------------------------------------------------------
async def resolve_chat_id(chat_input: str):
    """Link သို့မဟုတ် Username သို့မဟုတ် ID မှ Telegram Chat ID စစ်စစ်သို့ ပြောင်းပေးမည်"""
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

def process_text(text: str) -> str:
    """Caption နှင့် Text များကို Filter လုပ်ခြင်း၊ Link ဖြုတ်ခြင်း၊ စာသားလဲခြင်း ပြုလုပ်မည်"""
    if not text:
        return text

    filters_cfg = db.get("filters", {})

    # 1. Remove Links (ကျန်ခဲ့သည့် Hyperlink များ ဖြုတ်ခြင်း)
    if filters_cfg.get("remove_links"):
        text = re.sub(r'https?://\S+|www\.\S+', '', text)

    # 2. Text/Link Replacement
    replacements = db.get("replacements", {})
    for old_val, new_val in replacements.items():
        text = text.replace(old_val, new_val)

    # 3. Header & Footer တပ်ဆင်ခြင်း
    header = db.get("header", "")
    footer = db.get("footer", "")
    
    if header:
        text = f"{header}\n\n{text}"
    if footer:
        text = f"{text}\n\n{footer}"

    return text.strip()

def is_message_allowed(message) -> bool:
    """Media Type နှင့် Blacklisted Words များ စစ်ထုတ်ပေးမည်"""
    filters_cfg = db.get("filters", {})
    text_content = message.text or message.caption or ""

    # Keyword Blacklist Check
    for word in filters_cfg.get("blacklisted_words", []):
        if word.lower() in text_content.lower():
            return False

    # Media Type Check
    if message.photo and not filters_cfg.get("allow_photo", True):
        return False
    if message.video and not filters_cfg.get("allow_video", True):
        return False
    if message.document and not filters_cfg.get("allow_document", True):
        return False
    if message.audio and not filters_cfg.get("allow_audio", True):
        return False
    if message.text and not filters_cfg.get("allow_text", True):
        return False

    return True

async def copy_smart(message, target_id: int):
    """
    Direct Copy ပြုလုပ်မည်။ 
    Save Content/Forward ပိတ်ထားသော Restricted Channel ဖြစ်ပါက Download လုပ်၍ Re-upload Bypass ပြုလုပ်မည်။
    """
    caption = process_text(message.caption or "")
    text = process_text(message.text or "")

    try:
        # ပထမနည်းလမ်း - Direct Copy / Forward
        if message.text:
            await userbot.send_message(target_id, text)
        else:
            await message.copy(chat_id=target_id, caption=caption)
        print(f"[+] Direct Copy Successful: Message {message.id}")
        
    except Exception as e:
        # ဒုတိယနည်းလမ်း - Restricted Content Bypass (Download & Re-upload)
        print(f"[!] Direct copy failed ({e}). Attempting Restricted Bypass...")
        try:
            if message.text:
                await userbot.send_message(target_id, text)
            else:
                # Media ကို Temp File အဖြစ် ဒေါင်းလုဒ်ဆွဲမည်
                file_path = await userbot.download_media(message)
                
                if message.photo:
                    await userbot.send_photo(target_id, file_path, caption=caption)
                elif message.video:
                    await userbot.send_video(target_id, file_path, caption=caption)
                elif message.document:
                    await userbot.send_document(target_id, file_path, caption=caption)
                elif message.audio:
                    await userbot.send_audio(target_id, file_path, caption=caption)
                elif message.voice:
                    await userbot.send_voice(target_id, file_path, caption=caption)

                # ဖိုင်တင်ပြီးပါက Temp File အား ပြန်လည်ဖျက်ဆီးမည်
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
            print(f"[+] Bypass Upload Successful: Message {message.id}")
        except Exception as bypass_err:
            print(f"[-] Bypass Error: {bypass_err}")

# ---------------------------------------------------------------------------------
# 5. USERBOT AUTOMATION (LIVE CLONING)
# ---------------------------------------------------------------------------------
@userbot.on_message(filters.channel)
async def auto_clone_listener(client, message):
    source_id = str(message.chat.id)
    pairs = db.get("pairs", {})

    if source_id in pairs:
        target_id = int(pairs[source_id])
        if is_message_allowed(message):
            await copy_smart(message, target_id)

# ---------------------------------------------------------------------------------
# 6. CONTROL BOT (DASHBOARD & COMMANDS)
# ---------------------------------------------------------------------------------
def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Active Pairs", callback_data="btn_pairs"), InlineKeyboardButton("➕ Add Pair", callback_data="btn_add")],
        [InlineKeyboardButton("⚙️ Media Filters", callback_data="btn_filters"), InlineKeyboardButton("✏️ Replacements", callback_data="btn_replace")],
        [InlineKeyboardButton("🏷️ Header / Footer", callback_data="btn_header_footer"), InlineKeyboardButton("🔄 Batch Clone", callback_data="btn_batch")]
    ])

@control_bot.on_message(filters.command("start") & filters.user(ADMIN_ID))
async def start_cmd(client, message):
    await message.reply_text(
        "🚀 **Enterprise Telegram Cloner Control Panel**\n\n"
        "အောက်ပါ Menu များမှတစ်ဆင့် Bot ၏ Features များကို ထိန်းချုပ်နိုင်ပါသည်။",
        reply_markup=get_main_keyboard()
    )

@control_bot.on_callback_query(filters.user(ADMIN_ID))
async def cb_handler(client, query: CallbackQuery):
    data = query.data

    if data == "main_menu":
        await query.message.edit_text("🚀 **Enterprise Telegram Cloner Control Panel**", reply_markup=get_main_keyboard())

    elif data == "btn_pairs":
        pairs = db.get("pairs", {})
        if not pairs:
            msg = "📋 **လက်ရှိ မည်သည့် Pair မျှ မရှိသေးပါ။**"
        else:
            msg = "📋 **Active Cloning Pairs:**\n\n" + "\n".join([f"• `{src}` ➡️ `{tgt}`" for src, tgt in pairs.items()])
        await query.message.edit_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]))

    elif data == "btn_add":
        await query.message.edit_text(
            "➕ **Channel ချိတ်ဆက်နည်း:**\n\n"
            "အောက်ပါ Command ဖြင့် ထည့်သွင်းပါ -\n"
            "`/add <source_channel> <target_channel>`\n\n"
            "**ဥပမာ:**\n`/add @my_source @my_target`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]])
        )

    elif data == "btn_filters":
        f = db.get("filters", {})
        status = (
            f"⚙️ **Media Filter Settings:**\n\n"
            f"• 🖼️ Photos: {'✅' if f.get('allow_photo') else '❌'}\n"
            f"• 🎥 Videos: {'✅' if f.get('allow_video') else '❌'}\n"
            f"• 📁 Documents: {'✅' if f.get('allow_document') else '❌'}\n"
            f"• 🔗 Remove Links: {'✅' if f.get('remove_links') else '❌'}\n"
            f"• 🚫 Blacklisted Words: `{', '.join(f.get('blacklisted_words', [])) or 'None'}`\n\n"
            "ပြောင်းလဲရန် Command မက: `/toggle <photo/video/document/links>`"
        )
        await query.message.edit_text(status, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]))

    elif data == "btn_replace":
        reps = db.get("replacements", {})
        rep_text = "\n".join([f"• `{k}` ➡️ `{v}`" for k, v in reps.items()]) or "မရှိသေးပါ"
        await query.message.edit_text(
            f"✏️ **Text Replacement List:**\n\n{rep_text}\n\n"
            "ထည့်သွင်းရန် Command - `/replace <old_text> | <new_text>`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]])
        )

    elif data == "btn_header_footer":
        h = db.get("header", "မရှိပါ")
        ft = db.get("footer", "မရှိပါ")
        await query.message.edit_text(
            f"🏷️ **Header & Footer Settings:**\n\n"
            f"**Header:**\n`{h}`\n\n"
            f"**Footer:**\n`{ft}`\n\n"
            "ပြင်ဆင်ရန် Command များ -\n"
            "• `/setheader <စာသား>`\n"
            "• `/setfooter <စာသား>`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]])
        )

    elif data == "btn_batch":
        await query.message.edit_text(
            "🔄 **Batch Clone (Old Posts):**\n\n"
            "Channel ထဲရှိ ပို့စ်ဟောင်း အားလုံးကို Clone လုပ်ရန် -\n"
            "`/batch <source_channel> <target_channel>`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]])
        )

# Command Handlers
@control_bot.on_message(filters.command("add") & filters.user(ADMIN_ID))
async def add_pair_cmd(client, message):
    try:
        args = message.text.split()
        status = await message.reply_text("🔄 စစ်ဆေးနေပါသည်...")
        src_id = str(await resolve_chat_id(args[1]))
        tgt_id = str(await resolve_chat_id(args[2]))
        
        db["pairs"][src_id] = tgt_id
        save_db(db)
        await status.edit_text(f"✅ **Pair ချိတ်ဆက်ပြီးပါပြီ!**\n\n`{src_id}` ➡️ `{tgt_id}`", reply_markup=get_main_keyboard())
    except Exception as e:
        await message.reply_text(f"❌ Error: `{e}`")

@control_bot.on_message(filters.command("replace") & filters.user(ADMIN_ID))
async def replace_cmd(client, message):
    try:
        text = message.text.split(" ", 1)[1]
        old_val, new_val = text.split("|")
        db["replacements"][old_val.strip()] = new_val.strip()
        save_db(db)
        await message.reply_text(f"✅ **Text Replacement ထည့်ပြီးပါပြီ!**")
    except Exception:
        await message.reply_text("❌ Format: `/replace old_text | new_text`")

@control_bot.on_message(filters.command("setheader") & filters.user(ADMIN_ID))
async def set_header_cmd(client, message):
    text = message.text.split(" ", 1)[1] if len(message.text.split()) > 1 else ""
    db["header"] = text
    save_db(db)
    await message.reply_text("✅ **Header ပြင်ဆင်ပြီးပါပြီ!**")

@control_bot.on_message(filters.command("setfooter") & filters.user(ADMIN_ID))
async def set_footer_cmd(client, message):
    text = message.text.split(" ", 1)[1] if len(message.text.split()) > 1 else ""
    db["footer"] = text
    save_db(db)
    await message.reply_text("✅ **Footer ပြင်ဆင်ပြီးပါပြီ!**")

@control_bot.on_message(filters.command("batch") & filters.user(ADMIN_ID))
async def batch_clone_cmd(client, message):
    try:
        args = message.text.split()
        status = await message.reply_text("🔄 Batch Clone စတင်ရန် ပြင်ဆင်နေပါသည်...")
        src_id = await resolve_chat_id(args[1])
        tgt_id = await resolve_chat_id(args[2])

        count = 0
        async for msg in userbot.get_chat_history(src_id, reverse=True):
            if is_message_allowed(msg):
                await copy_smart(msg, tgt_id)
                count += 1
                await asyncio.sleep(1.5) # FloodWait ကာကွယ်ရန်
                if count % 15 == 0:
                    await status.edit_text(f"📦 ပို့စ်ပေါင်း **{count}** ခု ကူးယူပြီးပါပြီ...")
            
        await status.edit_text(f"🎉 **Batch Clone ပြီးစီးပါပြီ!**\n\nစုစုပေါင်း ပို့စ်: **{count}** ခု")
    except FloodWait as f:
        await asyncio.sleep(f.value)
    except Exception as e:
        await message.reply_text(f"❌ Batch Error: `{e}`")

# ---------------------------------------------------------------------------------
# 7. MAIN ASYNC RUNNER
# ---------------------------------------------------------------------------------
async def main():
    await userbot.start()
    await control_bot.start()
    print("=========================================")
    print("=== ENTERPRISE CLONER BOT IS RUNNING ===")
    print("=========================================")
    await idle()
    await userbot.stop()
    await control_bot.stop()

if __name__ == "__main__":
    asyncio.run(main())
