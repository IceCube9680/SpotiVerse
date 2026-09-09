import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import os

os.environ["API_ID"] = "123456"
os.environ["API_HASH"] = "dummy_hash"
os.environ["BOT_TOKEN"] = "dummy_token"

from config import Config
from handlers.commands import CommandHandler
from handlers.admin_panel import AdminPanelHandler
from utils.db import db
from utils.ui_helpers import safe_edit_or_reply, safe_answer_callback
from pyrogram.errors import MessageNotModified, RPCError

class TestAllBackButtons(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        self.mock_client.send_message = AsyncMock()
        self.mock_logger = MagicMock()
        self.mock_search = MagicMock()
        self.mock_download = MagicMock()
        self.handler = CommandHandler(self.mock_client, self.mock_logger, self.mock_search, self.mock_download)
        self.admin_panel = self.handler.admin_panel
        self.owner_id = Config.OWNER_ID or 111111111
        Config.OWNER_ID = self.owner_id

    def _make_cb(self, data: str, user_id: int, is_doc: bool = False):
        cb = MagicMock()
        cb.data = data
        cb.from_user = MagicMock()
        cb.from_user.id = user_id
        cb.from_user.first_name = "TestUser"
        cb.from_user.username = "testuser"
        cb.answer = AsyncMock()
        
        msg = MagicMock()
        msg.chat = MagicMock()
        msg.chat.id = user_id
        msg.delete = AsyncMock()
        msg.reply_text = AsyncMock()
        if is_doc:
            msg.edit_text = AsyncMock(side_effect=RPCError("Telegram says: 400 MESSAGE_DOC_MODIFIED"))
        else:
            msg.edit_text = AsyncMock()
        cb.message = msg
        return cb

    async def test_user_back_button_from_menus(self):
        user_id = 999888777
        db.add_user(user_id, username="normaluser", first_name="Normal")

        # 1. Main Menu back button
        cb = self._make_cb("main_menu", user_id)
        await self.handler.handle_callback(self.mock_client, cb)
        cb.message.edit_text.assert_called_once()
        self.assertIn("SpotiVerse", cb.message.edit_text.call_args[0][0])

        # 2. 'back' callback alias
        cb = self._make_cb("back", user_id)
        await self.handler.handle_callback(self.mock_client, cb)
        cb.message.edit_text.assert_called_once()
        self.assertIn("SpotiVerse", cb.message.edit_text.call_args[0][0])

        # 3. Download menu and its back button
        cb = self._make_cb("menu_download", user_id)
        await self.handler.handle_callback(self.mock_client, cb)
        cb.message.edit_text.assert_called_once()
        self.assertIn("Search & Download Music", cb.message.edit_text.call_args[0][0])

        # 4. Settings menu and its back button
        cb = self._make_cb("menu_settings", user_id)
        await self.handler.handle_callback(self.mock_client, cb)
        cb.message.edit_text.assert_called_once()

        # 5. Help menu and its back button
        cb = self._make_cb("menu_help", user_id)
        await self.handler.handle_callback(self.mock_client, cb)
        cb.message.edit_text.assert_called_once()
        self.assertIn("Help & Guide", cb.message.edit_text.call_args[0][0])

        # 6. User profile and its back button
        cb = self._make_cb("user_profile", user_id)
        await self.handler.handle_callback(self.mock_client, cb)
        cb.message.edit_text.assert_called_once()

        # 7. View plans and its back button
        cb = self._make_cb("view_plans", user_id)
        await self.handler.handle_callback(self.mock_client, cb)
        cb.message.edit_text.assert_called_once()
        self.assertIn("Premium Plans", cb.message.edit_text.call_args[0][0])

    async def test_plan_checkout_back_navigation(self):
        user_id = 999888777
        db.add_user(user_id, username="normaluser", first_name="Normal")

        # Checkout screen
        cb = self._make_cb("buy_plan_monthly", user_id)
        await self.handler.handle_callback(self.mock_client, cb)
        cb.message.edit_text.assert_called_once()
        self.assertIn("Subscription Invoice", cb.message.edit_text.call_args[0][0])

        # Back to plans from checkout
        cb_plans = self._make_cb("view_plans", user_id)
        await self.handler.handle_callback(self.mock_client, cb_plans)
        cb_plans.message.edit_text.assert_called_once()
        self.assertIn("Premium Plans", cb_plans.message.edit_text.call_args[0][0])

        # Main menu from checkout
        cb_main = self._make_cb("main_menu", user_id)
        await self.handler.handle_callback(self.mock_client, cb_main)
        cb_main.message.edit_text.assert_called_once()
        self.assertIn("SpotiVerse", cb_main.message.edit_text.call_args[0][0])

    async def test_admin_back_buttons(self):
        # 1. Back to adm_main from statistics
        cb = self._make_cb("adm_main", self.owner_id)
        await self.admin_panel.handle_callback(self.mock_client, cb)
        cb.message.edit_text.assert_called_once()
        self.assertIn("Admin Panel", cb.message.edit_text.call_args[0][0])

        # 2. Stats menu and back button
        cb = self._make_cb("adm_stats_30d", self.owner_id)
        await self.admin_panel.handle_callback(self.mock_client, cb)
        cb.message.edit_text.assert_called_once()
        self.assertIn("Statistics", cb.message.edit_text.call_args[0][0])

        # 3. Settings menu and back button
        cb = self._make_cb("adm_settings_menu", self.owner_id)
        await self.admin_panel.handle_callback(self.mock_client, cb)
        cb.message.edit_text.assert_called_once()
        self.assertIn("Bot Settings", cb.message.edit_text.call_args[0][0])

        # 4. Providers menu and back button
        cb = self._make_cb("adm_prov_menu", self.owner_id)
        await self.admin_panel.handle_callback(self.mock_client, cb)
        cb.message.edit_text.assert_called_once()
        self.assertIn("Provider Management", cb.message.edit_text.call_args[0][0])

        # 5. Maintenance menu and back button
        cb = self._make_cb("adm_maint_menu", self.owner_id)
        await self.admin_panel.handle_callback(self.mock_client, cb)
        cb.message.edit_text.assert_called_once()
        self.assertIn("Maintenance Mode", cb.message.edit_text.call_args[0][0])

        # 6. Premium menu and back button
        cb = self._make_cb("adm_prem_menu", self.owner_id)
        await self.admin_panel.handle_callback(self.mock_client, cb)
        cb.message.edit_text.assert_called_once()
        self.assertIn("Premium Management", cb.message.edit_text.call_args[0][0])

        # 7. Users list and back button
        cb = self._make_cb("adm_prem_list_0", self.owner_id)
        await self.admin_panel.handle_callback(self.mock_client, cb)
        cb.message.edit_text.assert_called_once()
        self.assertIn("Premium Users", cb.message.edit_text.call_args[0][0])

        # 8. Expiring soon and back button
        cb = self._make_cb("adm_prem_expiring_0", self.owner_id)
        await self.admin_panel.handle_callback(self.mock_client, cb)
        cb.message.edit_text.assert_called_once()
        self.assertIn("Expiring Soon", cb.message.edit_text.call_args[0][0])

        # 9. Check user card and back button
        cb = self._make_cb(f"adm_check_{self.owner_id}", self.owner_id)
        await self.admin_panel.handle_callback(self.mock_client, cb)
        cb.message.edit_text.assert_called_once()
        self.assertIn("User Information Card", cb.message.edit_text.call_args[0][0])

        # 10. Grant duration selection and back button
        cb = self._make_cb(f"adm_grant_to_{self.owner_id}", self.owner_id)
        await self.admin_panel.handle_callback(self.mock_client, cb)
        cb.message.edit_text.assert_called_once()
        self.assertIn("Select Premium Duration", cb.message.edit_text.call_args[0][0])

        # 11. Revoke prompt and cancel back button
        cb = self._make_cb(f"adm_revoke_from_{self.owner_id}", self.owner_id)
        await self.admin_panel.handle_callback(self.mock_client, cb)
        cb.message.edit_text.assert_called_once()
        self.assertIn("Remove Premium?", cb.message.edit_text.call_args[0][0])

        # 12. Users menu and back button
        cb = self._make_cb("adm_users_menu", self.owner_id)
        await self.admin_panel.handle_callback(self.mock_client, cb)
        cb.message.edit_text.assert_called_once()
        self.assertIn("User Management", cb.message.edit_text.call_args[0][0])

        # 13. Broadcast prompt and cancel back button
        cb = self._make_cb("adm_broadcast_prompt", self.owner_id)
        await self.admin_panel.handle_callback(self.mock_client, cb)
        cb.message.edit_text.assert_called_once()
        self.assertIn("Broadcast Announcement", cb.message.edit_text.call_args[0][0])

    async def test_document_message_back_button_resilience(self):
        # When clicking Back (adm_main) from a Document Message (e.g. Logs export)
        cb = self._make_cb("adm_main", self.owner_id, is_doc=True)
        await self.admin_panel.handle_callback(self.mock_client, cb)
        # Should catch the RPCError, delete the document message, and send/reply clean text
        cb.message.delete.assert_called_once()
        cb.message.reply_text.assert_called_once()
        self.assertIn("Admin Panel", cb.message.reply_text.call_args[0][0])

    async def test_message_not_modified_resilience(self):
        cb = self._make_cb("adm_main", self.owner_id)
        cb.message.edit_text = AsyncMock(side_effect=MessageNotModified())
        # Should not raise exception
        await self.admin_panel.handle_callback(self.mock_client, cb)
        cb.answer.assert_called_once()

    async def test_search_cancel_callback(self):
        cb = self._make_cb("cancel_search", 999888777)
        await self.handler.handle_callback(self.mock_client, cb)
        cb.message.delete.assert_called_once()
        cb.answer.assert_called_once()

    async def test_broadcast_cancel_callback(self):
        cb = self._make_cb("broadcast_cancel", self.owner_id)
        await self.handler.handle_callback(self.mock_client, cb)
        cb.message.edit_text.assert_called_once()
        self.assertIn("Broadcast cancelled", cb.message.edit_text.call_args[0][0])

if __name__ == "__main__":
    unittest.main()
