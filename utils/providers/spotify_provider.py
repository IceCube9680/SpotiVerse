# utils/providers/spotify_provider.py
import re
import time
import json
import asyncio
import aiohttp
import socket
import logging
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from typing import Optional, List, Dict, Any, Union

from config import Config
from utils.providers.base import (
    BaseProvider, ProviderHealth, ProviderHealthStatus, TrackMetadata, AudioSource
)

logger = logging.getLogger(__name__)

class SpotifyProvider(BaseProvider):
    """
    Spotify Metadata and Search Provider:
    - Official Spotify Web API with Client Credentials flow
    - Anonymous Web Token extraction fallback when credentials are not configured
    - Rich metadata extraction: ISRC, Album Art, Release Date, Artists, Track Number
    """
    def __init__(self):
        super().__init__(
            provider_id="spotify",
            display_name="Spotify",
            emoji="",
            can_search=True,
            can_track=True,
            can_album=True,
            can_playlist=True,
            can_download=True,  # Downloadable via matched audio source resolution
            is_lossless_source=False
        )
        self.spotify: Optional[spotipy.Spotify] = None
        self._use_anon_token = True
        self._anon_token: Optional[str] = None
        self._anon_token_expiry: float = 0.0
        self._rate_limited_until: float = 0.0

    async def initialize(self) -> bool:
        cid = getattr(Config, "SPOTIFY_CLIENT_ID", "")
        csec = getattr(Config, "SPOTIFY_CLIENT_SECRET", "")
        if cid and csec:
            try:
                auth_manager = SpotifyClientCredentials(
                    client_id=cid,
                    client_secret=csec,
                    requests_timeout=5
                )
                self.spotify = spotipy.Spotify(auth_manager=auth_manager, retries=0, status_retries=0, requests_timeout=5)
                self._use_anon_token = False
                logger.info("SpotifyProvider initialized with API credentials.")
                return True
            except Exception as e:
                logger.warning(f"Spotify API init failed: {e}. Falling back to web token.")
                self._use_anon_token = True
        else:
            self._use_anon_token = True
        return True

    def _fetch_anon_token_sync(self) -> Optional[str]:
        url = "https://open.spotify.com/embed/track/4cOdK2wGLETKBW3PvgPWqT"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        try:
            import requests
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                m = re.search(r'"accessToken":"([^"]+)"', resp.text)
                if m:
                    token = m.group(1)
                    m_exp = re.search(r'"accessTokenExpirationTimestampMs":(\d+)', resp.text)
                    exp_ms = int(m_exp.group(1)) if m_exp else 0
                    self._anon_token = token
                    self._anon_token_expiry = exp_ms / 1000.0 if exp_ms else time.time() + 3600
                    return token
        except Exception as e:
            logger.debug(f"Could not fetch Spotify anon token: {e}")
        return None

    def get_client(self) -> Optional[spotipy.Spotify]:
        now = time.time()
        if now < self._rate_limited_until:
            return None
        if self.spotify and not self._use_anon_token:
            return self.spotify
        if not self._anon_token or now >= (self._anon_token_expiry - 60):
            self._fetch_anon_token_sync()
        if self._anon_token:
            return spotipy.Spotify(auth=self._anon_token, retries=0, status_retries=0, requests_timeout=5)
        return None

    async def health_check(self) -> ProviderHealth:
        start = time.time()
        client = self.get_client()
        latency = (time.time() - start) * 1000

        cid = getattr(Config, "SPOTIFY_CLIENT_ID", "")
        csec = getattr(Config, "SPOTIFY_CLIENT_SECRET", "")

        if client:
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, lambda: client.search(q="music", limit=1))
                latency = (time.time() - start) * 1000
                return ProviderHealth(
                    status=ProviderHealthStatus.ONLINE,
                    latency_ms=latency,
                    message="Spotify API / Web Gateway operational."
                )
            except Exception as e:
                serr = str(e).lower()
                if "429" in serr or "rate" in serr:
                    return ProviderHealth(
                        status=ProviderHealthStatus.DEGRADED,
                        latency_ms=latency,
                        message="Spotify API rate limited."
                    )
                return ProviderHealth(
                    status=ProviderHealthStatus.DEGRADED,
                    latency_ms=latency,
                    message=f"Spotify check degraded: {e}"
                )

        if not cid or not csec:
            return ProviderHealth(
                status=ProviderHealthStatus.ONLINE,  # Web fallback is operational
                latency_ms=latency,
                message="Spotify operating in Web Scraping / Embed Token mode."
            )

        return ProviderHealth(
            status=ProviderHealthStatus.AUTH_REQUIRED,
            latency_ms=latency,
            message="Spotify credentials invalid or expired."
        )

    async def search(self, query: str, limit: int = 10, search_type: str = "track") -> List[TrackMetadata]:
        client = self.get_client()
        if not client:
            return []

        try:
            loop = asyncio.get_running_loop()
            results = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: client.search(q=query, type='track', limit=limit)),
                timeout=6.0
            )
            tracks = []
            if results and 'tracks' in results and 'items' in results['tracks']:
                for item in results['tracks']['items']:
                    if not item:
                        continue
                    album_obj = item.get('album') or {}
                    artists_list = item.get('artists') or []
                    artist_names = [a.get('name', 'Unknown') for a in artists_list if isinstance(a, dict) and a.get('name')]
                    artist_str = ', '.join(artist_names) if artist_names else 'Unknown Artist'
                    album_name = album_obj.get('name', 'Spotify')
                    rel_date = str(album_obj.get('release_date') or '')
                    images = album_obj.get('images') or []
                    thumb = images[0].get('url') if images and isinstance(images[0], dict) else None
                    external_ids = item.get('external_ids') or {}
                    isrc = external_ids.get('isrc')

                    track = TrackMetadata(
                        provider="spotify",
                        provider_track_id=str(item.get('id')),
                        title=item.get('name', 'Unknown Track'),
                        artist=artist_str,
                        album=album_name,
                        album_artist=artist_names[0] if artist_names else artist_str,
                        duration=int(item.get('duration_ms', 0)) // 1000,
                        release_date=rel_date,
                        isrc=isrc,
                        artwork=thumb,
                        webpage_url=item.get('external_urls', {}).get('spotify') or f"https://open.spotify.com/track/{item.get('id')}",
                        explicit=bool(item.get('explicit', False)),
                        raw_data=item
                    )
                    tracks.append(track)
            return tracks
        except Exception as e:
            logger.debug(f"Spotify search error: {e}")
            return []

    async def get_track_info(self, track_id: str) -> Optional[TrackMetadata]:
        client = self.get_client()
        if client:
            try:
                loop = asyncio.get_running_loop()
                item = await loop.run_in_executor(None, lambda: client.track(track_id))
                if item:
                    album_obj = item.get('album') or {}
                    artists_list = item.get('artists') or []
                    artist_names = [a.get('name', 'Unknown') for a in artists_list if isinstance(a, dict) and a.get('name')]
                    artist_str = ', '.join(artist_names) if artist_names else 'Unknown Artist'
                    rel_date = str(album_obj.get('release_date') or '')
                    images = album_obj.get('images') or []
                    thumb = images[0].get('url') if images and isinstance(images[0], dict) else None
                    external_ids = item.get('external_ids') or {}

                    return TrackMetadata(
                        provider="spotify",
                        provider_track_id=str(item.get('id', track_id)),
                        title=item.get('name', 'Unknown Track'),
                        artist=artist_str,
                        album=album_obj.get('name', 'Spotify'),
                        album_artist=artist_names[0] if artist_names else artist_str,
                        duration=int(item.get('duration_ms', 0)) // 1000,
                        release_date=rel_date,
                        isrc=external_ids.get('isrc'),
                        artwork=thumb,
                        webpage_url=f"https://open.spotify.com/track/{track_id}",
                        explicit=bool(item.get('explicit', False)),
                        raw_data=item
                    )
            except Exception as e:
                logger.debug(f"Spotify get_track_info spotipy error: {e}")

        # Web embed fallback
        try:
            embed_url = f"https://open.spotify.com/embed/track/{track_id}"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            connector = aiohttp.TCPConnector(family=socket.AF_INET)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(embed_url, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html)
                        if m:
                            data = json.loads(m.group(1))
                            entity = data.get('props', {}).get('pageProps', {}).get('state', {}).get('data', {}).get('entity', {})
                            if entity:
                                title = entity.get('name') or entity.get('title') or "Unknown Track"
                                artists = [a.get('name') for a in entity.get('artists', []) if isinstance(a, dict) and a.get('name')]
                                artist_str = ", ".join(artists) if artists else "Unknown Artist"
                                images = entity.get('visualIdentity', {}).get('image', [])
                                thumb = images[0].get('url') if images else None
                                rel_date = entity.get('releaseDate', {}).get('isoString', '')
                                return TrackMetadata(
                                    provider="spotify",
                                    provider_track_id=track_id,
                                    title=title,
                                    artist=artist_str,
                                    album="Spotify",
                                    duration=int(entity.get('duration', 0)) // 1000,
                                    release_date=rel_date[:10] if rel_date else "",
                                    artwork=thumb,
                                    webpage_url=f"https://open.spotify.com/track/{track_id}"
                                )
        except Exception as e:
            logger.debug(f"Spotify web embed fallback error: {e}")

        return None
