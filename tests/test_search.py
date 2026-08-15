import unittest
from unittest.mock import patch, MagicMock
import os

from handlers.search import SearchHandler

class TestSearchHandlerAnonymous(unittest.TestCase):
    @patch.dict(os.environ, {"SPOTIFY_CLIENT_ID": "", "SPOTIFY_CLIENT_SECRET": ""}, clear=True)
    def test_search_handler_init_without_credentials(self):
        handler = SearchHandler()
        self.assertTrue(handler._use_anonymous_token)
        self.assertIsNone(handler.spotify)

    def test_get_spotify_client_anonymous(self):
        handler = SearchHandler()
        handler._use_anonymous_token = True
        handler._anon_token = "dummy_token"
        handler._anon_token_expiry = 9999999999
        
        client = handler.get_spotify_client()
        self.assertIsNotNone(client)

if __name__ == "__main__":
    unittest.main()
