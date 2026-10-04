# utils/providers/registry.py
import time
import logging
from typing import Dict, List, Optional, Tuple, Any, Union

from utils.db import db
from utils.providers.base import (
    BaseProvider, ProviderHealth, ProviderHealthStatus, TrackMetadata, AudioSource
)
from utils.providers.matcher import TrackMatcher
from utils.providers.spotify_provider import SpotifyProvider
from utils.providers.youtube_provider import YouTubeProvider, YouTubeMusicProvider
from utils.providers.jiosaavn_provider import JioSaavnProvider
from utils.providers.soundcloud_provider import SoundCloudProvider
from utils.providers.deezer_provider import DeezerProvider
from utils.providers.applemusic_provider import AppleMusicProvider
from utils.providers.tidal_provider import TidalProvider
from utils.providers.qobuz_provider import QobuzProvider
from utils.providers.amazon_provider import AmazonMusicProvider
from utils.providers.pandora_provider import PandoraProvider
from utils.providers.archive_provider import ArchiveProvider
from utils.providers.bandcamp_provider import BandcampProvider

logger = logging.getLogger(__name__)

class ProviderInfo:
    """Compatibility wrapper for provider metadata and capabilities"""
    def __init__(self, provider_id: str, display_name: str, emoji: str,
                 can_search: bool = True, can_track: bool = True,
                 can_album: bool = True, can_playlist: bool = True,
                 can_download: bool = True, is_lossless_source: bool = False,
                 instance: Optional[BaseProvider] = None):
        self.id = provider_id.lower().strip()
        self.display_name = display_name
        self.emoji = emoji
        self.can_search = can_search
        self.can_track = can_track
        self.can_album = can_album
        self.can_playlist = can_playlist
        self.can_download = can_download
        self.is_lossless_source = is_lossless_source
        self.instance = instance

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
            "can_download": self.can_download,
            "is_lossless_source": self.is_lossless_source
        }


