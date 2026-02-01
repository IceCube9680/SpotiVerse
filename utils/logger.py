# utils/logger.py
from pyrogram.errors import RPCError
import logging
from utils.db import db
from config import Config

logger = logging.getLogger(__name__)

class BotLogger:
    def __init__(self, bot):
        """
        bot: pyrogram.Client instance (or similar) with send_message method
        """
        self.bot = bot

    async def log_to_channel(self, message: str, channel_id=None):
        """
        Send a text message to the configured log channel.
        If channel_id is falsy, nothing is attempted.
        """
        if not channel_id:
            # nothing configured — skip silently
            logger.debug("No channel_id provided to log_to_channel; skipping.")
            return

        try:
            # Ensure bot has send_message (pyrogram)
            await self.bot.send_message(channel_id, message)
        except RPCError as e:
            logger.warning(f"Can't access channel {channel_id}: {type(e).__name__}: {e}")
        except Exception as e:
            logger.warning(f"Unexpected error when logging to channel {channel_id}: {e}")

    async def log_new_user(self, user_id: int, username: str = None, first_name: str = None):
        """
        Post "New user started bot" to log channel only once per user.
        Uses the DB 'seen' flag to ensure idempotency.
        """
        try:
            # Ensure we have up-to-date user record (db.get_user will create default if missing)
            user = db.get_user(user_id)

            # If user already seen, do nothing
            if user.get("seen"):
                logger.debug(f"User {user_id} already marked seen — skipping new-user log.")
                return

            # Mark user as seen in DB (upsert) so subsequent /start won't re-log
            db.update_user(user_id, {"seen": True})

            # Prepare contextual message. Avoid None/False mentions.
            uname = username or ""
            fname = first_name or ""
            msg = (
                f"🔔 **New user started bot**\n\n"
                f"**User ID:** `{user_id}`\n"
                f"**Username:** @{uname}\n"
                f"**Name:** {fname}"
            )

            # Use LOG_CHANNEL if provided, otherwise skip
            channel = getattr(Config, "LOG_CHANNEL", None) or None
            if not channel:
                logger.info(f"LOG_CHANNEL not configured; not sending new-user log for user {user_id}.")
                return

            await self.log_to_channel(msg, channel)

        except Exception as e:
            # Don't raise — logging failure shouldn't crash bot
            logger.warning(f"Failed in log_new_user for {user_id}: {e}")

    async def log_download(self, user_id: int, track_info: dict, format_used: str):
        """
        Log a download event to DOWNLOAD_LOG_CHANNEL if configured.
        track_info is expected to have 'title' and 'artist' keys (best-effort).
        """
        try:
            title = track_info.get("title", "Unknown")
            artist = track_info.get("artist", "Unknown")
            timestamp = track_info.get("timestamp")

            message = (
                f"**Download Recorded**\n"
                f"**User:** `{user_id}`\n"
                f"**Track:** {title}\n"
                f"**Artist:** {artist}\n"
                f"**Format:** {format_used}\n"
            )
            if timestamp:
                message += f"**Time:** {timestamp}\n"

            channel = getattr(Config, "DOWNLOAD_LOG_CHANNEL", None)
            if channel:
                await self.log_to_channel(message, channel)
            else:
                logger.debug("DOWNLOAD_LOG_CHANNEL not configured; skipping download log.")
        except Exception as e:
            logger.warning(f"Failed in log_download for {user_id}: {e}")

    async def log_premium_change(self, user_id: int, action: str, duration: int = None):
        """
        Log when premium is added or removed.
        action: 'added' or 'removed'
        duration: days (optional)
        """
        try:
            message = f"**Premium {action.capitalize()}**\n**User ID:** `{user_id}`\n"
            if action == "added" and duration:
                message += f"**Duration:** {duration} days\n"

            channel = getattr(Config, "LOG_CHANNEL", None)
            if channel:
                await self.log_to_channel(message, channel)
            else:
                logger.debug("LOG_CHANNEL not configured; skipping premium change log.")
        except Exception as e:
            logger.warning(f"Failed in log_premium_change for {user_id}: {e}")
