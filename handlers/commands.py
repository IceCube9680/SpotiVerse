# handlers/commands.py
import os
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional
from pyrogram.errors import MessageNotModified
from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
)
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
import re
from info import DEFAULT_SETTINGS, get_premium_plans, get_plan_by_id
from config import Config
from utils.db import db, _parse_datetime
from utils.logger import BotLogger
from utils.providers import ProviderRegistry
from utils.feature_gates import FeatureGate
from utils.payment import payment_manager
from utils.admin_security import admin_security
from utils.audio_formats import AudioProfile, AudioFormat
from utils.ui_helpers import safe_answer_callback, safe_edit_or_reply
from handlers.search import SearchHandler
from handlers.downloads import DownloadHandler
from handlers.admin_panel import AdminPanelHandler
from pyrogram.types import InputMediaDocument

logger = logging.getLogger(__name__)


# ----------------------
# Small helpers
# ----------------------
def _get_command_parts(message: Message) -> list[str]:
    if message and hasattr(message, "command") and message.command:
        return list(message.command)
    if message and getattr(message, "text", None):
        return message.text.split()
    return []


def _display_name_from_user_obj(user_obj) -> str:
    if not user_obj:
        return "there"
    return (user_obj.first_name or user_obj.username or "there").strip()


def _display_name_from_callback(callback_query: CallbackQuery) -> str:
    try:
        u = callback_query.from_user
        if u and (u.first_name or u.username):
            return _display_name_from_user_obj(u)
    except Exception:
        pass

    try:
        if callback_query.from_user:
            rec = db.get_user(callback_query.from_user.id)
            if rec and rec.get("display_name"):
                return rec.get("display_name")
    except Exception:
        pass

    return "there"


def _format_time_remaining(expiry_dt: datetime) -> str:
    if not expiry_dt:
        return "N/A"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if expiry_dt < now:
        return "Expired"
    diff = expiry_dt - now
    days = diff.days
    hours = diff.seconds // 3600
    if days >= 3650:
        return "Lifetime ♾️"
    if days > 0:
        return f"{days} day(s) {hours} hr(s) remaining"
    return f"{hours} hr(s) remaining"


def _build_start_keyboard(user_id: int = 0) -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("📥 Download Music", callback_data="menu_download")],
        [InlineKeyboardButton("👑 Premium Plans", callback_data="view_plans"),
         InlineKeyboardButton("👤 My Profile", callback_data="user_profile")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="menu_settings"),
         InlineKeyboardButton("❓ Help", callback_data="menu_help")]
    ]
    if user_id and Config.is_owner(user_id):
        kb.append([InlineKeyboardButton("🛠 Admin Panel", callback_data="adm_main")])
    return InlineKeyboardMarkup(kb)


def _build_premium_markup() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("💎 View All Plans", callback_data="view_plans")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back")],
    ]
    return InlineKeyboardMarkup(kb)


def _settings_keyboard_for(user: dict) -> InlineKeyboardMarkup:
    uid = user.get("user_id") or user.get("telegram_id")
    is_premium = bool(user.get("lifetime_premium")) or bool(user.get("premium"))
    if uid and Config.is_owner(uid):
        is_premium = True

    allowed_formats = AudioProfile.get_allowed_formats(is_premium=is_premium)
    current_format = str(user.get("preferred_format", "mp3")).lower().strip()
    if current_format not in allowed_formats:
        current_format = allowed_formats[0]

    next_fmt_idx = (allowed_formats.index(current_format) + 1) % len(allowed_formats)
    next_fmt = allowed_formats[next_fmt_idx]

    allowed_qualities = AudioProfile.get_allowed_qualities(current_format, is_premium=is_premium)
    current_quality = user.get("preferred_quality", AudioProfile.get_default_quality(current_format, is_premium))

    curr_q_str = str(current_quality).lower().strip()
    match_idx = -1
    for i, q in enumerate(allowed_qualities):
        if str(q).lower().strip() == curr_q_str:
            match_idx = i
            break
    if match_idx == -1:
        current_quality = allowed_qualities[-1]
        next_q = allowed_qualities[0]
    else:
        next_q = allowed_qualities[(match_idx + 1) % len(allowed_qualities)]

    cur_label = AudioProfile.format_quality_label(current_format, current_quality)
    next_label = AudioProfile.format_quality_label(current_format, next_q)

    kb = []
    if len(allowed_formats) > 1:
        kb.append([InlineKeyboardButton(f"🎵 Format: {current_format.upper()} → {next_fmt.upper()}", callback_data="setting_format")])
    else:
        kb.append([InlineKeyboardButton(f"🎵 Format: {current_format.upper()} (MP3 Only)", callback_data="setting_format_info")])

    kb.append([InlineKeyboardButton(f"🎚️ Quality: {cur_label} → {next_label}", callback_data="setting_quality")])

    if not is_premium:
        kb.append([InlineKeyboardButton("💎 Unlock Lossless FLAC, M4A, OGG & WAV", callback_data="view_plans")])

    kb.append([InlineKeyboardButton("🔙 Back", callback_data="main_menu")])
    return InlineKeyboardMarkup(kb)


