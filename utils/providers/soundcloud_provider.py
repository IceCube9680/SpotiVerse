# utils/providers/soundcloud_provider.py
import asyncio
import logging
import time
from typing import Optional, List, Dict, Any, Union
import yt_dlp

from utils.ytdlp_utils import get_ytdlp_options
from utils.providers.base import (
    BaseProvider, ProviderHealth, ProviderHealthStatus, TrackMetadata, AudioSource
)

logger = logging.getLogger(__name__)

class SoundCloudProvider(BaseProvider):
    """
    SoundCloud Metadata, Search, and Audio Stream Provider using yt-dlp / public web APIs.
    """
    def __init__(self):
        super().__init__(
            provider_id="soundcloud",
            display_name="SoundCloud",
            emoji="",
            can_search=True,
            can_track=True,
            can_album=True,
            can_playlist=True,
            can_download=True,
            is_lossless_source=False
        )

    async def health_check(self) -> ProviderHealth:
        start = time.time()
        try:
            loop = asyncio.get_running_loop()
            def _probe():
                opts = get_ytdlp_options({'quiet': True, 'skip_download': True, 'extract_flat': True})
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info("scsearch1:electronic", download=False)

            info = await asyncio.wait_for(loop.run_in_executor(None, _probe), timeout=8.0)
            latency = (time.time() - start) * 1000
            if info and info.get("entries"):
                return ProviderHealth(
                    status=ProviderHealthStatus.ONLINE,
                    latency_ms=latency,
                    message="SoundCloud search & stream gateway operational."
                )
            return ProviderHealth(
                status=ProviderHealthStatus.DEGRADED,
                latency_ms=latency,
                message="SoundCloud returned empty results."
            )
        except Exception as e:
            latency = (time.time() - start) * 1000
            return ProviderHealth(
                status=ProviderHealthStatus.DEGRADED,
                latency_ms=latency,
                message=f"SoundCloud check error: {e}"
            )

    async def search(self, query: str, limit: int = 10, search_type: str = "track") -> List[TrackMetadata]:
        try:
            loop = asyncio.get_running_loop()
            def _sc_search():
                opts = get_ytdlp_options({
                    'quiet': True,
                    'skip_download': True,
                    'noplaylist': True,
                    'extract_flat': True,
                })
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info(f"scsearch{limit}:{query}", download=False)

            info = await asyncio.wait_for(loop.run_in_executor(None, _sc_search), timeout=12.0)
            entries = info.get('entries', []) if info else []
            tracks = []
            for e in entries[:limit]:
                if not e:
                    continue
                tid = e.get('id')
                title = e.get('title', 'Unknown Title')
                artist = e.get('uploader') or 'SoundCloud Artist'
                dur = int(e.get('duration') or 0)
                thumb = e.get('thumbnail')
                url = e.get('webpage_url') or f"https://soundcloud.com/{tid}"

                tracks.append(TrackMetadata(
                    provider=self.provider_id,
                    provider_track_id=str(tid),
                    title=title,
                    artist=artist,
                    album="SoundCloud",
                    duration=dur,
                    artwork=thumb,
                    webpage_url=url,
                    raw_data=e
                ))
            return tracks
        except Exception as e:
            logger.debug(f"SoundCloud search error: {e}")
            return []

    async def get_track_info(self, track_id: str) -> Optional[TrackMetadata]:
        url = track_id if "http" in track_id else f"https://soundcloud.com/{track_id}"
        try:
            loop = asyncio.get_running_loop()
            def _extract():
                opts = get_ytdlp_options({'quiet': True, 'skip_download': True})
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info(url, download=False)

            info = await loop.run_in_executor(None, _extract)
            if info:
                return TrackMetadata(
                    provider=self.provider_id,
                    provider_track_id=str(info.get("id")),
                    title=info.get("title", "Unknown Title"),
                    artist=info.get("uploader") or "SoundCloud Artist",
                    album="SoundCloud",
                    duration=int(info.get("duration") or 0),
                    artwork=info.get("thumbnail"),
                    webpage_url=info.get("webpage_url", url),
                    raw_data=info
                )
        except Exception as e:
            logger.debug(f"SoundCloud get_track_info error: {e}")
        return None
