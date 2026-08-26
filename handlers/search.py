import json
import re
import time
import socket
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import aiohttp
import asyncio
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from config import Config
from info import SEARCH_PROVIDERS, DEFAULT_SEARCH_PROVIDER
from utils.ytdlp_utils import get_ytdlp_options
import logging
import yt_dlp

try:
    import urllib3.util.connection as urllib3_cn
    urllib3_cn.allowed_gai_family = lambda: socket.AF_INET
except Exception:
    pass

logger = logging.getLogger(__name__)

class SearchHandler:
    def __init__(self):
        self._use_anonymous_token = True
        self._anon_token = None
        self._anon_token_expiry = 0
        self.spotify = None
        self._search_cache = {}
        self._cache_ttl = 300
        self._spotify_rate_limited_until = 0

        # Initialize Spotify client
        if Config.SPOTIFY_CLIENT_ID and Config.SPOTIFY_CLIENT_SECRET:
            try:
                auth_manager = SpotifyClientCredentials(
                    client_id=Config.SPOTIFY_CLIENT_ID,
                    client_secret=Config.SPOTIFY_CLIENT_SECRET,
                    requests_timeout=5
                )
                self.spotify = spotipy.Spotify(auth_manager=auth_manager, retries=0, status_retries=0, requests_timeout=5)
                self._use_anonymous_token = False
                logger.info("Spotify client initialized successfully with API credentials")
            except Exception as e:
                logger.error(f"Failed to initialize Spotify client with API credentials: {e}")
                self._use_anonymous_token = True
        else:
            self._use_anonymous_token = True
            logger.info("Spotify credentials not configured. Using automatic web token / provider fallback mode.")

    def fetch_anonymous_spotify_token(self):
        """Fetch an anonymous access token from Spotify web embed"""
        url = "https://open.spotify.com/embed/track/4cOdK2wGLETKBW3PvgPWqT"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        html = None

        # 1. Try curl subprocess (fastest on Linux systems)
        try:
            import subprocess
            cmd = ['curl', '-s', '-4', '-A', headers['User-Agent'], url]
            html = subprocess.check_output(cmd, timeout=5).decode('utf-8', errors='ignore')
        except Exception:
            html = None

        # 2. Fallback to requests if curl is unavailable or failed
        if not html:
            try:
                import requests
                resp = requests.get(url, headers=headers, timeout=5)
                if resp.status_code == 200:
                    html = resp.text
            except Exception as e:
                logger.error(f"Error fetching Spotify embed page via requests: {e}")

        if html:
            m_tok = re.search(r'"accessToken":"([^"]+)"', html)
            if m_tok:
                token = m_tok.group(1)
                m_exp = re.search(r'"accessTokenExpirationTimestampMs":(\d+)', html)
                exp_ms = int(m_exp.group(1)) if m_exp else 0
                self._anon_token = token
                self._anon_token_expiry = exp_ms / 1000.0 if exp_ms else time.time() + 3600
                logger.info("Successfully fetched anonymous Spotify access token")
                return token

        logger.error("Failed to extract Spotify anonymous access token")
        return None

    def get_spotify_client(self):
        """Get standard or anonymous spotipy client"""
        now = time.time()
        if now < self._spotify_rate_limited_until:
            return None

        if self.spotify and not self._use_anonymous_token:
            return self.spotify

        # Check token freshness
        if not self._anon_token or now >= (self._anon_token_expiry - 60):
            self.fetch_anonymous_spotify_token()

        if self._anon_token:
            return spotipy.Spotify(auth=self._anon_token, retries=0, status_retries=0, requests_timeout=5)
        return None

    async def search_spotify(self, query, limit=10):
        """Search Spotify for tracks with fallback handling"""
        sp_client = self.get_spotify_client()
        if sp_client and not self._use_anonymous_token:
            try:
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = asyncio.get_event_loop()
                results = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: sp_client.search(q=query, type='track', limit=limit)),
                    timeout=5.0
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

                        track = {
                            'id': item.get('id'),
                            'title': item.get('name', 'Unknown Track'),
                            'artist': artist_str,
                            'album': album_name,
                            'year': rel_date[:4] if rel_date else 'Unknown',
                            'duration': int(item.get('duration_ms', 0)) // 1000,
                            'thumbnail': thumb,
                            'provider': 'spotify'
                        }
                        tracks.append(track)
                    if tracks:
                        return tracks
            except Exception as e:
                serr = str(e)
                if "429" in serr or "rate" in serr.lower() or "too many" in serr.lower():
                    logger.warning("Spotify API rate limit encountered. Cooldown for 5 minutes.")
                    self._spotify_rate_limited_until = time.time() + 300
                else:
                    logger.error(f"Spotify search error: {e}")

        # Fallback to JioSaavn or YouTube search if Spotify search returned nothing
        logger.info("Falling back from Spotify search to JioSaavn/YouTube search")
        saavn_res = await self.search_saavn(query, limit)
        if saavn_res:
            return saavn_res
        return await self.search_youtube(query, limit)

    async def search_youtube(self, query, limit=10):
        """Search YouTube for tracks using yt-dlp (ytsearch) non-blockingly"""
        try:
            def _yt_search():
                ydl_opts = get_ytdlp_options({
                    'quiet': True,
                    'skip_download': True,
                    'noplaylist': True,
                    'extract_flat': True,
                })
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        return ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
                except Exception as err:
                    logger.warning(f"Primary YouTube search failed: {err}. Retrying with fallback player clients...")
                    fallback_opts = get_ytdlp_options(
                        extra_opts={'quiet': True, 'skip_download': True, 'noplaylist': True, 'extract_flat': True},
                        player_clients=['mweb', 'android', 'ios', 'web']
                    )
                    with yt_dlp.YoutubeDL(fallback_opts) as ydl:
                        return ydl.extract_info(f"ytsearch{limit}:{query}", download=False)

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.get_event_loop()

            info = await asyncio.wait_for(loop.run_in_executor(None, _yt_search), timeout=15.0)

            entries = info.get('entries', []) if info else []
            tracks = []
            for e in entries[:limit]:
                if not e:
                    continue
                tracks.append({
                    'id': e.get('id'),
                    'title': e.get('title', 'Unknown Title'),
                    'artist': e.get('uploader') or e.get('uploader_url') or 'Unknown Artist',
                    'album': 'YouTube',
                    'year': str(e.get('upload_date', '')[:4]) if e.get('upload_date') else 'Unknown',
                    'duration': int(e.get('duration') or 0),
                    'thumbnail': e.get('thumbnail') or (e.get('thumbnails', [{}])[-1].get('url') if e.get('thumbnails') else None),
                    'provider': 'youtube',
                    'webpage_url': e.get('webpage_url') or f"https://www.youtube.com/watch?v={e.get('id')}"
                })
            return tracks if tracks else None
        except Exception as e:
            logger.error(f"YouTube search error: {e}")
            return None

    async def search_saavn(self, query, limit=10):
        """Search JioSaavn for tracks with autocomplete and getResults fallbacks"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        try:
            connector = aiohttp.TCPConnector(family=socket.AF_INET)
            # 1. Try Autocomplete API
            url_auto = f"https://www.jiosaavn.com/api.php?__call=autocomplete.get&query={query}&_format=json&_marker=0"
            async with aiohttp.ClientSession(connector=connector, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as session:
                async with session.get(url_auto) as response:
                    if response.status == 200:
                        data = await response.json(content_type=None)
                        songs_data = data.get('songs', {}).get('data', []) if isinstance(data, dict) else []
                        if songs_data:
                            tracks = []
                            for item in songs_data[:limit]:
                                if not item:
                                    continue
                                more_info = item.get('more_info') or {}
                                artist_str = more_info.get('primary_artists') or ''
                                if not artist_str:
                                    desc = item.get('description', '')
                                    if ' · ' in desc:
                                        artist_str = desc.split(' · ')[0]
                                    elif desc:
                                        artist_str = desc
                                if not artist_str:
                                    artist_str = 'Unknown Artist'

                                album_val = item.get('album')
                                if isinstance(album_val, dict):
                                    album_name = album_val.get('title') or album_val.get('name') or 'JioSaavn'
                                elif isinstance(album_val, str) and album_val:
                                    album_name = album_val
                                else:
                                    album_name = 'JioSaavn'

                                thumb_img = item.get('image', '')
                                if isinstance(thumb_img, str) and thumb_img:
                                    thumb = thumb_img.replace('50x50', '500x500').replace('150x150', '500x500')
                                else:
                                    thumb = None

                                track = {
                                    'id': item.get('id') or item.get('url', ''),
                                    'title': item.get('title') or item.get('song') or 'Unknown Track',
                                    'artist': artist_str,
                                    'album': album_name,
                                    'year': 'Unknown',
                                    'duration': 0,
                                    'thumbnail': thumb,
                                    'provider': 'saavn'
                                }
                                tracks.append(track)
                            if tracks:
                                return tracks

                # 2. Try search.getResults API
                url_search = f"https://www.jiosaavn.com/api.php?__call=search.getResults&_format=json&n={limit}&p=1&_marker=0&ctx=android&q={query}"
                async with session.get(url_search) as response:
                    if response.status == 200:
                        data = await response.json(content_type=None)
                        results_list = data.get('results', []) if isinstance(data, dict) else []
                        if results_list:
                            tracks = []
                            for item in results_list[:limit]:
                                if not item:
                                    continue
                                artist_str = item.get('primary_artists') or item.get('singers') or 'Unknown Artist'
                                album_name = item.get('album') or 'JioSaavn'
                                year_str = str(item.get('year') or '')[:4]
                                thumb_img = item.get('image', '')
                                if isinstance(thumb_img, str) and thumb_img:
                                    thumb = thumb_img.replace('50x50', '500x500').replace('150x150', '500x500')
                                else:
                                    thumb = None

                                track = {
                                    'id': item.get('id'),
                                    'title': item.get('song') or item.get('title') or 'Unknown Track',
                                    'artist': artist_str,
                                    'album': album_name,
                                    'year': year_str if year_str else 'Unknown',
                                    'duration': int(item.get('duration', 0)),
                                    'thumbnail': thumb,
                                    'provider': 'saavn'
                                }
                                tracks.append(track)
                            if tracks:
                                return tracks

        except Exception as e:
            logger.error(f"Saavn search error: {e}")
            return None

    async def search_all(self, query, provider=DEFAULT_SEARCH_PROVIDER, limit=10):
        """Search across all available providers with in-memory caching and resilient fallback"""
        cache_key = f"{provider}:{limit}:{query.lower().strip()}"
        now = time.time()
        if cache_key in self._search_cache:
            ts, cached_res = self._search_cache[cache_key]
            if now - ts < self._cache_ttl:
                return cached_res

        results = None
        if provider == "spotify":
            results = await self.search_spotify(query, limit)
        elif provider == "youtube":
            results = await self.search_youtube(query, limit)
        elif provider == "saavn" or provider == "jiosaavn":
            results = await self.search_saavn(query, limit)

        # If primary provider yielded no results, try all available providers
        if not results:
            for prov in ["spotify", "saavn", "youtube"]:
                if prov == provider:
                    continue
                if prov == "spotify":
                    results = await self.search_spotify(query, limit)
                elif prov == "saavn":
                    results = await self.search_saavn(query, limit)
                elif prov == "youtube":
                    results = await self.search_youtube(query, limit)

                if results:
                    break

        if results:
            if len(self._search_cache) > 500:
                self._search_cache.clear()
            self._search_cache[cache_key] = (now, results)

        return results

    def create_search_results_keyboard(self, tracks, page=0, results_per_page=10):
        """Create inline keyboard for search results with pagination"""
        keyboard = []

        # Calculate start and end indices for current page
        start_idx = page * results_per_page
        end_idx = min(start_idx + results_per_page, len(tracks))

        # Add track buttons
        for i in range(start_idx, end_idx):
            track = tracks[i]
            btn_text = f"{i+1}. {track['title']} - {track['artist']}"
            # Truncate if too long
            if len(btn_text) > 35:
                btn_text = btn_text[:32] + "..."

            # include webpage_url if present
            track_id = track['id']
            if track.get('webpage_url'):
                # For youtube entries the id may not be a full url; keep provider to indicate how to download
                pass

            keyboard.append([
                InlineKeyboardButton(
                    btn_text,
                    callback_data=f"download_{track['provider']}_{track_id}"
                )
            ])

        # Add pagination buttons if needed
        pagination_buttons = []
        if page > 0:
            pagination_buttons.append(
                InlineKeyboardButton("⬅️ Previous", callback_data=f"search_page_{page-1}")
            )

        if end_idx < len(tracks):
            pagination_buttons.append(
                InlineKeyboardButton("Next ➡️", callback_data=f"search_page_{page+1}")
            )

        if pagination_buttons:
            keyboard.append(pagination_buttons)

        # Add cancel button
        keyboard.append([
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_search")
        ])

        return InlineKeyboardMarkup(keyboard)
