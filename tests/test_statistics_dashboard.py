import unittest
from datetime import datetime, timedelta, timezone
from utils.db import Database, _fallback_store

class TestStatisticsDashboard(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = Database(connect=False)
        self.db.available = False
        _fallback_store["users"].clear()
        _fallback_store["downloads"].clear()
        _fallback_store["admin_audit"].clear()
        _fallback_store["bot_settings"].clear()
        _fallback_store["provider_settings"].clear()

    def tearDown(self):
        self.db.close()

    def test_empty_database_zero_division_safety(self):
        stats = self.db.get_statistics(period="30d")
        self.assertEqual(stats["total_users"], 0)
        self.assertEqual(stats["premium_users"], 0)
        self.assertEqual(stats["total_downloads"], 0)
        self.assertEqual(stats["success_rate"], 0.0)
        self.assertEqual(stats["top_platforms"], {})
        self.assertEqual(stats["audio_volume_mb"], 0.0)

    def test_statistics_aggregation_and_math_accuracy(self):
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # 1. Users setup: 2 premium, 3 free
        self.db.add_premium(1, 30)
        self.db.update_user(1, {"created_at": (now - timedelta(days=2)).isoformat()})
        self.db.add_premium(2, 30)
        self.db.update_user(2, {"created_at": (now - timedelta(days=5)).isoformat()})
        self.db.update_user(3, {"premium": False, "created_at": (now - timedelta(days=10)).isoformat()})
        self.db.update_user(4, {"premium": False, "created_at": (now - timedelta(days=40)).isoformat()})
        self.db.update_user(5, {"premium": False, "created_at": (now - timedelta(days=1)).isoformat()})

        # 2. Downloads setup:
        # YouTube: 4 success, 1 failed
        # Spotify: 3 success
        # JioSaavn: 1 success
        # Total attempted = 8 success + 1 failed = 9 completed attempts
        # Expected success rate = 8 / 9 = 88.89% (or 88.9%)
        # Platform shares of successful downloads:
        # YouTube: 4/8 = 50.0%
        # Spotify: 3/8 = 37.5%
        # JioSaavn: 1/8 = 12.5%

        # 4 YouTube success (10 MB each)
        for i in range(4):
            rec = self.db.record_download_attempt(1, "youtube", f"yt_{i}", "success", "mp3", 320, premium=True)
            self.db.update_download_record(rec, status="success", file_size=10 * 1024 * 1024, duration=180)

        # 1 YouTube failed
        self.db.record_download_attempt(3, "youtube", "yt_fail", "failed", "mp3", 64, premium=False)

        # 3 Spotify success (15 MB each)
        for i in range(3):
            rec = self.db.record_download_attempt(2, "spotify", f"sp_{i}", "success", "flac", 0, premium=True)
            self.db.update_download_record(rec, status="success", file_size=15 * 1024 * 1024, duration=200)

        # 1 JioSaavn success (8 MB)
        rec = self.db.record_download_attempt(5, "jiosaavn", "saavn_1", "success", "mp3", 128, premium=False)
        self.db.update_download_record(rec, status="success", file_size=8 * 1024 * 1024, duration=150)

        # 1 Queued download (should not count towards completed success rate)
        self.db.record_download_attempt(4, "soundcloud", "sc_queued", "queued", "mp3", 64, premium=False)

        # Compute 30d stats
        stats = self.db.get_statistics(period="30d")
        self.assertEqual(stats["total_users"], 5)
        self.assertEqual(stats["premium_users"], 2)
        self.assertEqual(stats["free_users"], 3)
        self.assertEqual(stats["successful_downloads"], 8)
        self.assertEqual(stats["failed_downloads"], 1)

        # Verify mathematically accurate success rate: 8 / 9 = 88.9%
        self.assertAlmostEqual(stats["success_rate"], 88.9, places=1)

        # Verify top platform percentages
        top_platforms = stats["top_platforms"]
        self.assertAlmostEqual(top_platforms["YouTube"], 50.0, places=1)
        self.assertAlmostEqual(top_platforms["Spotify"], 37.5, places=1)
        self.assertAlmostEqual(top_platforms["JioSaavn"], 12.5, places=1)

        # Verify format counts
        self.assertEqual(stats["mp3_count"], 5)  # 4 yt + 1 saavn
        self.assertEqual(stats["flac_count"], 3) # 3 spotify

        # Verify user tier downloads
        self.assertEqual(stats["premium_downloads"], 7) # 4 yt + 3 sp
        self.assertEqual(stats["free_downloads"], 3)    # 1 fail + 1 saavn + 1 queued

    def test_statistics_periods(self):
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Recent download (2 hours ago)
        r1 = self.db.record_download_attempt(10, "spotify", "sp_recent", "success", "mp3", 320)
        self.db.update_download_record(r1, status="success", file_size=5000000, duration=120)

        # Older download (15 days ago)
        r2 = self.db.record_download_attempt(11, "youtube", "yt_old", "success", "mp3", 320)
        old_time = (now - timedelta(days=15)).isoformat()
        r2["timestamp"] = old_time
        r2["started_at"] = old_time
        r2["completed_at"] = old_time

        # 24h stats should only include recent
        stats_24h = self.db.get_statistics(period="24h")
        self.assertEqual(stats_24h["successful_downloads"], 1)

        # 30d stats should include both
        stats_30d = self.db.get_statistics(period="30d")
        self.assertEqual(stats_30d["successful_downloads"], 2)

        # All-time stats
        stats_all = self.db.get_statistics(period="all")
        self.assertEqual(stats_all["successful_downloads"], 2)

if __name__ == "__main__":
    unittest.main()
