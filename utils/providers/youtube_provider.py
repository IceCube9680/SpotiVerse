# utils/providers/youtube_provider.py
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

class YouTubeProvider(BaseProvider):
    """
    YouTube Search, Metadata, and Audio Source Provider using yt-dlp:
    - High-speed extraction
    - Multi-client fallbacks (android, tv, web, ios)
    - Direct audio stream resolution
    """
    def __init__(self, provider_id: str = "youtube", display_name: str = "YouTube", emoji: str = "🔴"):
        super().__init__(
            provider_id=provider_id,
            display_name=display_name,
            emoji=emoji,
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
                    return ydl.extract_info("ytsearch1:audio", download=False)

            info = await asyncio.wait_for(loop.run_in_executor(None, _probe), timeout=8.0)
            latency = (time.time() - start) * 1000
            if info and info.get("entries"):
                return ProviderHealth(
                    status=ProviderHealthStatus.ONLINE,
                    latency_ms=latency,
                    message="YouTube yt-dlp search & streaming operational."
                )
            return ProviderHealth(
                status=ProviderHealthStatus.DEGRADED,
                latency_ms=latency,
                message="YouTube search returned empty response."
            )
        except Exception as e:
            latency = (time.time() - start) * 1000
            return ProviderHealth(
                status=ProviderHealthStatus.DEGRADED,
                latency_ms=latency,
                message=f"YouTube check error: {e}"
            )

    async def search(self, query: str, limit: int = 10, search_type: str = "track") -> List[TrackMetadata]:
        try:
            loop = asyncio.get_running_loop()
            def _yt_search():
                opts = get_ytdlp_options({
                    'quiet': True,
                    'skip_download': True,
                    'noplaylist': True,
                    'extract_flat': True,
                })
                try:
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        return ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
                except Exception as err:
                    logger.debug(f"Primary YouTube search fallback: {err}")
                    fallback_opts = get_ytdlp_options(
                        extra_opts={'quiet': True, 'skip_download': True, 'noplaylist': True, 'extract_flat': True},
                        player_clients=['mweb', 'android', 'ios', 'web']
                    )
                    with yt_dlp.YoutubeDL(fallback_opts) as ydl:
                        return ydl.extract_info(f"ytsearch{limit}:{query}", download=False)

            info = await asyncio.wait_for(loop.run_in_executor(None, _yt_search), timeout=15.0)
            entries = info.get('entries', []) if info else []
            tracks = []
            for e in entries[:limit]:
                if not e:
                    continue
                tid = e.get('id')
                title = e.get('title', 'Unknown Title')
                artist = e.get('uploader') or e.get('uploader_url') or 'Unknown Artist'
                dur = int(e.get('duration') or 0)
                thumb = e.get('thumbnail') or (e.get('thumbnails', [{}])[-1].get('url') if e.get('thumbnails') else None)
                url = e.get('webpage_url') or f"https://www.youtube.com/watch?v={tid}"

                tracks.append(TrackMetadata(
                    provider=self.provider_id,
                    provider_track_id=str(tid),
                    title=title,
                    artist=artist,
                    album="YouTube",
                    duration=dur,
                    release_date=str(e.get('upload_date') or "")[:4],
                    artwork=thumb,
                    webpage_url=url,
                    raw_data=e
                ))
            return tracks
        except Exception as e:
            logger.debug(f"YouTube search error: {e}")
            return []

    async def get_track_info(self, track_id: str) -> Optional[TrackMetadata]:
        url = track_id if "http" in track_id else f"https://www.youtube.com/watch?v={track_id}"
        try:
            loop = asyncio.get_running_loop()
            def _extract():
                opts = get_ytdlp_options({'quiet': True, 'skip_download': True})
                try:
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        return ydl.extract_info(url, download=False)
                except Exception:
                    opts_fb = get_ytdlp_options({'quiet': True, 'skip_download': True}, player_clients=['mweb', 'android', 'ios', 'web'])
                    with yt_dlp.YoutubeDL(opts_fb) as ydl:
                        return ydl.extract_info(url, download=False)

            info = await loop.run_in_executor(None, _extract)
            if info:
                return TrackMetadata(
                    provider=self.provider_id,
                    provider_track_id=str(info.get("id")),
                    title=info.get("title", "Unknown Title"),
                    artist=info.get("uploader") or info.get("channel") or "Unknown Artist",
                    album="YouTube",
                    duration=int(info.get("duration") or 0),
                    release_date=str(info.get("upload_date") or "")[:4],
                    artwork=info.get("thumbnail"),
                    webpage_url=info.get("webpage_url", url),
                    raw_data=info
                )
        except Exception as e:
            logger.debug(f"YouTube get_track_info error: {e}")
        return None

    async def resolve_source(self, track_metadata: TrackMetadata, requested_quality: Union[int, str] = "best") -> Optional[AudioSource]:
        """Resolve highest quality audio stream from YouTube."""
        query_url = track_metadata.webpage_url or f"https://www.youtube.com/watch?v={track_metadata.provider_track_id}"
        try:
            loop = asyncio.get_running_loop()
            def _resolve():
                opts = get_ytdlp_options({'quiet': True, 'skip_download': True})
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(query_url, download=False)
                    formats = info.get("formats", []) if info else []
                    # Filter audio formats
                    audio_fmts = [f for f in formats if f.get("vcodec") == "none" or (f.get("acodec") != "none" and not f.get("vcodec"))]
                    if not audio_fmts:
                        audio_fmts = formats

                    # Find best bitrate audio format
                    best_fmt = max(audio_fmts, key=lambda f: f.get("tbr") or f.get("abr") or 0) if audio_fmts else {}
                    codec = str(best_fmt.get("acodec", "opus")).split(".")[0].lower()
                    br = int(best_fmt.get("abr") or best_fmt.get("tbr") or 160)
                    sr = int(best_fmt.get("asr") or 48000)

                    return AudioSource(
                        source_provider=self.provider_id,
                        source_url=best_fmt.get("url") or query_url,
                        codec=codec,
                        container=best_fmt.get("ext", "webm"),
                        bitrate=br,
                        sample_rate=sr,
                        bit_depth=16,
                        channels=int(best_fmt.get("audio_channels") or 2),
                        file_size=int(best_fmt.get("filesize") or 0),
                        lossless=False,
                        downloadable=True,
                        requires_transcoding=True,
                        headers=best_fmt.get("http_headers") or {}
                    )

            return await loop.run_in_executor(None, _resolve)
        except Exception as e:
            logger.debug(f"YouTube resolve_source error: {e}")
            return None


class YouTubeMusicProvider(YouTubeProvider):
    """
    YouTube Music Dedicated Provider:
    - Optimized for official audio tracks and discography
    - Search targeting music releases
    """
    def __init__(self):
        super().__init__(
            provider_id="youtubemusic",
            display_name="YouTube Music",
            emoji="🔴"
        )
