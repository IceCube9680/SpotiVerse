import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import os

os.environ["API_ID"] = "123456"
os.environ["API_HASH"] = "dummy_hash"
os.environ["BOT_TOKEN"] = "dummy_token"

from handlers.commands import CommandHandler
from handlers.downloads import DownloadHandler
from handlers.search import SearchHandler
from utils.logger import BotLogger
from utils.db import db
from config import Config

class TestSearchAndPremiumEnforcement(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mock_bot = MagicMock()
        self.mock_bot.send_message = AsyncMock()
        self.mock_bot.send_audio = AsyncMock()
        self.mock_logger = MagicMock()
        self.mock_logger.log_download = AsyncMock()
        self.mock_search = MagicMock()
        self.download_handler = DownloadHandler(self.mock_bot, self.mock_logger, self.mock_search)
        self.download_handler.download_track = AsyncMock(return_value=True)
        self.command_handler = CommandHandler(self.mock_bot, self.mock_logger, self.mock_search, self.download_handler)

    async def test_free_user_can_search_successfully(self):
        # Free user
        free_uid = 101010
        db.update_user(free_uid, {"premium": False, "premium_until": None})

        # Mock search results
        self.mock_search.search_all = AsyncMock(return_value=[
            {"id": "s1", "title": "Faded", "artist": "Alan Walker", "provider": "saavn"},
            {"id": "s2", "title": "Spectre", "artist": "Alan Walker", "provider": "saavn"},
        ])

        message = MagicMock()
        message.from_user = MagicMock()
        message.from_user.id = free_uid
        message.from_user.username = "free_user"
        message.from_user.first_name = "Free"
        message.command = ["search", "alan", "walker"]
        loading_msg = MagicMock()
        loading_msg.edit_text = AsyncMock()
        message.reply_text = AsyncMock(return_value=loading_msg)

        await self.command_handler.search_command(self.mock_bot, message)

        # Search should be called and loading message updated with results
        self.mock_search.search_all.assert_awaited_once_with("alan walker", limit=10)
        loading_msg.edit_text.assert_called_once()
        self.assertIn("Results for", loading_msg.edit_text.call_args[0][0])

    async def test_free_user_download_command_is_blocked(self):
        # Free user attempting album batch download
        free_uid = 202020
        db.update_user(free_uid, {"premium": False, "premium_until": None})

        message = MagicMock()
        message.from_user = MagicMock()
        message.from_user.id = free_uid
        message.from_user.username = "free_user"
        message.command = ["download", "https://open.spotify.com/album/4cOdK2wGLETKBW3PvgPWqT"]
        message.reply_text = AsyncMock()

        await self.command_handler.download_command(self.mock_bot, message)

        message.reply_text.assert_called_once()
        reply_content = message.reply_text.call_args[0][0]
        self.assertIn("Premium Required", reply_content)

    async def test_free_user_can_download_from_search(self):
        # Free user with downloads available
        free_uid = 303030
        db.update_user(free_uid, {"premium": False, "premium_until": None, "downloads_today": 0})

        cb = MagicMock()
        cb.from_user = MagicMock()
        cb.from_user.id = free_uid
        cb.data = "download_saavn_1xqHQw3J"
        cb.answer = AsyncMock()
        cb.message = MagicMock()
        cb.message.reply_text = AsyncMock(return_value=MagicMock())

        self.download_handler.download_track = AsyncMock(return_value=True)

        await self.command_handler.handle_callback(self.mock_bot, cb)

        self.download_handler.download_track.assert_awaited_once_with("saavn", "1xqHQw3J", free_uid, cb.message.reply_text.return_value)

    async def test_free_user_quota_limit_blocked(self):
        free_uid = 303031

        cb = MagicMock()
        cb.from_user = MagicMock()
        cb.from_user.id = free_uid
        cb.data = "download_saavn_1xqHQw3J"
        cb.answer = AsyncMock()

        with patch.object(db, "can_download", return_value=(False, "Daily download limit reached (5/5)")):
            await self.download_handler.handle_download_callback(self.mock_bot, cb)

        self.mock_bot.send_message.assert_awaited_once()
        sent_text = self.mock_bot.send_message.call_args.kwargs.get("text") or self.mock_bot.send_message.call_args[0][1]
        self.assertIn("Download Limit Reached", sent_text)
        self.assertIn(str(free_uid), sent_text)

    async def test_premium_user_can_download(self):
        # Premium user
        prem_uid = 404040
        db.add_premium(prem_uid, 30)

        message = MagicMock()
        message.from_user = MagicMock()
        message.from_user.id = prem_uid
        message.from_user.username = "premium_user"
        message.command = ["download", "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT"]
        progress_msg = MagicMock()
        progress_msg.edit_text = AsyncMock()
        message.reply_text = AsyncMock(return_value=progress_msg)

        self.download_handler.download_track = AsyncMock(return_value=True)

        await self.command_handler.download_command(self.mock_bot, message)

        self.download_handler.download_track.assert_awaited_once()

    async def test_log_download_formatting_user_id_and_username(self):
        bot_logger = BotLogger(self.mock_bot)

        # 1. When user_id and username are provided
        with patch.object(Config, "DOWNLOAD_LOG_CHANNEL", -1001234567):
            await bot_logger.log_download(
                user_id=78910,
                track_info={"title": "Faded", "artist": "Alan Walker"},
                format_used="mp3 320",
                username="music_king"
            )
            self.mock_bot.send_message.assert_awaited_once()
            msg = self.mock_bot.send_message.call_args[0][1]
            self.assertIn("**Download Recorded**", msg)
            self.assertIn("**User ID:** `78910` (@music_king)", msg)
            self.assertIn("**Track:** Faded", msg)
            self.assertIn("**Artist:** Alan Walker", msg)
            self.assertIn("**Format:** mp3 320", msg)

        # 2. When user_id is None / missing, fallback to username
        self.mock_bot.send_message.reset_mock()
        with patch.object(Config, "DOWNLOAD_LOG_CHANNEL", -1001234567):
            await bot_logger.log_download(
                user_id=None,
                track_info={"title": "Spectre", "artist": "Alan Walker"},
                format_used="mp3 320",
                username="anonymous_hero"
            )
            self.mock_bot.send_message.assert_awaited_once()
            msg = self.mock_bot.send_message.call_args[0][1]
            self.assertIn("**Download Recorded**", msg)
            self.assertIn("**Username:** @anonymous_hero", msg)

    async def test_search_handler_saavn_and_fallback(self):
        handler = SearchHandler()
        # Verify Saavn search returns valid structured tracks
        res = await handler.search_saavn("faded", limit=3)
        self.assertIsNotNone(res)
        self.assertTrue(len(res) > 0)
        track = res[0]
        self.assertIn("title", track)
        self.assertIn("artist", track)
        self.assertEqual(track["provider"], "saavn")

    async def test_premium_false_unlocks_all_features_for_free_users(self):
        # Set premium mode to False (Public Mode)
        db.set_premium_mode(False)
        self.addCleanup(lambda: db.set_premium_mode(True))

        free_uid = 888111
        db.update_user(free_uid, {"premium": False, "premium_until": None, "downloads_today": 10})

        # 1. db.is_premium should return True for free user
        self.assertTrue(db.is_premium(free_uid))

        # 2. db.can_download should return True with unlimited quota
        can_dl, reason = db.can_download(free_uid)
        self.assertTrue(can_dl)
        self.assertIsNone(reason)

        # 3. Direct /download <url> should be allowed for free user
        message = MagicMock()
        message.from_user = MagicMock()
        message.from_user.id = free_uid
        message.from_user.username = "free_user_public"
        message.command = ["download", "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT"]
        progress_msg = MagicMock()
        progress_msg.edit_text = AsyncMock()
        message.reply_text = AsyncMock(return_value=progress_msg)

        self.download_handler.download_track = AsyncMock(return_value=True)
        await self.command_handler.download_command(self.mock_bot, message)
        self.download_handler.download_track.assert_awaited_once()

        # 4. Settings command should be accessible to free user
        settings_msg = MagicMock()
        settings_msg.from_user = MagicMock()
        settings_msg.from_user.id = free_uid
        settings_msg.reply_text = AsyncMock()
        await self.command_handler.settings_command(self.mock_bot, settings_msg)
        settings_msg.reply_text.assert_called_once()
        self.assertIn("Settings", settings_msg.reply_text.call_args[0][0])

        # 5. /premium command should show public mode unlocked message
        prem_msg = MagicMock()
        prem_msg.from_user = MagicMock()
        prem_msg.from_user.id = free_uid
        prem_msg.command = ["premium"]
        prem_msg.reply_text = AsyncMock()
        await self.command_handler.premium_command(self.mock_bot, prem_msg)
        prem_msg.reply_text.assert_called_once()
        self.assertIn("All Features Unlocked", prem_msg.reply_text.call_args[0][0])

    async def test_admin_toggle_premium_mode_via_premium_command(self):
        # As owner, test toggling premium mode via /premium false and /premium true
        owner_msg = MagicMock()
        owner_msg.from_user = MagicMock()
        owner_msg.from_user.id = Config.OWNER_ID
        owner_msg.chat = MagicMock()
        owner_msg.chat.id = Config.OWNER_ID
        owner_msg.sender_chat = None
        owner_msg.reply_text = AsyncMock()

        # 1. Toggle off (False)
        owner_msg.command = ["premium", "false"]
        await self.command_handler.premium_command(self.mock_bot, owner_msg)
        self.assertFalse(db.get_premium_mode())
        owner_msg.reply_text.assert_called_once()
        self.assertIn("DISABLED", owner_msg.reply_text.call_args[0][0])

        # 2. Toggle on (True)
        owner_msg.reply_text.reset_mock()
        owner_msg.command = ["premium", "true"]
        await self.command_handler.premium_command(self.mock_bot, owner_msg)
        self.assertTrue(db.get_premium_mode())
        owner_msg.reply_text.assert_called_once()
        self.assertIn("ENABLED", owner_msg.reply_text.call_args[0][0])

if __name__ == "__main__":
    unittest.main()

