import os
import unittest
from unittest.mock import patch
from config import _int_env, Config

class TestConfigParsing(unittest.TestCase):
    @patch.dict(os.environ, {"TEST_VAR_INT": "42", "TEST_VAR_STR": "abc", "TEST_VAR_EMPTY": ""})
    def test_int_env(self):
        # Valid integer
        self.assertEqual(_int_env("TEST_VAR_INT", 10), 42)

        # Missing variable
        self.assertEqual(_int_env("TEST_VAR_NONEXISTENT", 10), 10)

        # Empty string
        self.assertEqual(_int_env("TEST_VAR_EMPTY", 10), 10)

        # Invalid integer string
        self.assertEqual(_int_env("TEST_VAR_STR", 10), 10)

    def test_config_attributes(self):
        # Ensure default limits/configs are of expected types
        self.assertIsInstance(Config.FREE_USER_DAILY_LIMIT, int)
        self.assertIsInstance(Config.MAX_CONCURRENT_DOWNLOADS, int)
        self.assertIsInstance(Config.API_ID, int)
        self.assertIsInstance(Config.LOG_CHANNEL, int)
        self.assertIsInstance(Config.DOWNLOAD_LOG_CHANNEL, int)
        self.assertIsInstance(Config.OWNER_ID, int)
