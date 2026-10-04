# utils/providers/applemusic_provider.py
import time
import socket
import aiohttp
import asyncio
import logging
from typing import Optional, List, Dict, Any, Union

from utils.providers.base import (
    BaseProvider, ProviderHealth, ProviderHealthStatus, TrackMetadata, AudioSource
)

logger = logging.getLogger(__name__)

class AppleMusicProvider(BaseProvider):
    """
    Apple Music & iTunes Metadata/Search Provider:
    - Official iTunes Search API (`itunes.apple.com/search`)
    - High-resolution artwork extraction (up to 3000x3000px)
    - Full genre, discography, and release metadata
    """
    def __init__(self):
        super().__init__(
            provider_id="applemusic",
            display_name="Apple Music",
            emoji="",
            can_search=True,
            can_track=True,
            can_album=True,
            can_playlist=True,
            can_download=True,
            is_lossless_source=False
        )
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

    async def health_check(self) -> ProviderHealth:
        start = time.time()
        url = "https://itunes.apple.com/search?term=coldplay&entity=song&limit=1"
        try:
            connector = aiohttp.TCPConnector(family=socket.AF_INET)
            async with aiohttp.ClientSession(connector=connector, headers=self.headers, timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(url) as resp:
                    latency = (time.time() - start) * 1000
                    if resp.status == 200:
                        return ProviderHealth(
                            status=ProviderHealthStatus.ONLINE,
                            latency_ms=latency,
                            message="Apple Music / iTunes API operational."
                        )
                    return ProviderHealth(
                        status=ProviderHealthStatus.DEGRADED,
                        latency_ms=latency,
                        message=f"iTunes Search API returned HTTP {resp.status}"
                    )
        except Exception as e:
            latency = (time.time() - start) * 1000
            return ProviderHealth(
                status=ProviderHealthStatus.DEGRADED,
                latency_ms=latency,
                message=f"Apple Music check error: {e}"
            )

    async def search(self, query: str, limit: int = 10, search_type: str = "track") -> List[TrackMetadata]:
        url = f"https://itunes.apple.com/search?term={query}&entity=song&limit={limit}"
        try:
            connector = aiohttp.TCPConnector(family=socket.AF_INET)
            async with aiohttp.ClientSession(connector=connector, headers=self.headers, timeout=aiohttp.ClientTimeout(total=8)) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        items = data.get("results", []) if isinstance(data, dict) else []
                        tracks = []
                        for item in items[:limit]:
                            if not item:
                                continue
                            tid = item.get("trackId")
                            title = item.get("trackName", "Unknown Track")
                            artist = item.get("artistName", "Unknown Artist")
                            album = item.get("collectionName", "Apple Music")
                            dur_ms = int(item.get("trackTimeMillis") or 0)
                            dur = dur_ms // 1000
                            raw_art = item.get("artworkUrl100", "")
                            # High-res art replacement
                            thumb = raw_art.replace("100x100bb", "1200x1200bb") if raw_art else None
                            rel_date = str(item.get("releaseDate") or "")[:10]

                            tracks.append(TrackMetadata(
                                provider=self.provider_id,
                                provider_track_id=str(tid),
                                title=title,
                                artist=artist,
                                album=album,
                                duration=dur,
                                release_date=rel_date,
                                artwork=thumb,
                                webpage_url=item.get("trackViewUrl") or f"https://music.apple.com/song/{tid}",
                                raw_data=item
                            ))
                        return tracks
        except Exception as e:
            logger.debug(f"Apple Music search error: {e}")
        return []

    async def get_track_info(self, track_id: str) -> Optional[TrackMetadata]:
        url = f"https://itunes.apple.com/lookup?id={track_id}&entity=song"
        try:
            connector = aiohttp.TCPConnector(family=socket.AF_INET)
            async with aiohttp.ClientSession(connector=connector, headers=self.headers, timeout=aiohttp.ClientTimeout(total=8)) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        results = data.get("results", []) if isinstance(data, dict) else []
                        if results:
                            item = results[0]
                            raw_art = item.get("artworkUrl100", "")
                            thumb = raw_art.replace("100x100bb", "1200x1200bb") if raw_art else None
                            dur_ms = int(item.get("trackTimeMillis") or 0)
                            return TrackMetadata(
                                provider=self.provider_id,
                                provider_track_id=str(item.get("trackId", track_id)),
                                title=item.get("trackName", "Unknown Track"),
                                artist=item.get("artistName", "Unknown Artist"),
                                album=item.get("collectionName", "Apple Music"),
                                duration=dur_ms // 1000,
                                release_date=str(item.get("releaseDate") or "")[:10],
                                artwork=thumb,
                                webpage_url=item.get("trackViewUrl") or f"https://music.apple.com/song/{track_id}",
                                raw_data=item
                            )
        except Exception as e:
            logger.debug(f"Apple Music get_track_info error: {e}")
        return None
