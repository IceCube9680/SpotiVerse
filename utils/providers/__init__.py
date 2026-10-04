# utils/providers/__init__.py
from utils.providers.base import (
    BaseProvider,
    ProviderHealth,
    ProviderHealthStatus,
    TrackMetadata,
    AudioSource
)
from utils.providers.matcher import TrackMatcher
from utils.providers.registry import (
    ProviderInfo,
    ProviderRegistry,
    provider_registry
)
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

__all__ = [
    "BaseProvider",
    "ProviderHealth",
    "ProviderHealthStatus",
    "TrackMetadata",
    "AudioSource",
    "TrackMatcher",
    "ProviderInfo",
    "ProviderRegistry",
    "provider_registry",
    "SpotifyProvider",
    "YouTubeProvider",
    "YouTubeMusicProvider",
    "JioSaavnProvider",
    "SoundCloudProvider",
    "DeezerProvider",
    "AppleMusicProvider",
    "TidalProvider",
    "QobuzProvider",
    "AmazonMusicProvider",
    "PandoraProvider",
    "ArchiveProvider",
    "BandcampProvider"
]
