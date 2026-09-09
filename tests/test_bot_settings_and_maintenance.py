import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from config import Config
from utils.db import Database, _fallback_store
from utils.feature_gates import FeatureGate
from utils.queue import DownloadQueueManager, DownloadSlot

class TestBotSettingsAndMaintenance(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = Database(connect=False)
        self.db.available = False
        _fallback_store["bot_settings"].clear()
        _fallback_store["provider_settings"].clear()
        _fallback_store["users"].clear()

    def tearDown(self):
        FeatureGate.set_maintenance_mode(False)
        self.db.set_bot_setting("free_download", True)
        self.db.set_bot_setting("premium_download", True)
        self.db.set_bot_setting("premium_flac", True)
        self.db.set_bot_setting("premium_batch", True)
        self.db.set_bot_setting("premium_priority", True)
        self.db.close()

    def test_bot_settings_toggles_and_persistence(self):
        # Default states
        self.assertTrue(FeatureGate.is_feature_enabled("free_download", True))
        self.assertTrue(FeatureGate.is_feature_enabled("premium_download", True))
        self.assertTrue(FeatureGate.is_feature_enabled("premium_flac", True))

        # Disable free download
        self.db.set_bot_setting("free_download", False)
        self.assertFalse(FeatureGate.is_feature_enabled("free_download"))

        # Disable premium FLAC
        self.db.set_bot_setting("premium_flac", False)
        self.assertFalse(FeatureGate.is_feature_enabled("premium_flac"))

    def test_feature_gate_free_download_toggle(self):
        free_uid = 111000
        self.db.update_user(free_uid, {"premium": False, "downloads_today": 0})

        # When free download enabled
        self.db.set_bot_setting("free_download", True)
        auth = FeatureGate.authorize_download(free_uid, provider="youtube")
        self.assertTrue(auth.allowed)

        # When free download disabled by admin
        self.db.set_bot_setting("free_download", False)
        auth_disabled = FeatureGate.authorize_download(free_uid, provider="youtube")
        self.assertFalse(auth_disabled.allowed)
        self.assertIn("Free downloads are temporarily disabled", auth_disabled.reason)

    def test_feature_gate_flac_enforcement(self):
        free_uid = 222000
        prem_uid = 333000
        self.db.update_user(free_uid, {"premium": False, "preferred_format": "flac"})
        self.db.add_premium(prem_uid, 30)
        self.db.update_user(prem_uid, {"preferred_format": "flac"})

        # Free user requesting FLAC gets downgraded to MP3 64kbps
        auth_free = FeatureGate.authorize_download(free_uid, provider="youtube")
        self.assertEqual(auth_free.effective_format, "mp3")
        self.assertEqual(auth_free.effective_quality, 64)

        # Premium user gets FLAC when enabled
        self.db.set_bot_setting("premium_flac", True)
        auth_prem = FeatureGate.authorize_download(prem_uid, provider="youtube")
        self.assertEqual(auth_prem.effective_format, "flac")

        # When admin disables FLAC feature flag, premium user gets MP3 320kbps
        self.db.set_bot_setting("premium_flac", False)
        auth_prem_noflac = FeatureGate.authorize_download(prem_uid, provider="youtube")
        self.assertEqual(auth_prem_noflac.effective_format, "mp3")
        self.assertEqual(auth_prem_noflac.effective_quality, 320)

    def test_maintenance_mode_blocking_and_roles(self):
        free_uid = 444000
        prem_uid = 555000
        owner_id = Config.OWNER_ID

        self.db.update_user(free_uid, {"premium": False, "downloads_today": 0})
        self.db.add_premium(prem_uid, 30)

        # 1. Maintenance OFF
        FeatureGate.set_maintenance_mode(False)
        self.assertFalse(FeatureGate.is_maintenance_enabled())
        self.assertTrue(FeatureGate.authorize_download(free_uid, "youtube").allowed)
        self.assertTrue(FeatureGate.authorize_download(prem_uid, "youtube").allowed)

        # 2. Maintenance ON
        FeatureGate.set_maintenance_mode(True)
        self.assertTrue(FeatureGate.is_maintenance_enabled())

        # Free user blocked
        auth_free = FeatureGate.authorize_download(free_uid, "youtube")
        self.assertFalse(auth_free.allowed)
        self.assertIn("Maintenance Mode Active", auth_free.reason)

        # Owner allowed (MAINTENANCE_ALLOW_ADMIN=True)
        auth_owner = FeatureGate.authorize_download(owner_id, "youtube")
        self.assertTrue(auth_owner.allowed)

        # Premium user blocked by default (MAINTENANCE_ALLOW_PREMIUM=False)
        with patch.object(Config, "MAINTENANCE_ALLOW_PREMIUM", False):
            auth_prem = FeatureGate.authorize_download(prem_uid, "youtube")
            self.assertFalse(auth_prem.allowed)

        # Premium user allowed when MAINTENANCE_ALLOW_PREMIUM=True
        with patch.object(Config, "MAINTENANCE_ALLOW_PREMIUM", True):
            auth_prem_allowed = FeatureGate.authorize_download(prem_uid, "youtube")
            self.assertTrue(auth_prem_allowed.allowed)

    async def test_priority_queue_slot_management(self):
        queue = DownloadQueueManager()
        self.assertEqual(queue.queue_status["active_downloads"], 0)

        # Acquire premium slot
        async with DownloadSlot(queue, is_premium=True, priority=True):
            self.assertEqual(queue.queue_status["active_downloads"], 1)

        self.assertEqual(queue.queue_status["active_downloads"], 0)

if __name__ == "__main__":
    unittest.main()
