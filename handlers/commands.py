# handlers/commands.py
import os
import logging
import asyncio
from datetime import datetime
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
from info import DEFAULT_SETTINGS
from config import Config
from utils.db import db
from utils.logger import BotLogger
from handlers.search import SearchHandler
from handlers.downloads import DownloadHandler
from pyrogram.types import InputMediaDocument

logger = logging.getLogger(__name__)


# ----------------------
# Small helpers
# ----------------------
async def safe_answer_callback(callback_query: Optional[CallbackQuery], **kwargs):
    """
    Safely answer callback queries. Ignore QUERY_ID_INVALID and some benign errors.
    """
    if not callback_query:
        return
    try:
        await callback_query.answer(**kwargs)
    except Exception as e:
        serr = str(e).lower()
        if "query_id_invalid" in serr or "query id invalid" in serr:
            logger.debug("Ignored QUERY_ID_INVALID when answering callback query.")
            return
        if "peer_id_invalid" in serr or "user_is_blocked" in serr:
            logger.debug(f"Ignored callback answer error: {serr}")
            return
        logger.warning(f"Failed to answer callback query: {e}")


def _display_name_from_user_obj(user_obj) -> str:
    if not user_obj:
        return "there"
    return (user_obj.first_name or user_obj.username or "there").strip()


def _display_name_from_callback(callback_query: CallbackQuery) -> str:
    # prefer clicking user
    try:
        u = callback_query.from_user
        if u and (u.first_name or u.username):
            return _display_name_from_user_obj(u)
    except Exception:
        pass

    # fallback to DB-stored display name
    try:
        rec = db.get_user(callback_query.from_user.id)
        if rec and rec.get("display_name"):
            return rec.get("display_name")
    except Exception:
        pass

    return "there"


def _build_start_keyboard() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("📥 Download", callback_data="menu_download")],
        [InlineKeyboardButton("💎 Premium Info", callback_data="premium_info")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="menu_settings")],
    ]
    return InlineKeyboardMarkup(kb)


def _build_premium_markup() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("⬅️ Back", callback_data="back")],
    ]
    return InlineKeyboardMarkup(kb)


