# utils/providers/archive_provider.py
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

class ArchiveProvider(BaseProvider):
    """
    Internet Archive (archive.org) Audio Provider:
    - Direct access to millions of public domain recordings, Live Music Archive (etree),
      historical broadcasts, 78rpm records, and lossless audio.
    - Native direct downloads for FLAC, OGG, and MP3 files!
    """
    def __init__(self):
        super().__init__(
            provider_id="archive",
            display_name="Internet Archive",
            emoji="",
            can_search=True,
            can_track=True,
            can_album=True,
            can_playlist=True,
            can_download=True,
            is_lossless_source=True
        )
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

    async def health_check(self) -> ProviderHealth:
        start = time.time()
        url = "https://archive.org/advancedsearch.php?q=mediatype:audio&rows=1&output=json"
        try:
            connector = aiohttp.TCPConnector(family=socket.AF_INET)
            async with aiohttp.ClientSession(connector=connector, headers=self.headers, timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(url) as resp:
                    latency = (time.time() - start) * 1000
                    if resp.status == 200:
                        return ProviderHealth(
                            status=ProviderHealthStatus.ONLINE,
                            latency_ms=latency,
                            message="Internet Archive Search & Audio API operational."
                        )
                    return ProviderHealth(
                        status=ProviderHealthStatus.DEGRADED,
                        latency_ms=latency,
                        message=f"Archive.org returned HTTP {resp.status}"
                    )
        except Exception as e:
            latency = (time.time() - start) * 1000
            return ProviderHealth(
                status=ProviderHealthStatus.DEGRADED,
                latency_ms=latency,
                message=f"Internet Archive check error: {e}"
            )

    async def search(self, query: str, limit: int = 10, search_type: str = "track") -> List[TrackMetadata]:
        url = f"https://archive.org/advancedsearch.php?q={query}+AND+mediatype:audio&fl[]=identifier,title,creator,collection,year,publicdate&rows={limit}&output=json"
        try:
            connector = aiohttp.TCPConnector(family=socket.AF_INET)
            async with aiohttp.ClientSession(connector=connector, headers=self.headers, timeout=aiohttp.ClientTimeout(total=8)) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        docs = data.get("response", {}).get("docs", [])
                        tracks = []
                        for doc in docs[:limit]:
                            if not doc:
                                continue
                            ident = doc.get("identifier")
                            title = doc.get("title") or ident or "Unknown Track"
                            if isinstance(title, list):
                                title = title[0]
                            creator = doc.get("creator") or "Internet Archive"
                            if isinstance(creator, list):
                                creator = ", ".join(creator)
                            year = str(doc.get("year") or doc.get("publicdate") or "")[:4]
                            col = doc.get("collection")
                            album = col[0] if isinstance(col, list) and col else "Archive Audio"

                            tracks.append(TrackMetadata(
                                provider=self.provider_id,
                                provider_track_id=str(ident),
                                title=str(title),
                                artist=str(creator),
                                album=str(album),
                                release_date=year,
                                artwork=f"https://archive.org/services/img/{ident}",
                                webpage_url=f"https://archive.org/details/{ident}",
                                raw_data=doc
                            ))
                        return tracks
        except Exception as e:
            logger.debug(f"Archive.org search error: {e}")
        return []

    async def get_track_info(self, track_id: str) -> Optional[TrackMetadata]:
        url = f"https://archive.org/metadata/{track_id}"
        try:
            connector = aiohttp.TCPConnector(family=socket.AF_INET)
            async with aiohttp.ClientSession(connector=connector, headers=self.headers, timeout=aiohttp.ClientTimeout(total=8)) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        meta = data.get("metadata", {})
                        if meta:
                            title = meta.get("title") or track_id
                            creator = meta.get("creator") or meta.get("artist") or "Internet Archive"
                            if isinstance(creator, list):
                                creator = ", ".join(creator)
                            year = str(meta.get("year") or meta.get("publicdate") or "")[:4]

                            return TrackMetadata(
                                provider=self.provider_id,
                                provider_track_id=track_id,
                                title=str(title),
                                artist=str(creator),
                                album=str(meta.get("collection", ["Archive Audio"])[0] if isinstance(meta.get("collection"), list) else "Archive Audio"),
                                release_date=year,
                                artwork=f"https://archive.org/services/img/{track_id}",
                                webpage_url=f"https://archive.org/details/{track_id}",
                                raw_data=data
                            )
        except Exception as e:
            logger.debug(f"Archive.org get_track_info error: {e}")
        return None
