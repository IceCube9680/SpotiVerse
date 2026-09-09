# utils/feature_gates.py
import logging
from typing import Tuple, Optional, NamedTuple
from config import Config
from utils.db import db
from utils.providers import ProviderRegistry
from utils.audio_formats import AudioProfile, AudioFormat

logger = logging.getLogger(__name__)

class AuthorizationResult(NamedTuple):
    allowed: bool
    reason: Optional[str]
    is_premium: bool
    is_owner: bool
    priority: bool
    effective_format: str
    effective_quality: int | str
    user: dict

class FeatureGate:
    """
    Central SystemState / FeatureGate / Authorization Service for SpotiVerse.
    Ensures identical business rules across all download entry points (/download,
    direct links, search inline callbacks, album/playlist batch downloads).
    """

    @classmethod
    def is_maintenance_enabled(cls) -> bool:
        return bool(db.get_bot_setting("maintenance_mode", False))

    @classmethod
    def set_maintenance_mode(cls, mode: bool, admin_id: int = None) -> bool:
        return db.set_bot_setting("maintenance_mode", bool(mode), admin_id=admin_id)

    @classmethod
    def is_feature_enabled(cls, feature_name: str, default: bool = True) -> bool:
        return bool(db.get_bot_setting(feature_name, default))

    @classmethod
    def is_provider_enabled(cls, provider: str) -> bool:
        return ProviderRegistry.is_enabled(provider)

    @classmethod
    def get_available_formats(cls, user_id: int) -> list:
        is_prem = db.is_premium(user_id) or Config.is_owner(user_id)
        return AudioProfile.get_allowed_formats(is_premium=is_prem)

    @classmethod
    def get_available_qualities(cls, user_id: int, format_type: str) -> list:
        is_prem = db.is_premium(user_id) or Config.is_owner(user_id)
        return AudioProfile.get_allowed_qualities(format_type, is_premium=is_prem)

    @classmethod
    def can_user_use_format(cls, user_id: int, format_type: str) -> bool:
        is_prem = db.is_premium(user_id) or Config.is_owner(user_id)
        return AudioProfile.is_format_allowed(format_type, is_premium=is_prem)

    @classmethod
    def can_user_use_quality(cls, user_id: int, format_type: str, quality) -> bool:
        is_prem = db.is_premium(user_id) or Config.is_owner(user_id)
        return AudioProfile.is_quality_allowed(format_type, quality, is_premium=is_prem)

    @classmethod
    def authorize_download(cls, user_id: int, provider: str = None, is_batch: bool = False,
                           requested_format: str = None, format: str = None) -> AuthorizationResult:
        """
        Runs complete 11-step authorization pipeline for downloads:
        1. User existence & profile
        2. Banned check
        3. Maintenance mode check
        4. Provider validation
        5. Premium status
        6. Bot settings feature flags (free_download, premium_download, premium_batch, premium_flac, premium_priority)
        7. Daily quota check
        8. Format permission (FLAC vs MP3)
        9. Batch permission
        10. Priority allocation
        11. Produce result
        """
        requested_format = format or requested_format
        # 1. Check user exists
        user = db.get_user(user_id) or {}
        is_owner = Config.is_owner(user_id)

        # 2. Check banned state
        if user.get("banned"):
            return AuthorizationResult(
                allowed=False,
                reason="🚫 **Account Suspended.** You have been restricted from using this service.",
                is_premium=False,
                is_owner=is_owner,
                priority=False,
                effective_format="mp3",
                effective_quality=64,
                user=user
            )

        # 5. Determine premium status
        is_premium = db.is_premium(user_id)

        # 3. Check maintenance mode
        maintenance = cls.is_maintenance_enabled()
        if maintenance:
            allow_admin = Config.MAINTENANCE_ALLOW_ADMIN
            allow_prem = Config.MAINTENANCE_ALLOW_PREMIUM

            if is_owner and allow_admin:
                pass  # Owner allowed during maintenance
            elif is_premium and allow_prem:
                pass  # Premium allowed during maintenance
            else:
                return AuthorizationResult(
                    allowed=False,
                    reason="🔧 **Maintenance Mode Active**\n\nThe bot is currently undergoing scheduled maintenance. New downloads are temporarily paused.\n\nPlease try again shortly.",
                    is_premium=is_premium,
                    is_owner=is_owner,
                    priority=False,
                    effective_format="mp3",
                    effective_quality=64,
                    user=user
                )

        # 4. Check provider validation
        if provider:
            canonical_provider = ProviderRegistry.get_canonical_id(provider)
            if not ProviderRegistry.is_enabled(canonical_provider):
                prov_name = ProviderRegistry.get_display_name(canonical_provider)
                return AuthorizationResult(
                    allowed=False,
                    reason=f"⚠️ **{prov_name}** is currently disabled by the administrator. Please try another provider.",
                    is_premium=is_premium,
                    is_owner=is_owner,
                    priority=False,
                    effective_format="mp3",
                    effective_quality=64,
                    user=user
                )

        # 6. Check Bot Settings feature flags
        free_dl_enabled = cls.is_feature_enabled("free_download", True)
        prem_dl_enabled = cls.is_feature_enabled("premium_download", True)
        prem_batch_enabled = cls.is_feature_enabled("premium_batch", True)
        prem_flac_enabled = cls.is_feature_enabled("premium_flac", True)
        prem_priority_enabled = cls.is_feature_enabled("premium_priority", True)

        if not is_premium and not free_dl_enabled and not is_owner:
            return AuthorizationResult(
                allowed=False,
                reason="⚠️ Free downloads are temporarily disabled by the administrator. Upgrade to Premium for access.",
                is_premium=is_premium,
                is_owner=is_owner,
                priority=False,
                effective_format="mp3",
                effective_quality=64,
                user=user
            )

        if is_premium and not prem_dl_enabled and not is_owner:
            return AuthorizationResult(
                allowed=False,
                reason="⚠️ Premium downloads are temporarily disabled by the administrator.",
                is_premium=is_premium,
                is_owner=is_owner,
                priority=False,
                effective_format="mp3",
                effective_quality=64,
                user=user
            )

        # 9. Check batch permission
        if is_batch:
            if not is_premium and not is_owner:
                return AuthorizationResult(
                    allowed=False,
                    reason="❌ **Premium Required!**\n\n📥 Album and playlist batch downloads are available for **Premium users only**.\n\n💎 Upgrade to Premium to unlock full discography downloads!",
                    is_premium=is_premium,
                    is_owner=is_owner,
                    priority=False,
                    effective_format="mp3",
                    effective_quality=64,
                    user=user
                )
            if not prem_batch_enabled and not is_owner:
                return AuthorizationResult(
                    allowed=False,
                    reason="⚠️ Batch downloading is currently disabled by the administrator.",
                    is_premium=is_premium,
                    is_owner=is_owner,
                    priority=False,
                    effective_format="mp3",
                    effective_quality=64,
                    user=user
                )

        # 7. Check quota for free users
        if not is_premium and not is_owner:
            can_dl, reason = db.can_download(user_id)
            if not can_dl:
                return AuthorizationResult(
                    allowed=False,
                    reason=f"❌ **Download Limit Reached!**\n\n{reason}\n\n💎 Upgrade to Premium to unlock unlimited high-quality downloads!\nContact: @icecube9608\n\n👤 **Your User ID:** `{user_id}`",
                    is_premium=False,
                    is_owner=is_owner,
                    priority=False,
                    effective_format="mp3",
                    effective_quality=64,
                    user=user
                )

        # 8. Check format & quality permissions across all formats
        eff_settings = db.get_effective_settings(user_id)
        fmt = str(requested_format or eff_settings.get("preferred_format", "mp3")).lower().strip()
        quality = eff_settings.get("preferred_quality", AudioProfile.get_default_quality(fmt, is_premium))

        # Check if user tier allows requested format
        if not AudioProfile.is_format_allowed(fmt, is_premium=is_premium or is_owner):
            fmt = "mp3"
            quality = 128 if not is_premium else 320

        # Special feature gate check for FLAC toggle
        if fmt == AudioFormat.FLAC and not prem_flac_enabled and not is_owner:
            fmt = "mp3"
            quality = 320

        # Verify quality validity for format
        if not AudioProfile.is_quality_allowed(fmt, quality, is_premium=is_premium or is_owner):
            quality = AudioProfile.get_default_quality(fmt, is_premium=is_premium or is_owner)

        # 10. Check priority permission
        priority = is_premium and prem_priority_enabled

        return AuthorizationResult(
            allowed=True,
            reason=None,
            is_premium=is_premium,
            is_owner=is_owner,
            priority=priority,
            effective_format=fmt,
            effective_quality=quality,
            user=user
        )

feature_gate = FeatureGate()
