# handlers/admin_panel.py
import logging
from datetime import datetime, timezone
from pyrogram import Client
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)
from config import Config
from utils.db import db, _parse_datetime
from utils.providers import ProviderRegistry
from utils.feature_gates import FeatureGate
from utils.admin_security import admin_security
from utils.ui_helpers import safe_answer_callback, safe_edit_or_reply

logger = logging.getLogger(__name__)

# State store for multi-step admin input prompts (user_id -> dict)
_admin_action_states = {}

def _format_time_remaining(expiry_dt: datetime) -> str:
    if not expiry_dt:
        return "N/A"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if expiry_dt < now:
        return "Expired"
    diff = expiry_dt - now
    days = diff.days
    hours = diff.seconds // 3600
    if days >= 3650:
        return "Lifetime ♾️"
    if days > 0:
        return f"{days}d {hours}h left"
    return f"{hours}h left"

class AdminPanelHandler:
    """
    Centralized Telegram Admin Panel:
    - Statistics Dashboard (24h, 7d, 30d, all-time)
    - Premium Management (Add, Remove, Check User, Paginated lists, Expiring soon)
    - Bot Settings (Interactive toggles for all feature gates)
    - Provider Management (Interactive toggles for Spotify, YouTube, JioSaavn, SoundCloud, Deezer)
    - Maintenance Mode (Interactive enable/disable controls)
    - User Management (Inspect, Ban, Unban)
    - Broadcast & Logs
    """
    def __init__(self, bot: Client):
        self.bot = bot

    # --- Authorization Helper ---
    def check_access(self, user_id: int) -> bool:
        return Config.is_owner(user_id)

    def _check_auth(self, user_id: int) -> bool:
        return self.check_access(user_id)

    # --- Keyboards ---
    def build_main_menu_keyboard(self) -> InlineKeyboardMarkup:
        kb = [
            [InlineKeyboardButton("📊 Statistics", callback_data="adm_stats_30d"),
             InlineKeyboardButton("👑 Premium", callback_data="adm_prem_menu")],
            [InlineKeyboardButton("⚙️ Bot Settings", callback_data="adm_settings_menu"),
             InlineKeyboardButton("🔌 Providers", callback_data="adm_prov_menu")],
            [InlineKeyboardButton("🔧 Maintenance", callback_data="adm_maint_menu"),
             InlineKeyboardButton("👥 Users", callback_data="adm_users_menu")],
            [InlineKeyboardButton("📢 Broadcast", callback_data="adm_broadcast_prompt"),
             InlineKeyboardButton("📜 Logs", callback_data="adm_logs_view")],
            [InlineKeyboardButton("🚪 Close Panel", callback_data="adm_close")]
        ]
        return InlineKeyboardMarkup(kb)

    def build_stats_keyboard(self, current_period: str = "30d") -> InlineKeyboardMarkup:
        p24 = "🔘 24h" if current_period == "24h" else "24h"
        p7 = "🔘 7d" if current_period == "7d" else "7d"
        p30 = "🔘 30d" if current_period == "30d" else "30d"
        pall = "🔘 All" if current_period == "all" else "All"

        kb = [
            [
                InlineKeyboardButton(p24, callback_data="adm_stats_24h"),
                InlineKeyboardButton(p7, callback_data="adm_stats_7d"),
                InlineKeyboardButton(p30, callback_data="adm_stats_30d"),
                InlineKeyboardButton(pall, callback_data="adm_stats_all"),
            ],
            [
                InlineKeyboardButton("🔄 Refresh", callback_data=f"adm_stats_{current_period}"),
                InlineKeyboardButton("⬅️ Back", callback_data="adm_main")
            ]
        ]
        return InlineKeyboardMarkup(kb)

    def build_settings_keyboard(self) -> InlineKeyboardMarkup:
        settings = db.get_all_bot_settings()

        def _btn(label: str, key: str):
            val = settings.get(key, True)
            icon = "🟢 ON" if val else "🔴 OFF"
            return InlineKeyboardButton(f"{label}: {icon}", callback_data=f"adm_toggle_setting_{key}")

        kb = [
            [_btn("Premium System", "premium_system")],
            [_btn("Free Download", "free_download"), _btn("Premium Download", "premium_download")],
            [_btn("Premium FLAC", "premium_flac"), _btn("Premium Batch", "premium_batch")],
            [_btn("Priority Queue", "premium_priority")],
            [InlineKeyboardButton("⬅️ Back", callback_data="adm_main")]
        ]
        return InlineKeyboardMarkup(kb)

    def build_providers_keyboard(self) -> InlineKeyboardMarkup:
        provs = ProviderRegistry.get_all_providers()
        kb = []
        for p in provs:
            icon = "🟢 ON" if p.enabled else "🔴 OFF"
            kb.append([InlineKeyboardButton(f"{p.emoji} {p.display_name}: {icon}", callback_data=f"adm_toggle_prov_{p.id}")])
        kb.append([InlineKeyboardButton("⬅️ Back", callback_data="adm_main")])
        return InlineKeyboardMarkup(kb)

    def build_maintenance_keyboard(self) -> InlineKeyboardMarkup:
        is_maint = FeatureGate.is_maintenance_enabled()
        toggle_btn = InlineKeyboardButton("✅ Disable Maintenance", callback_data="adm_maint_disable") if is_maint else InlineKeyboardButton("⚠️ Enable Maintenance", callback_data="adm_maint_enable")
        kb = [
            [toggle_btn],
            [InlineKeyboardButton("⬅️ Back", callback_data="adm_main")]
        ]
        return InlineKeyboardMarkup(kb)

    def build_premium_menu_keyboard(self) -> InlineKeyboardMarkup:
        kb = [
            [InlineKeyboardButton("➕ Add Premium", callback_data="adm_prem_add_prompt"),
             InlineKeyboardButton("➖ Remove Premium", callback_data="adm_prem_rem_prompt")],
            [InlineKeyboardButton("🔍 Check User", callback_data="adm_prem_check_prompt"),
             InlineKeyboardButton("📄 Premium Users", callback_data="adm_prem_list_0")],
            [InlineKeyboardButton("⌛ Expiring Soon", callback_data="adm_prem_expiring_0")],
            [InlineKeyboardButton("⬅️ Back", callback_data="adm_main")]
        ]
        return InlineKeyboardMarkup(kb)

    # --- Screen Renderers ---
    async def show_main_menu(self, message_or_cb):
        text = (
            "🛠 **Admin Panel**\n\n"
            "Select an administrative module from the options below:"
        )
        kb = self.build_main_menu_keyboard()
        await safe_edit_or_reply(message_or_cb, text, reply_markup=kb, client=self.bot)

    async def show_statistics(self, message_or_cb, period: str = "30d"):
        stats = db.get_statistics(period)
        uptime_h = stats["bot_uptime_seconds"] // 3600
        uptime_m = (stats["bot_uptime_seconds"] % 3600) // 60

        text = (
            f"📊 **Statistics ({stats['label']})**\n\n"
            f"👥 **Total Users:** `{stats['total_users']:,}`\n"
            f"💎 **Premium Users:** `{stats['premium_users']:,}`\n"
            f"🆓 **Free Users:** `{stats['free_users']:,}`\n"
            f"⚡ **Active Users ({stats['label']}):** `{stats['active_users']:,}`\n"
            f"🆕 **New Users ({stats['label']}):** `{stats['new_users']:,}`\n\n"
            f"📥 **Total Downloads:** `{stats['total_downloads']:,}`\n"
            f"✅ **Successful:** `{stats['successful_downloads']:,}`\n"
            f"❌ **Failed:** `{stats['failed_downloads']:,}`\n"
            f"📈 **Success Rate:** `{stats['success_rate']}%`\n"
            f"📦 **Audio Processed:** `{stats['total_audio_mb']:.1f} MB`\n\n"
            "🏆 **Top Platforms:**\n"
            f"• YouTube: `{stats['platform_percentages'].get('youtube', 0)}%` ({stats['platform_usage'].get('youtube', 0):,})\n"
            f"• Spotify: `{stats['platform_percentages'].get('spotify', 0)}%` ({stats['platform_usage'].get('spotify', 0):,})\n"
            f"• JioSaavn: `{stats['platform_percentages'].get('jiosaavn', 0)}%` ({stats['platform_usage'].get('jiosaavn', 0):,})\n"
            f"• SoundCloud: `{stats['platform_percentages'].get('soundcloud', 0)}%` ({stats['platform_usage'].get('soundcloud', 0):,})\n"
            f"• Deezer: `{stats['platform_percentages'].get('deezer', 0)}%` ({stats['platform_usage'].get('deezer', 0):,})\n\n"
            f"🎛️ **Audio Formats (Successful):**\n"
            f"• MP3: `{stats['format_usage'].get('mp3', 0):,}` | FLAC: `{stats['format_usage'].get('flac', 0):,}`\n"
            f"• M4A: `{stats['format_usage'].get('m4a', 0):,}` | OGG: `{stats['format_usage'].get('ogg', 0):,}` | WAV: `{stats['format_usage'].get('wav', 0):,}`\n\n"
            f"⚡ **Conversion Metrics:**\n"
            f"• Avg Conversion Speed: `{stats.get('avg_conversion_duration_sec', 0.0):.2f}s`\n"
            f"• Avg File Size: `{stats.get('avg_output_size_mb', 0.0):.2f} MB`\n\n"
            f"💾 **Database:** `{stats['db_status']}`\n"
            f"⏱ **Bot Uptime:** `{uptime_h}h {uptime_m}m`"
        )
        kb = self.build_stats_keyboard(period)
        await safe_edit_or_reply(message_or_cb, text, reply_markup=kb, client=self.bot)

    async def show_settings(self, message_or_cb):
        text = (
            "⚙️ **Bot Settings**\n\n"
            "Toggle feature flags to immediately enable or disable features across the bot:\n\n"
            "• **Premium System:** Enforce subscription access\n"
            "• **Free Download:** Allow downloads for free users\n"
            "• **Premium Download:** Allow downloads for premium users\n"
            "• **Premium FLAC:** Allow lossless FLAC format\n"
            "• **Premium Batch:** Allow album/playlist downloads\n"
            "• **Priority Queue:** High-priority execution queue"
        )
        kb = self.build_settings_keyboard()
        await safe_edit_or_reply(message_or_cb, text, reply_markup=kb, client=self.bot)

    async def show_providers(self, message_or_cb):
        text = (
            "🔌 **Provider Management**\n\n"
            "Toggle music source providers independently. Disabling a provider blocks incoming searches and downloads for that provider immediately:"
        )
        kb = self.build_providers_keyboard()
        await safe_edit_or_reply(message_or_cb, text, reply_markup=kb, client=self.bot)

    async def show_maintenance(self, message_or_cb):
        is_maint = FeatureGate.is_maintenance_enabled()
        status_text = "🟢 **ON (Active)**" if is_maint else "🔴 **OFF (Inactive)**"
        text = (
            "🔧 **Maintenance Mode**\n\n"
            f"**Status:** {status_text}\n\n"
            "When enabled:\n"
            "• Normal users cannot initiate new downloads\n"
            "• Existing active downloads will finish processing\n"
            "• Administrators retain full testing access\n"
            f"• Premium users blocked: `{'No' if Config.MAINTENANCE_ALLOW_PREMIUM else 'Yes'}`"
        )
        kb = self.build_maintenance_keyboard()
        await safe_edit_or_reply(message_or_cb, text, reply_markup=kb, client=self.bot)

    async def show_premium_menu(self, message_or_cb):
        text = (
            "👑 **Premium Management**\n\n"
            "Select an operation to manage premium subscribers:"
        )
        kb = self.build_premium_menu_keyboard()
        await safe_edit_or_reply(message_or_cb, text, reply_markup=kb, client=self.bot)

    async def show_premium_users_list(self, message_or_cb, page: int = 0):
        users, total = db.get_premium_users(page=page, per_page=5)
        total_pages = max(1, (total + 4) // 5)
        current_page = min(page, total_pages - 1)

        text = f"📄 **Premium Users** (Page {current_page + 1}/{total_pages} — Total: {total})\n\n"
        if not users:
            text += "No active premium users found."
        else:
            for i, u in enumerate(users, start=current_page * 5 + 1):
                name = u.get("first_name") or u.get("display_name") or "User"
                uname = f"@{u.get('username')}" if u.get("username") else "No username"
                uid = u.get("user_id")
                plan = u.get("premium_plan") or ("Lifetime" if u.get("lifetime_premium") else "Premium")
                until_dt = _parse_datetime(u.get("premium_until"))
                rem_str = _format_time_remaining(until_dt) if not u.get("lifetime_premium") else "Lifetime ♾️"
                text += (
                    f"**{i}. {name}** ({uname})\n"
                    f"• ID: `{uid}`\n"
                    f"• Plan: `{plan}` | Remaining: `{rem_str}`\n\n"
                )

        nav_buttons = []
        if current_page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"adm_prem_list_{current_page - 1}"))
        if current_page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"adm_prem_list_{current_page + 1}"))

        kb = []
        if nav_buttons:
            kb.append(nav_buttons)
        kb.append([InlineKeyboardButton("⬅️ Back", callback_data="adm_prem_menu")])

        await safe_edit_or_reply(message_or_cb, text, reply_markup=InlineKeyboardMarkup(kb), client=self.bot)

    async def show_expiring_soon_list(self, message_or_cb, page: int = 0):
        warn_days = getattr(Config, "PREMIUM_EXPIRY_WARNING_DAYS", 7)
        users, total = db.get_expiring_soon_users(days=warn_days, page=page, per_page=5)
        total_pages = max(1, (total + 4) // 5)
        current_page = min(page, total_pages - 1)

        text = f"⌛ **Expiring Soon (Within {warn_days} Days)** (Page {current_page + 1}/{total_pages} — Total: {total})\n\n"
        if not users:
            text += f"No subscriptions expiring in the next {warn_days} days."
        else:
            for i, u in enumerate(users, start=current_page * 5 + 1):
                name = u.get("first_name") or u.get("display_name") or "User"
                uname = f"@{u.get('username')}" if u.get("username") else "No username"
                uid = u.get("user_id")
                plan = u.get("premium_plan") or "Premium"
                until_dt = _parse_datetime(u.get("premium_until"))
                rem_str = _format_time_remaining(until_dt)
                text += (
                    f"**{i}. {name}** ({uname})\n"
                    f"• ID: `{uid}` | Plan: `{plan}`\n"
                    f"• Expires: `{until_dt.strftime('%Y-%m-%d %H:%M') if until_dt else 'N/A'}` (`{rem_str}`)\n\n"
                )

        nav_buttons = []
        if current_page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"adm_prem_expiring_{current_page - 1}"))
        if current_page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"adm_prem_expiring_{current_page + 1}"))

        kb = []
        if nav_buttons:
            kb.append(nav_buttons)
        kb.append([InlineKeyboardButton("⬅️ Back", callback_data="adm_prem_menu")])

        await safe_edit_or_reply(message_or_cb, text, reply_markup=InlineKeyboardMarkup(kb), client=self.bot)

    async def show_user_check_card(self, message_or_cb, target_user_id: int):
        user = db.get_user(target_user_id) or {}
        is_prem = db.is_premium(target_user_id)
        until_dt = _parse_datetime(user.get("premium_until"))
        rem_str = _format_time_remaining(until_dt) if is_prem else "N/A"
        if user.get("lifetime_premium"):
            rem_str = "Lifetime ♾️"

        name = user.get("first_name") or user.get("display_name") or "Unknown"
        uname = f"@{user.get('username')}" if user.get("username") else "None"
        plan = user.get("premium_plan") or ("Lifetime" if user.get("lifetime_premium") else ("Active" if is_prem else "Free Tier"))

        text = (
            "👤 **User Information Card**\n\n"
            f"**Name:** {name}\n"
            f"**Username:** {uname}\n"
            f"**Telegram ID:** `{target_user_id}`\n\n"
            f"**Membership:** `{'💎 Premium' if is_prem else '👤 Free Member'}`\n"
            f"**Premium Plan:** `{plan}`\n"
            f"**Valid Until:** `{until_dt.strftime('%Y-%m-%d %H:%M') if until_dt else 'None'}`\n"
            f"**Remaining:** `{rem_str}`\n\n"
            f"**Daily Usage:** `{user.get('downloads_today', 0)}` downloads today\n"
            f"**Daily Limit:** `{'Unlimited ♾️' if is_prem else Config.FREE_USER_DAILY_LIMIT}`\n"
            f"**Total Downloads:** `{user.get('total_downloads', 0):,}`\n"
            f"**Banned:** `{'🔴 Yes' if user.get('banned') else '🟢 No'}`\n"
            f"**Preferred Format:** `{user.get('preferred_format', 'mp3').upper()} {user.get('preferred_quality', 320)}`"
        )
        kb = [
            [InlineKeyboardButton("➕ Grant Premium", callback_data=f"adm_grant_to_{target_user_id}"),
             InlineKeyboardButton("➖ Revoke Premium", callback_data=f"adm_revoke_from_{target_user_id}")],
            [InlineKeyboardButton("🚫 Ban User" if not user.get("banned") else "✅ Unban User", callback_data=f"adm_toggle_ban_{target_user_id}")],
            [InlineKeyboardButton("⬅️ Back", callback_data="adm_prem_menu")]
        ]
        await safe_edit_or_reply(message_or_cb, text, reply_markup=InlineKeyboardMarkup(kb), client=self.bot)

    # --- Callback Query Router ---
    async def handle_callback(self, client: Client, callback_query: CallbackQuery):
        data = callback_query.data or ""
        user_id = callback_query.from_user.id if callback_query.from_user else 0

        # Owner authorization check
        if not Config.is_owner(user_id):
            await safe_answer_callback(callback_query, "❌ You are not authorized to access the admin panel.", show_alert=True)
            return

        if data in ("adm_close", "adm_logout"):
            try:
                await callback_query.message.delete()
            except Exception:
                await safe_edit_or_reply(callback_query, "🔒 Admin panel closed.", client=self.bot)
            await safe_answer_callback(callback_query, "Admin panel closed.")
            return

        # Main Navigation
        if data == "adm_main":
            await safe_answer_callback(callback_query)
            await self.show_main_menu(callback_query)
            return

        # Statistics Callbacks
        if data.startswith("adm_stats_"):
            period = data.split("_")[-1]
            await safe_answer_callback(callback_query, "Loading statistics...")
            await self.show_statistics(callback_query, period)
            return

        # Settings Callbacks
        if data == "adm_settings_menu":
            await safe_answer_callback(callback_query)
            await self.show_settings(callback_query)
            return

        if data.startswith("adm_toggle_setting_"):
            key = data.replace("adm_toggle_setting_", "")
            current = db.get_bot_setting(key, True)
            db.set_bot_setting(key, not current, admin_id=user_id)
            await safe_answer_callback(callback_query, f"Setting updated: {key} -> {not current}")
            await self.show_settings(callback_query)
            return

        # Provider Callbacks
        if data == "adm_prov_menu":
            await safe_answer_callback(callback_query)
            await self.show_providers(callback_query)
            return

        if data.startswith("adm_toggle_prov_"):
            prov = data.replace("adm_toggle_prov_", "")
            new_state = ProviderRegistry.toggle(prov, admin_id=user_id)
            await safe_answer_callback(callback_query, f"{prov.capitalize()} is now {'ENABLED 🟢' if new_state else 'DISABLED 🔴'}", show_alert=True)
            await self.show_providers(callback_query)
            return

        # Maintenance Callbacks
        if data == "adm_maint_menu":
            await safe_answer_callback(callback_query)
            await self.show_maintenance(callback_query)
            return

        if data == "adm_maint_enable":
            FeatureGate.set_maintenance_mode(True, admin_id=user_id)
            await safe_answer_callback(callback_query, "⚠️ Maintenance Mode ENABLED", show_alert=True)
            await self.show_maintenance(callback_query)
            return

        if data == "adm_maint_disable":
            FeatureGate.set_maintenance_mode(False, admin_id=user_id)
            await safe_answer_callback(callback_query, "✅ Maintenance Mode DISABLED", show_alert=True)
            await self.show_maintenance(callback_query)
            return

        # Premium Menu Callbacks
        if data == "adm_prem_menu":
            await safe_answer_callback(callback_query)
            await self.show_premium_menu(callback_query)
            return

        if data.startswith("adm_prem_list_"):
            page = int(data.split("_")[-1])
            await safe_answer_callback(callback_query)
            await self.show_premium_users_list(callback_query, page)
            return

        if data.startswith("adm_prem_expiring_"):
            page = int(data.split("_")[-1])
            await safe_answer_callback(callback_query)
            await self.show_expiring_soon_list(callback_query, page)
            return

        if data == "adm_prem_add_prompt":
            _admin_action_states[user_id] = {"action": "add_premium_user_id"}
            await safe_answer_callback(callback_query)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="adm_prem_menu")]])
            await safe_edit_or_reply(
                callback_query,
                "➕ **Add Premium — Step 1/2**\n\n"
                "Please send the **Telegram User ID** or `@username` of the target user:",
                reply_markup=kb,
                client=self.bot
            )
            return

        if data.startswith("adm_grant_duration_"):
            # Format: adm_grant_duration_{target_uid}_{days}_{plan_name}
            parts = data.split("_")
            target_uid = int(parts[3])
            days = float(parts[4])
            plan_name = "_".join(parts[5:])

            until_dt = db.add_premium(target_uid, days, plan_name=plan_name, admin_id=user_id)
            await safe_answer_callback(callback_query, "✅ Premium granted successfully!", show_alert=True)

            # PM Target user if possible
            try:
                expiry_str = until_dt.strftime('%Y-%m-%d %H:%M UTC') if days < 36500 else "Lifetime Access"
                await client.send_message(
                    target_uid,
                    f"🎉 **Congratulations!**\n\n"
                    f"Your account has been upgraded to **{plan_name}**!\n"
                    f"📅 **Valid Until:** `{expiry_str}`\n\n"
                    "Enjoy unlimited high-speed downloads & all premium features!"
                )
            except Exception:
                pass

            await self.show_user_check_card(callback_query, target_uid)
            return

        if data == "adm_prem_rem_prompt":
            _admin_action_states[user_id] = {"action": "remove_premium_user_id"}
            await safe_answer_callback(callback_query)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="adm_prem_menu")]])
            await safe_edit_or_reply(
                callback_query,
                "➖ **Remove Premium**\n\n"
                "Please send the **Telegram User ID** or `@username` of the user:",
                reply_markup=kb,
                client=self.bot
            )
            return

        if data.startswith("adm_revoke_from_"):
            target_uid = int(data.replace("adm_revoke_from_", ""))
            user = db.get_user(target_uid)
            name = user.get("first_name") or user.get("display_name") or str(target_uid)
            plan = user.get("premium_plan") or "Premium"
            until_dt = _parse_datetime(user.get("premium_until"))

            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("⚠️ Confirm Revocation", callback_data=f"adm_confirm_revoke_{target_uid}")],
                [InlineKeyboardButton("❌ Cancel", callback_data=f"adm_check_{target_uid}")]
            ])
            await safe_edit_or_reply(
                callback_query,
                f"⚠️ **Remove Premium?**\n\n"
                f"**User:** {name} (`{target_uid}`)\n"
                f"**Current Plan:** `{plan}`\n"
                f"**Expires:** `{until_dt.strftime('%Y-%m-%d') if until_dt else 'N/A'}`\n\n"
                "Are you sure you want to revoke premium access immediately?",
                reply_markup=kb,
                client=self.bot
            )
            return

        if data.startswith("adm_confirm_revoke_"):
            target_uid = int(data.replace("adm_confirm_revoke_", ""))
            db.remove_premium(target_uid, admin_id=user_id)
            await safe_answer_callback(callback_query, "Premium access revoked.", show_alert=True)
            try:
                await client.send_message(
                    target_uid,
                    "ℹ️ **Your premium access has ended.**\n\nYou can continue using free search & download features."
                )
            except Exception:
                pass
            await self.show_user_check_card(callback_query, target_uid)
            return

        if data == "adm_prem_check_prompt":
            _admin_action_states[user_id] = {"action": "check_user_id"}
            await safe_answer_callback(callback_query)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="adm_prem_menu")]])
            await safe_edit_or_reply(
                callback_query,
                "🔍 **Check User**\n\n"
                "Please send the **Telegram User ID** or `@username` to inspect:",
                reply_markup=kb,
                client=self.bot
            )
            return

        if data.startswith("adm_check_"):
            target_uid = int(data.replace("adm_check_", ""))
            await safe_answer_callback(callback_query)
            await self.show_user_check_card(callback_query, target_uid)
            return

        if data.startswith("adm_grant_to_"):
            target_uid = int(data.replace("adm_grant_to_", ""))
            await safe_answer_callback(callback_query)
            kb = [
                [InlineKeyboardButton("7 Days", callback_data=f"adm_grant_duration_{target_uid}_7_7_Days"),
                 InlineKeyboardButton("30 Days (1 Month)", callback_data=f"adm_grant_duration_{target_uid}_30_1_Month")],
                [InlineKeyboardButton("90 Days (3 Months)", callback_data=f"adm_grant_duration_{target_uid}_90_3_Months"),
                 InlineKeyboardButton("180 Days (6 Months)", callback_data=f"adm_grant_duration_{target_uid}_180_6_Months")],
                [InlineKeyboardButton("1 Year", callback_data=f"adm_grant_duration_{target_uid}_365_1_Year"),
                 InlineKeyboardButton("👑 Lifetime", callback_data=f"adm_grant_duration_{target_uid}_36500_Lifetime")],
                [InlineKeyboardButton("⬅️ Back", callback_data=f"adm_check_{target_uid}")]
            ]
            await safe_edit_or_reply(
                callback_query,
                f"➕ **Select Premium Duration for User `{target_uid}`:**",
                reply_markup=InlineKeyboardMarkup(kb),
                client=self.bot
            )
            return

        if data.startswith("adm_toggle_ban_"):
            target_uid = int(data.replace("adm_toggle_ban_", ""))
            user = db.get_user(target_uid)
            if user.get("banned"):
                db.unban_user(target_uid, admin_id=user_id)
                await safe_answer_callback(callback_query, "User unbanned.", show_alert=True)
            else:
                db.ban_user(target_uid, admin_id=user_id)
                await safe_answer_callback(callback_query, "User banned.", show_alert=True)
            await self.show_user_check_card(callback_query, target_uid)
            return

        # Users Menu
        if data == "adm_users_menu":
            await safe_answer_callback(callback_query)
            kb = [
                [InlineKeyboardButton("🔍 Inspect User", callback_data="adm_prem_check_prompt")],
                [InlineKeyboardButton("📄 All Premium Users", callback_data="adm_prem_list_0")],
                [InlineKeyboardButton("⌛ Expiring Soon", callback_data="adm_prem_expiring_0")],
                [InlineKeyboardButton("⬅️ Back", callback_data="adm_main")]
            ]
            await safe_edit_or_reply(callback_query, "👥 **User Management**\n\nChoose an action:", reply_markup=InlineKeyboardMarkup(kb), client=self.bot)
            return

        # Logs View
        if data == "adm_logs_view":
            await safe_answer_callback(callback_query, "Exporting logs...")
            import os
            log_path = os.path.join(os.getcwd(), "bot.log")
            if os.path.exists(log_path):
                file_size = os.path.getsize(log_path)
                clear_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🗑️ Clear Logs", callback_data="clear_logs")], [InlineKeyboardButton("⬅️ Back", callback_data="adm_main")]])
                await callback_query.message.reply_document(document=log_path, caption=f"📄 **Latest Bot Logs** ({file_size / 1024:.1f} KB)", reply_markup=clear_kb)
            else:
                await safe_answer_callback(callback_query, "Log file not found.", show_alert=True)
            return

        # Clear Logs
        if data == "clear_logs":
            if not self._check_auth(user_id):
                await safe_answer_callback(callback_query, "⛔ Access denied.", show_alert=True)
                return
            import os
            log_path = os.path.join(os.getcwd(), "bot.log")
            try:
                if os.path.exists(log_path):
                    with open(log_path, "w") as f:
                        f.write("")
                db.log_admin_action(user_id, "clear_logs", details="Cleared bot.log")
                await safe_answer_callback(callback_query, "Logs cleared successfully!")
                await safe_edit_or_reply(callback_query, "🗑️ **Logs cleared successfully!**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="adm_main")]]), client=self.bot)
            except Exception as e:
                await safe_answer_callback(callback_query, f"Failed to clear logs: {e}", show_alert=True)
            return

        # Broadcast Prompt
        if data == "adm_broadcast_prompt":
            _admin_action_states[user_id] = {"action": "broadcast_message"}
            await safe_answer_callback(callback_query)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="adm_main")]])
            await safe_edit_or_reply(
                callback_query,
                "📢 **Broadcast Announcement**\n\n"
                "Please send the message text you wish to broadcast to all users:",
                reply_markup=kb,
                client=self.bot
            )
            return

        logger.debug(f"Unhandled admin callback: {data}")

    async def handle_admin_text_input(self, client: Client, message: Message) -> bool:
        """
        Processes interactive admin text inputs (admin code, user ID prompts, broadcast message).
        Returns True if the message was handled by the admin state machine.
        """
        if not message.from_user:
            return False
        user_id = message.from_user.id
        text = (message.text or "").strip()
        # Check multi-step admin states
        state = _admin_action_states.get(user_id)
        if not state:
            return False

        action = state.get("action")

        if action == "add_premium_user_id":
            _admin_action_states.pop(user_id, None)
            target_uid = None
            if text.lstrip("-").isdigit():
                target_uid = int(text)
            else:
                try:
                    tg_u = await client.get_users(text)
                    target_uid = tg_u.id
                except Exception as e:
                    await message.reply_text(f"❌ User `{text}` not found: {e}")
                    return True

            kb = [
                [InlineKeyboardButton("7 Days", callback_data=f"adm_grant_duration_{target_uid}_7_7_Days"),
                 InlineKeyboardButton("30 Days (1 Month)", callback_data=f"adm_grant_duration_{target_uid}_30_1_Month")],
                [InlineKeyboardButton("90 Days (3 Months)", callback_data=f"adm_grant_duration_{target_uid}_90_3_Months"),
                 InlineKeyboardButton("180 Days (6 Months)", callback_data=f"adm_grant_duration_{target_uid}_180_6_Months")],
                [InlineKeyboardButton("1 Year", callback_data=f"adm_grant_duration_{target_uid}_365_1_Year"),
                 InlineKeyboardButton("👑 Lifetime", callback_data=f"adm_grant_duration_{target_uid}_36500_Lifetime")],
                [InlineKeyboardButton("❌ Cancel", callback_data="adm_prem_menu")]
            ]
            await message.reply_text(
                f"➕ **User Selected:** `{target_uid}`\n\n"
                "Please choose the subscription duration to grant:",
                reply_markup=InlineKeyboardMarkup(kb)
            )
            return True

        if action == "remove_premium_user_id":
            _admin_action_states.pop(user_id, None)
            target_uid = None
            if text.lstrip("-").isdigit():
                target_uid = int(text)
            else:
                try:
                    tg_u = await client.get_users(text)
                    target_uid = tg_u.id
                except Exception as e:
                    await message.reply_text(f"❌ User `{text}` not found: {e}")
                    return True

            await self.show_user_check_card(message, target_uid)
            return

        if action == "check_user_id":
            _admin_action_states.pop(user_id, None)
            target_uid = None
            if text.lstrip("-").isdigit():
                target_uid = int(text)
            else:
                try:
                    tg_u = await client.get_users(text)
                    target_uid = tg_u.id
                except Exception as e:
                    await message.reply_text(f"❌ User `{text}` not found: {e}")
                    return True

            await self.show_user_check_card(message, target_uid)
            return

        if action == "broadcast_message":
            _admin_action_states.pop(user_id, None)
            confirm_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Send Broadcast", callback_data="broadcast_confirm")],
                [InlineKeyboardButton("❌ Cancel", callback_data="broadcast_cancel")]
            ])
            await message.reply_text(
                f"📢 **Broadcast Confirmation**\n\n"
                f"**Message Content:**\n{text}\n\n"
                "Are you sure you want to broadcast this message to all registered users?",
                reply_markup=confirm_kb
            )
            return True

        return False
