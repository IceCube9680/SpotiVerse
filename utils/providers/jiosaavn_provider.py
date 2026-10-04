# utils/providers/jiosaavn_provider.py
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

class JioSaavnProvider(BaseProvider):
    """
    JioSaavn Metadata and Audio Source Provider:
    - High-quality 320kbps AAC audio streams
    - Autocomplete and search.getResults API
    - Rich Indian & International music catalog
    """
    def __init__(self):
        super().__init__(
            provider_id="jiosaavn",
            display_name="JioSaavn",
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
        url = "https://www.jiosaavn.com/api.php?__call=autocomplete.get&query=arijit&_format=json&_marker=0"
        try:
            connector = aiohttp.TCPConnector(family=socket.AF_INET)
            async with aiohttp.ClientSession(connector=connector, headers=self.headers, timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(url) as resp:
                    latency = (time.time() - start) * 1000
                    if resp.status == 200:
                        return ProviderHealth(
                            status=ProviderHealthStatus.ONLINE,
                            latency_ms=latency,
                            message="JioSaavn API operational."
                        )
                    return ProviderHealth(
                        status=ProviderHealthStatus.DEGRADED,
                        latency_ms=latency,
                        message=f"JioSaavn returned HTTP {resp.status}"
                    )
        except Exception as e:
            latency = (time.time() - start) * 1000
            return ProviderHealth(
                status=ProviderHealthStatus.DEGRADED,
                latency_ms=latency,
                message=f"JioSaavn health check error: {e}"
            )

    async def search(self, query: str, limit: int = 10, search_type: str = "track") -> List[TrackMetadata]:
        try:
            connector = aiohttp.TCPConnector(family=socket.AF_INET)
            async with aiohttp.ClientSession(connector=connector, headers=self.headers, timeout=aiohttp.ClientTimeout(total=8)) as session:
                # 1. Search getResults
                url = f"https://www.jiosaavn.com/api.php?__call=search.getResults&_format=json&n={limit}&p=1&_marker=0&ctx=android&q={query}"
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        results = data.get("results", []) if isinstance(data, dict) else []
                        tracks = []
                        for item in results[:limit]:
                            if not item:
                                continue
                            tid = item.get("id")
                            title = item.get("song") or item.get("title") or "Unknown Song"
                            artist = item.get("primary_artists") or item.get("singers") or "Unknown Artist"
                            album = item.get("album") or "JioSaavn"
                            year = str(item.get("year") or "")[:4]
                            dur = int(item.get("duration") or 0)
                            thumb_img = item.get("image", "")
                            thumb = thumb_img.replace("50x50", "500x500").replace("150x150", "500x500") if thumb_img else None

                            tracks.append(TrackMetadata(
                                provider=self.provider_id,
                                provider_track_id=str(tid),
                                title=title,
                                artist=artist,
                                album=album,
                                duration=dur,
                                release_date=year,
                                artwork=thumb,
                                webpage_url=item.get("perma_url") or f"https://www.jiosaavn.com/song/{tid}",
                                raw_data=item
                            ))
                        if tracks:
                            return tracks

                # 2. Fallback to Autocomplete
                url_auto = f"https://www.jiosaavn.com/api.php?__call=autocomplete.get&query={query}&_format=json&_marker=0"
                async with session.get(url_auto) as resp_auto:
                    if resp_auto.status == 200:
                        data_auto = await resp_auto.json(content_type=None)
                        songs_data = data_auto.get('songs', {}).get('data', []) if isinstance(data_auto, dict) else []
                        tracks = []
                        for item in songs_data[:limit]:
                            if not item:
                                continue
                            more_info = item.get('more_info') or {}
                            artist = more_info.get('primary_artists') or item.get('description', 'Unknown Artist')
                            album = item.get('album') or "JioSaavn"
                            if isinstance(album, dict):
                                album = album.get("name", "JioSaavn")
                            thumb_img = item.get('image', '')
                            thumb = thumb_img.replace('50x50', '500x500').replace('150x150', '500x500') if thumb_img else None

                            tracks.append(TrackMetadata(
                                provider=self.provider_id,
                                provider_track_id=str(item.get("id") or item.get("url", "")),
                                title=item.get('title') or item.get('song') or 'Unknown Track',
                                artist=artist,
                                album=album,
                                artwork=thumb,
                                webpage_url=f"https://www.jiosaavn.com{item.get('url', '')}" if str(item.get('url', '')).startswith('/') else item.get('url')
                            ))
                        return tracks
        except Exception as e:
            logger.debug(f"JioSaavn search error: {e}")
        return []

    async def get_track_info(self, track_id: str) -> Optional[TrackMetadata]:
        url = f"https://www.jiosaavn.com/api.php?__call=song.getDetails&pids={track_id}&_format=json&_marker=0&ctx=android"
        try:
            connector = aiohttp.TCPConnector(family=socket.AF_INET)
            async with aiohttp.ClientSession(connector=connector, headers=self.headers, timeout=aiohttp.ClientTimeout(total=8)) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        sdata = data.get(track_id, {}) or (data.get('songs', [{}])[0] if 'songs' in data else {})
                        if sdata:
                            thumb_img = sdata.get('image', '')
                            thumb = thumb_img.replace('50x50', '500x500').replace('150x150', '500x500') if thumb_img else None
                            return TrackMetadata(
                                provider=self.provider_id,
                                provider_track_id=track_id,
                                title=sdata.get('song') or sdata.get('title') or "Unknown Track",
                                artist=sdata.get('primary_artists') or sdata.get('singers') or "Unknown Artist",
                                album=sdata.get('album') or "JioSaavn",
                                duration=int(sdata.get('duration', 0)),
                                release_date=str(sdata.get('year', ''))[:4],
                                artwork=thumb,
                                webpage_url=sdata.get("perma_url") or f"https://www.jiosaavn.com/song/{track_id}",
                                raw_data=sdata
                            )
        except Exception as e:
            logger.debug(f"JioSaavn get_track_info error: {e}")
        return None
