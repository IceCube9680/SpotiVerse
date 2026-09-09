import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timedelta, timezone
from config import Config
from utils.db import Database, _fallback_store
from utils.admin_security import AdminSecurityManager, admin_security, AdminAuthService
from handlers.admin_panel import AdminPanelHandler

class TestAdminSecurityAndPanel(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = Database(connect=False)
        self.db.available = False
        _fallback_store["users"].clear()
        _fallback_store["admin_audit"].clear()
        _fallback_store["bot_settings"].clear()
        _fallback_store["provider_settings"].clear()

        self.mock_bot = MagicMock()
        self.mock_bot.send_message = AsyncMock()
        self.panel = AdminPanelHandler(self.mock_bot)

    def tearDown(self):
        self.db.close()

    def test_owner_inherent_access(self):
        sec = AdminSecurityManager()
        owner_id = 12345678
        with patch.object(Config, "OWNER_ID", owner_id):
            self.assertTrue(sec.is_authenticated(owner_id))

    def test_unauthorized_user_rejected(self):
        sec = AdminSecurityManager()
        unauthorized_id = 999111
        with patch.object(Config, "OWNER_ID", 12345), \
             patch.object(Config, "OWNER_IDS", []), \
             patch.object(Config, "ADMINS", []):
            self.assertFalse(sec.is_authenticated(unauthorized_id))
            ok, msg = sec.verify_admin_code(unauthorized_id, "any")
            self.assertFalse(ok)
            self.assertIn("not authorized", msg)

    def test_admins_and_sudo_users_access(self):
        sec = AdminSecurityManager()
        admin_id = 888777
        with patch.object(Config, "OWNER_ID", 12345), \
             patch.object(Config, "ADMINS", [admin_id]):
            self.assertTrue(sec.is_authenticated(admin_id))

    async def test_admin_callback_owner_allowed(self):
        from pyrogram.types import CallbackQuery
        owner_id = 123456
        cb = MagicMock()
        cb.__class__ = CallbackQuery
        cb.from_user = MagicMock()
        cb.from_user.id = owner_id
        cb.data = "adm_stats_30d"
        cb.answer = AsyncMock()
        cb.message = MagicMock()
        cb.message.edit_text = AsyncMock()
        cb.reply_text = AsyncMock()

        with patch.object(Config, "OWNER_ID", owner_id):
            await self.panel.handle_callback(self.mock_bot, cb)
            cb.answer.assert_called_with("Loading statistics...")

    async def test_admin_callback_unauthorized_rejected(self):
        user_id = 999888
        cb = MagicMock()
        cb.from_user.id = user_id
        cb.data = "adm_stats_30d"
        cb.answer = AsyncMock()
        cb.message.edit_text = AsyncMock()

        with patch.object(Config, "OWNER_ID", 12345), \
             patch.object(Config, "OWNER_IDS", []), \
             patch.object(Config, "ADMINS", []):
            await self.panel.handle_callback(self.mock_bot, cb)
            cb.answer.assert_called_with("❌ You are not authorized to access the admin panel.", show_alert=True)

    async def test_admin_close_callback(self):
        owner_id = 123456
        cb = MagicMock()
        cb.from_user.id = owner_id
        cb.data = "adm_close"
        cb.answer = AsyncMock()
        cb.message.delete = AsyncMock()

        with patch.object(Config, "OWNER_ID", owner_id):
            await self.panel.handle_callback(self.mock_bot, cb)
            cb.message.delete.assert_called_once()
            cb.answer.assert_called_with("Admin panel closed.")

    def test_check_user_profile(self):
        uid = 555666
        self.db.update_user(uid, {
            "first_name": "Alice",
            "username": "alice_test",
            "premium": True,
            "premium_plan": "3 Months",
            "premium_until": (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=60)).isoformat(),
            "downloads_today": 3,
            "download_count": 42,
            "banned": False
        })
        user = self.db.get_user(uid)
        self.assertEqual(user["first_name"], "Alice")
        self.assertTrue(self.db.is_premium(uid))

    def test_expiring_soon_and_premium_users_lists(self):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        u1, u2, u3 = 101, 102, 103

        self.db.update_user(u1, {
            "first_name": "User 1",
            "premium": True,
            "premium_until": (now + timedelta(days=3)).isoformat()
        })
        self.db.update_user(u2, {
            "first_name": "User 2",
            "premium": True,
            "premium_until": (now + timedelta(days=20)).isoformat()
        })
        self.db.update_user(u3, {
            "first_name": "User 3",
            "premium": True,
            "lifetime_premium": True,
            "premium_until": None
        })

        expiring, exp_total = self.db.get_expiring_soon_users(warning_days=7)
        expiring_ids = [u.get("user_id") or u.get("telegram_id") for u in expiring]
        self.assertIn(u1, expiring_ids)
        self.assertNotIn(u2, expiring_ids)

        all_prem, total = self.db.get_premium_users(page=0, per_page=10)
        self.assertEqual(total, 3)

    def test_admin_audit_logging(self):
        admin_id = 999
        self.db.log_admin_action(admin_id, "add_premium", target_user=777, details="Added 30d plan")
        logs = self.db.get_admin_audit_logs(limit=10)
        self.assertTrue(len(logs) > 0)
        self.assertEqual(logs[0]["action"], "add_premium")

if __name__ == "__main__":
    unittest.main()