def _settings_keyboard_for(user: dict) -> InlineKeyboardMarkup:
    current_format = user.get("preferred_format", "mp3")
    current_quality = user.get("preferred_quality", 320)

    if current_format == "mp3":
        format_text = "Format: MP3 → FLAC"
    else:
        format_text = "Format: FLAC → MP3"

    if current_format == "mp3":
        qualities = [64, 128, 192, 256, 320]
        cur = current_quality if isinstance(current_quality, int) else 320
        next_q = qualities[(qualities.index(cur) + 1) % len(qualities)] if cur in qualities else qualities[-1]
        quality_text = f"Quality: {cur} → {next_q}"
    else:
        qualities = ["low", "medium", "high"]
        cur = str(current_quality)
        next_q = qualities[(qualities.index(cur) + 1) % len(qualities)] if cur in qualities else qualities[-1]
        quality_text = f"Quality: {cur} → {next_q}"

    kb = [
        [InlineKeyboardButton(format_text, callback_data="setting_format")],
        [InlineKeyboardButton(quality_text, callback_data="setting_quality")],
        [InlineKeyboardButton("🔙 Back", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(kb)


# ----------------------
# Binder class: registers handlers on a pyrogram.Client
# ----------------------
class CommandsBinder:
    """
    Create an instance with the running Client, SearchHandler and DownloadHandler.
    It registers message & callback handlers on the Client.
    """
    def __init__(self, app: Client, search_handler: SearchHandler, download_handler: DownloadHandler, logger_obj: BotLogger = None):
        self.app = app
        self.search_handler = search_handler
        self.download_handler = download_handler
        self.logger = logger_obj or BotLogger(app)

        # register message handlers as Handler objects (correct API)
        # MessageHandler(callback, filters)
        app.add_handler(MessageHandler(self._on_start_wrapper, filters.command("start")))
        app.add_handler(MessageHandler(self._on_search_wrapper, filters.command("search")))
        app.add_handler(MessageHandler(self._on_help_wrapper, filters.command("help")))
        app.add_handler(MessageHandler(self._on_settings_wrapper, filters.command("settings")))
        app.add_handler(MessageHandler(self._on_download_wrapper, filters.command("download")))
        app.add_handler(MessageHandler(self._on_userinfo_wrapper, filters.command("userinfo")))
        app.add_handler(MessageHandler(self._on_premium_wrapper, filters.command("premium")))
        app.add_handler(MessageHandler(self._on_addpremium_wrapper, filters.command("addpremium")))
        app.add_handler(MessageHandler(self._on_removepremium_wrapper, filters.command("removepremium")))
        app.add_handler(MessageHandler(self._on_stats_wrapper, filters.command("stats")))
        app.add_handler(MessageHandler(self._on_broadcast_wrapper, filters.command("broadcast")))

        # CallbackQuery handler (single)
        app.add_handler(CallbackQueryHandler(self._on_callback_wrapper))

        logger.info("Command handlers registered on Client.")

    # thin wrappers to match handler signature
    async def _on_start_wrapper(self, client: Client, message: Message):
        await self.start_command(client, message)

    async def _on_search_wrapper(self, client: Client, message: Message):
        await self.search_command(client, message)

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

    async def _on_addpremium_wrapper(self, client: Client, message: Message):
        await self.add_premium_command(client, message)

    async def _on_removepremium_wrapper(self, client: Client, message: Message):
        await self.remove_premium_command(client, message)

    async def _on_stats_wrapper(self, client: Client, message: Message):
        await self.stats_command(client, message)

    async def _on_broadcast_wrapper(self, client: Client, message: Message):
        await self.broadcast_command(client, message)

    async def _on_callback_wrapper(self, client: Client, callback_query: CallbackQuery):
        await self.handle_callback(client, callback_query)

    # -------------------------
    # Command implementations
    # -------------------------
    async def start_command(self, client: Client, message: Message):
        user_id = message.from_user.id
        first_name = getattr(message.from_user, "first_name", "there")

        # ensure user record exists and update display name/join_date
        rec = db.get_user(user_id) or {}
        try:
            db.update_user(user_id, {"display_name": first_name, "join_date": rec.get("join_date") or datetime.utcnow()})
        except Exception:
            logger.debug("Failed to update user record with display_name/join_date", exc_info=True)

        # log new user
        try:
            await self.logger.log_new_user(user_id, getattr(message.from_user, "username", None), first_name)
        except Exception:
            logger.debug("Could not log new user")

        rec = db.get_user(user_id) or {}
        is_premium = bool(rec.get("premium"))
        welcome_text = (
            f"👋 Hello {first_name}!\n\n"
            f"Welcome to **SpotiVerse Bot**!\n\n"
            "I can download high-quality audio from various platforms including:\n"
            "• Spotify\n• YouTube\n• JioSaavn\n\n"
            f"**Your Status:** {'Premium 🎉' if is_premium else 'Free User'}\n"
        )
        if is_premium and rec.get("premium_until"):
            try:
                tu = rec.get("premium_until")
                if isinstance(tu, datetime):
                    welcome_text += f"**Premium Until:** {tu.strftime('%Y-%m-%d')}\n\n"
                else:
                    welcome_text += f"**Premium Until:** {str(tu)}\n\n"
            except Exception:
                pass
        else:
            welcome_text += f"**Free Limits:** {rec.get('downloads_today', 0)}/{Config.FREE_USER_DAILY_LIMIT} downloads today\n\nUpgrade to premium for unlimited downloads and more features!\n"

        try:
            await message.reply_text(welcome_text, reply_markup=_build_start_keyboard())
        except Exception:
            try:
                await message.edit_text(welcome_text, reply_markup=_build_start_keyboard())
            except Exception as e:
                logger.warning(f"Failed to deliver welcome message: {e}")

    async def search_command(self, client: Client, message: Message):
        if len(message.command) < 2:
            await message.reply_text("Usage: /search <query>\nExample: `/search blinding lights`")
            return
        query = " ".join(message.command[1:]).strip()
        loading_msg = await message.reply_text(f"🔎 Searching for: **{query}** ...")
        try:
            tracks = await self.search_handler.search_all(query, limit=10)
            if not tracks:
                await loading_msg.edit_text("❌ No results found.")
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
            try:
                await self.logger.log_to_channel(f"Search error for user {message.from_user.id}: {e}")
            except Exception:
                pass
            await loading_msg.edit_text(f"❌ Search failed: {e}")

    async def help_command(self, client: Client, message: Message):
        help_text = (
            "🤖 **SpotiVerse Bot Commands**\n\n"
            "**User Commands:**\n"
            "/start - Start the bot\n"
            "/help - Show this help message\n"
            "/settings - Configure your preferences (Premium only)\n"
            "/userinfo - Show your user information\n"
            "/premium - Show premium information\n\n"
            "**Download Commands:**\n"
            "/search <query> - Search for music\n"
            "/download <url> - Download from supported URLs (Premium only for albums)\n\n"
            "Need support? Contact @icecube9680"
        )
        await message.reply_text(help_text)

    async def settings_command(self, client: Client, message: Message):
        user_id = message.from_user.id
        rec = db.get_user(user_id) or {}
        if not rec.get("premium"):
            await message.reply_text("❌ Settings are available to Premium users only.\n\nUpgrade to premium to access advanced settings and higher quality downloads.")
            return
        await message.reply_text("⚙️ **Settings**\n\nConfigure your download preferences:", reply_markup=_settings_keyboard_for(rec))

    async def handle_callback(self, client: Client, callback_query: CallbackQuery):
        """
        Unified callback handler for inline buttons.
        Handles:
        - premium_info / premium_*
        - back / main_menu
        - menu_download (open download prompt)
        - menu_settings (open settings or show message)
        - setting_* (format/quality toggles)
        - download_{provider}_{id}
        - broadcast_confirm / cancel
        """
        data = (callback_query.data or "").strip()
        user_id = callback_query.from_user.id if callback_query.from_user else None

        # Quick ACK to stop the spinner
        await safe_answer_callback(callback_query)

        # --- 1) Premium info flow ---
        if data == "premium_info" or data.startswith("premium_"):
            try:
                # Fetch user record
                rec = db.get_user(user_id)

                premium_text = (
                    "💎 **Premium Features**\n\n"
                    "• **Unlimited downloads** - No daily limits\n"
                    "• **Advanced search** - Search across multiple platforms\n"
                    "• **High quality audio** - FLAC and high-bitrate MP3\n"
                    "• **Batch downloads** - Download albums and playlists\n"
                    "• **Priority support** - Faster response times\n\n"
                )

                if rec.get("premium"):
                    tu = rec.get("premium_until")
                    try:
                        premium_text += f"**Your premium is active until:** {tu.strftime('%Y-%m-%d')}\n\n"
                    except Exception:
                        premium_text += f"**Your premium is active until:** {str(tu)}\n\n"
                else:
                    premium_text += (
                        "**Free Account Limitations:**\n"
                        f"• {Config.FREE_USER_DAILY_LIMIT} downloads per day\n"
                        "**To upgrade to premium,** contact @icecube9680\n"
                        f"**User ID**: `{user_id}`"
                    )

                await callback_query.message.edit_text(premium_text, reply_markup=_build_premium_markup())

            except Exception:
                # Fallback: send as new message if editing fails
                try:
                    await self.bot.send_message(user_id, premium_text, reply_markup=_build_premium_markup())
                except Exception as e:
                    logger.warning(f"Failed to show premium info: {e}")

            return


        # --- 2) Back / Main menu ---
        if data in ("back", "main_menu"):
            try:
                display_name = _display_name_from_callback(callback_query)
                rec = db.get_user(user_id) or {}
                is_premium = bool(rec.get("premium"))
                text = (
                    f"👋 Hello {display_name}!\n\n"
                    "Welcome to **SpotiVerse Bot**!\n\n"
                    "I can download high-quality audio from various platforms including:\n"
                    "• Spotify\n"
                    "• YouTube\n"
                    "• JioSaavn\n\n"
                    f"**Your Status:** {'Premium 🎉' if is_premium else 'Free User'}\n"
                )
                if is_premium and rec.get("premium_until"):
                    tu = rec.get("premium_until")
                    try:
                        text += f"**Premium Until:** {tu.strftime('%Y-%m-%d')}\n\n"
                    except Exception:
                        text += f"**Premium Until:** {str(tu)}\n\n"
                else:
                    text += f"**Free Limits:** {rec.get('downloads_today', 0)}/{Config.FREE_USER_DAILY_LIMIT} downloads today\n\nUpgrade to premium for unlimited downloads and more features!\n"
                try:
                    await callback_query.message.edit_text(text, reply_markup=_build_start_keyboard())
                except Exception:
                    await self.app.send_message(user_id, text, reply_markup=_build_start_keyboard())
            except Exception as e:
                logger.error(f"Error while handling back/main_menu callback: {e}", exc_info=True)
            return

        # --- 3) Start-menu: Download button ---
        if data == "menu_download":
            try:
                # Edit message to prompt the user to send a link/query.
                text = "🔎 Send me a Spotify/YouTube/JioSaavn link or a search query and I will download the track for you.\n\nExample: `blinding lights` or `https://open.spotify.com/track/...`"
                kb = [[InlineKeyboardButton("⬅️ Back", callback_data="main_menu")]]
                try:
                    await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kb))
                except Exception:
                    await self.app.send_message(user_id, text, reply_markup=InlineKeyboardMarkup(kb))
            except Exception as e:
                logger.error(f"Error handling menu_download: {e}", exc_info=True)
            return

        # --- 4) Start-menu: Settings button ---
        if data == "menu_settings":
            try:
                rec = db.get_user(user_id) or {}
                # If not premium, show alert and optionally the main settings prompt
                if not rec.get("premium"):
                    # Use show_alert so it appears as a popup
                    try:
                        await callback_query.answer("⚠️ Settings are available to Premium users only.", show_alert=True)
                    except Exception:
                        pass
                    # Optionally show a small menu with upgrade prompt
                    txt = "⚙️ Settings are available for Premium users only.\nUpgrade to access higher quality and more options."
                    kb = [[InlineKeyboardButton("💎 Premium Info", callback_data="premium_info")], [InlineKeyboardButton("⬅️ Back", callback_data="main_menu")]]
                    try:
                        await callback_query.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(kb))
                    except Exception:
                        try:
                            await self.app.send_message(user_id, txt, reply_markup=InlineKeyboardMarkup(kb))
                        except Exception:
                            pass
                    return
                # premium users -> show settings UI
                try:
                    await callback_query.message.edit_text("⚙️ **Settings**\n\nConfigure your download preferences:", reply_markup=_settings_keyboard_for(rec))
                except Exception:
                    try:
                        await self.app.send_message(user_id, "⚙️ **Settings**\n\nConfigure your download preferences:", reply_markup=_settings_keyboard_for(rec))
                    except Exception as e:
                        logger.warning(f"Failed to show settings: {e}")
            except Exception as e:
                logger.error(f"Error handling menu_settings: {e}", exc_info=True)
            return

        # --- 5) Settings toggles (existing code routes) ---
        if data.startswith("setting_"):
            await self._handle_settings_callback(callback_query)
            return

        # --- 6) Download action from search listing ---
        if data.startswith("download_"):
            parts = data.split("_", 2)
            if len(parts) >= 3:
                provider = parts[1]
                tid = parts[2]
                try:
                    # Create a new progress message
                    try:
                        msg = await callback_query.message.reply_text("🔄 Processing your download...")
                        success = await self.download_handler.download_track(provider, tid, user_id, msg)
                        if not success:
                            await msg.edit_text("❌ Failed to download track.")
                    except Exception as msg_e:
                        logger.error(f"Failed to create progress message: {msg_e}")
                        try:
                            await callback_query.answer("Failed to start download.", show_alert=True)
                        except Exception:
                            pass
                except Exception as e:
                    logger.error(f"Failed starting download via callback: {e}", exc_info=True)
                    try:
                        await callback_query.answer("Failed to start download.", show_alert=True)
                    except Exception:
                        pass
            else:
                try:
                    await callback_query.answer("Invalid download callback", show_alert=True)
                except Exception:
                    pass
            return

        # --- 7) Broadcast confirm/cancel (admin) ---
        if data in ("broadcast_confirm", "broadcast_cancel"):
            await self._handle_broadcast_callback(callback_query)
            return

        # Unknown callback (log quietly)
        logger.debug(f"Unhandled callback data: {data}")


    async def _handle_settings_callback(self, callback_query: CallbackQuery):
        data = callback_query.data or ""
        user_id = callback_query.from_user.id
        rec = db.get_user(user_id) or {}

        if not rec.get("premium"):
            try:
                await callback_query.answer("❌ Settings are for Premium users only.", show_alert=True)
            except Exception:
                pass
            return

        if data == "setting_format":
            new_format = "flac" if rec.get("preferred_format") == "mp3" else "mp3"
            db.update_user(user_id, {"preferred_format": new_format})
            if new_format == "mp3":
                db.update_user(user_id, {"preferred_quality": 320})
            else:
                db.update_user(user_id, {"preferred_quality": "high"})
            try:
                await callback_query.answer(f"Format set to {new_format.upper()}")
            except Exception:
                pass
            await callback_query.message.edit_text("⚙️ **Settings**\n\nConfigure your download preferences:", reply_markup=_settings_keyboard_for(db.get_user(user_id)))
            return

        if data == "setting_quality":
            current_format = rec.get("preferred_format", "mp3")
            current_quality = rec.get("preferred_quality", 320)
            if current_format == "mp3":
                qualities = [64, 128, 192, 256, 320]
                cur = current_quality if isinstance(current_quality, int) else 320
                new_q = qualities[(qualities.index(cur) + 1) % len(qualities)] if cur in qualities else qualities[-1]
            else:
                qualities = ["low", "medium", "high"]
                cur = str(current_quality)
                new_q = qualities[(qualities.index(cur) + 1) % len(qualities)] if cur in qualities else qualities[-1]
            db.update_user(user_id, {"preferred_quality": new_q})
            try:
                await callback_query.answer(f"Quality set to {new_q}")
            except Exception:
                pass
            # build the new text and keyboard
            new_text = "⚙️ **Settings**\n\nConfigure your download preferences:"
            new_markup = _settings_keyboard_for(db.get_user(user_id))

            try:
                await callback_query.message.edit_text(new_text, reply_markup=new_markup)
                # answer callback to close spinner / show nothing
                try:
                    await callback_query.answer()
                except Exception as e:
                    logger.debug(f"Could not answer callback after edit: {e}")
            except MessageNotModified:
                # Message already has the same content/keyboard — just answer the callback to stop spinner
                try:
                    await callback_query.answer()
                except Exception as e:
                    logger.debug(f"MessageNotModified and could not answer callback: {e}")
            except Exception as e:
                # Any other error should be logged, but don't crash the handler
                logger.warning(f"Failed to edit settings message: {e}")
                try:
                    await callback_query.answer("An error occurred")
                except Exception:
                    pass

            return

    async def download_command(self, client: Client, message: Message):
        """Handle /download command (supports single track and album/playlist for premium)"""
        user_id = message.from_user.id

        # basic validation
        if len(message.command) < 2:
            await message.reply_text(
                "Please provide a URL.\nUsage: /download link/album/playlist\n\nExample: `/download https://open.spotify.com/track/...`"
            )
            return
        url = message.command[1].strip()
        if not url.startswith(('http://', 'https://')):
            await message.reply_text(
                "❌ Please provide a valid URL starting with http:// or https://"
            )
            return

        # helper: parse provider and id
        def parse_provider_and_id(u: str):
            # spotify
            m = re.search(r"open\.spotify\.com/(track|album|playlist)/([A-Za-z0-9]+)", u)
            if m:
                return "spotify", m.group(1), m.group(2)
            # youtube: watch?v= or youtu.be
            m = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{6,})", u)
            if m:
                return "youtube", "video", m.group(1)
            # deezer album/track/playlist
            m = re.search(r"deezer\.com/(track|album|playlist)/([0-9]+)", u)
            if m:
                return "deezer", m.group(1), m.group(2)
            # soundcloud - we treat as track or set (set=playlist)
            if "soundcloud.com" in u:
                if "/sets/" in u:
                    return "soundcloud", "playlist", u
                return "soundcloud", "track", u
            # jiosaavn (song/album/playlist) - use rough detection
            if "jiosaavn.com" in u or "saavn" in u:
                if "/album/" in u or "/playlist/" in u:
                    return "jiosaavn", "album", u
                return "jiosaavn", "track", u
            # fallback
            return None, None, None

        provider, kind, tid = parse_provider_and_id(url)
        if not provider:
            await message.reply_text(
                "❌ Could not detect provider or ID from the URL. Supported: Spotify, YouTube, Deezer, SoundCloud, JioSaavn."
            )
            return

        # Determine if this request is album/playlist (i.e., multi-track)
        is_collection = kind in ("album", "playlist", "set")

        # Check user's download quota
        try:
            allowed, reason = db.can_download(user_id)
        except Exception as e:
            logger.warning(f"Error checking can_download for {user_id}: {e}")
            await message.reply_text("⚠️ Could not verify download quota. Try again later.")
            return

        if not allowed:
            await message.reply_text(f"❌ Cannot download: {reason}")
            return

        # Check if user is premium for album/playlist downloads
        user = db.get_user(user_id)
        is_premium = bool(user.get("premium"))

        if is_collection and not is_premium:
            await message.reply_text(
                "💎 Album/playlist downloads are available for Premium users only. Buy premium to download albums/playlists."
            )
            return

        # Create a progress message
        try:
            progress_msg = await message.reply_text("🚀 Starting download...")
        except Exception as e:
            logger.error(f"Failed to create progress message: {e}")
            progress_msg = None

        try:
            if is_collection:
                # Download album/playlist
                if hasattr(self.download_handler, "download_album"):
                    success = await self.download_handler.download_album(
                        provider, url, user_id, progress_msg or message
                    )
                    if not success:
                        await (progress_msg or message).edit_text(
                            "❌ Failed to download album/playlist. Some tracks may have failed."
                        )
                else:
                    await (progress_msg or message).edit_text(
                        "❌ Album/playlist downloads are not supported in this version."
                    )
            else:
                # Single track download
                # Send initial status
                if progress_msg:
                    await progress_msg.edit_text(f"⬇️ Downloading track...")
                
                # Call the download handler
                success = await self.download_handler.download_track(
                    provider, tid, user_id, progress_msg or message
                )
                
                if not success and progress_msg:
                    await progress_msg.edit_text("❌ Failed to download track.")
                    
        except Exception as e:
            logger.error(f"Failed starting download for {user_id} url={url}: {e}", exc_info=True)
            try:
                await (progress_msg or message).edit_text(f"❌ Download failed: {str(e)}")
            except Exception:
                pass

    async def userinfo_command(self, client: Client, message: Message):
        user_id = message.from_user.id
        if len(message.command) > 1 and message.from_user.id == Config.OWNER_ID:
            try:
                target_user_id = int(message.command[1])
            except ValueError:
                await message.reply_text("Invalid user ID. Usage: `/userinfo <user_id>`")
                return
        else:
            target_user_id = user_id

        user = db.get_user(target_user_id) or {}
        info_text = (
            f"👤 **User Information**\n\n"
            f"**User ID:** `{target_user_id}`\n"
            f"**Premium Status:** {'✅ Active' if user.get('premium') else '❌ Inactive'}\n"
        )
        if user.get('premium') and user.get('premium_until'):
            tu = user['premium_until']
            try:
                info_text += f"**Premium Until:** {tu.strftime('%Y-%m-%d')}\n"
            except Exception:
                info_text += f"**Premium Until:** {str(tu)}\n"
        info_text += (
            f"**Downloads Today:** {user.get('downloads_today', 0)}/{Config.FREE_USER_DAILY_LIMIT}\n"
            f"**Total Downloads:** {user.get('total_downloads', 0)}\n"
            f"**Preferred Format:** {user.get('preferred_format', 'mp3')}\n"
            f"**Preferred Quality:** {user.get('preferred_quality', 64)}\n"
            f"**Join Date:** {user.get('join_date', 'Unknown') if not isinstance(user.get('join_date'), datetime) else user.get('join_date').strftime('%Y-%m-%d')}\n"
        )
        await message.reply_text(info_text)

    async def premium_command(self, client: Client, message: Message):
        user_id = message.from_user.id
        rec = db.get_user(user_id) or {}
        premium_text = (
            "💎 **Premium Features**\n\n"
            "• **Unlimited downloads** - No daily limits\n"
            "• **Advanced search** - Search across multiple platforms\n"
            "• **High quality audio** - FLAC and high-bitrate MP3\n"
            "• **Batch downloads** - Download albums and playlists\n"
            "• **Priority support** - Faster response times\n\n"
        )
        if rec.get('premium'):
            tu = rec.get('premium_until')
            try:
                premium_text += f"**Your premium is active until:** {tu.strftime('%Y-%m-%d')}\n\n"
            except Exception:
                premium_text += f"**Your premium is active until:** {str(tu)}\n\n"
        else:
            premium_text += (
                "**Free Account Limitations:**\n"
                f"• {Config.FREE_USER_DAILY_LIMIT} downloads per day\n"
                "**To upgrade to premium,** contact @icecube9680\n"
                f"**User ID**: `{user_id}`"
            )
        await message.reply_text(premium_text)

    # ---- admin commands ----
    async def add_premium_command(self, client: Client, message: Message):
        if message.from_user.id != Config.OWNER_ID:
            await message.reply_text("❌ This command is for bot owner only.")
            return
        try:
            parts = message.text.split()
            if len(parts) < 3:
                await message.reply_text("Usage: /addpremium <user_id> <duration>\n\nDuration examples: 7d, 1m, 1y or just number of days")
                return
            user_id = int(parts[1])
            duration = parts[2].lower()
            if duration.endswith('d'):
                days = int(duration[:-1])
            elif duration.endswith('w'):
                days = int(duration[:-1]) * 7
            elif duration.endswith('m'):
                days = int(duration[:-1]) * 30
            elif duration.endswith('y'):
                days = int(duration[:-1]) * 365
            else:
                days = int(duration)
            premium_until = db.add_premium(user_id, days)
            try:
                await client.send_message(user_id, f"🎉 You've been granted premium access until {premium_until.strftime('%Y-%m-%d')}!\n\nEnjoy unlimited downloads and all premium features!")
            except Exception:
                logger.debug("Could not notify user about premium")
            await self.logger.log_premium_change(user_id, "added", days)
            await message.reply_text(f"✅ Premium access granted to user {user_id} for {days} days.\nPremium valid until: {premium_until.strftime('%Y-%m-%d')}")
        except Exception as e:
            logger.error(f"Error in addpremium: {e}", exc_info=True)
            await message.reply_text(f"Error: {e}")

    async def remove_premium_command(self, client: Client, message: Message):
        if message.from_user.id != Config.OWNER_ID:
            await message.reply_text("❌ This command is for bot owner only.")
            return
        try:
            parts = message.text.split()
            if len(parts) < 2:
                await message.reply_text("Usage: /removepremium <user_id>")
                return
            user_id = int(parts[1])
            db.remove_premium(user_id)
            try:
                await client.send_message(user_id, "ℹ️ Your premium access has been removed.\n\nYou can still use the bot with free limitations.")
            except Exception:
                logger.debug("Could not notify user about premium removal")
            await self.logger.log_premium_change(user_id, "removed")
            await message.reply_text(f"✅ Premium access removed from user {user_id}.")
        except Exception as e:
            logger.error(f"Error in removepremium: {e}", exc_info=True)
            await message.reply_text(f"Error: {e}")

    async def logs_command(self, client, message: Message):
        """Handle /logs command (owner only) — sends the latest log file or recent lines."""
        if message.from_user.id != Config.OWNER_ID:
            await message.reply_text("❌ This command is for bot owner only.")
            return

        # Path to your log file (adjust if you use a different filename)
        log_path = os.path.join(os.getcwd(), "bot.log")

        try:
            if os.path.exists(log_path):
                # Send as a document if file exists
                await message.reply_document(
                    document=log_path,
                    caption="📄 Latest bot logs"
                )
            else:
                # Fallback: read recent lines from logging memory or just warn
                await message.reply_text("⚠️ Log file not found. Make sure logging is configured to write to `bot.log`.")
        except Exception as e:
            logger.error(f"Error sending logs: {e}", exc_info=True)
            await message.reply_text(f"❌ Could not send logs: {e}")

    async def stats_command(self, client: Client, message: Message):
        if message.from_user.id != Config.OWNER_ID:
            await message.reply_text("❌ This command is for bot owner only.")
            return
        try:
            total_users = db.users.count_documents({})
            premium_users = db.users.count_documents({"premium": True})
            total_downloads = db.downloads.count_documents({})
            stats_text = (
                "📊 **Bot Statistics**\n\n"
                f"**Total Users:** {total_users}\n"
                f"**Premium Users:** {premium_users}\n"
                f"**Total Downloads:** {total_downloads}\n\n"
                "**Recent Activity:**\n"
            )
            recent_downloads = list(db.downloads.find().sort("timestamp", -1).limit(5))
            for i, dl in enumerate(recent_downloads, 1):
                t = dl.get("track_info", {})
                stats_text += f"{i}. {t.get('title','Unknown')} - {t.get('artist','Unknown')}\n"
            await message.reply_text(stats_text)
        except Exception as e:
            logger.error(f"Error in stats: {e}", exc_info=True)
            await message.reply_text(f"Error: {e}")

    async def broadcast_command(self, client: Client, message: Message):
        if message.from_user.id != Config.OWNER_ID:
            await message.reply_text("❌ This command is for bot owner only.")
            return
        if len(message.command) < 2:
            await message.reply_text("Usage: /broadcast <message>")
            return
        broadcast_msg = " ".join(message.command[1:])
        confirm_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes", callback_data="broadcast_confirm")],
            [InlineKeyboardButton("❌ Cancel", callback_data="broadcast_cancel")]
        ])
        await message.reply_text(
            f"📢 **Broadcast Confirmation**\n\nMessage: {broadcast_msg}\n\nAre you sure?",
            reply_markup=confirm_keyboard
        )

    async def _handle_broadcast_callback(self, callback_query: CallbackQuery):
        data = callback_query.data or ""
        user_id = callback_query.from_user.id
        if user_id != Config.OWNER_ID:
            try:
                await callback_query.answer("❌ Only the owner can broadcast messages.")
            except Exception:
                pass
            return

        if data == "broadcast_confirm":
            try:
                orig = callback_query.message.text or ""
                broadcast_msg = orig.split("Message: ")[1].split("\n\n")[0]
            except Exception:
                broadcast_msg = "Announcement from admin"

            users_cursor = db.users.find({}, {"user_id": 1})
            total_users = db.users.count_documents({})
            progress_msg = await callback_query.message.edit_text(f"📢 Broadcasting... 0/{total_users}")
            success, fail = 0, 0
            i = 0
            for u in users_cursor:
                i += 1
                uid = u.get("user_id") or u.get("_id") or None
                if not uid:
                    continue
                try:
                    await self.app.send_message(uid, f"📢 **Broadcast**\n\n{broadcast_msg}")
                    success += 1
                except Exception as e:
                    fail += 1
                    logger.debug(f"Broadcast failed for {uid}: {e}")
                if i % 10 == 0 or i == total_users:
                    try:
                        await progress_msg.edit_text(f"📢 Broadcasting... {i}/{total_users}\nSuccessful: {success}\nFailed: {fail}")
                    except Exception:
                        pass
            try:
                await progress_msg.edit_text(f"✅ Broadcast complete.\nSuccessful: {success}\nFailed: {fail}")
            except Exception:
                pass
            try:
                await callback_query.answer()
            except Exception:
                pass
            return

        if data == "broadcast_cancel":
            try:
                await callback_query.message.edit_text("❌ Broadcast cancelled.")
                await callback_query.answer()
            except Exception:
                pass
            return


# ----------------------
# Compatibility wrapper + convenience setup
# ----------------------
class CommandHandler:
    """
    Compatibility wrapper for code that expects CommandHandler(bot, logger, search_handler, download_handler)
    """
    def __init__(self, bot, logger: BotLogger, search_handler: SearchHandler, download_handler: DownloadHandler):
        # Use CommandsBinder under the hood
        try:
            CommandsBinder(bot, search_handler, download_handler, logger)
        except Exception as e:
            logger.error(f"Failed to initialize CommandHandler wrapper: {e}")
            raise

def setup_handlers(app: Client, search_handler: SearchHandler, download_handler: DownloadHandler, logger_obj: BotLogger = None):
    """
    Modern convenience function to register handlers on the pyrogram.Client.
    Call this from your bot runner before app.run()
    """
    CommandsBinder(app, search_handler, download_handler, logger_obj)
    logger.info("Command handlers registered (setup_handlers).")
