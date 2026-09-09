import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from utils.db import Database, _fallback_store
from utils.providers import ProviderRegistry
from utils.feature_gates import FeatureGate
from handlers.search import SearchHandler

class TestProviderManagement(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = Database(connect=False)
        self.db.available = False
        _fallback_store["provider_settings"].clear()
        _fallback_store["bot_settings"].clear()
        _fallback_store["users"].clear()

    def tearDown(self):
        for p in ProviderRegistry.get_all_providers():
            ProviderRegistry.set_enabled(p.id, True)
        self.db.close()

    def test_provider_initial_state_and_aliases(self):
        # All required providers exist
        all_provs = [p.id for p in ProviderRegistry.get_all_providers()]
        self.assertIn("spotify", all_provs)
        self.assertIn("youtube", all_provs)
        self.assertIn("jiosaavn", all_provs)
        self.assertIn("soundcloud", all_provs)
        self.assertIn("deezer", all_provs)

        # Aliases
        self.assertEqual(ProviderRegistry.normalize_id("sp"), "spotify")
        self.assertEqual(ProviderRegistry.normalize_id("yt"), "youtube")
        self.assertEqual(ProviderRegistry.normalize_id("saavn"), "jiosaavn")
        self.assertEqual(ProviderRegistry.normalize_id("sc"), "soundcloud")
        self.assertEqual(ProviderRegistry.normalize_id("dz"), "deezer")

    def test_provider_toggle_and_persistence(self):
        # Default is True
        self.assertTrue(ProviderRegistry.is_enabled("spotify"))

        # Disable Spotify
        ProviderRegistry.set_enabled("spotify", False)
        self.assertFalse(ProviderRegistry.is_enabled("spotify"))
        self.assertFalse(ProviderRegistry.is_enabled("sp"))

        # Toggle back to True
        new_state = ProviderRegistry.toggle("spotify")
        self.assertTrue(new_state)
        self.assertTrue(ProviderRegistry.is_enabled("spotify"))

    def test_download_rejection_when_provider_disabled(self):
        uid = 123456
        self.db.add_premium(uid, 30)

        # Enable Deezer
        ProviderRegistry.set_enabled("deezer", True)
        auth = FeatureGate.authorize_download(uid, provider="deezer")
        self.assertTrue(auth.allowed)

        # Disable Deezer
        ProviderRegistry.set_enabled("deezer", False)
        auth_disabled = FeatureGate.authorize_download(uid, provider="deezer")
        self.assertFalse(auth_disabled.allowed)
        self.assertIn("Deezer", auth_disabled.reason)
        self.assertIn("is currently disabled", auth_disabled.reason)

    async def test_search_routing_skips_disabled_provider(self):
        search_handler = SearchHandler()
        search_handler.search_spotify = AsyncMock(return_value=[{"id": "sp1", "title": "Track 1"}])
        search_handler.search_saavn = AsyncMock(return_value=None)
        search_handler.search_youtube = AsyncMock(return_value=[{"id": "yt1", "title": "Track 2"}])

        # Spotify enabled
        ProviderRegistry.set_enabled("spotify", True)
        res = await search_handler.search_all("test query", provider="spotify")
        search_handler.search_spotify.assert_awaited_once()

        # Disable Spotify
        ProviderRegistry.set_enabled("spotify", False)
        ProviderRegistry.set_enabled("youtube", True)
        search_handler.search_spotify.reset_mock()
        search_handler.search_youtube.reset_mock()

        # Searching with spotify requested should bypass spotify and fallback to youtube
        res_fb = await search_handler.search_all("different query", provider="spotify")
        search_handler.search_spotify.assert_not_called()
        search_handler.search_youtube.assert_awaited_once()

if __name__ == "__main__":
    unittest.main()
