# utils/providers.py
import logging
from utils.db import db

logger = logging.getLogger(__name__)

class ProviderInfo:
    def __init__(self, provider_id: str, display_name: str, emoji: str,
                 can_search: bool = True, can_track: bool = True,
                 can_album: bool = True, can_playlist: bool = True, can_download: bool = True):
        self.id = provider_id.lower()
        self.display_name = display_name
        self.emoji = emoji
        self.can_search = can_search
        self.can_track = can_track
        self.can_album = can_album
        self.can_playlist = can_playlist
        self.can_download = can_download

    @property
    def enabled(self) -> bool:
        return db.get_provider_setting(self.id, default=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "emoji": self.emoji,
            "enabled": self.enabled,
            "can_search": self.can_search,
            "can_track": self.can_track,
            "can_album": self.can_album,
            "can_playlist": self.can_playlist,
            "can_download": self.can_download
        }

class ProviderRegistry:
    """
    Central Registry for music source providers:
    Spotify, YouTube, JioSaavn, SoundCloud, Deezer.
    Provides runtime enabled/disabled state queries backed by persistent DB storage.
    """
    _PROVIDERS = {
        "spotify": ProviderInfo("spotify", "Spotify", "🟢", can_search=True, can_track=True, can_album=True, can_playlist=True, can_download=True),
        "youtube": ProviderInfo("youtube", "YouTube", "🔴", can_search=True, can_track=True, can_album=True, can_playlist=True, can_download=True),
        "jiosaavn": ProviderInfo("jiosaavn", "JioSaavn", "🟢", can_search=True, can_track=True, can_album=True, can_playlist=True, can_download=True),
        "soundcloud": ProviderInfo("soundcloud", "SoundCloud", "🟠", can_search=True, can_track=True, can_album=True, can_playlist=True, can_download=True),
        "deezer": ProviderInfo("deezer", "Deezer", "🟣", can_search=True, can_track=True, can_album=True, can_playlist=True, can_download=True),
    }

    # Aliases
    _ALIASES = {
        "sp": "spotify",
        "yt": "youtube",
        "saavn": "jiosaavn",
        "jio_saavn": "jiosaavn",
        "sc": "soundcloud",
        "dz": "deezer"
    }

    @classmethod
    def normalize_id(cls, provider: str) -> str:
        if not provider:
            return "youtube"
        p = str(provider).strip().lower()
        return cls._ALIASES.get(p, p)

    @classmethod
    def get_canonical_id(cls, provider: str) -> str:
        return cls.normalize_id(provider)

    @classmethod
    def get_display_name(cls, provider: str) -> str:
        prov = cls.get_provider(provider)
        if prov:
            return prov.display_name
        return str(provider).title()

    @classmethod
    def get_provider(cls, provider: str) -> ProviderInfo | None:
        p_id = cls.normalize_id(provider)
        return cls._PROVIDERS.get(p_id)

    @classmethod
    def is_enabled(cls, provider: str) -> bool:
        p_id = cls.normalize_id(provider)
        prov = cls._PROVIDERS.get(p_id)
        if not prov:
            return False
        return prov.enabled

    @classmethod
    def set_enabled(cls, provider: str, enabled: bool, admin_id: int = None) -> bool:
        p_id = cls.normalize_id(provider)
        if p_id not in cls._PROVIDERS:
            return False
        return db.set_provider_setting(p_id, bool(enabled), admin_id=admin_id)

    @classmethod
    def toggle(cls, provider: str, admin_id: int = None) -> bool:
        p_id = cls.normalize_id(provider)
        current = cls.is_enabled(p_id)
        new_state = not current
        cls.set_enabled(p_id, new_state, admin_id=admin_id)
        return new_state

    @classmethod
    def get_all_providers(cls) -> list[ProviderInfo]:
        return list(cls._PROVIDERS.values())

    @classmethod
    def get_enabled_providers(cls) -> list[ProviderInfo]:
        return [p for p in cls._PROVIDERS.values() if p.enabled]

    @classmethod
    def validate_for_action(cls, provider: str, action: str = "download") -> tuple[bool, str | None]:
        """
        Validate if provider is enabled and supports the requested action.
        Returns: (is_valid, error_message)
        """
        p_id = cls.normalize_id(provider)
        prov = cls._PROVIDERS.get(p_id)
        if not prov:
            return False, f"Unsupported music provider '{provider}'."

        if not prov.enabled:
            return False, f"⚠️ **{prov.display_name}** is currently disabled by the administrator. Please try another provider."

        if action == "search" and not prov.can_search:
            return False, f"Search is not supported for {prov.display_name}."
        if action == "download" and not prov.can_download:
            return False, f"Downloads are not supported for {prov.display_name}."
        if action in ("album", "playlist") and not (prov.can_album or prov.can_playlist):
            return False, f"Batch album/playlist downloads are not supported for {prov.display_name}."

        return True, None

provider_registry = ProviderRegistry()
