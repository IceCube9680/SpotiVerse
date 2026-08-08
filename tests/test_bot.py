import unittest
from unittest.mock import MagicMock, patch
import os

# Set dummy environment variables to avoid validation errors
os.environ["API_ID"] = "123456"
os.environ["API_HASH"] = "dummy_hash"
os.environ["BOT_TOKEN"] = "dummy_token"

from bot import SpotiVerseBot
from handlers.commands import CommandHandler

class TestBotInitialization(unittest.TestCase):
    @patch("bot.Client")
    @patch("handlers.search.spotipy.Spotify")
    def test_bot_init_and_handlers(self, mock_spotify, mock_client):
        # Create bot instance
        bot_instance = SpotiVerseBot()

        # Verify bot, logger, search_handler, download_handler, and command_handler are created
        self.assertIsNotNone(bot_instance.bot)
        self.assertIsNotNone(bot_instance.logger)
        self.assertIsNotNone(bot_instance.search_handler)
        self.assertIsNotNone(bot_instance.download_handler)
        self.assertIsNotNone(bot_instance.command_handler)

        # Verify command_handler is a CommandHandler
        self.assertIsInstance(bot_instance.command_handler, CommandHandler)

        # Verify individual command handler methods are present on command_handler
        # (This is crucial, because we made CommandHandler inherit from CommandsBinder)
        self.assertTrue(hasattr(bot_instance.command_handler, "start_command"))
        self.assertTrue(hasattr(bot_instance.command_handler, "help_command"))
        self.assertTrue(hasattr(bot_instance.command_handler, "search_command"))
        self.assertTrue(hasattr(bot_instance.command_handler, "download_command"))
        self.assertTrue(hasattr(bot_instance.command_handler, "userinfo_command"))
        self.assertTrue(hasattr(bot_instance.command_handler, "premium_command"))
        self.assertTrue(hasattr(bot_instance.command_handler, "settings_command"))
        self.assertTrue(hasattr(bot_instance.command_handler, "add_premium_command"))
        self.assertTrue(hasattr(bot_instance.command_handler, "remove_premium_command"))
        self.assertTrue(hasattr(bot_instance.command_handler, "stats_command"))
        self.assertTrue(hasattr(bot_instance.command_handler, "broadcast_command"))
        self.assertTrue(hasattr(bot_instance.command_handler, "logs_command"))

        # Verify that add_handler was called on client for registration of handlers
        self.assertTrue(mock_client.return_value.add_handler.called)
