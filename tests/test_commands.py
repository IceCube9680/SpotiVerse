import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import os

os.environ["API_ID"] = "123456"
os.environ["API_HASH"] = "dummy_hash"
os.environ["BOT_TOKEN"] = "dummy_token"

from handlers.commands import CommandHandler

class TestCommandsNoneUser(unittest.IsolatedAsyncioTestCase):
    @patch("handlers.search.spotipy.Spotify")
    async def test_commands_with_none_from_user(self, mock_spotify):
        mock_client = MagicMock()
        mock_logger = MagicMock()
        mock_search = MagicMock()
        mock_download = MagicMock()

        handler = CommandHandler(mock_client, mock_logger, mock_search, mock_download)

        # Create message with from_user = None
        message = MagicMock()
        message.from_user = None
        message.command = ["start"]
        message.text = "/start"
        message.reply_text = AsyncMock()
        message.edit_text = AsyncMock()

        # None of these should raise AttributeError: 'NoneType' object has no attribute 'id'
        await handler.start_command(mock_client, message)
        await handler.search_command(mock_client, message)
        await handler.help_command(mock_client, message)
        await handler.settings_command(mock_client, message)
        await handler.download_command(mock_client, message)
        await handler.userinfo_command(mock_client, message)
        await handler.premium_command(mock_client, message)
        await handler.add_premium_command(mock_client, message)
        await handler.remove_premium_command(mock_client, message)
        await handler.logs_command(mock_client, message)
        await handler.stats_command(mock_client, message)
        await handler.users_command(mock_client, message)
        await handler.broadcast_command(mock_client, message)

        # Test callback with from_user = None
        callback_query = MagicMock()
        callback_query.from_user = None
        callback_query.data = "main_menu"
        callback_query.answer = AsyncMock()
        await handler.handle_callback(mock_client, callback_query)
        await handler._handle_broadcast_callback(callback_query)
        await handler._handle_settings_callback(callback_query)

    @patch("handlers.search.spotipy.Spotify")
    async def test_users_command_as_owner(self, mock_spotify):
        from config import Config
        mock_client = MagicMock()
        mock_logger = MagicMock()
        mock_search = MagicMock()
        mock_download = MagicMock()

        handler = CommandHandler(mock_client, mock_logger, mock_search, mock_download)

        # Create message as owner
        message = MagicMock()
        message.from_user = MagicMock()
        message.from_user.id = Config.OWNER_ID
        message.command = ["users"]
        message.reply_text = AsyncMock()

        await handler.users_command(mock_client, message)
        message.reply_text.assert_called_once()
        self.assertIn("Total Users", message.reply_text.call_args[0][0])

    @patch("handlers.search.spotipy.Spotify")
    async def test_add_and_remove_premium_commands(self, mock_spotify):
        from config import Config
        from utils.db import db
        mock_client = MagicMock()
        mock_client.send_message = AsyncMock()
        mock_logger = MagicMock()
        mock_logger.log_premium_change = AsyncMock()
        mock_search = MagicMock()
        mock_download = MagicMock()

        handler = CommandHandler(mock_client, mock_logger, mock_search, mock_download)

        # 1. Test add_premium by numeric user ID (30d default)
        target_uid = 987654321
        message = MagicMock()
        message.from_user = MagicMock()
        message.from_user.id = Config.OWNER_ID
        message.reply_to_message = None
        message.command = ["add_premium", str(target_uid), "30d"]
        message.reply_text = AsyncMock()

        await handler.add_premium_command(mock_client, message)
        message.reply_text.assert_called_once()
        self.assertIn("Premium access granted", message.reply_text.call_args[0][0])
        user_data = db.get_user(target_uid)
        self.assertTrue(user_data.get("premium"))
        self.assertIsNotNone(user_data.get("premium_until"))

        # 2. Test add_premium with hours (e.g. 12h)
        message.command = ["add_premium", str(target_uid), "12h"]
        message.reply_text = AsyncMock()
        await handler.add_premium_command(mock_client, message)
        self.assertIn("Premium access granted", message.reply_text.call_args[0][0])

        # 3. Test add_premium by replying to a user's message
        reply_user_id = 555666777
        message_reply = MagicMock()
        message_reply.from_user = MagicMock()
        message_reply.from_user.id = reply_user_id

        message.reply_to_message = message_reply
        message.command = ["add_premium", "7d"]
        message.reply_text = AsyncMock()
        await handler.add_premium_command(mock_client, message)
        self.assertIn("Premium access granted", message.reply_text.call_args[0][0])
        reply_user_data = db.get_user(reply_user_id)
        self.assertTrue(reply_user_data.get("premium"))

        # 4. Test add_premium with lifetime
        message.reply_to_message = None
        message.command = ["add_premium", str(target_uid), "lifetime"]
        message.reply_text = AsyncMock()
        await handler.add_premium_command(mock_client, message)
        self.assertIn("Lifetime", message.reply_text.call_args[0][0])

        # 5. Test remove_premium by user ID
        message.command = ["remove_premium", str(target_uid)]
        message.reply_text = AsyncMock()
        await handler.remove_premium_command(mock_client, message)
        self.assertIn("Premium access removed", message.reply_text.call_args[0][0])
        user_data_removed = db.get_user(target_uid)
        self.assertFalse(user_data_removed.get("premium"))
        self.assertIsNone(user_data_removed.get("premium_until"))

        # 6. Test remove_premium by reply
        message.reply_to_message = message_reply
        message.command = ["remove_premium"]
        message.reply_text = AsyncMock()
        await handler.remove_premium_command(mock_client, message)
        self.assertIn("Premium access removed", message.reply_text.call_args[0][0])
        reply_user_removed = db.get_user(reply_user_id)
        self.assertFalse(reply_user_removed.get("premium"))

        # 7. Non-owner cannot use add_premium / remove_premium
        non_owner_msg = MagicMock()
        non_owner_msg.from_user = MagicMock()
        non_owner_msg.from_user.id = 111222333  # non-owner
        non_owner_msg.chat = MagicMock()
        non_owner_msg.chat.id = 111222333
        non_owner_msg.sender_chat = None
        non_owner_msg.reply_to_message = None
        non_owner_msg.command = ["add_premium", "123", "30d"]
        non_owner_msg.reply_text = AsyncMock()

        await handler.add_premium_command(mock_client, non_owner_msg)
        self.assertIn("bot owner only", non_owner_msg.reply_text.call_args[0][0])

        non_owner_msg.command = ["remove_premium", "123"]
        non_owner_msg.reply_text = AsyncMock()
        await handler.remove_premium_command(mock_client, non_owner_msg)
        self.assertIn("bot owner only", non_owner_msg.reply_text.call_args[0][0])

    @patch("handlers.search.spotipy.Spotify")
    async def test_direct_message_handler(self, mock_spotify):
        mock_client = MagicMock()
        mock_logger = MagicMock()
        mock_search = MagicMock()
        mock_download = MagicMock()

        handler = CommandHandler(mock_client, mock_logger, mock_search, mock_download)
        handler.download_command = AsyncMock()
        handler.search_command = AsyncMock()

        # 1. Direct URL message
        url_msg = MagicMock()
        url_msg.from_user = MagicMock()
        url_msg.from_user.id = 12345
        url_msg.text = "https://open.spotify.com/intl-pt-br/track/4cOdK2wGLETKBW3PvgPWqT"

        await handler.direct_message_handler(mock_client, url_msg)
        handler.download_command.assert_awaited_once_with(mock_client, url_msg)
        self.assertEqual(url_msg.command, ["download", url_msg.text])

        # 2. Direct search query message
        query_msg = MagicMock()
        query_msg.from_user = MagicMock()
        query_msg.from_user.id = 12345
        query_msg.text = "alan walker faded"

        await handler.direct_message_handler(mock_client, query_msg)
        handler.search_command.assert_awaited_once_with(mock_client, query_msg)
        self.assertEqual(query_msg.command, ["search", "alan", "walker", "faded"])

    @patch("handlers.search.spotipy.Spotify")
    async def test_broadcast_offline_resilience_and_multiparagraph(self, mock_spotify):
        from config import Config
        from utils.db import db, _fallback_store
        mock_client = MagicMock()
        mock_client.send_message = AsyncMock()
        mock_logger = MagicMock()
        mock_search = MagicMock()
        mock_download = MagicMock()

        handler = CommandHandler(mock_client, mock_logger, mock_search, mock_download)

        # Set up fallback store with users
        _fallback_store["users"].clear()
        _fallback_store["users"][1001] = {"user_id": 1001}
        _fallback_store["users"][1002] = {"user_id": 1002}
        db.available = False  # Simulate MongoDB offline

        # Mock callback query with multi-paragraph text
        cb = MagicMock()
        cb.from_user = MagicMock()
        cb.from_user.id = Config.OWNER_ID
        cb.data = "broadcast_confirm"
        cb.message = MagicMock()
        cb.message.text = "📢 **Broadcast Confirmation**\n\nMessage: Paragraph 1\n\nParagraph 2\n\nParagraph 3\n\nAre you sure?"
        cb.message.edit_text = AsyncMock()
        cb.answer = AsyncMock()

        await handler._handle_broadcast_callback(cb)

        # Verify broadcast sent to all fallback users
        self.assertEqual(mock_client.send_message.call_count, 2)
        sent_text = mock_client.send_message.call_args_list[0][0][1]
        self.assertIn("Paragraph 1\n\nParagraph 2\n\nParagraph 3", sent_text)
        self.assertNotIn("Are you sure?", sent_text)

    @patch("handlers.search.spotipy.Spotify")
    async def test_search_cancel_and_clear_logs_callbacks(self, mock_spotify):
        from config import Config
        mock_client = MagicMock()
        mock_logger = MagicMock()
        mock_search = MagicMock()
        mock_download = MagicMock()

        handler = CommandHandler(mock_client, mock_logger, mock_search, mock_download)

        # 1. cancel_search callback
        cb_cancel = MagicMock()
        cb_cancel.from_user = MagicMock()
        cb_cancel.from_user.id = 12345
        cb_cancel.data = "cancel_search"
        cb_cancel.message = MagicMock()
        cb_cancel.message.delete = AsyncMock()
        cb_cancel.answer = AsyncMock()

        await handler.handle_callback(mock_client, cb_cancel)
        cb_cancel.message.delete.assert_called_once()

        # 2. clear_logs callback as owner
        owner_uid = 999888
        cb_clear = MagicMock()
        cb_clear.from_user = MagicMock()
        cb_clear.from_user.id = owner_uid
        cb_clear.data = "clear_logs"
        cb_clear.message = MagicMock()
        cb_clear.message.edit_text = AsyncMock()
        cb_clear.answer = AsyncMock()

        with patch.object(Config, "OWNER_ID", owner_uid):
            await handler.handle_callback(mock_client, cb_clear)
            cb_clear.message.edit_text.assert_called_once()
            self.assertIn("cleared successfully", cb_clear.message.edit_text.call_args[0][0])

    def test_database_iso_string_date_parsing_and_expiry(self):
        from utils.db import Database, _fallback_store
        db_instance = Database(connect=False)
        db_instance.available = False
        self.addCleanup(db_instance.close)

        uid = 777888999
        # Expired ISO string date
        _fallback_store["users"][uid] = {
            "user_id": uid,
            "premium": True,
            "premium_until": "2020-01-01T00:00:00",
            "downloads_today": 5,
            "total_downloads": 5,
            "last_download_date": "2020-01-01"
        }

        # can_download should detect expired ISO string date and downgrade to free
        allowed, reason = db_instance.can_download(uid)
        u = db_instance.get_user(uid)
        self.assertFalse(u.get("premium"))
        self.assertIsNone(u.get("premium_until"))

    @patch("handlers.search.spotipy.Spotify")
    async def test_settings_command_for_owner_and_premium(self, mock_spotify):
        from config import Config
        from utils.db import db
        mock_client = MagicMock()
        mock_logger = MagicMock()
        mock_search = MagicMock()
        mock_download = MagicMock()

        handler = CommandHandler(mock_client, mock_logger, mock_search, mock_download)

        # 1. Owner should always have access to settings
        owner_msg = MagicMock()
        owner_msg.from_user = MagicMock()
        owner_msg.from_user.id = Config.OWNER_ID
        owner_msg.reply_text = AsyncMock()

        await handler.settings_command(mock_client, owner_msg)
        owner_msg.reply_text.assert_called_once()
        self.assertIn("Settings", owner_msg.reply_text.call_args[0][0])

        # 2. Free user should be blocked from settings
        free_uid = 333444555
        db.update_user(free_uid, {"premium": False, "premium_until": None})
        free_msg = MagicMock()
        free_msg.from_user = MagicMock()
        free_msg.from_user.id = free_uid
        free_msg.reply_text = AsyncMock()

        await handler.settings_command(mock_client, free_msg)
        free_msg.reply_text.assert_called_once()
        self.assertIn("Premium users only", free_msg.reply_text.call_args[0][0])

        # 3. User granted premium should have access to settings
        db.add_premium(free_uid, 30)
        prem_msg = MagicMock()
        prem_msg.from_user = MagicMock()
        prem_msg.from_user.id = free_uid
        prem_msg.reply_text = AsyncMock()

        await handler.settings_command(mock_client, prem_msg)
        prem_msg.reply_text.assert_called_once()
        self.assertIn("Settings", prem_msg.reply_text.call_args[0][0])

if __name__ == "__main__":
    unittest.main()
