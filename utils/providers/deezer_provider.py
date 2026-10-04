# utils/providers/deezer_provider.py
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

class DeezerProvider(BaseProvider):
    """
    Deezer Metadata & Search Provider:
    - Official Deezer public REST API (`api.deezer.com`)
    - Exact ISRC extraction, release date, high-resolution album artwork
    """
    def __init__(self):
        super().__init__(
            provider_id="deezer",
            display_name="Deezer",
            emoji="🟣",
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
        url = "https://api.deezer.com/search?q=daft+punk&limit=1"
        try:
            connector = aiohttp.TCPConnector(family=socket.AF_INET)
            async with aiohttp.ClientSession(connector=connector, headers=self.headers, timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(url) as resp:
                    latency = (time.time() - start) * 1000
                    if resp.status == 200:
                        return ProviderHealth(
                            status=ProviderHealthStatus.ONLINE,
                            latency_ms=latency,
                            message="Deezer REST API operational."
                        )
                    return ProviderHealth(
                        status=ProviderHealthStatus.DEGRADED,
                        latency_ms=latency,
                        message=f"Deezer returned HTTP {resp.status}"
                    )
        except Exception as e:
            latency = (time.time() - start) * 1000
            return ProviderHealth(
                status=ProviderHealthStatus.DEGRADED,
                latency_ms=latency,
                message=f"Deezer check error: {e}"
            )

    async def search(self, query: str, limit: int = 10, search_type: str = "track") -> List[TrackMetadata]:
        url = f"https://api.deezer.com/search?q={query}&limit={limit}"
        try:
            connector = aiohttp.TCPConnector(family=socket.AF_INET)
            async with aiohttp.ClientSession(connector=connector, headers=self.headers, timeout=aiohttp.ClientTimeout(total=8)) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        items = data.get("data", []) if isinstance(data, dict) else []
                        tracks = []
                        for item in items[:limit]:
                            if not item:
                                continue
                            tid = item.get("id")
                            title = item.get("title", "Unknown Track")
                            artist_obj = item.get("artist", {})
                            artist = artist_obj.get("name", "Unknown Artist")
                            album_obj = item.get("album", {})
                            album = album_obj.get("title", "Deezer")
                            dur = int(item.get("duration", 0))
                            thumb = album_obj.get("cover_xl") or album_obj.get("cover_big") or album_obj.get("cover_medium")
                            link = item.get("link") or f"https://www.deezer.com/track/{tid}"

                            tracks.append(TrackMetadata(
                                provider=self.provider_id,
                                provider_track_id=str(tid),
                                title=title,
                                artist=artist,
                                album=album,
                                duration=dur,
                                artwork=thumb,
                                webpage_url=link,
                                explicit=bool(item.get("explicit_lyrics", False)),
                                raw_data=item
                            ))
                        return tracks
        except Exception as e:
            logger.debug(f"Deezer search error: {e}")
        return []

    async def get_track_info(self, track_id: str) -> Optional[TrackMetadata]:
        url = f"https://api.deezer.com/track/{track_id}"
        try:
            connector = aiohttp.TCPConnector(family=socket.AF_INET)
            async with aiohttp.ClientSession(connector=connector, headers=self.headers, timeout=aiohttp.ClientTimeout(total=8)) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        if data and not data.get("error"):
                            artist_obj = data.get("artist", {})
                            album_obj = data.get("album", {})
                            thumb = album_obj.get("cover_xl") or album_obj.get("cover_big") or album_obj.get("cover_medium")
                            rel_date = str(data.get("release_date") or "")
                            return TrackMetadata(
                                provider=self.provider_id,
                                provider_track_id=str(data.get("id", track_id)),
                                title=data.get("title", "Unknown Track"),
                                artist=artist_obj.get("name", "Unknown Artist"),
                                album=album_obj.get("title", "Deezer"),
                                duration=int(data.get("duration", 0)),
                                release_date=rel_date,
                                isrc=data.get("isrc"),
                                artwork=thumb,
                                webpage_url=data.get("link") or f"https://www.deezer.com/track/{track_id}",
                                explicit=bool(data.get("explicit_lyrics", False)),
                                raw_data=data
                            )
        except Exception as e:
            logger.debug(f"Deezer get_track_info error: {e}")
        return None
