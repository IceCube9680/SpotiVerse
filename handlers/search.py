import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import aiohttp
import asyncio
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from config import Config
from info import SEARCH_PROVIDERS, DEFAULT_SEARCH_PROVIDER
import logging
import yt_dlp

logger = logging.getLogger(__name__)

class SearchHandler:
    def __init__(self):
        # Initialize Spotify client
        if Config.SPOTIFY_CLIENT_ID and Config.SPOTIFY_CLIENT_SECRET:
            try:
                auth_manager = SpotifyClientCredentials(
                    client_id=Config.SPOTIFY_CLIENT_ID,
                    client_secret=Config.SPOTIFY_CLIENT_SECRET
                )
                self.spotify = spotipy.Spotify(auth_manager=auth_manager)
                logger.info("Spotify client initialized successfully")
            except Exception as e:
                self.spotify = None
                logger.error(f"Failed to initialize Spotify client: {e}")
        else:
            self.spotify = None
            logger.warning("Spotify credentials not configured")

    async def search_spotify(self, query, limit=10):
        """Search Spotify for tracks"""
        if not self.spotify:
            return None

        try:
            results = self.spotify.search(q=query, type='track', limit=limit)
            tracks = []

            for item in results['tracks']['items']:
                track = {
                    'id': item['id'],
                    'title': item['name'],
                    'artist': ', '.join([artist['name'] for artist in item['artists']]),
                    'album': item['album']['name'],
                    'year': item['album']['release_date'][:4] if item['album']['release_date'] else 'Unknown',
                    'duration': item['duration_ms'] // 1000,  # Convert to seconds
                    'thumbnail': item['album']['images'][0]['url'] if item['album']['images'] else None,
                    'provider': 'spotify'
                }
                tracks.append(track)

            return tracks
        except Exception as e:
            logger.error(f"Spotify search error: {e}")
            return None

    async def search_youtube(self, query, limit=10):
        """Search YouTube for tracks using yt-dlp (ytsearch)"""
        try:
            ydl_opts = {
                'format': 'bestaudio/best',
                'quiet': True,
                'skip_download': True,
                'noplaylist': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
                entries = info.get('entries', []) if info else []
                tracks = []
                for e in entries[:limit]:
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
