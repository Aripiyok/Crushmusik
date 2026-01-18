import os, json, yt_dlp
from pyrogram import Client, filters
from pyrogram.enums import ChatType
from pyrogram.errors import (
    UserAlreadyParticipant,
    UserBannedInChannel,
    ChatWriteForbidden,
    ChatAdminRequired,
    UserDeactivated,
    AuthKeyUnregistered
)

from pytgcalls import PyTgCalls
from config import *

# ================= FILE STORAGE =================
STATUS_FILE = "group_status.json"
ADMIN_FILE = "admin_groups.json"

def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

GROUP_STATUS = load_json(STATUS_FILE)
ADMIN_GROUPS = load_json(ADMIN_FILE)

# ================= CLIENT =================
bot = Client(
    "bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

assistant = Client(
    "assistant",
    api_id=API_ID,
    api_hash=API_HASH
)

call = PyTgCalls(assistant)

# ================= UTIL =================
def is_owner(uid):
    return uid == OWNER_ID

def is_on(cid):
    return GROUP_STATUS.get(str(cid), True)

def guard(func):
    async def wrapper(client, msg):
        if not is_on(msg.chat.id):
            return
        return await func(client, msg)
    return wrapper

async def notify(chat_id, text):
    try:
        await bot.send_message(chat_id, text)
    except Exception:
        pass

# ================= AUTO INVITE ASSISTANT =================
async def ensure_assistant(chat):
    try:
        # Coba join sendiri (kalau grup public)
        await assistant.join_chat(chat.id)
        return True

    except UserAlreadyParticipant:
        return True

    except ChatWriteForbidden:
        # Bot invite asisten (karena bot ADMIN)
        try:
            await bot.add_chat_members(chat.id, ASSISTANT_ID)
            await notify(
                chat.id,
                "👤 Asisten berhasil diundang.\n▶️ Ketik /play lagi"
            )
        except Exception as e:
            await notify(
                chat.id,
                f"❌ Gagal invite asisten\n"
                f"Reason: {e}\n\n"
                f"Checklist:\n"
                f"- Bot ADMIN\n"
                f"- ASSISTANT_ID benar ({ASSISTANT_ID})\n"
                f"- Privacy asisten = Everybody"
            )
        return False

    except UserBannedInChannel:
        await notify(chat.id, "🚫 Akun asisten TERBANNED di grup ini")
        return False

    except Exception as e:
        await notify(chat.id, f"❌ Error join asisten:\n{e}")
        return False

# ================= AUDIO =================
def download_audio(query: str):
    ydl_opts = {
        "format": "bestaudio",
        "outtmpl": "music.%(ext)s",
        "quiet": True,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(query, download=True)
        filename = ydl.prepare_filename(info)
    return filename

# ================= OWNER ON / OFF =================
@bot.on_message(filters.command("on") & filters.group)
async def on_group(_, msg):
    if not is_owner(msg.from_user.id):
        return
    GROUP_STATUS[str(msg.chat.id)] = True
    save_json(STATUS_FILE, GROUP_STATUS)
    await msg.reply("✅ Bot diaktifkan di grup ini")

@bot.on_message(filters.command("off") & filters.group)
async def off_group(_, msg):
    if not is_owner(msg.from_user.id):
        return
    GROUP_STATUS[str(msg.chat.id)] = False
    save_json(STATUS_FILE, GROUP_STATUS)
    # silent setelah ini

# ================= MUSIC =================
@bot.on_message(filters.command("play") & filters.group)
@guard
async def play(_, msg):
    if len(msg.command) < 2:
        return

    if not await ensure_assistant(msg.chat):
        return

    query = " ".join(msg.command[1:])
    await msg.reply("🎵 Mengunduh audio...")

    try:
        audio_path = download_audio(query)
    except Exception:
        await msg.reply("❌ Gagal download audio")
        return

    try:
        await call.play(msg.chat.id, audio_path)
        await msg.reply("▶️ Memutar musik")
    except Exception as e:
        await msg.reply(f"❌ Gagal memutar audio\n{e}")

# ================= ADMIN GROUP TRACK =================
@bot.on_chat_member_updated()
async def admin_update(_, u):
    me = await bot.get_me()
    if u.new_chat_member.user.id != me.id:
        return

    if u.new_chat_member.status in ("administrator", "owner"):
        ADMIN_GROUPS[str(u.chat.id)] = u.chat.title
        save_json(ADMIN_FILE, ADMIN_GROUPS)
        await notify(
            OWNER_ID,
            f"🔔 Bot di-admin-kan di grup baru:\n{u.chat.title}\n{u.chat.id}"
        )

# ================= OWNER COMMAND =================
@bot.on_message(filters.command("scangrup"))
async def scan(_, msg):
    if not is_owner(msg.from_user.id):
        return

    ADMIN_GROUPS.clear()
    async for d in bot.get_dialogs():
        if d.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
            try:
                m = await bot.get_chat_member(d.chat.id, "me")
                if m.status in ("administrator", "owner"):
                    ADMIN_GROUPS[str(d.chat.id)] = d.chat.title
            except ChatAdminRequired:
                pass

    save_json(ADMIN_FILE, ADMIN_GROUPS)
    await msg.reply(f"✅ Scan selesai: {len(ADMIN_GROUPS)} grup")

@bot.on_message(filters.command("broadcast"))
async def bc(_, msg):
    if not is_owner(msg.from_user.id):
        return

    if len(msg.command) < 2:
        return

    text = msg.text.split(None, 1)[1]
    ok = 0

    for cid in ADMIN_GROUPS:
        try:
            await bot.send_message(int(cid), text)
            ok += 1
        except Exception:
            pass

    await msg.reply(f"📣 Broadcast terkirim ke {ok} grup")

# ================= START =================
try:
    assistant.start()
except (UserDeactivated, AuthKeyUnregistered):
    print("❌ Session asisten mati, login ulang")
    exit(1)

# py-tgcalls v2 → TIDAK pakai call.start()
bot.run()
