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
    # prefer clicking user
    try:
        u = callback_query.from_user
        if u and (u.first_name or u.username):
            return _display_name_from_user_obj(u)
    except Exception:
        pass

    # fallback to DB-stored display name
    try:
        if callback_query.from_user:
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
        app.add_handler(MessageHandler(self._on_search_wrapper, filters.command(["search", "s", "find"])))
        app.add_handler(MessageHandler(self._on_help_wrapper, filters.command(["help", "h"])))
        app.add_handler(MessageHandler(self._on_settings_wrapper, filters.command(["settings", "setting", "set"])))
        app.add_handler(MessageHandler(self._on_download_wrapper, filters.command(["download", "dl", "d"])))
        app.add_handler(MessageHandler(self._on_userinfo_wrapper, filters.command(["userinfo", "user_info", "info", "myinfo", "me"])))
        app.add_handler(MessageHandler(self._on_premium_wrapper, filters.command(["premium", "prem", "plan"])))
        app.add_handler(MessageHandler(self._on_addpremium_wrapper, filters.command(["addpremium", "add_premium", "setpremium", "set_premium", "give_premium", "givepremium"])))
        app.add_handler(MessageHandler(self._on_removepremium_wrapper, filters.command(["removepremium", "remove_premium", "delpremium", "del_premium", "unpremium", "revoke_premium", "remove_prem", "del_prem"])))
        app.add_handler(MessageHandler(self._on_stats_wrapper, filters.command(["stats", "stat"])))
        app.add_handler(MessageHandler(self._on_users_wrapper, filters.command(["users", "user", "totalusers"])))
        app.add_handler(MessageHandler(self._on_broadcast_wrapper, filters.command(["broadcast", "bc"])))
        app.add_handler(MessageHandler(self._on_logs_wrapper, filters.command(["logs", "log"])))

        # Direct text message handler (for private chats without slash commands)
        app.add_handler(MessageHandler(self._on_direct_message_wrapper, filters.text & filters.private & ~filters.regex(r"^/")))

        # CallbackQuery handler (single)
        app.add_handler(CallbackQueryHandler(self._on_callback_wrapper))

        logger.info("Command handlers registered on Client.")

    # thin wrappers to match handler signature
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

    async def _on_addpremium_wrapper(self, client: Client, message: Message):
        await self.add_premium_command(client, message)

    async def _on_removepremium_wrapper(self, client: Client, message: Message):
        await self.remove_premium_command(client, message)

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

        # retrieve and update user record
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

        # log new user asynchronously
        try:
            await self.logger.log_new_user(user_id, username, first_name)
        except Exception:
            pass

        is_premium = db.is_premium(user_id)
        welcome_text = (
            f"👋 Hello {first_name}!\n\n"
            f"Welcome to **SpotiVerse Bot**!\n\n"
            "I can search and download high-quality audio from:\n"
            "• Spotify\n• JioSaavn\n• YouTube\n\n"
            f"**Your Status:** {'💎 Premium User' if is_premium else '👤 Free User'}\n"
        )
        if is_premium:
            if rec.get("premium_until"):
                try:
                    tu = rec.get("premium_until")
                    if isinstance(tu, datetime):
                        welcome_text += f"**Premium Until:** {tu.strftime('%Y-%m-%d')}\n"
                    else:
                        welcome_text += f"**Premium Until:** {str(tu)}\n"
                except Exception:
                    pass
            welcome_text += "**Downloads:** Unlimited ♾️ (No daily limit)\n\nEnjoy your unlimited high-quality downloads!"
        else:
            welcome_text += (
                f"**Free Limit:** {rec.get('downloads_today', 0)}/{Config.FREE_USER_DAILY_LIMIT} downloads today\n"
                "🔍 Search & download songs using `/search <song name>`\n\n"
                "💎 Upgrade to Premium for unlimited downloads and album/playlist support!\n"
                "Contact: @icecube9608\n\n"
                f"👤 **Your User ID:** `{user_id}`"
            )

        try:
            await message.reply_text(welcome_text, reply_markup=_build_start_keyboard())
        except Exception:
            try:
                await message.edit_text(welcome_text, reply_markup=_build_start_keyboard())
            except Exception as e:
                logger.warning(f"Failed to deliver welcome message: {e}")

    async def search_command(self, client: Client, message: Message):
        if not message.from_user:
            return
        user_id = message.from_user.id
        username = getattr(message.from_user, "username", None)
        first_name = getattr(message.from_user, "first_name", "there") or "there"

        # Save user info in DB
        try:
            db.update_user(user_id, {"username": username, "first_name": first_name, "display_name": first_name})
        except Exception:
            pass

        parts = _get_command_parts(message)
        if len(parts) < 2:
            await message.reply_text("Usage: /search <query>\nExample: `/search blinding lights`")
            return
        query = " ".join(parts[1:]).strip()
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
                uid = message.from_user.id if message.from_user else "unknown"
                await self.logger.log_to_channel(f"Search error for user {uid}: {e}")
            except Exception:
                pass
            await loading_msg.edit_text(f"❌ Search failed: {e}")

    async def help_command(self, client: Client, message: Message):
        help_text = (
            "🤖 **SpotiVerse Bot Commands**\n\n"
            "**Music Commands:**\n"
            "• `/search <query>` - Search for music (Free & Premium)\n"
            "• `/download <url>` - Download songs/albums (Premium Only)\n\n"
            "**User Commands:**\n"
            "• `/start` - Start the bot\n"
            "• `/help` - Show this help message\n"
            "• `/userinfo` - Show your user information\n"
            "• `/premium` - Show premium plans & status\n"
            "• `/settings` - Configure audio format/quality (Premium only)\n\n"
            "Need support? Contact @icecube9608"
        )
        await message.reply_text(help_text)

    async def settings_command(self, client: Client, message: Message):
        if not message.from_user:
            return
        user_id = message.from_user.id
        if not db.is_premium(user_id):
            await message.reply_text("❌ Settings are available to Premium users only.\n\nUpgrade to premium to access advanced settings and higher quality downloads.")
            return
        rec = db.get_user(user_id) or {}
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
        if not callback_query.from_user:
            await safe_answer_callback(callback_query, text="User not found")
            return
        user_id = callback_query.from_user.id

        # Quick ACK to stop the spinner
        await safe_answer_callback(callback_query)

        # --- 1) Premium info flow ---
        if data == "premium_info" or data.startswith("premium_"):
            try:
                # Fetch user record
                rec = db.get_user(user_id) or {}

                premium_text = (
                    "💎 **Premium Features**\n\n"
                    "• **Unlimited downloads** - No daily limits\n"
                    "• **Advanced search** - Search across multiple platforms\n"
                    "• **High quality audio** - FLAC and high-bitrate MP3\n"
                    "• **Batch downloads** - Download albums and playlists\n"
                    "• **Priority support** - Faster response times\n\n"
                )

                if db.is_premium(user_id):
                    tu = rec.get("premium_until")
                    try:
                        if tu:
                            premium_text += f"**Your premium is active until:** {tu.strftime('%Y-%m-%d')}\n\n"
                        else:
                            premium_text += "**Your premium is active:** Lifetime / Unlimited ♾️\n\n"
                    except Exception:
                        premium_text += f"**Your premium is active until:** {str(tu)}\n\n"
                else:
                    premium_text += (
                        "**Free Account Limitations:**\n"
                        f"• {Config.FREE_USER_DAILY_LIMIT} downloads per day\n"
                        "**To upgrade to premium,** contact @icecube9608\n"
                        f"**User ID**: `{user_id}`"
                    )

                await callback_query.message.edit_text(premium_text, reply_markup=_build_premium_markup())

            except Exception:
                # Fallback: send as new message if editing fails
                try:
                    await self.app.send_message(user_id, premium_text, reply_markup=_build_premium_markup())
                except Exception as e:
                    logger.warning(f"Failed to show premium info: {e}")

            return


        # --- 2) Back / Main menu ---
        if data in ("back", "main_menu"):
            try:
                display_name = _display_name_from_callback(callback_query)
                rec = db.get_user(user_id) or {}
                is_premium = db.is_premium(user_id)
                text = (
                    f"👋 Hello {display_name}!\n\n"
                    "Welcome to **SpotiVerse Bot**!\n\n"
                    "I can download high-quality audio from various platforms including:\n"
                    "• Spotify\n"
                    "• YouTube\n"
                    "• JioSaavn\n\n"
                    f"**Your Status:** {'💎 Premium User' if is_premium else '👤 Free User'}\n"
                )
                if is_premium:
                    if rec.get("premium_until"):
                        tu = rec.get("premium_until")
                        try:
                            text += f"**Premium Until:** {tu.strftime('%Y-%m-%d')}\n"
                        except Exception:
                            text += f"**Premium Until:** {str(tu)}\n"
                    text += "**Downloads:** Unlimited ♾️ (No daily limit)\n\n"
                else:
                    text += f"**Free Limits:** {rec.get('downloads_today', 0)}/{Config.FREE_USER_DAILY_LIMIT} downloads today\n\n💎 Upgrade to premium for unlimited downloads and album/playlist support!\n\n"
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
                text = (
                    "🔎 **Search & Download Music**\n\n"
                    "Send me a song name or Spotify/YouTube/JioSaavn link to search & download.\n\n"
                    "Examples:\n"
                    "• `/search blinding lights`\n"
                    "• `faded alan walker`\n"
                    "• `https://open.spotify.com/track/...`"
                )
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
                # Check if premium using db.is_premium
                if not db.is_premium(user_id):
                    try:
                        await callback_query.answer("⚠️ Settings are available to Premium users only.", show_alert=True)
                    except Exception:
                        pass
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
                rec = db.get_user(user_id) or {}
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
                            pass
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

        # --- 8) Clear logs (admin) ---
        if data == "clear_logs":
            if not Config.is_authorized_callback(callback_query):
                await safe_answer_callback(callback_query, text="❌ Owner only", show_alert=True)
                return
            log_path = os.path.join(os.getcwd(), "bot.log")
            try:
                if os.path.exists(log_path):
                    with open(log_path, "w", encoding="utf-8") as f:
                        f.write("")
                await callback_query.message.edit_text("🗑️ **Bot logs have been cleared successfully.**")
                await safe_answer_callback(callback_query, text="Logs cleared")
            except Exception as e:
                await safe_answer_callback(callback_query, text=f"Error: {e}", show_alert=True)
            return

        # --- 9) Search cancel / pagination ---
        if data == "cancel_search":
            try:
                await callback_query.message.delete()
            except Exception:
                try:
                    await callback_query.message.edit_text("❌ Search cancelled.")
                except Exception:
                    pass
            await safe_answer_callback(callback_query, text="Search cancelled")
            return

        if data.startswith("search_page_"):
            await safe_answer_callback(callback_query)
            return

        # Unknown callback (log quietly)
        logger.debug(f"Unhandled callback data: {data}")


    async def _handle_settings_callback(self, callback_query: CallbackQuery):
        data = callback_query.data or ""
        if not callback_query.from_user:
            return
        user_id = callback_query.from_user.id
        rec = db.get_user(user_id) or {}

        if not db.is_premium(user_id):
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

    async def direct_message_handler(self, client: Client, message: Message):
        """Handle plain text or direct links in private messages without /search or /download command."""
        if not message or not message.from_user:
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
        """Handle /download command (supports single track and album/playlist - Premium Only)"""
        if not message.from_user:
            return
        user_id = message.from_user.id
        username = getattr(message.from_user, "username", None)
        first_name = getattr(message.from_user, "first_name", "there") or "there"

        # Update user profile in DB
        try:
            db.update_user(user_id, {"username": username, "first_name": first_name, "display_name": first_name})
        except Exception:
            pass

        # Enforce Premium Only for downloads
        if not db.is_premium(user_id):
            await message.reply_text(
                f"❌ **Premium Required!**\n\n"
                f"📥 Downloads are available for **Premium users only**.\n\n"
                f"💡 Free users can search for any song using `/search <song name>`!\n\n"
                f"💎 Upgrade to Premium to unlock unlimited high-quality downloads & album support!\n"
                f"Contact: @icecube9608\n\n"
                f"👤 **Your User ID:** `{user_id}`"
            )
            return

        # basic validation
        parts = _get_command_parts(message)
        if len(parts) < 2:
            await message.reply_text(
                "Please provide a URL.\nUsage: /download link/album/playlist\n\nExample: `/download https://open.spotify.com/track/...`"
            )
            return
        url = parts[1].strip()
        if not url.startswith(('http://', 'https://', 'spotify:')):
            await message.reply_text(
                "❌ Please provide a valid URL starting with http:// or https://"
            )
            return

        # helper: parse provider and id
        def parse_provider_and_id(u: str):
            # spotify (track, album, playlist, artist - with optional /intl-xx/ prefix)
            m = re.search(r"open\.spotify\.com/(?:intl-[^/]+/)?(track|album|playlist|artist)/([A-Za-z0-9]+)", u)
            if m:
                return "spotify", m.group(1), m.group(2)
            # spotify URI format
            m = re.search(r"spotify:(track|album|playlist|artist):([A-Za-z0-9]+)", u)
            if m:
                return "spotify", m.group(1), m.group(2)
            # youtube: watch?v= or youtu.be or shorts/ or playlist
            if "list=" in u:
                return "youtube", "playlist", u
            m = re.search(r"(?:v=|youtu\.be/|/shorts/)([A-Za-z0-9_-]{6,})", u)
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
        is_collection = kind in ("album", "playlist", "set", "artist")

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
                        await self.download_handler.safe_edit_message(
                            progress_msg or message,
                            "❌ Failed to download album/playlist. Some tracks may have failed."
                        )
                else:
                    await self.download_handler.safe_edit_message(
                        progress_msg or message,
                        "❌ Album/playlist downloads are not supported in this version."
                    )
            else:
                # Single track download
                if progress_msg:
                    await self.download_handler.safe_edit_message(progress_msg, "⬇️ Downloading track...")
                
                # Call the download handler
                success = await self.download_handler.download_track(
                    provider, tid, user_id, progress_msg or message
                )
                
                if not success and progress_msg:
                    await self.download_handler.safe_edit_message(progress_msg, "❌ Failed to download track.")
                    
        except Exception as e:
            logger.error(f"Failed starting download for {user_id} url={url}: {e}", exc_info=True)
            try:
                await self.download_handler.safe_edit_message(progress_msg or message, f"❌ Download failed: {str(e)}")
            except Exception:
                pass

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
        is_prem = db.is_premium(target_user_id)
        info_text = (
            f"👤 **User Information**\n\n"
            f"**User ID:** `{target_user_id}`\n"
            f"**Premium Status:** {'✅ Active (💎 Premium)' if is_prem else '❌ Inactive (👤 Free User)'}\n"
        )
        if user.get('premium') and user.get('premium_until'):
            tu = user['premium_until']
            try:
                info_text += f"**Premium Until:** {tu.strftime('%Y-%m-%d %H:%M UTC')}\n"
            except Exception:
                info_text += f"**Premium Until:** {str(tu)}\n"
        elif is_prem:
            info_text += "**Premium Until:** Lifetime / Unlimited ♾️\n"

        if is_prem:
            info_text += "**Downloads:** Unlimited ♾️ (No daily limit)\n"
        else:
            info_text += f"**Downloads Today:** {user.get('downloads_today', 0)}/{Config.FREE_USER_DAILY_LIMIT}\n"

        info_text += (
            f"**Total Downloads:** {user.get('total_downloads', 0)}\n"
            f"**Preferred Format:** {user.get('preferred_format', 'mp3')}\n"
            f"**Preferred Quality:** {user.get('preferred_quality', 64)}\n"
            f"**Join Date:** {user.get('join_date', 'Unknown') if not isinstance(user.get('join_date'), datetime) else user.get('join_date').strftime('%Y-%m-%d')}\n"
        )
        await message.reply_text(info_text)

    async def premium_command(self, client: Client, message: Message):
        if not message.from_user:
            return
        user_id = message.from_user.id
        rec = db.get_user(user_id) or {}
        is_prem = db.is_premium(user_id)
        premium_text = (
            "💎 **Premium Features**\n\n"
            "• **Unlimited Downloads** - Download any track with no restrictions\n"
            "• **Batch Downloads** - Download complete albums & playlists\n"
            "• **High Quality Audio** - FLAC & 320kbps MP3\n"
            "• **Custom Format Settings** - Configure quality and format\n"
            "• **Priority Processing** - High-speed downloads\n\n"
        )
        if is_prem:
            if rec.get('premium_until'):
                tu = rec.get('premium_until')
                try:
                    premium_text += f"**Your premium is active until:** {tu.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
                except Exception:
                    premium_text += f"**Your premium is active until:** {str(tu)}\n\n"
            else:
                premium_text += "**Your premium is active:** Unlimited / Lifetime ♾️\n\n"
            premium_text += "Enjoy your unlimited downloads! 🎉"
        else:
            premium_text += (
                "**Free vs Premium:**\n"
                "• 🔍 **Search & Downloads:** Free users get 5 song downloads/day (`/search <query>`)\n"
                "• 💎 **Premium:** Unlimited downloads, 320kbps/FLAC & album/playlist support\n\n"
                "**To upgrade to premium,** contact @icecube9608\n"
                f"**Your User ID**: `{user_id}`"
            )
        await message.reply_text(premium_text)

    # ---- admin commands ----
    def _parse_duration(self, raw_duration: str) -> tuple[float, str]:
        """
        Parse duration string (e.g. '30d', '12h', '1m', '1y', 'lifetime', '7') into (days_float, friendly_text).
        """
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

            premium_until = db.add_premium(user_id, days)
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
                logger.debug(f"Could not send PM notification to user {user_id}")

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

            db.remove_premium(user_id)

            try:
                await client.send_message(
                    user_id,
                    "ℹ️ **Your premium access has been removed.**\n\n"
                    "You can still use the bot with free limitations."
                )
            except Exception:
                logger.debug(f"Could not notify user {user_id} about premium removal")

            await self.logger.log_premium_change(user_id, "removed")
            await message.reply_text(f"✅ Premium access removed from user `{user_id}`.")
        except Exception as e:
            logger.error(f"Error in remove_premium: {e}", exc_info=True)
            await message.reply_text(f"❌ Error: {e}")

    async def logs_command(self, client, message: Message):
        """Handle /logs command (owner only) — sends the latest log file or recent lines."""
        if not Config.is_authorized(message):
            await message.reply_text("❌ This command is for bot owner only.")
            return

        log_path = os.path.join(os.getcwd(), "bot.log")
        clear_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🗑️ Clear Logs", callback_data="clear_logs")]])

        try:
            if os.path.exists(log_path):
                file_size = os.path.getsize(log_path)
                # If log file is under 40MB, send directly
                if file_size <= 40 * 1024 * 1024:
                    await message.reply_document(
                        document=log_path,
                        caption=f"📄 **Latest bot logs** ({file_size / 1024:.1f} KB)",
                        reply_markup=clear_kb
                    )
                else:
                    # If larger, send the last 10,000 lines in a temp file
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
                await message.reply_text("⚠️ Log file not found. Make sure logging is configured to write to `bot.log`.")
        except Exception as e:
            logger.error(f"Error sending logs: {e}", exc_info=True)
            await message.reply_text(f"❌ Could not send logs: {e}")

    async def stats_command(self, client: Client, message: Message):
        if not Config.is_authorized(message):
            await message.reply_text("❌ This command is for bot owner only.")
            return
        try:
            stats = db.get_user_stats()
            stats_text = (
                "📊 **Bot Statistics**\n\n"
                f"**Total Users:** {stats['total_users']}\n"
                f"**Premium Users:** {stats['premium_users']}\n"
                f"**Free Users:** {stats['free_users']}\n"
                f"**Active Today:** {stats['active_today']}\n"
                f"**Total Downloads:** {stats['total_downloads']}\n\n"
                "**Recent Activity:**\n"
            )
            if db.available:
                recent_downloads = list(db.downloads.find().sort("timestamp", -1).limit(5))
            else:
                from utils.db import _fallback_store
                recent_downloads = list(_fallback_store.get("downloads", []))[-5:]
            for i, dl in enumerate(recent_downloads, 1):
                t = dl.get("track_info", {})
                stats_text += f"{i}. {t.get('title','Unknown')} - {t.get('artist','Unknown')}\n"
            await message.reply_text(stats_text)
        except Exception as e:
            logger.error(f"Error in stats: {e}", exc_info=True)
            await message.reply_text(f"Error: {e}")

    async def users_command(self, client: Client, message: Message):
        """Handle /users or /user command (owner only) — shows user counts and stats."""
        if not Config.is_authorized(message):
            await message.reply_text("❌ This command is for bot owner only.")
            return

        parts = _get_command_parts(message)
        # If user passed a specific user ID: /user <user_id>, route to userinfo
        if len(parts) > 1 and parts[1].isdigit():
            await self.userinfo_command(client, message)
            return

        try:
            stats = db.get_user_stats()
            total = stats["total_users"]
            premium = stats["premium_users"]
            free = stats["free_users"]
            active = stats["active_today"]
            downloads = stats["total_downloads"]

            text = (
                "👥 **SpotiVerse User Statistics**\n\n"
                f"👤 **Total Users:** `{total:,}`\n"
                f"💎 **Premium Users:** `{premium:,}`\n"
                f"🆓 **Free Users:** `{free:,}`\n"
                f"⚡ **Active Today:** `{active:,}`\n"
                f"📥 **Total Downloads:** `{downloads:,}`\n\n"
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
            await message.reply_text("Usage: /broadcast <message>")
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

    async def _handle_broadcast_callback(self, callback_query: CallbackQuery):
        data = callback_query.data or ""
        if not Config.is_authorized_callback(callback_query):
            try:
                await callback_query.answer("❌ Only the owner can broadcast messages.")
            except Exception:
                pass
            return
        user_id = callback_query.from_user.id if callback_query.from_user else 0

        if data == "broadcast_confirm":
            try:
                orig = callback_query.message.text or ""
                if "Message: " in orig:
                    broadcast_msg = orig.split("Message: ", 1)[1]
                    if "\n\nAre you sure?" in broadcast_msg:
                        broadcast_msg = broadcast_msg.rsplit("\n\nAre you sure?", 1)[0]
                else:
                    broadcast_msg = orig
            except Exception:
                broadcast_msg = "Announcement from admin"

            # Retrieve user list with MongoDB / in-memory fallback
            if db.available and db.users is not None:
                try:
                    users_list = list(db.users.find({}, {"user_id": 1}))
                except Exception:
                    from utils.db import _fallback_store
                    users_list = [{"user_id": uid} for uid in _fallback_store.get("users", {}).keys()]
            else:
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
                except Exception as e:
                    fail += 1
                    logger.debug(f"Broadcast failed for {uid}: {e}")
                # small pause to stay well within Telegram broadcast limits
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
class CommandHandler(CommandsBinder):
    """
    Compatibility wrapper for code that expects CommandHandler(bot, logger, search_handler, download_handler)
    """
    def __init__(self, bot, logger: BotLogger, search_handler: SearchHandler, download_handler: DownloadHandler):
        # Use CommandsBinder under the hood
        try:
            super().__init__(bot, search_handler, download_handler, logger)
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
