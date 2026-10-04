# utils/providers/base.py
import time
import abc
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Union

logger = logging.getLogger(__name__)

class ProviderHealthStatus(str, Enum):
    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"
    DISABLED = "DISABLED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    NOT_CONFIGURED = "NOT_CONFIGURED"


@dataclass
class ProviderHealth:
    status: ProviderHealthStatus
    latency_ms: float = 0.0
    message: str = ""
    checked_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "latency_ms": round(self.latency_ms, 2),
            "message": self.message,
            "checked_at": self.checked_at
        }


@dataclass
class TrackMetadata:
    title: str
    artist: str
    provider: str = ""
    provider_track_id: str = ""
    album: str = "Unknown Album"
    album_artist: str = ""
    duration: int = 0
    release_date: str = ""
    isrc: Optional[str] = None
    artwork: Optional[str] = None
    webpage_url: Optional[str] = None
    explicit: bool = False
    available_formats: List[str] = field(default_factory=list)
    raw_data: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.album_artist:
            self.album_artist = self.artist
        if not self.available_formats:
            self.available_formats = ["mp3", "flac", "m4a", "ogg", "wav", "opus"]

    def to_dict(self) -> dict:
        return {
            "id": self.provider_track_id,
            "provider_track_id": self.provider_track_id,
            "provider": self.provider,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "album_artist": self.album_artist,
            "duration": self.duration,
            "year": self.release_date[:4] if self.release_date else "",
            "release_date": self.release_date,
            "isrc": self.isrc,
            "thumbnail": self.artwork,
            "artwork": self.artwork,
            "webpage_url": self.webpage_url,
            "explicit": self.explicit,
            "available_formats": self.available_formats
        }


@dataclass
class AudioSource:
    source_provider: str
    source_url: str
    codec: str = "unknown"
    container: str = ""
    bitrate: int = 0
    sample_rate: int = 44100
    bit_depth: int = 16
    channels: int = 2
    file_size: int = 0
    lossless: bool = False
    downloadable: bool = True
    requires_transcoding: bool = False
    headers: Dict[str, str] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source_provider": self.source_provider,
            "source_url": self.source_url,
            "codec": self.codec,
            "container": self.container,
            "bitrate": self.bitrate,
            "sample_rate": self.sample_rate,
            "bit_depth": self.bit_depth,
            "channels": self.channels,
            "file_size": self.file_size,
            "lossless": self.lossless,
            "downloadable": self.downloadable,
            "requires_transcoding": self.requires_transcoding
        }


class BaseProvider(abc.ABC):
    """
    Standardized Abstract Base Class for Music Providers.
    Separates concerns across Metadata, Search, Audio Source Resolution, and Downloading.
    """
    def __init__(self, provider_id: str, display_name: str, emoji: str,
                 can_search: bool = True, can_track: bool = True,
                 can_album: bool = True, can_playlist: bool = True,
                 can_download: bool = True, is_lossless_source: bool = False):
        self.provider_id = provider_id.lower().strip()
        self.display_name = display_name
        self.emoji = emoji
        self.can_search = can_search
        self.can_track = can_track
        self.can_album = can_album
        self.can_playlist = can_playlist
        self.can_download = can_download
        self.is_lossless_source = is_lossless_source
        self._last_health: Optional[ProviderHealth] = None
        self._health_cache_ttl = 60  # seconds

    async def initialize(self) -> bool:
        """Initialize connections, API clients, credentials."""
        return True

    @abc.abstractmethod
    async def health_check(self) -> ProviderHealth:
        """Perform health check and return accurate ProviderHealth."""
        raise NotImplementedError

    async def search(self, query: str, limit: int = 10, search_type: str = "track") -> List[TrackMetadata]:
        """Search provider for tracks or albums."""
        return []

    async def get_track_info(self, track_id: str) -> Optional[TrackMetadata]:
        """Fetch normalized track metadata."""
        return None

    async def get_album_info(self, album_id: str) -> Optional[Dict[str, Any]]:
        """Fetch album/playlist metadata and track listing."""
        return None

    async def resolve_source(self, track_metadata: TrackMetadata, requested_quality: Union[int, str] = "best") -> Optional[AudioSource]:
        """Resolve downloadable audio stream for the given track."""
        return None

    async def download(self, source: AudioSource, output_path: str, progress_hook=None) -> Optional[str]:
        """Download audio source to output_path."""
        return None

    async def close(self):
        """Clean up sessions, clients, and background executors."""
        pass

    def to_dict(self) -> dict:
        return {
            "id": self.provider_id,
            "display_name": self.display_name,
            "emoji": self.emoji,
            "can_search": self.can_search,
            "can_track": self.can_track,
            "can_album": self.can_album,
            "can_playlist": self.can_playlist,
            "can_download": self.can_download,
            "is_lossless_source": self.is_lossless_source
        }
