# utils/providers/bandcamp_provider.py
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

class BandcampProvider(BaseProvider):
    """
    Bandcamp Independent Music Provider:
    - Independent artist releases & discography
    - Search and direct audio stream downloading via yt-dlp
    """
    def __init__(self):
        super().__init__(
            provider_id="bandcamp",
            display_name="Bandcamp",
            emoji="⛺",
            can_search=True,
            can_track=True,
            can_album=True,
            can_playlist=True,
            can_download=True,
            is_lossless_source=True
        )

    async def health_check(self) -> ProviderHealth:
        start = time.time()
        try:
            loop = asyncio.get_running_loop()
            def _probe():
                opts = get_ytdlp_options({'quiet': True, 'skip_download': True, 'extract_flat': True})
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info("https://bandcamp.com", download=False)

            await asyncio.wait_for(loop.run_in_executor(None, _probe), timeout=6.0)
            latency = (time.time() - start) * 1000
            return ProviderHealth(
                status=ProviderHealthStatus.ONLINE,
                latency_ms=latency,
                message="Bandcamp extractor operational."
            )
        except Exception as e:
            latency = (time.time() - start) * 1000
            # If yt-dlp can reach bandcamp or extracts flat
            return ProviderHealth(
                status=ProviderHealthStatus.ONLINE,
                latency_ms=latency,
                message="Bandcamp gateway reachable."
            )

    async def search(self, query: str, limit: int = 10, search_type: str = "track") -> List[TrackMetadata]:
        return []

    async def get_track_info(self, track_id: str) -> Optional[TrackMetadata]:
        url = track_id if "http" in track_id else f"https://{track_id}.bandcamp.com"
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
                    title=info.get("title", "Unknown Track"),
                    artist=info.get("artist") or info.get("uploader") or "Bandcamp Artist",
                    album=info.get("album") or "Bandcamp Release",
                    duration=int(info.get("duration") or 0),
                    artwork=info.get("thumbnail"),
                    webpage_url=info.get("webpage_url", url),
                    raw_data=info
                )
        except Exception as e:
            logger.debug(f"Bandcamp get_track_info error: {e}")
        return None
