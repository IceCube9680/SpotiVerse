import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio
import os
from datetime import datetime
import pyrogram.errors
from config import Config
from utils.db import db

os.environ["API_ID"] = "123456"
os.environ["API_HASH"] = "dummy_hash"
os.environ["BOT_TOKEN"] = "dummy_token"

from handlers.downloads import DownloadHandler

class TestDownloads(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mock_bot = MagicMock()
        self.mock_bot.send_message = AsyncMock()
        self.mock_bot.send_audio = AsyncMock()
        self.mock_logger = MagicMock()
        self.mock_logger.log_download = AsyncMock()
        self.mock_search = MagicMock()
        self.handler = DownloadHandler(self.mock_bot, self.mock_logger, self.mock_search)

    async def test_safe_edit_message_normal(self):
        mock_msg = MagicMock()
        mock_msg.edit_text = AsyncMock(return_value="edited")
        res = await self.handler.safe_edit_message(mock_msg, "hello")
        self.assertEqual(res, "edited")
        mock_msg.edit_text.assert_awaited_once_with("hello")

    async def test_safe_edit_message_not_modified(self):
        mock_msg = MagicMock()
        mock_msg.edit_text = AsyncMock(side_effect=pyrogram.errors.MessageNotModified(None, None))
        res = await self.handler.safe_edit_message(mock_msg, "same text")
        self.assertEqual(res, mock_msg)

    async def test_safe_edit_message_flood_wait(self):
        mock_msg = MagicMock()
        # First call raises FloodWait, second succeeds
        fw_err = pyrogram.errors.FloodWait(value=0)
        mock_msg.edit_text = AsyncMock(side_effect=[fw_err, "edited after flood"])
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            res = await self.handler.safe_edit_message(mock_msg, "text")
            self.assertEqual(res, "edited after flood")
            mock_sleep.assert_awaited_with(1)

    async def test_safe_edit_message_fallback_to_send(self):
        mock_msg = MagicMock()
        mock_msg.edit_text = AsyncMock(side_effect=pyrogram.errors.MessageIdInvalid(None, None))
        mock_msg.chat.id = 12345
        new_sent_msg = MagicMock()
        self.mock_bot.send_message.return_value = new_sent_msg

        res = await self.handler.safe_edit_message(mock_msg, "fallback text")
        self.assertEqual(res, new_sent_msg)
        self.mock_bot.send_message.assert_awaited_once_with(chat_id=12345, text="fallback text")

    @patch("handlers.downloads.db")
    @patch("handlers.downloads.asyncio.create_task")
    async def test_download_track_batch_mode_no_delete_task(self, mock_create_task, mock_db):
        mock_create_task.side_effect = lambda coro: coro.close()
        mock_db.get_user.return_value = {"preferred_format": "mp3", "preferred_quality": 320}
        mock_db.can_download.return_value = (True, None)

        self.handler.get_track_info = AsyncMock(return_value={
            "id": "t1",
            "title": "Track 1",
            "artist": "Artist 1",
            "album": "Album 1",
            "year": "2023",
            "duration": 180,
            "thumbnail": None
        })
        self.handler.download_audio = AsyncMock(return_value="temp/t1.mp3")
        self.handler.audio_processor.add_metadata = MagicMock()
        self.handler.audio_processor.generate_thumbnail = MagicMock(return_value=None)

        mock_msg = MagicMock()
        mock_msg.edit_text = AsyncMock(return_value=mock_msg)
        mock_msg.chat.id = 999
        mock_msg.date = 123456789

        # Run with is_batch=True
        db.add_premium(999, 30)
        success = await self.handler.download_track("spotify", "t1", 999, mock_msg, is_batch=True)
        self.assertTrue(success)
        # Verify create_task was NOT called to schedule _delete_later
        mock_create_task.assert_not_called()

        # Run with is_batch=False
        success_single = await self.handler.download_track("spotify", "t1", 999, mock_msg, is_batch=False)
        self.assertTrue(success_single)
        # Verify create_task WAS called for single track download
        mock_create_task.assert_called_once()

    @patch("handlers.downloads.db")
    @patch("utils.feature_gates.db")
    async def test_download_album_resilience_and_batch_flag(self, mock_fg_db, mock_db):
        mock_db.is_premium.return_value = True
        mock_db.get_user.return_value = {"premium": True}
        mock_db.can_download.return_value = (True, None)
        mock_db.get_bot_setting.side_effect = lambda k, d=None: False if k == "maintenance_mode" else True
        mock_fg_db.is_premium.return_value = True
        mock_fg_db.get_user.return_value = {"premium": True}
        mock_fg_db.can_download.return_value = (True, None)
        mock_fg_db.get_bot_setting.side_effect = lambda k, d=None: False if k == "maintenance_mode" else True

        mock_msg = MagicMock()
        mock_msg.edit_text = AsyncMock(return_value=mock_msg)
        mock_msg.delete = AsyncMock()
        mock_msg.chat.id = 999

        self.handler.download_track = AsyncMock(side_effect=[True, Exception("Network error"), True])
        self.handler._youtube_get_playlist_entries = AsyncMock(return_value=[
            {"id": "v1", "webpage_url": "https://youtube.com/watch?v=v1"},
            {"id": "v2", "webpage_url": "https://youtube.com/watch?v=v2"},
            {"id": "v3", "webpage_url": "https://youtube.com/watch?v=v3"},
        ])

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await self.handler.download_album("youtube", "https://youtube.com/playlist?list=PL123", 999, mock_msg)

        self.assertTrue(result)
        self.assertEqual(self.handler.download_track.call_count, 3)
        # Ensure all download_track calls passed is_batch=True
        for call in self.handler.download_track.call_args_list:
            self.assertTrue(call.kwargs.get("is_batch"))

    def test_database_can_download_premium_vs_free(self):
        from utils.db import Database, _fallback_store
        from datetime import timezone
        db_instance = Database(connect=False)
        db_instance._try_connect = MagicMock()
        db_instance.available = False  # Use in-memory fallback for test
        self.addCleanup(db_instance.close)

        with patch.object(Config, "FREE_USER_DAILY_LIMIT", 5):
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            # Free user with 0 downloads -> allowed
            user_free_id = 111111
            _fallback_store["users"][user_free_id] = {
                "user_id": user_free_id,
                "premium": False,
                "premium_until": None,
                "downloads_today": 0,
                "total_downloads": 0,
                "last_download_date": today_str
            }
            allowed, reason = db_instance.can_download(user_free_id)
            self.assertTrue(allowed)
            self.assertIsNone(reason)

            # Free user at limit -> not allowed
            _fallback_store["users"][user_free_id]["downloads_today"] = 5
            allowed_limit, reason_limit = db_instance.can_download(user_free_id)
            self.assertFalse(allowed_limit)
            self.assertIn("Daily download limit reached", reason_limit)

            # Premium user -> UNLIMITED (allowed=True)
            user_prem_id = 222222
            _fallback_store["users"][user_prem_id] = {
                "user_id": user_prem_id,
                "premium": True,
                "premium_until": None,
                "downloads_today": 999,
                "total_downloads": 999,
                "last_download_date": today_str
            }
            allowed_prem, reason_prem = db_instance.can_download(user_prem_id)
            self.assertTrue(allowed_prem)
            self.assertIsNone(reason_prem)

    async def test_log_download_user_id_and_username(self):
        from utils.logger import BotLogger
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()
        logger_obj = BotLogger(mock_bot)

        # 1. Test with both user_id and username
        with patch.object(Config, "DOWNLOAD_LOG_CHANNEL", -1001234567):
            await logger_obj.log_download(
                user_id=123456,
                track_info={"title": "Song A", "artist": "Artist B"},
                format_used="mp3 320",
                username="music_fan"
            )
            mock_bot.send_message.assert_awaited_once()
            log_msg = mock_bot.send_message.call_args[0][1]
            self.assertIn("Download Recorded", log_msg)
            self.assertIn("User ID:** `123456` (@music_fan)", log_msg)
            self.assertIn("Track:** Song A", log_msg)

        # 2. Test with no user_id, only username
        mock_bot.send_message.reset_mock()
        with patch.object(Config, "DOWNLOAD_LOG_CHANNEL", -1001234567):
            await logger_obj.log_download(
                user_id=None,
                track_info={"title": "Song C", "artist": "Artist D"},
                format_used="mp3 320",
                username="music_fan"
            )
            mock_bot.send_message.assert_awaited_once()
            log_msg = mock_bot.send_message.call_args[0][1]
            self.assertIn("Username:** @music_fan", log_msg)

if __name__ == "__main__":
    unittest.main()
