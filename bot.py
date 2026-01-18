import os, json, yt_dlp
from pyrogram import Client, filters
from pyrogram.enums import ChatType
from pyrogram.errors import (
    UserAlreadyParticipant,
    UserBannedInChannel,
    ChatAdminRequired,
    UserDeactivated,
    AuthKeyUnregistered,
    PeerIdInvalid
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

def is_url(text: str):
    return text.startswith("http://") or text.startswith("https://")

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
    # 1️⃣ jika sudah ada
    try:
        m = await bot.get_chat_member(chat.id, ASSISTANT_ID)
        if m.status in ("member", "administrator", "owner"):
            return True
    except Exception:
        pass

    # 2️⃣ join via username (public group)
    if chat.username:
        try:
            await assistant.join_chat(chat.username)
            return True
        except UserAlreadyParticipant:
            return True
        except Exception as e:
            await notify(chat.id, f"ℹ️ Join via username gagal:\n{e}")

    # 3️⃣ invite via bot (bot admin)
    try:
        await bot.add_chat_members(chat.id, ASSISTANT_ID)
        await notify(chat.id, "👤 Asisten berhasil diundang.\n▶️ Ketik /play lagi")
    except UserAlreadyParticipant:
        return True
    except PeerIdInvalid:
        await notify(chat.id, "❌ ASSISTANT_ID tidak valid (bukan akun USER)")
    except Exception as e:
        await notify(chat.id, f"❌ Gagal invite asisten:\n{e}")

    return False

# ================= AUDIO (YT-DLP + COOKIES) =================
def download_audio(query: str):
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": "music.%(ext)s",
        "quiet": True,
        "noplaylist": True,
        "cookiefile": "cookies.txt",   # 🔥 WAJIB
        "nocheckcertificate": True,
        "ignoreerrors": True,
        "geo_bypass": True,
        "extractor_args": {
            "youtube": {
                "skip": ["dash", "hls"]
            }
        }
    }

    target = query if is_url(query) else f"ytsearch1:{query}"

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(target, download=True)

        if not info:
            raise Exception("Video tidak ditemukan")

        if "entries" in info:
            info = info["entries"][0]

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

# ================= MUSIC =================
@bot.on_message(filters.command("play") & filters.group)
@guard
async def play(_, msg):
    if len(msg.command) < 2:
        await msg.reply("❌ Gunakan: /play judul lagu atau url")
        return

    if not await ensure_assistant(msg.chat):
        return

    query = " ".join(msg.command[1:])
    await msg.reply("🎵 Mencari & mengunduh audio...")

    try:
        audio_path = download_audio(query)
    except Exception as e:
        await msg.reply(f"❌ Gagal download audio\n{e}")
        return

    try:
        await call.play(msg.chat.id, audio_path)
        await msg.reply("▶️ Memutar musik")
    except Exception as e:
        await msg.reply(f"❌ Gagal memutar audio\n{e}")

# ================= ADMIN GROUP TRACK =================
@bot.on_chat_member_updated()
async def admin_update(_, u):
    if not u.new_chat_member or not u.new_chat_member.user:
        return

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

# py-tgcalls v2 → tidak pakai call.start()
bot.run()
