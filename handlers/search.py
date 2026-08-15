import json
import re
import time
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

logger = logging.getLogger(__name__)

class SearchHandler:
    def __init__(self):
        self._use_anonymous_token = False
        self._anon_token = None
        self._anon_token_expiry = 0
        self.spotify = None

        # Initialize Spotify client
        if Config.SPOTIFY_CLIENT_ID and Config.SPOTIFY_CLIENT_SECRET:
            try:
                auth_manager = SpotifyClientCredentials(
                    client_id=Config.SPOTIFY_CLIENT_ID,
                    client_secret=Config.SPOTIFY_CLIENT_SECRET
                )
                self.spotify = spotipy.Spotify(auth_manager=auth_manager)
                logger.info("Spotify client initialized successfully with API credentials")
            except Exception as e:
                logger.error(f"Failed to initialize Spotify client with API credentials: {e}")
                self._use_anonymous_token = True
        else:
            self._use_anonymous_token = True
            logger.info("Spotify credentials not configured. Using automatic anonymous web token mode.")

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
        if self.spotify and not self._use_anonymous_token:
            return self.spotify

        # Check token freshness
        now = time.time()
        if not self._anon_token or now >= (self._anon_token_expiry - 60):
            self.fetch_anonymous_spotify_token()

        if self._anon_token:
            return spotipy.Spotify(auth=self._anon_token)
        return None

    async def search_spotify(self, query, limit=10):
        """Search Spotify for tracks with fallback handling"""
        sp_client = self.get_spotify_client()
        if sp_client:
            try:
                loop = asyncio.get_event_loop()
                results = await loop.run_in_executor(None, lambda: sp_client.search(q=query, type='track', limit=limit))
                tracks = []

                if results and 'tracks' in results and 'items' in results['tracks']:
                    for item in results['tracks']['items']:
                        track = {
                            'id': item['id'],
                            'title': item['name'],
                            'artist': ', '.join([artist['name'] for artist in item['artists']]),
                            'album': item['album']['name'],
                            'year': item['album']['release_date'][:4] if item['album']['release_date'] else 'Unknown',
                            'duration': item['duration_ms'] // 1000,
                            'thumbnail': item['album']['images'][0]['url'] if item['album']['images'] else None,
                            'provider': 'spotify'
                        }
                        tracks.append(track)
                    if tracks:
                        return tracks
            except Exception as e:
                logger.error(f"Spotify search error: {e}")
                # If using anonymous token and failed, try refreshing token once
                if self._use_anonymous_token:
                    logger.info("Refreshing anonymous Spotify token and retrying search...")
                    self.fetch_anonymous_spotify_token()
                    sp_client = self.get_spotify_client()
                    if sp_client:
                        try:
                            results = await loop.run_in_executor(None, lambda: sp_client.search(q=query, type='track', limit=limit))
                            if results and 'tracks' in results and 'items' in results['tracks']:
                                tracks = []
                                for item in results['tracks']['items']:
                                    tracks.append({
                                        'id': item['id'],
                                        'title': item['name'],
                                        'artist': ', '.join([artist['name'] for artist in item['artists']]),
                                        'album': item['album']['name'],
                                        'year': item['album']['release_date'][:4] if item['album']['release_date'] else 'Unknown',
                                        'duration': item['duration_ms'] // 1000,
                                        'thumbnail': item['album']['images'][0]['url'] if item['album']['images'] else None,
                                        'provider': 'spotify'
                                    })
                                if tracks:
                                    return tracks
                        except Exception as retry_e:
                            logger.error(f"Spotify retry search error: {retry_e}")

        # Fallback to JioSaavn or YouTube search if Spotify search returned nothing
        logger.info("Falling back from Spotify search to JioSaavn/YouTube search")
        saavn_res = await self.search_saavn(query, limit)
        if saavn_res:
            return saavn_res
        return await self.search_youtube(query, limit)

    async def search_youtube(self, query, limit=10):
        """Search YouTube for tracks using yt-dlp (ytsearch)"""
        try:
            ydl_opts = get_ytdlp_options({
                'quiet': True,
                'skip_download': True,
                'noplaylist': True,
            })
            info = None
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
            except Exception as err:
                logger.warning(f"Primary YouTube search failed: {err}. Retrying with fallback player clients...")
                fallback_opts = get_ytdlp_options(
                    extra_opts={'quiet': True, 'skip_download': True, 'noplaylist': True},
                    player_clients=['mweb', 'android', 'ios', 'web']
                )
                with yt_dlp.YoutubeDL(fallback_opts) as ydl:
                    info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)

            entries = info.get('entries', []) if info else []
            tracks = []
            for e in entries[:limit]:
                if not e:
                    continue
                tracks.append({
                    'id': e.get('id'),
                    'title': e.get('title'),
                    'artist': e.get('uploader') or e.get('uploader_url') or 'Unknown',
                    'album': 'YouTube',
                    'year': str(e.get('upload_date', '')[:4]) if e.get('upload_date') else 'Unknown',
                    'duration': e.get('duration', 0),
                    'thumbnail': e.get('thumbnail'),
                    'provider': 'youtube',
                    'webpage_url': e.get('webpage_url')
                })
            return tracks
        except Exception as e:
            logger.error(f"YouTube search error: {e}")
            return None

    async def search_saavn(self, query, limit=10):
        """Search JioSaavn for tracks"""
        try:
            # Saavn API endpoint
            url = f"https://www.jiosaavn.com/api.php?__call=autocomplete.get&query={query}&_format=json&_marker=0"

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    data = await response.json()

                    tracks = []
                    for item in data.get('songs', {}).get('data', [])[:limit]:
                        track = {
                            'id': item.get('id'),
                            'title': item.get('title', 'Unknown'),
                            'artist': ', '.join([artist.get('name', 'Unknown') for artist in item.get('primary_artists', [])]),
                            'album': item.get('album', {}).get('title', 'Unknown'),
                            'year': 'Unknown',  # Saavn doesn't provide year in search results
                            'duration': int(item.get('duration', 0)),
                            'thumbnail': item.get('image', '').replace('50x50', '500x500') if item.get('image') else None,
                            'provider': 'saavn'
                        }
                        tracks.append(track)

                    return tracks
        except Exception as e:
            logger.error(f"Saavn search error: {e}")
            return None

    async def search_all(self, query, provider=DEFAULT_SEARCH_PROVIDER, limit=10):
        """Search across all available providers"""
        if provider == "spotify":
            return await self.search_spotify(query, limit)
        elif provider == "youtube":
            return await self.search_youtube(query, limit)
        elif provider == "saavn":
            return await self.search_saavn(query, limit)
        else:
            # Try all providers in order
            for prov in SEARCH_PROVIDERS:
                if prov == "spotify":
                    results = await self.search_spotify(query, limit)
                elif prov == "youtube":
                    results = await self.search_youtube(query, limit)
                elif prov == "saavn":
                    results = await self.search_saavn(query, limit)
                else:
                    results = None

                if results:
                    return results

            return None

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