# ----------------------
# Binder class: registers handlers on a pyrogram.Client
# ----------------------
class CommandsBinder:
    def __init__(self, app: Client, search_handler: SearchHandler, download_handler: DownloadHandler, logger_obj: BotLogger = None):
        self.app = app
        self.search_handler = search_handler
        self.download_handler = download_handler
        self.logger = logger_obj or BotLogger(app)
        self.admin_panel = AdminPanelHandler(app)

        # Register message handlers
        app.add_handler(MessageHandler(self._on_start_wrapper, filters.command("start")))
        app.add_handler(MessageHandler(self._on_search_wrapper, filters.command(["search", "s", "find"])))
        app.add_handler(MessageHandler(self._on_help_wrapper, filters.command(["help", "h"])))
        app.add_handler(MessageHandler(self._on_settings_wrapper, filters.command(["settings", "setting", "set"])))
        app.add_handler(MessageHandler(self._on_download_wrapper, filters.command(["download", "dl", "d"])))
        app.add_handler(MessageHandler(self._on_userinfo_wrapper, filters.command(["userinfo", "user_info", "info", "myinfo", "me", "profile"])))
        app.add_handler(MessageHandler(self._on_premium_wrapper, filters.command(["premium", "prem"])))
        app.add_handler(MessageHandler(self._on_plans_wrapper, filters.command(["plans", "plan", "pricing", "buy", "upgrade"])))
        app.add_handler(MessageHandler(self._on_admin_wrapper, filters.command(["admin", "panel", "adm"])))
        app.add_handler(MessageHandler(self._on_addpremium_wrapper, filters.command(["addpremium", "add_premium", "setpremium", "set_premium", "give_premium", "givepremium"])))
        app.add_handler(MessageHandler(self._on_removepremium_wrapper, filters.command(["removepremium", "remove_premium", "delpremium", "del_premium", "unpremium", "revoke_premium", "remove_prem", "del_prem"])))
        app.add_handler(MessageHandler(self._on_premiummode_wrapper, filters.command(["premiummode", "premium_mode", "setmode", "setpremiummode", "togglemode"])))
        app.add_handler(MessageHandler(self._on_stats_wrapper, filters.command(["stats", "stat"])))
        app.add_handler(MessageHandler(self._on_users_wrapper, filters.command(["users", "user", "totalusers"])))
        app.add_handler(MessageHandler(self._on_broadcast_wrapper, filters.command(["broadcast", "bc"])))
        app.add_handler(MessageHandler(self._on_logs_wrapper, filters.command(["logs", "log"])))

        # Direct text handler
        app.add_handler(MessageHandler(self._on_direct_message_wrapper, filters.text & filters.private & ~filters.regex(r"^/")))

        # CallbackQuery handler
        app.add_handler(CallbackQueryHandler(self._on_callback_wrapper))

        logger.info("Command handlers registered on Client.")

    async def _on_start_wrapper(self, client: Client, message: Message):
        await self.start_command(client, message)

    async def _on_search_wrapper(self, client: Client, message: Message):
        await self.search_command(client, message)

    async def _on_direct_message_wrapper(self, client: Client, message: Message):
        await self.direct_message_handler(client, message)

    async def _on_help_wrapper(self, client: Client, message: Message):
        await self.help_command(client, message)

    async def _on_settings_wrapper(self, client: Client, message: Message):
        await self.settings_command(client, message)

    async def _on_download_wrapper(self, client: Client, message: Message):
        await self.download_command(client, message)

    async def _on_userinfo_wrapper(self, client: Client, message: Message):
        await self.userinfo_command(client, message)

    async def _on_premium_wrapper(self, client: Client, message: Message):
        await self.premium_command(client, message)

    async def _on_plans_wrapper(self, client: Client, message: Message):
        await self.plans_command(client, message)

    async def _on_admin_wrapper(self, client: Client, message: Message):
        await self.admin_command(client, message)

    async def _on_addpremium_wrapper(self, client: Client, message: Message):
        await self.add_premium_command(client, message)

    async def _on_removepremium_wrapper(self, client: Client, message: Message):
        await self.remove_premium_command(client, message)

    async def _on_premiummode_wrapper(self, client: Client, message: Message):
        await self.premiummode_command(client, message)

    async def _on_stats_wrapper(self, client: Client, message: Message):
        await self.stats_command(client, message)

    async def _on_users_wrapper(self, client: Client, message: Message):
        await self.users_command(client, message)

    async def _on_broadcast_wrapper(self, client: Client, message: Message):
        await self.broadcast_command(client, message)

    async def _on_logs_wrapper(self, client: Client, message: Message):
        await self.logs_command(client, message)

    async def _on_callback_wrapper(self, client: Client, callback_query: CallbackQuery):
        await self.handle_callback(client, callback_query)

    # -------------------------
    # Command implementations
    # -------------------------
    async def start_command(self, client: Client, message: Message):
        if not message.from_user:
            logger.warning("Received /start from non-user or channel message.")
            return
        user_id = message.from_user.id
        first_name = getattr(message.from_user, "first_name", "there") or "there"
        username = getattr(message.from_user, "username", None)

        # Retrieve and update user record
        rec = db.get_user(user_id) or {}
        user_updates = {}
        if rec.get("display_name") != first_name:
            user_updates["display_name"] = first_name
        if username and rec.get("username") != username:
            user_updates["username"] = username
        if user_updates:
            try:
                db.update_user(user_id, user_updates)
                rec.update(user_updates)
            except Exception:
                pass

        try:
            await self.logger.log_new_user(user_id, username, first_name)
        except Exception:
            pass

        prem_mode = db.get_premium_mode()
        is_premium = db.is_premium(user_id)
        start_kb = _build_start_keyboard(user_id)

        if not prem_mode:
            welcome_text = (
                f"👋 Hello **{first_name}**!\n\n"
                "Welcome to **SpotiVerse Bot** — High-Performance Music Downloader!\n\n"
                "I can search and download high-quality audio from:\n"
                "• **Spotify** • **YouTube** • **JioSaavn** • **SoundCloud** • **Deezer**\n\n"
                "**Your Status:** ✨ All Features Unlocked (Public Mode)\n"
                "**Downloads:** Unlimited ♾️ (No daily limit)\n\n"
                "Enjoy your music downloads!"
            )
        else:
            welcome_text = (
                f"👋 Hello **{first_name}**!\n\n"
                "Welcome to **SpotiVerse Bot** — Studio-Grade Music Downloader!\n\n"
                "Supported platforms:\n"
                "• **Spotify** • **YouTube** • **JioSaavn** • **SoundCloud** • **Deezer**\n\n"
                f"**Membership:** `{'👑 Premium Member' if is_premium else '👤 Free Member'}`\n"
            )
            if is_premium:
                until_dt = _parse_datetime(rec.get("premium_until"))
                rem_str = _format_time_remaining(until_dt) if not rec.get("lifetime_premium") else "Lifetime Access ♾️"
                welcome_text += f"**Validity:** `{rem_str}`\n**Downloads:** Unlimited ♾️ (Priority Queue Active)\n\nReady to download your favorite songs & albums!"
            else:
                welcome_text += (
                    f"**Daily Limit:** `{rec.get('downloads_today', 0)}/{Config.FREE_USER_DAILY_LIMIT}` downloads used today\n\n"
                    "🔍 Search & download tracks with `/search <song name>`\n"
                    "👑 Upgrade to Premium for **Unlimited Downloads**, **FLAC Audio**, and **Full Playlist Support**!"
                )

        try:
            await message.reply_text(welcome_text, reply_markup=start_kb)
        except Exception:
            try:
                await message.edit_text(welcome_text, reply_markup=start_kb)
            except Exception as e:
                logger.warning(f"Failed to deliver welcome message: {e}")

    async def search_command(self, client: Client, message: Message):
        if not message.from_user:
            return
        user_id = message.from_user.id
        username = getattr(message.from_user, "username", None)
        first_name = getattr(message.from_user, "first_name", "there") or "there"

        try:
            db.update_user(user_id, {"username": username, "first_name": first_name, "display_name": first_name})
        except Exception:
            pass

        # Check banned state
        if db.is_banned(user_id):
            await message.reply_text("🚫 **Account Suspended.** You have been restricted from using this service.")
            return

        parts = _get_command_parts(message)
        if len(parts) < 2:
            await message.reply_text("Usage: `/search <song name>`\nExample: `/search blinding lights`")
            return
        query = " ".join(parts[1:]).strip()
        loading_msg = await message.reply_text(f"🔎 Searching for: **{query}** ...")
        try:
            tracks = await self.search_handler.search_all(query, limit=10)
            if not tracks:
                await loading_msg.edit_text("❌ No results found. Try another search query.")
                return

            try:
                kb = self.search_handler.create_search_results_keyboard(tracks, page=0, results_per_page=10)
                await loading_msg.edit_text(f"🔎 Results for: **{query}**\n\nSelect a track to download:", reply_markup=kb)
            except Exception:
                kb_rows = []
                for idx, t in enumerate(tracks[:10], start=1):
                    title = t.get("title", "Unknown")
                    artist = t.get("artist", "")
                    provider = t.get("provider", "youtube")
                    tid = t.get("id")
                    btn_text = f"{idx}. {title} - {artist}"
                    kb_rows.append([InlineKeyboardButton(btn_text[:60], callback_data=f"download_{provider}_{tid}")])
                await loading_msg.edit_text(f"🔎 Results for: **{query}**\n\nSelect a track to download:", reply_markup=InlineKeyboardMarkup(kb_rows))
        except Exception as e:
            logger.error(f"Search failed: {e}", exc_info=True)
            await loading_msg.edit_text(f"❌ Search failed: {e}")

    async def help_command(self, client: Client, message: Message):
        prem_mode = db.get_premium_mode()
        help_text = (
            "🤖 **SpotiVerse Bot Commands**\n\n"
            "**Music Commands:**\n"
            "• `/search <query>` - Search songs across all platforms\n"
            "• `/download <url>` - Download song, album, or playlist\n"
            "• `/plans` - View available Premium subscription plans\n\n"
            "**User Commands:**\n"
            "• `/start` - Start bot & open main menu\n"
            "• `/help` - Show this help manual\n"
            "• `/userinfo` - Check membership & daily usage\n"
            "• `/premium` - View your active subscription status\n"
            f"• `/settings` - Audio format & quality settings {'(Free for All)' if not prem_mode else '(Premium only)'}\n\n"
        )
        if Config.is_authorized(message):
            help_text += (
                "**Admin & Owner Commands:**\n"
                "• `/admin` - Open Centralized Admin Panel\n"
                "• `/premiummode <true|false>` - Global Premium switch\n"
                "• `/addpremium <user_id> [duration]` - Grant premium to user\n"
                "• `/removepremium <user_id>` - Revoke premium from user\n"
                "• `/stats` - View real-time analytics & platform metrics\n"
                "• `/users` - User count breakdown\n"
                "• `/broadcast <msg>` - Send announcement to users\n"
                "• `/logs` - Export bot logs\n\n"
            )
        help_text += "Need support? Contact @icecube9608"
        await message.reply_text(help_text)

    async def settings_command(self, client: Client, message: Message):
        if not message.from_user:
            return
        user_id = message.from_user.id
        if not db.is_premium(user_id):
            await message.reply_text(
                "❌ **Settings are available to Premium users only.**\n\n"
                "Upgrade to Premium to configure lossless FLAC, 320kbps MP3, and priority routing.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💎 View Premium Plans", callback_data="view_plans")]])
            )
            return
        rec = db.get_user(user_id) or {}
        await message.reply_text("⚙️ **Settings**\n\nConfigure your download preferences:", reply_markup=_settings_keyboard_for(rec))

    async def direct_message_handler(self, client: Client, message: Message):
        """Handle text messages or links in private chats without command prefixes."""
        if not message or not message.from_user:
            return

        # Check if admin is currently entering interactive text
        handled = await self.admin_panel.handle_admin_text_input(client, message)
        if handled:
            return

        text = (message.text or "").strip()
        if not text:
            return

        if text.startswith(("http://", "https://", "spotify:")):
            message.command = ["download", text]
            await self.download_command(client, message)
        else:
            message.command = ["search"] + text.split()
            await self.search_command(client, message)

    async def download_command(self, client: Client, message: Message):
        """Handle /download command with centralized authorization pipeline."""
        if not message.from_user:
            return
        user_id = message.from_user.id
        username = getattr(message.from_user, "username", None)
        first_name = getattr(message.from_user, "first_name", "there") or "there"

        try:
            db.update_user(user_id, {"username": username, "first_name": first_name, "display_name": first_name})
        except Exception:
            pass

        parts = _get_command_parts(message)
        if len(parts) < 2:
            await message.reply_text(
                "Please provide a music URL.\nUsage: `/download <link>`\n\nExample: `/download https://open.spotify.com/track/...`"
            )
            return

        url = parts[1].strip()
        if not url.startswith(('http://', 'https://', 'spotify:')):
            await message.reply_text("❌ Please provide a valid URL starting with `http://`, `https://`, or `spotify:`")
            return

        # Parse provider and content type
        def _parse_url(u: str):
            # Spotify
            m = re.search(r"open\.spotify\.com/(?:intl-[^/]+/)?(track|album|playlist|artist)/([A-Za-z0-9]+)", u)
            if m:
                return "spotify", m.group(1), m.group(2)
            m = re.search(r"spotify:(track|album|playlist|artist):([A-Za-z0-9]+)", u)
            if m:
                return "spotify", m.group(1), m.group(2)
            # YouTube
            if "list=" in u:
                return "youtube", "playlist", u
            m = re.search(r"(?:v=|youtu\.be/|/shorts/)([A-Za-z0-9_-]{6,})", u)
            if m:
                return "youtube", "track", m.group(1)
            # Deezer
            m = re.search(r"deezer\.com/(track|album|playlist)/([0-9]+)", u)
            if m:
                return "deezer", m.group(1), m.group(2)
            # SoundCloud
            if "soundcloud.com" in u:
                if "/sets/" in u:
                    return "soundcloud", "playlist", u
                return "soundcloud", "track", u
            # JioSaavn
            if "jiosaavn.com" in u or "saavn" in u:
                if "/album/" in u or "/playlist/" in u:
                    return "jiosaavn", "album", u
                return "jiosaavn", "track", u
            return None, None, None

        provider, kind, tid = _parse_url(url)
        if not provider:
            await message.reply_text("❌ Could not detect provider from URL. Supported: Spotify, YouTube, JioSaavn, SoundCloud, Deezer.")
            return

        is_collection = kind in ("album", "playlist", "artist", "set")

        # Run centralized authorization pipeline
        auth = FeatureGate.authorize_download(user_id, provider=provider, is_batch=is_collection)
        if not auth.allowed:
            await message.reply_text(auth.reason)
            return

        # Proceed with download
        progress_msg = await message.reply_text("🚀 Starting download processing...")

        try:
            if is_collection:
                success = await self.download_handler.download_album(provider, url, user_id, progress_msg or message)
                if not success and progress_msg:
                    await self.download_handler.safe_edit_message(progress_msg, "❌ Failed to download album/playlist.")
            else:
                success = await self.download_handler.download_track(provider, tid, user_id, progress_msg or message)
                if not success and progress_msg:
                    await self.download_handler.safe_edit_message(progress_msg, "❌ Failed to download track.")
        except Exception as e:
            logger.error(f"Download execution error: {e}", exc_info=True)
            if progress_msg:
                await self.download_handler.safe_edit_message(progress_msg, f"❌ Download failed: {e}")

    async def userinfo_command(self, client: Client, message: Message):
        user_id = message.from_user.id if message.from_user else None
        parts = _get_command_parts(message)

        target_user_id = None
        if len(parts) > 1 and Config.is_authorized(message):
            user_raw = parts[1]
            if user_raw.lstrip('-').isdigit():
                target_user_id = int(user_raw)
            else:
                try:
                    user_obj = await client.get_users(user_raw)
                    target_user_id = user_obj.id
                except Exception as e:
                    await message.reply_text(f"❌ Could not find user `{user_raw}`: {e}")
                    return
        elif message.reply_to_message and getattr(message.reply_to_message, "from_user", None) and Config.is_authorized(message):
            target_user_id = message.reply_to_message.from_user.id
        elif user_id:
            target_user_id = user_id
        else:
            await message.reply_text("Usage: `/userinfo <user_id>`")
            return

        user = db.get_user(target_user_id) or {}
        prem_mode = db.get_premium_mode()
        is_prem = db.is_premium(target_user_id)

        if not prem_mode:
            status_display = "✨ Active (Public Mode - All Features Unlocked)"
        else:
            status_display = '✅ Active (💎 Premium)' if is_prem else '❌ Inactive (👤 Free User)'

        info_text = (
            f"👤 **User Information**\n\n"
            f"**User ID:** `{target_user_id}`\n"
            f"**Premium Status:** {status_display}\n"
        )
        if prem_mode and user.get('premium') and user.get('premium_until'):
            tu = _parse_datetime(user['premium_until'])
            try:
                info_text += f"**Premium Until:** {tu.strftime('%Y-%m-%d %H:%M UTC') if tu else 'N/A'}\n"
            except Exception:
                info_text += f"**Premium Until:** {str(tu)}\n"
        elif is_prem:
            info_text += "**Premium Until:** Lifetime / Unlimited ♾️\n"

        if is_prem:
            info_text += "**Downloads:** Unlimited ♾️ (No daily limit)\n"
        else:
            info_text += f"**Downloads Today:** {user.get('downloads_today', 0)}/{Config.FREE_USER_DAILY_LIMIT}\n"

        join_d = user.get('join_date')
        if isinstance(join_d, datetime):
            join_str = join_d.strftime('%Y-%m-%d')
        else:
            join_str = str(join_d) if join_d else 'Unknown'

        info_text += (
            f"**Total Downloads:** {user.get('total_downloads', 0)}\n"
            f"**Preferred Format:** {user.get('preferred_format', 'mp3')}\n"
            f"**Preferred Quality:** {user.get('preferred_quality', 64)}\n"
            f"**Join Date:** {join_str}\n"
        )
        await message.reply_text(info_text)

    # -------------------------
    # Premium Screens & Plans
    # -------------------------
    async def premium_command(self, client: Client, message: Message):
        if not message.from_user:
            return
        parts = _get_command_parts(message)
        if len(parts) > 1 and Config.is_authorized(message):
            arg = parts[1].strip().lower()
            if arg in ("true", "false", "on", "off", "enable", "disable", "1", "0", "t", "f", "yes", "no"):
                await self.premiummode_command(client, message)
                return

        user_id = message.from_user.id
        await self.show_user_premium_screen(message, user_id)

    async def plans_command(self, client: Client, message: Message):
        if not message.from_user:
            return
        await self.show_premium_plans_screen(message)

    async def show_user_premium_screen(self, message_or_cb, user_id: int):
        """Displays Premium Member Card or Free Member Card based on status (Phase 12)."""
        user = db.get_user(user_id) or {}
        is_prem = db.is_premium(user_id)
        prem_mode = db.get_premium_mode()
        name = user.get("first_name") or user.get("display_name") or "Music Lover"

        if not prem_mode:
            text = (
                f"🎉 **All Features Unlocked! (Public Mode)**\n\n"
                f"Hello {name}!\n"
                "All SpotiVerse premium features are currently **FREE** for everyone:\n\n"
                "✓ Unlimited song downloads\n"
                "✓ 320kbps MP3 & Lossless FLAC\n"
                "✓ All enabled platforms (Spotify, YouTube, JioSaavn, SoundCloud, Deezer)\n"
                "✓ Full album & playlist batch downloads\n"
                "✓ No daily quotas or limits"
            )
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="main_menu")]])
        elif is_prem:
            until_dt = _parse_datetime(user.get("premium_until"))
            is_lifetime = bool(user.get("lifetime_premium"))
            if is_lifetime:
                valid_str = "Lifetime (Permanent Access ♾️)"
            else:
                valid_str = f"{until_dt.strftime('%Y-%m-%d %H:%M UTC') if until_dt else 'Active'} ({_format_time_remaining(until_dt)})"

            plan_name = user.get("premium_plan") or ("Lifetime" if is_lifetime else "Premium Plan")

            text = (
                "👑 **Premium Member**\n\n"
                f"**Name:** {name}\n"
                f"**Telegram ID:** `{user_id}`\n"
                "**Membership:** Premium\n"
                f"**Plan:** {plan_name}\n"
                f"**Valid Until:** {valid_str}\n\n"
                "**Your Premium Benefits:**\n"
                "✓ Unlimited song downloads\n"
                "✓ Studio-grade MP3 (320kbps) & Lossless FLAC\n"
                "✓ All enabled platforms (Spotify, YouTube, JioSaavn, SoundCloud, Deezer)\n"
                "✓ Full album & playlist batch downloads\n"
                "✓ Priority queue processing\n"
                "✓ Zero daily limits or wait times"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 Extend / Change Plan", callback_data="view_plans")],
                [InlineKeyboardButton("⬅️ Back", callback_data="main_menu")]
            ])
        else:
            # Free user or expired
            until_dt = _parse_datetime(user.get("premium_until"))
            is_expired = until_dt and until_dt < datetime.now(timezone.utc).replace(tzinfo=None)

            if is_expired:
                header = "⚠️ **Premium Expired**\n\nYour premium subscription has expired. Renew to restore unlimited downloads and lossless audio!"
            else:
                header = "👤 **Free Member**"

            text = (
                f"{header}\n\n"
                f"**Name:** {name}\n"
                f"**Telegram ID:** `{user_id}`\n"
                "**Membership:** Free Tier\n"
                f"**Daily Limit:** {Config.FREE_USER_DAILY_LIMIT} downloads/day\n"
                f"**Used Today:** {user.get('downloads_today', 0)}/{Config.FREE_USER_DAILY_LIMIT}\n\n"
                "**Upgrade to Premium to Unlock:**\n"
                "✓ Unlimited downloads with no daily limits\n"
                "✓ Lossless FLAC & 320kbps MP3 audio\n"
                "✓ Full album & playlist batch downloads\n"
                "✓ High-speed priority queue\n"
                "✓ All music platforms enabled"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 View Premium Plans", callback_data="view_plans")],
                [InlineKeyboardButton("⬅️ Back", callback_data="main_menu")]
            ])

        await safe_edit_or_reply(message_or_cb, text, reply_markup=kb, client=self.app)

    async def show_premium_plans_screen(self, message_or_cb):
        """Displays Premium Plans UI matching Phase 11 specifications."""
        plans = get_premium_plans()
        text = (
            "👑 **Premium Plans**\n"
            "Get more features, higher limits and lossless audio quality.\n\n"
            "**Available Plans:**\n"
        )
        plan_buttons = []
        for p in plans:
            badge = f" ({p['badge']})" if p.get("badge") else ""
            savings = f" — `{p['savings']}`" if p.get("savings") else ""
            text += f"• **{p['name']}**: {p['symbol']}{p['price']}{savings}{badge}\n"
            btn_label = f"Select {p['name']} — {p['symbol']}{p['price']}"
            plan_buttons.append([InlineKeyboardButton(btn_label, callback_data=f"buy_plan_{p['id']}")])

        text += (
            "\n**Included Premium Benefits:**\n"
            "✓ Unlimited downloads with no daily limit\n"
            "✓ Studio-grade MP3 & Lossless FLAC quality\n"
            "✓ All enabled platforms (Spotify, YouTube, JioSaavn, SoundCloud, Deezer)\n"
            "✓ Batch album & playlist downloads\n"
            "✓ High-speed priority download queue"
        )

        plan_buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="main_menu")])
        kb = InlineKeyboardMarkup(plan_buttons)
        await safe_edit_or_reply(message_or_cb, text, reply_markup=kb, client=self.app)

    async def show_plan_checkout(self, callback_query: CallbackQuery, plan_id: str):
        """Initiates plan purchase without granting fake instant premium."""
        user_id = callback_query.from_user.id
        order = await payment_manager.initiate_plan_purchase(user_id, plan_id)
        if not order:
            await safe_answer_callback(callback_query, text="Plan not found", show_alert=True)
            return

        upi_id = getattr(Config, "PAYMENT_UPI_ID", "icecube@upi")
        text = (
            f"💳 **Subscription Invoice: {order.plan_name}**\n\n"
            f"• **Order ID:** `{order.order_id}`\n"
            f"• **Plan:** {order.plan_name} ({order.duration})\n"
            f"• **Amount:** ₹{order.amount}\n"
            f"• **Status:** Pending Verification\n\n"
            "**How to Complete Payment:**\n"
            f"1. Pay **₹{order.amount}** via UPI to:\n"
            f"   `{upi_id}` (Tap to copy)\n"
            f"2. Add Note / Remarks: `SpotiVerse_{order.order_id}`\n"
            "3. Send your payment screenshot or UTR number to @icecube9608 along with your Order ID.\n\n"
            "⚡ _Your account will be upgraded immediately upon verification._"
        )
        kb = [
            [InlineKeyboardButton("⬅️ Back to Plans", callback_data="view_plans")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        await safe_edit_or_reply(callback_query, text, reply_markup=InlineKeyboardMarkup(kb), client=self.app)

    # -------------------------
    # Admin Panel Commands
    # -------------------------
    async def admin_command(self, client: Client, message: Message):
        if not message.from_user:
            return
        user_id = message.from_user.id
        if not Config.is_owner(user_id):
            await message.reply_text("❌ You are not authorized to access the admin panel.")
            return

        await self.admin_panel.show_main_menu(message)

    def _parse_duration(self, raw_duration: str) -> tuple[float, str]:
        raw = raw_duration.strip().lower()
        if raw in ("lifetime", "perm", "permanent", "unlimited", "forever"):
            return 36500.0, "Lifetime"

        match = re.match(r"^(\d+(?:\.\d+)?)\s*([a-z]*)$", raw)
        if not match:
            raise ValueError(f"Invalid duration format '{raw_duration}'. Examples: 12h, 7d, 2w, 1m, 1y, lifetime")

        val = float(match.group(1))
        unit = match.group(2)

        if not unit or unit in ("d", "day", "days"):
            days = val
            friendly = f"{int(val) if val.is_integer() else val} day(s)"
        elif unit in ("h", "hr", "hrs", "hour", "hours"):
            days = val / 24.0
            friendly = f"{int(val) if val.is_integer() else val} hour(s)"
        elif unit in ("w", "wk", "wks", "week", "weeks"):
            days = val * 7.0
            friendly = f"{int(val) if val.is_integer() else val} week(s)"
        elif unit in ("m", "mo", "mon", "month", "months"):
            days = val * 30.0
            friendly = f"{int(val) if val.is_integer() else val} month(s)"
        elif unit in ("y", "yr", "yrs", "year", "years"):
            days = val * 365.0
            friendly = f"{int(val) if val.is_integer() else val} year(s)"
        else:
            raise ValueError(f"Unknown duration unit '{unit}'. Use h, d, w, m, y, or lifetime.")

        return days, friendly

    async def add_premium_command(self, client: Client, message: Message):
        if not Config.is_authorized(message):
            await message.reply_text("❌ This command is for bot owner only.")
            return
        try:
            parts = _get_command_parts(message)
            user_id = None
            raw_duration = "30d"

            has_reply = bool(message.reply_to_message and getattr(message.reply_to_message, "from_user", None))

            if has_reply:
                user_id = message.reply_to_message.from_user.id
                if len(parts) >= 2:
                    raw_duration = parts[1]
            else:
                if len(parts) < 2:
                    await message.reply_text(
                        "ℹ️ **Usage:**\n"
                        "• `/add_premium <user_id|@username> [duration]`\n"
                        "• Reply to a user with `/add_premium [duration]`\n\n"
                        "**Duration examples:** `12h`, `7d`, `2w`, `1m`, `1y`, `lifetime` (default: `30d`)"
                    )
                    return
                user_raw = parts[1]
                if len(parts) >= 3:
                    raw_duration = parts[2]

                if user_raw.lstrip('-').isdigit():
                    user_id = int(user_raw)
                else:
                    try:
                        user_obj = await client.get_users(user_raw)
                        user_id = user_obj.id
                    except Exception as e:
                        await message.reply_text(f"❌ Could not find user `{user_raw}`: {e}")
                        return

            try:
                days, friendly_duration = self._parse_duration(raw_duration)
            except ValueError as ve:
                await message.reply_text(f"❌ {ve}")
                return

            admin_id = message.from_user.id if message.from_user else 0
            premium_until = db.add_premium(user_id, days, plan_name=friendly_duration, admin_id=admin_id)
            expiry_str = premium_until.strftime('%Y-%m-%d %H:%M UTC') if days < 36500 else "Permanent / Lifetime"

            try:
                await client.send_message(
                    user_id,
                    f"🎉 **You've been granted Premium Access!**\n\n"
                    f"⏱ **Duration:** {friendly_duration}\n"
                    f"📅 **Valid Until:** `{expiry_str}`\n\n"
                    f"Enjoy unlimited downloads and all premium features!"
                )
            except Exception:
                pass

            duration_days_int = int(days) if days >= 1 else 1
            await self.logger.log_premium_change(user_id, "added", duration_days_int)

            await message.reply_text(
                f"✅ **Premium access granted!**\n\n"
                f"👤 **User ID:** `{user_id}`\n"
                f"⏱ **Duration:** {friendly_duration}\n"
                f"📅 **Premium valid until:** `{expiry_str}`"
            )
        except Exception as e:
            logger.error(f"Error in add_premium: {e}", exc_info=True)
            await message.reply_text(f"❌ Error: {e}")

    async def remove_premium_command(self, client: Client, message: Message):
        if not Config.is_authorized(message):
            await message.reply_text("❌ This command is for bot owner only.")
            return
        try:
            parts = _get_command_parts(message)
            user_id = None

            has_reply = bool(message.reply_to_message and getattr(message.reply_to_message, "from_user", None))

            if has_reply:
                user_id = message.reply_to_message.from_user.id
            else:
                if len(parts) < 2:
                    await message.reply_text(
                        "ℹ️ **Usage:**\n"
                        "• `/remove_premium <user_id|@username>`\n"
                        "• Reply to a user with `/remove_premium`"
                    )
                    return
                user_raw = parts[1]
                if user_raw.lstrip('-').isdigit():
                    user_id = int(user_raw)
                else:
                    try:
                        user_obj = await client.get_users(user_raw)
                        user_id = user_obj.id
                    except Exception as e:
                        await message.reply_text(f"❌ Could not find user `{user_raw}`: {e}")
                        return

            admin_id = message.from_user.id if message.from_user else 0
            db.remove_premium(user_id, admin_id=admin_id)

            try:
                await client.send_message(
                    user_id,
                    "ℹ️ **Your premium access has been removed.**\n\n"
                    "You can still use the bot with free limitations."
                )
            except Exception:
                pass

            await self.logger.log_premium_change(user_id, "removed")
            await message.reply_text(f"✅ Premium access removed from user `{user_id}`.")
        except Exception as e:
            logger.error(f"Error in remove_premium: {e}", exc_info=True)
            await message.reply_text(f"❌ Error: {e}")

    async def premiummode_command(self, client: Client, message: Message):
        if not Config.is_authorized(message):
            await message.reply_text("❌ This command is for bot owner only.")
            return

        parts = _get_command_parts(message)
        admin_id = message.from_user.id if message.from_user else 0

        if len(parts) < 2:
            current_mode = db.get_premium_mode()
            status_desc = "🔒 **ENABLED (Strict Mode)** — Premium features restricted to premium users only." if current_mode else "🔓 **DISABLED (Public Mode)** — All features UNLOCKED for EVERY user!"
            await message.reply_text(
                f"⚙️ **Premium Mode Setting:**\n\n"
                f"• Status: {status_desc}\n"
                f"• Current value: `{current_mode}`\n\n"
                f"**How to change:**\n"
                f"• `/premiummode true` (Enable strict premium requirements)\n"
                f"• `/premiummode false` (Unlock all features for everyone)"
            )
            return

        action = parts[1].strip().lower()
        if action in ("true", "on", "enable", "1", "yes", "t"):
            db.set_bot_setting("premium_system", True, admin_id=admin_id)
            await message.reply_text(
                "🔒 **Premium Mode is now ENABLED (True)**\n\n"
                "• Advanced features are now restricted to **Premium Users** only.\n"
                f"• Free users are subject to daily limits ({Config.FREE_USER_DAILY_LIMIT} downloads/day)."
            )
        elif action in ("false", "off", "disable", "0", "no", "f"):
            db.set_bot_setting("premium_system", False, admin_id=admin_id)
            await message.reply_text(
                "🔓 **Premium Mode is now DISABLED (False)**\n\n"
                "🎉 **All features are now UNLOCKED for ALL users!**\n"
                "• Unlimited downloads for everyone (no daily limits)\n"
                "• Direct `/download <url>` unlocked for everyone\n"
                "• Album & playlist downloads unlocked for everyone\n"
                "• `/settings` (FLAC & 320kbps MP3) unlocked for everyone"
            )
        else:
            await message.reply_text("❌ Invalid option. Use `/premiummode true` or `/premiummode false`.")

    async def logs_command(self, client, message: Message):
        if not Config.is_authorized(message):
            await message.reply_text("❌ This command is for bot owner only.")
            return

        log_path = os.path.join(os.getcwd(), "bot.log")
        clear_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🗑️ Clear Logs", callback_data="clear_logs")]])

        try:
            if os.path.exists(log_path):
                file_size = os.path.getsize(log_path)
                if file_size <= 40 * 1024 * 1024:
                    await message.reply_document(
                        document=log_path,
                        caption=f"📄 **Latest bot logs** ({file_size / 1024:.1f} KB)",
                        reply_markup=clear_kb
                    )
                else:
                    tail_path = "temp/bot_tail.log"
                    os.makedirs("temp", exist_ok=True)
                    with open(log_path, "r", encoding="utf-8", errors="ignore") as src:
                        lines = src.readlines()[-10000:]
                    with open(tail_path, "w", encoding="utf-8") as dst:
                        dst.writelines(lines)
                    await message.reply_document(
                        document=tail_path,
                        caption="📄 **Latest bot logs (last 10,000 lines)**",
                        reply_markup=clear_kb
                    )
            else:
                await message.reply_text("⚠️ Log file not found.")
        except Exception as e:
            logger.error(f"Error sending logs: {e}", exc_info=True)
            await message.reply_text(f"❌ Could not send logs: {e}")

    async def stats_command(self, client: Client, message: Message):
        if not Config.is_authorized(message):
            await message.reply_text("❌ This command is for bot owner only.")
            return
        await self.admin_panel.show_statistics(message, period="30d")

    async def users_command(self, client: Client, message: Message):
        if not Config.is_authorized(message):
            await message.reply_text("❌ This command is for bot owner only.")
            return

        parts = _get_command_parts(message)
        if len(parts) > 1 and parts[1].isdigit():
            await self.userinfo_command(client, message)
            return

        try:
            stats = db.get_statistics("30d")
            text = (
                "👥 **SpotiVerse User Statistics**\n\n"
                f"👤 **Total Users:** `{stats['total_users']:,}`\n"
                f"💎 **Premium Users:** `{stats['premium_users']:,}`\n"
                f"🆓 **Free Users:** `{stats['free_users']:,}`\n"
                f"⚡ **Active Users (30d):** `{stats['active_users']:,}`\n"
                f"📥 **Total Downloads:** `{stats['total_downloads']:,}`\n\n"
                "💡 _Use `/userinfo <user_id>` to view details for a specific user._"
            )
            await message.reply_text(text)
        except Exception as e:
            logger.error(f"Error in users_command: {e}", exc_info=True)
            await message.reply_text(f"❌ Failed to get user statistics: {e}")

    async def broadcast_command(self, client: Client, message: Message):
        if not Config.is_authorized(message):
            await message.reply_text("❌ This command is for bot owner only.")
            return
        parts = _get_command_parts(message)
        if len(parts) < 2:
            await message.reply_text("Usage: `/broadcast <message>`")
            return
        broadcast_msg = " ".join(parts[1:])
        confirm_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes", callback_data="broadcast_confirm")],
            [InlineKeyboardButton("❌ Cancel", callback_data="broadcast_cancel")]
        ])
        await message.reply_text(
            f"📢 **Broadcast Confirmation**\n\nMessage: {broadcast_msg}\n\nAre you sure?",
            reply_markup=confirm_keyboard
        )

    # -------------------------
    # Unified Callback Handler
    # -------------------------
    async def handle_callback(self, client: Client, callback_query: CallbackQuery):
        data = (callback_query.data or "").strip()
        if not callback_query.from_user:
            await safe_answer_callback(callback_query, text="User not found")
            return
        user_id = callback_query.from_user.id
        from_user = callback_query.from_user
        username = getattr(from_user, "username", None)
        first_name = getattr(from_user, "first_name", "there") or "there"

        # Update user profile
        try:
            updates = {"first_name": first_name, "display_name": first_name}
            if username:
                updates["username"] = username
            db.update_user(user_id, updates)
        except Exception:
            pass

        # 1. Check if callback belongs to Admin Panel module
        if data.startswith("adm_") or data in ("clear_logs",):
            await self.admin_panel.handle_callback(client, callback_query)
            return

        # 2. Plan Purchase Callbacks
        if data == "view_plans":
            await safe_answer_callback(callback_query)
            await self.show_premium_plans_screen(callback_query)
            return

        if data.startswith("buy_plan_"):
            plan_id = data.replace("buy_plan_", "")
            await safe_answer_callback(callback_query)
            await self.show_plan_checkout(callback_query, plan_id)
            return

        if data == "user_profile":
            await safe_answer_callback(callback_query)
            await self.show_user_premium_screen(callback_query, user_id)
            return

        # 3. Main Menu / Back
        if data in ("back", "main_menu"):
            await safe_answer_callback(callback_query)
            display_name = _display_name_from_callback(callback_query)
            rec = db.get_user(user_id) or {}
            prem_mode = db.get_premium_mode()
            is_premium = db.is_premium(user_id)
            start_kb = _build_start_keyboard(user_id)

            if not prem_mode:
                text = (
                    f"👋 Hello **{display_name}**!\n\n"
                    "Welcome to **SpotiVerse Bot**!\n\n"
                    "I can download high-quality audio from:\n"
                    "• **Spotify** • **YouTube** • **JioSaavn** • **SoundCloud** • **Deezer**\n\n"
                    "**Your Status:** ✨ All Features Unlocked (Public Mode)\n"
                    "**Downloads:** Unlimited ♾️ (No daily limit)"
                )
            else:
                text = (
                    f"👋 Hello **{display_name}**!\n\n"
                    "Welcome to **SpotiVerse Bot**!\n\n"
                    f"**Your Status:** {'👑 Premium Member' if is_premium else '👤 Free Member'}\n"
                )
                if is_premium:
                    until_dt = _parse_datetime(rec.get("premium_until"))
                    rem_str = _format_time_remaining(until_dt) if not rec.get("lifetime_premium") else "Lifetime Access ♾️"
                    text += f"**Validity:** `{rem_str}`\n**Downloads:** Unlimited ♾️"
                else:
                    text += f"**Free Limits:** {rec.get('downloads_today', 0)}/{Config.FREE_USER_DAILY_LIMIT} downloads today\n\n👑 Upgrade to premium for unlimited downloads & FLAC audio!"

            await safe_edit_or_reply(callback_query, text, reply_markup=start_kb, client=self.app)
            return

        # 4. Premium info callback
        if data == "premium_info" or data.startswith("premium_"):
            await safe_answer_callback(callback_query)
            await self.show_user_premium_screen(callback_query, user_id)
            return

        # 5. Menu Download
        if data == "menu_download":
            await safe_answer_callback(callback_query)
            text = (
                "🔎 **Search & Download Music**\n\n"
                "Send me a song name or Spotify/YouTube/JioSaavn link to search & download.\n\n"
                "Examples:\n"
                "• `/search blinding lights`\n"
                "• `faded alan walker`\n"
                "• `https://open.spotify.com/track/...`"
            )
            kb = [[InlineKeyboardButton("⬅️ Back", callback_data="main_menu")]]
            await safe_edit_or_reply(callback_query, text, reply_markup=InlineKeyboardMarkup(kb), client=self.app)
            return

        # 6. Menu Settings
        if data == "menu_settings":
            await safe_answer_callback(callback_query)
            if not db.is_premium(user_id):
                txt = "⚙️ Settings are available for Premium users only.\nUpgrade to access lossless FLAC, 320kbps MP3, and priority queue."
                kb = [[InlineKeyboardButton("💎 View Premium Plans", callback_data="view_plans")], [InlineKeyboardButton("⬅️ Back", callback_data="main_menu")]]
                await safe_edit_or_reply(callback_query, txt, reply_markup=InlineKeyboardMarkup(kb), client=self.app)
                return

            rec = db.get_user(user_id) or {}
            await safe_edit_or_reply(callback_query, "⚙️ **Settings**\n\nConfigure your download preferences:", reply_markup=_settings_keyboard_for(rec), client=self.app)
            return

        # 7. Menu Help
        if data == "menu_help":
            await safe_answer_callback(callback_query)
            help_text = (
                "❓ **SpotiVerse Help & Guide**\n\n"
                "1. **Search**: Send any song name or use `/search <query>`\n"
                "2. **Download**: Click any search result or send a direct URL\n"
                "3. **Supported Platforms**: Spotify, YouTube, JioSaavn, SoundCloud, Deezer\n"
                "4. **Formats**: High-bitrate MP3 (320kbps) & Lossless FLAC\n"
                "5. **Premium**: Unlimited downloads & albums with no queues!"
            )
            kb = [[InlineKeyboardButton("👑 View Premium Plans", callback_data="view_plans")], [InlineKeyboardButton("⬅️ Back", callback_data="main_menu")]]
            await safe_edit_or_reply(callback_query, help_text, reply_markup=InlineKeyboardMarkup(kb), client=self.app)
            return

        # 8. Settings toggles
        if data.startswith("setting_"):
            await self._handle_settings_callback(callback_query)
            return

        # 9. Download action from search results
        if data.startswith("download_"):
            parts = data.split("_", 2)
            if len(parts) >= 3:
                provider = parts[1]
                tid = parts[2]
                try:
                    msg = await callback_query.message.reply_text("🔄 Processing your download...")
                    await self.download_handler.download_track(provider, tid, user_id, msg)
                except Exception as e:
                    logger.error(f"Failed starting download via callback: {e}")
            return

        # 10. Broadcast callbacks
        if data in ("broadcast_confirm", "broadcast_cancel"):
            await self._handle_broadcast_callback(callback_query)
            return

        # 11. Search cancel & pagination
        if data == "cancel_search":
            try:
                await callback_query.message.delete()
            except Exception:
                pass
            await safe_answer_callback(callback_query, text="Search cancelled")
            return

        if data.startswith("search_page_"):
            await safe_answer_callback(callback_query)
            return

        logger.debug(f"Unhandled callback: {data}")

    async def _handle_settings_callback(self, callback_query: CallbackQuery):
        data = callback_query.data or ""
        if not callback_query.from_user:
            return
        user_id = callback_query.from_user.id
        is_premium = db.is_premium(user_id) or Config.is_owner(user_id)
        rec = db.get_user(user_id) or {}

        if data == "setting_format_info":
            await safe_answer_callback(
                callback_query,
                text="ℹ️ Free users can download MP3. Upgrade to Premium to unlock FLAC, M4A, OGG, and WAV!",
                show_alert=True
            )
            return

        if data == "setting_format":
            allowed_formats = AudioProfile.get_allowed_formats(is_premium=is_premium)
            if len(allowed_formats) <= 1:
                await safe_answer_callback(
                    callback_query,
                    text="💎 Upgrade to Premium to unlock Lossless FLAC, M4A, OGG, and Studio WAV formats!",
                    show_alert=True
                )
                return
            cur_fmt = str(rec.get("preferred_format", "mp3")).lower().strip()
            if cur_fmt not in allowed_formats:
                cur_fmt = allowed_formats[0]
            next_idx = (allowed_formats.index(cur_fmt) + 1) % len(allowed_formats)
            new_fmt = allowed_formats[next_idx]
            new_q = AudioProfile.get_default_quality(new_fmt, is_premium=is_premium)
            db.update_user(user_id, {"preferred_format": new_fmt, "preferred_quality": new_q})
            await safe_answer_callback(callback_query, text=f"Format set to {new_fmt.upper()}")
            new_text = "⚙️ **Settings**\n\nConfigure your download preferences:"
            new_markup = _settings_keyboard_for(db.get_user(user_id))
            await safe_edit_or_reply(callback_query, new_text, reply_markup=new_markup, client=self.app)
            return

        if data == "setting_quality":
            cur_fmt = str(rec.get("preferred_format", "mp3")).lower().strip()
            allowed_qualities = AudioProfile.get_allowed_qualities(cur_fmt, is_premium=is_premium)
            cur_q = rec.get("preferred_quality", AudioProfile.get_default_quality(cur_fmt, is_premium))
            curr_q_str = str(cur_q).lower().strip()
            match_idx = -1
            for i, q in enumerate(allowed_qualities):
                if str(q).lower().strip() == curr_q_str:
                    match_idx = i
                    break
            if match_idx == -1:
                new_q = allowed_qualities[0]
            else:
                new_q = allowed_qualities[(match_idx + 1) % len(allowed_qualities)]
            db.update_user(user_id, {"preferred_quality": new_q})
            q_label = AudioProfile.format_quality_label(cur_fmt, new_q)
            await safe_answer_callback(callback_query, text=f"Quality set to {q_label}")
            new_text = "⚙️ **Settings**\n\nConfigure your download preferences:"
            new_markup = _settings_keyboard_for(db.get_user(user_id))
            await safe_edit_or_reply(callback_query, new_text, reply_markup=new_markup, client=self.app)
            return

    async def _handle_broadcast_callback(self, callback_query: CallbackQuery):
        data = callback_query.data or ""
        if not Config.is_authorized_callback(callback_query):
            await safe_answer_callback(callback_query, text="❌ Unauthorized", show_alert=True)
            return

        if data == "broadcast_confirm":
            try:
                orig = callback_query.message.text or ""
                if "Message: " in orig:
                    broadcast_msg = orig.split("Message: ", 1)[1]
                    if "\n\nAre you sure?" in broadcast_msg:
                        broadcast_msg = broadcast_msg.rsplit("\n\nAre you sure?", 1)[0]
                elif "Message Content:\n" in orig:
                    broadcast_msg = orig.split("Message Content:\n", 1)[1].split("\n\nAre you sure?", 1)[0]
                else:
                    broadcast_msg = orig
            except Exception:
                broadcast_msg = "Announcement from admin"

            # Retrieve user list
            users_list = []
            if db.available and db.users is not None:
                try:
                    users_list = list(db.users.find({}, {"user_id": 1}))
                except Exception:
                    pass
            if not users_list:
                from utils.db import _fallback_store
                users_list = [{"user_id": uid} for uid in _fallback_store.get("users", {}).keys()]

            total_users = len(users_list)
            progress_msg = await callback_query.message.edit_text(f"📢 Broadcasting... 0/{total_users}")
            success, fail = 0, 0
            for i, u in enumerate(users_list, 1):
                uid = u.get("user_id") or u.get("_id") or None
                if not uid:
                    continue
                try:
                    await self.app.send_message(uid, f"📢 **Broadcast**\n\n{broadcast_msg}")
                    success += 1
                except Exception:
                    fail += 1
                await asyncio.sleep(0.04)
                if i % 25 == 0 or i == total_users:
                    try:
                        await progress_msg.edit_text(f"📢 Broadcasting... {i}/{total_users}\n✅ Successful: {success}\n❌ Failed/Blocked: {fail}")
                    except Exception:
                        pass
            try:
                await progress_msg.edit_text(f"✅ **Broadcast Complete**\n\n👥 Total Recipients: {total_users}\n✅ Successful: {success}\n❌ Failed/Blocked: {fail}")
            except Exception:
                pass
            await safe_answer_callback(callback_query)
            return

        if data == "broadcast_cancel":
            await safe_edit_or_reply(callback_query, "❌ Broadcast cancelled.", client=self.app)
            await safe_answer_callback(callback_query)
            return


class CommandHandler(CommandsBinder):
    """
    Compatibility wrapper for CommandHandler(bot, logger, search_handler, download_handler)
    """
    def __init__(self, bot, logger: BotLogger, search_handler: SearchHandler, download_handler: DownloadHandler):
        super().__init__(bot, search_handler, download_handler, logger)

def setup_handlers(app: Client, search_handler: SearchHandler, download_handler: DownloadHandler, logger_obj: BotLogger = None):
    CommandsBinder(app, search_handler, download_handler, logger_obj)
    logger.info("Command handlers registered (setup_handlers).")