class ProviderRegistry:
    """
    Central Registry for all 13 Music Source Providers:
    Spotify, YouTube, YouTube Music, SoundCloud, JioSaavn, Deezer, Apple Music,
    TIDAL, Qobuz, Amazon Music, Pandora, Internet Archive, Bandcamp.

    Features:
    - Runtime enabled/disabled state queries backed by persistent DB storage
    - Provider health diagnostics and caching
    - Intelligent multi-provider audio source resolution and fallback matching
    - Priority-based provider selection
    """

    # Provider instances
    _INSTANCES: Dict[str, BaseProvider] = {
        "spotify": SpotifyProvider(),
        "youtube": YouTubeProvider(),
        "youtubemusic": YouTubeMusicProvider(),
        "jiosaavn": JioSaavnProvider(),
        "soundcloud": SoundCloudProvider(),
        "deezer": DeezerProvider(),
        "applemusic": AppleMusicProvider(),
        "tidal": TidalProvider(),
        "qobuz": QobuzProvider(),
        "amazonmusic": AmazonMusicProvider(),
        "pandora": PandoraProvider(),
        "archive": ArchiveProvider(),
        "bandcamp": BandcampProvider(),
    }

    # Provider metadata registry (wrapped with ProviderInfo for 100% backward compatibility)
    _PROVIDERS: Dict[str, ProviderInfo] = {
        "spotify": ProviderInfo("spotify", "Spotify", "🟢", can_search=True, can_track=True, can_album=True, can_playlist=True, can_download=True, instance=_INSTANCES["spotify"]),
        "youtube": ProviderInfo("youtube", "YouTube", "🔴", can_search=True, can_track=True, can_album=True, can_playlist=True, can_download=True, instance=_INSTANCES["youtube"]),
        "youtubemusic": ProviderInfo("youtubemusic", "YouTube Music", "🔴", can_search=True, can_track=True, can_album=True, can_playlist=True, can_download=True, instance=_INSTANCES["youtubemusic"]),
        "jiosaavn": ProviderInfo("jiosaavn", "JioSaavn", "🟢", can_search=True, can_track=True, can_album=True, can_playlist=True, can_download=True, instance=_INSTANCES["jiosaavn"]),
        "soundcloud": ProviderInfo("soundcloud", "SoundCloud", "🟠", can_search=True, can_track=True, can_album=True, can_playlist=True, can_download=True, instance=_INSTANCES["soundcloud"]),
        "deezer": ProviderInfo("deezer", "Deezer", "🟣", can_search=True, can_track=True, can_album=True, can_playlist=True, can_download=True, instance=_INSTANCES["deezer"]),
        "applemusic": ProviderInfo("applemusic", "Apple Music", "🍎", can_search=True, can_track=True, can_album=True, can_playlist=True, can_download=True, instance=_INSTANCES["applemusic"]),
        "tidal": ProviderInfo("tidal", "TIDAL", "⬛", can_search=True, can_track=True, can_album=True, can_playlist=True, can_download=True, is_lossless_source=True, instance=_INSTANCES["tidal"]),
        "qobuz": ProviderInfo("qobuz", "Qobuz", "🔷", can_search=True, can_track=True, can_album=True, can_playlist=True, can_download=True, is_lossless_source=True, instance=_INSTANCES["qobuz"]),
        "amazonmusic": ProviderInfo("amazonmusic", "Amazon Music", "📦", can_search=True, can_track=True, can_album=True, can_playlist=True, can_download=True, instance=_INSTANCES["amazonmusic"]),
        "pandora": ProviderInfo("pandora", "Pandora", "📻", can_search=True, can_track=True, can_album=True, can_playlist=True, can_download=True, instance=_INSTANCES["pandora"]),
        "archive": ProviderInfo("archive", "Internet Archive", "🏛️", can_search=True, can_track=True, can_album=True, can_playlist=True, can_download=True, is_lossless_source=True, instance=_INSTANCES["archive"]),
        "bandcamp": ProviderInfo("bandcamp", "Bandcamp", "⛺", can_search=True, can_track=True, can_album=True, can_playlist=True, can_download=True, is_lossless_source=True, instance=_INSTANCES["bandcamp"]),
    }

    # Aliases
    _ALIASES = {
        "sp": "spotify",
        "yt": "youtube",
        "ytm": "youtubemusic",
        "ytmusic": "youtubemusic",
        "youtube_music": "youtubemusic",
        "saavn": "jiosaavn",
        "jio_saavn": "jiosaavn",
        "sc": "soundcloud",
        "dz": "deezer",
        "apple": "applemusic",
        "itunes": "applemusic",
        "apple_music": "applemusic",
        "amazon": "amazonmusic",
        "amz": "amazonmusic",
        "amazon_music": "amazonmusic",
        "ia": "archive",
        "archive_org": "archive",
        "internet_archive": "archive",
        "internetarchive": "archive",
        "bc": "bandcamp"
    }

    # Health check cache: provider_id -> (timestamp, ProviderHealth)
    _HEALTH_CACHE: Dict[str, Tuple[float, ProviderHealth]] = {}
    _HEALTH_CACHE_TTL = 60.0  # seconds

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
    def get_provider(cls, provider: str) -> Optional[ProviderInfo]:
        p_id = cls.normalize_id(provider)
        return cls._PROVIDERS.get(p_id)

    @classmethod
    def get_instance(cls, provider: str) -> Optional[BaseProvider]:
        p_id = cls.normalize_id(provider)
        return cls._INSTANCES.get(p_id)

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
    def get_all_providers(cls) -> List[ProviderInfo]:
        return list(cls._PROVIDERS.values())

    @classmethod
    def get_all_provider_ids(cls) -> List[str]:
        return list(cls._PROVIDERS.keys())

    @classmethod
    def is_registered(cls, provider: str) -> bool:
        p_id = cls.normalize_id(provider)
        return p_id in cls._PROVIDERS

    @classmethod
    def get_enabled_providers(cls) -> List[ProviderInfo]:
        return [p for p in cls._PROVIDERS.values() if p.enabled]

    @classmethod
    async def get_health(cls, provider: str, force_refresh: bool = False) -> ProviderHealth:
        """Fetch provider health status with caching"""
        p_id = cls.normalize_id(provider)
        if not cls.is_enabled(p_id):
            return ProviderHealth(
                status=ProviderHealthStatus.DISABLED,
                latency_ms=0.0,
                message=f"{p_id.capitalize()} is currently disabled in settings."
            )

        now = time.time()
        if not force_refresh and p_id in cls._HEALTH_CACHE:
            ts, health = cls._HEALTH_CACHE[p_id]
            if now - ts < cls._HEALTH_CACHE_TTL:
                return health

        instance = cls.get_instance(p_id)
        if not instance:
            health = ProviderHealth(
                status=ProviderHealthStatus.NOT_CONFIGURED,
                latency_ms=0.0,
                message="Provider instance not found."
            )
        else:
            try:
                health = await instance.health_check()
            except Exception as e:
                health = ProviderHealth(
                    status=ProviderHealthStatus.DEGRADED,
                    latency_ms=0.0,
                    message=f"Health check failed: {e}"
                )

        cls._HEALTH_CACHE[p_id] = (now, health)
        return health

    @classmethod
    async def get_all_health(cls) -> Dict[str, ProviderHealth]:
        """Check health of all registered providers concurrently"""
        results = {}
        for p_id in cls._PROVIDERS.keys():
            results[p_id] = await cls.get_health(p_id)
        return results

    @classmethod
    def validate_for_action(cls, provider: str, action: str = "download") -> Tuple[bool, Optional[str]]:
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

    @classmethod
    async def resolve_track_metadata(cls, provider: str, track_id: str) -> Optional[TrackMetadata]:
        """Fetch normalized metadata from requested provider with fallback"""
        p_id = cls.normalize_id(provider)
        instance = cls.get_instance(p_id)
        if instance and cls.is_enabled(p_id):
            meta = await instance.get_track_info(track_id)
            if meta:
                return meta

        # Try Spotify / YouTube / JioSaavn fallbacks if track_id is valid
        for fallback_id in ["spotify", "youtube", "jiosaavn", "deezer", "applemusic"]:
            if fallback_id == p_id or not cls.is_enabled(fallback_id):
                continue
            fb_inst = cls.get_instance(fallback_id)
            if fb_inst:
                meta = await fb_inst.get_track_info(track_id)
                if meta:
                    return meta

        return None

    @classmethod
    async def match_audio_source(cls, target_meta: TrackMetadata,
                                 preferred_provider: str = "auto",
                                 requested_quality: str = "best") -> Tuple[Optional[AudioSource], str]:
        """
        Intelligently resolves and ranks the best audio stream matching target metadata.
        Queries enabled audio source providers, compares title/artist/duration/ISRC,
        and returns best match.
        """
        # Determine candidate search providers
        candidate_providers = []
        pref_id = cls.normalize_id(preferred_provider)
        if pref_id != "auto" and cls.is_enabled(pref_id):
            candidate_providers.append(pref_id)

        # Standard audio source search order
        default_order = ["youtube", "youtubemusic", "jiosaavn", "soundcloud", "archive", "bandcamp"]
        for p in default_order:
            if p not in candidate_providers and cls.is_enabled(p):
                candidate_providers.append(p)

        search_query = f"{target_meta.title} {target_meta.artist}"
        logger.info(f"Resolving audio stream for '{search_query}' across {candidate_providers}")

        candidates_pool: List[Tuple[float, TrackMetadata, str]] = []

        # Query source providers in parallel
        for prov_id in candidate_providers:
            inst = cls.get_instance(prov_id)
            if not inst:
                continue
            try:
                results = await inst.search(search_query, limit=5)
                for res in results:
                    conf = TrackMatcher.compute_match_confidence(
                        target=target_meta,
                        candidate_title=res.title,
                        candidate_artist=res.artist,
                        candidate_duration=res.duration,
                        candidate_isrc=res.isrc
                    )
                    if conf >= 0.55:  # Minimum acceptable match threshold
                        candidates_pool.append((conf, res, prov_id))
            except Exception as e:
                logger.debug(f"Candidate search failed on {prov_id}: {e}")

        # Sort candidates by match confidence
        candidates_pool.sort(key=lambda x: x[0], reverse=True)

        if not candidates_pool:
            # Last-resort fallback: Direct YouTube query
            yt_inst = cls.get_instance("youtube")
            if yt_inst and cls.is_enabled("youtube"):
                fallback_track = TrackMetadata(
                    provider="youtube",
                    provider_track_id=target_meta.provider_track_id,
                    title=target_meta.title,
                    artist=target_meta.artist,
                    album=target_meta.album,
                    duration=target_meta.duration,
                    webpage_url=f"ytsearch1:{search_query} audio"
                )
                source = await yt_inst.resolve_source(fallback_track, requested_quality)
                if source:
                    return source, "youtube (fallback)"

            return None, "No matching audio source found"

        # Resolve stream from top candidate
        best_conf, best_meta, source_prov = candidates_pool[0]
        logger.info(f"Top matching candidate: '{best_meta.title} - {best_meta.artist}' (confidence: {best_conf:.2f}, provider: {source_prov})")

        inst = cls.get_instance(source_prov)
        if inst:
            source = await inst.resolve_source(best_meta, requested_quality)
            if source:
                return source, f"{source_prov} ({int(best_conf * 100)}% match)"

        return None, "Failed to resolve stream from top candidate"

    @classmethod
    async def resolve_audio_source(cls, target_meta: Any,
                                   preferred_provider: str = "auto",
                                   requested_quality: str = "best") -> Optional[AudioSource]:
        """Convenience method resolving and returning the best AudioSource object directly"""
        if isinstance(target_meta, dict):
            target_meta = TrackMetadata(
                title=target_meta.get("title", "Unknown"),
                artist=target_meta.get("artist", "Unknown"),
                album=target_meta.get("album", "Unknown Album"),
                duration=target_meta.get("duration", 0),
                release_date=str(target_meta.get("year", "")),
                isrc=target_meta.get("isrc"),
                provider=target_meta.get("provider", "unknown")
            )
        source, _ = await cls.match_audio_source(target_meta, preferred_provider, requested_quality)
        return source

provider_registry = ProviderRegistry()
