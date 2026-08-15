import unittest
from unittest.mock import patch
import os
from utils.ytdlp_utils import get_ytdlp_options

class TestYtdlpUtils(unittest.TestCase):
    def test_get_ytdlp_options_default(self):
        opts = get_ytdlp_options()
        self.assertEqual(opts['format'], 'bestaudio/best')
        self.assertTrue(opts['quiet'])
        self.assertIn('youtube', opts['extractor_args'])
        self.assertEqual(opts['extractor_args']['youtube']['player_client'], ['ios', 'android', 'mweb', 'web'])

    def test_get_ytdlp_options_custom_extra(self):
        opts = get_ytdlp_options({'outtmpl': 'test.mp3'}, player_clients=['mweb', 'web'])
        self.assertEqual(opts['outtmpl'], 'test.mp3')
        self.assertEqual(opts['extractor_args']['youtube']['player_client'], ['mweb', 'web'])

    @patch("os.path.exists")
    def test_get_ytdlp_options_with_cookiefile(self, mock_exists):
        mock_exists.side_effect = lambda p: p == "cookies.txt"
        opts = get_ytdlp_options()
        self.assertEqual(opts.get('cookiefile'), 'cookies.txt')

if __name__ == "__main__":
    unittest.main()
