import os
import aiohttp
import asyncio
import yt_dlp
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from config import Config
from utils.db import db
from utils.audio import AudioProcessor
from utils.logger import BotLogger
from utils.ytdlp_utils import get_ytdlp_options
from handlers.search import SearchHandler
import logging
import re
from spotipy.exceptions import SpotifyException
import traceback
import json
import urllib.request

logger = logging.getLogger(__name__)

class DownloadHandler:
    def __init__(self, bot, logger: BotLogger, search_handler: SearchHandler):
        self.bot = bot
        self.logger = logger
        self.search_handler = search_handler
        self.audio_processor = AudioProcessor()
        self.ydl_opts = get_ytdlp_options({'outtmpl': 'temp/%(id)s.%(ext)s'})

        # Ensure directories exist
        os.makedirs("temp", exist_ok=True)
        os.makedirs("data/thumbnails", exist_ok=True)

    async def safe_edit_message(self, message, text, **kwargs):
        """Safely edit a message, handling potential deletion or invalid states"""
        try:
            if message and hasattr(message, 'edit_text'):
                return await message.edit_text(text, **kwargs)
            return None
        except Exception as e:
            logger.warning(f"Could not edit message: {e}")
            # If we can't edit, try to send a new message
            try:
                return await self.bot.send_message(
                    chat_id=message.chat.id,
                    text=text,
                    **kwargs
                )
            except Exception as send_e:
                logger.error(f"Could not send new message either: {send_e}")
                return None

    async def fetch_spotify_track_info_via_web(self, track_id):
        """Fallback to fetch track details using Spotify embed HTML or oEmbed API"""
        try:
            embed_url = f"https://open.spotify.com/embed/track/{track_id}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(embed_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html)
                        if m:
                            data = json.loads(m.group(1))
                            entity = data.get('props', {}).get('pageProps', {}).get('state', {}).get('data', {}).get('entity', {})
                            if entity:
                                title = entity.get('name') or entity.get('title')
                                artists = [a.get('name') for a in entity.get('artists', []) if isinstance(a, dict) and a.get('name')]
                                artist_str = ", ".join(artists) if artists else "Unknown Artist"
                                images = entity.get('visualIdentity', {}).get('image', [])
                                thumb = images[0].get('url') if images else None
                                rel_date = entity.get('releaseDate', {}).get('isoString', '')
                                return {
                                    "id": track_id,
                                    "title": title or "Unknown Title",
                                    "artist": artist_str,
                                    "album": "Spotify",
                                    "year": rel_date[:4] if rel_date else "",
                                    "duration": int(entity.get('duration', 0)) // 1000,
                                    "thumbnail": thumb,
                                    "provider": "spotify"
                                }

            oembed_url = f"https://open.spotify.com/oembed?url=https://open.spotify.com/track/{track_id}"
            async with aiohttp.ClientSession() as session:
                async with session.get(oembed_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return {
                            "id": track_id,
                            "title": data.get("title", "Unknown Track"),
                            "artist": "Spotify",
                            "album": "Spotify",
                            "year": "",
                            "duration": 0,
                            "thumbnail": data.get("thumbnail_url"),
                            "provider": "spotify"
                        }
        except Exception as e:
            logger.error(f"Failed web fallback for Spotify track {track_id}: {e}")
        return None

    async def get_track_info(self, provider, track_id):
        """Get track metadata from provider"""
        try:
            if provider in ["spotify", "sp"]:
                sp_client = self.search_handler.get_spotify_client()
                if sp_client:
                    try:
                        loop = asyncio.get_event_loop()
                        track = await loop.run_in_executor(None, lambda: sp_client.track(track_id))
                        return {
                            "id": track["id"],
                            "title": track["name"],
                            "artist": ", ".join([artist["name"] for artist in track["artists"]]),
                            "album": track["album"]["name"],
                            "year": track["album"]["release_date"][:4] if track["album"].get("release_date") else "",
                            "duration": track["duration_ms"] // 1000,
                            "thumbnail": track["album"]["images"][0]["url"] if track["album"].get("images") else None,
                            "provider": "spotify"
                        }
                    except Exception as e:
                        logger.error(f"Error fetching spotify track via spotipy client: {e}")

                # Fallback to web scraping / oembed
                return await self.fetch_spotify_track_info_via_web(track_id)
            
            elif provider in ["youtube", "yt"]:
                url = track_id if "http" in track_id else f"https://www.youtube.com/watch?v={track_id}"
                
                def _get_yt_info():
                    opts = get_ytdlp_options({'quiet': True, 'skip_download': True})
                    try:
                        with yt_dlp.YoutubeDL(opts) as ydl:
                            return ydl.extract_info(url, download=False)
                    except Exception as err:
                        logger.warning(f"Primary yt-dlp info extraction failed: {err}. Retrying with fallback player clients...")
                        opts_fb = get_ytdlp_options({'quiet': True, 'skip_download': True}, player_clients=['mweb', 'android', 'ios', 'web'])
                        with yt_dlp.YoutubeDL(opts_fb) as ydl:
                            return ydl.extract_info(url, download=False)

                loop = asyncio.get_event_loop()
                info = await loop.run_in_executor(None, _get_yt_info)
                
                return {
                    "id": info.get("id"),
                    "title": info.get("title"),
                    "artist": info.get("uploader", "Unknown"),
                    "album": "YouTube",
                    "year": str(info.get("upload_date", ""))[:4],
                    "duration": info.get("duration", 0),
                    "thumbnail": info.get("thumbnail"),
                    "provider": "youtube",
                    "webpage_url": info.get("webpage_url", url)
                }
            
            return None
        except Exception as e:
            logger.error(f"Error in get_track_info: {e}")
            return None

    async def download_audio(self, provider, track_info):
        """Download audio from YouTube (searching if necessary)"""
        try:
            download_url = None
            
            if provider in ["youtube", "yt"]:
                download_url = track_info.get("webpage_url")
            else:
                query = f"{track_info['title']} - {track_info['artist']} audio"
                def _search_yt():
                    opts = get_ytdlp_options({'quiet': True, 'skip_download': True, 'noplaylist': True, 'default_search': 'ytsearch1'})
                    try:
                        with yt_dlp.YoutubeDL(opts) as ydl:
                            info = ydl.extract_info(query, download=False)
                            if info and 'entries' in info and info['entries']:
                                return info['entries'][0]['webpage_url']
                            return None
                    except Exception as err:
                        logger.warning(f"Primary yt-dlp search failed: {err}. Retrying with fallback player clients...")
                        opts_fb = get_ytdlp_options({'quiet': True, 'skip_download': True, 'noplaylist': True, 'default_search': 'ytsearch1'}, player_clients=['mweb', 'android', 'ios', 'web'])
                        with yt_dlp.YoutubeDL(opts_fb) as ydl:
                            info = ydl.extract_info(query, download=False)
                            if info and 'entries' in info and info['entries']:
                                return info['entries'][0]['webpage_url']
                            return None
                
                loop = asyncio.get_event_loop()
                download_url = await loop.run_in_executor(None, _search_yt)
            
            if not download_url:
                return None
            
            def _download():
                # Refresh ydl_opts to include any newly placed cookies.txt
                current_opts = get_ytdlp_options({'outtmpl': 'temp/%(id)s.%(ext)s'})
                try:
                    with yt_dlp.YoutubeDL(current_opts) as ydl:
                        info = ydl.extract_info(download_url, download=True)
                        return ydl.prepare_filename(info)
                except Exception as err:
                    logger.warning(f"Primary yt-dlp download failed: {err}. Retrying with fallback player clients...")
                    fallback_opts = get_ytdlp_options(
                        extra_opts={'outtmpl': 'temp/%(id)s.%(ext)s'},
                        player_clients=['mweb', 'android', 'ios', 'web']
                    )
                    with yt_dlp.YoutubeDL(fallback_opts) as ydl:
                        info = ydl.extract_info(download_url, download=True)
                        return ydl.prepare_filename(info)
            
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _download)
        except Exception as e:
            logger.error(f"Error in download_audio: {e}")
            return None

    async def download_track(self, provider, track_id, user_id, message):
        """Download a track from the specified provider - returns success status"""
        user = db.get_user(user_id)

        # Check if user can download
        can_download, reason = db.can_download(user_id)
        if not can_download:
            await self.safe_edit_message(
                message,
                f"❌ {reason}\n\n"
                f"You've used {user.get('downloads_today', 0)}/{Config.FREE_USER_DAILY_LIMIT} downloads today."
            )
            return False

        # Get track info based on provider
        track_info = await self.get_track_info(provider, track_id)
        if not track_info:
            await self.safe_edit_message(message, "❌ Could not retrieve track information.")
            return False

        # Download the audio
        await self.safe_edit_message(message, f"⬇️ Downloading **{track_info['title']}**...")
        audio_path = await self.download_audio(provider, track_info)

        if not audio_path:
            await self.safe_edit_message(message, "❌ Failed to download audio.")
            return False

        # Process the audio
        await self.safe_edit_message(message, f"🔄 Processing **{track_info['title']}**...")

        # Get user preferences
        preferred_format = user.get("preferred_format", "mp3")
        preferred_quality = user.get("preferred_quality", 320)

        # Convert if needed
        try:
            if not audio_path.endswith(f".{preferred_format}"):
                base, _ = os.path.splitext(audio_path)
                converted_path = f"{base}.{preferred_format}"
                success = self.audio_processor.convert_audio(audio_path, converted_path, preferred_format, preferred_quality)

                if success:
                    try:
                        os.remove(audio_path)
                    except Exception:
                        pass
                    audio_path = converted_path
                else:
                    logger.error(f"Audio conversion failed for {audio_path}")
                    await self.safe_edit_message(message, "❌ Failed to process audio.")
                    return False
        except Exception as e:
            logger.error(f"Error during conversion: {e}")
            await self.safe_edit_message(message, "❌ Error during audio conversion.")
            return False

        # Add metadata and thumbnail
        thumbnail_path = None
        if track_info.get("thumbnail"):
            try:
                thumbnail_path = f"data/thumbnails/{track_info['id']}.jpg"
                async with aiohttp.ClientSession() as session:
                    async with session.get(track_info["thumbnail"]) as resp:
                        if resp.status == 200:
                            content = await resp.read()
                            with open(thumbnail_path, "wb") as f:
                                f.write(content)
                        else:
                            thumbnail_path = None
            except Exception as e:
                logger.warning(f"Could not download thumbnail: {e}")
                thumbnail_path = None

        if not thumbnail_path:
            thumbnail_path = self.audio_processor.generate_thumbnail(track_info.get("title", ""), track_info.get("artist", ""))

        # Add metadata (sync)
        try:
            self.audio_processor.add_metadata(audio_path, {
                "title": track_info.get("title"),
                "artist": track_info.get("artist"),
                "album": track_info.get("album", "Unknown Album"),
                "year": track_info.get("year", ""),
                "genre": track_info.get("genre", "Music")
            }, thumbnail_url=track_info.get("thumbnail"))
        except Exception as e:
            logger.warning(f"Failed to add metadata: {e}")

        # Send audio file
        await self.safe_edit_message(message, f"📤 Uploading **{track_info['title']}**...")

        try:
            caption = (
                f"🎵 **{track_info['title']}**\n\n"
                f"👤 **{track_info['artist']}**\n\n"
                f"💿 **Album:** {track_info.get('album', 'Unknown')}\n\n"
                f"📅 **Year:** {track_info.get('year', 'Unknown')}\n\n"
                f"🎛️ **Format:** {preferred_format.upper()} {preferred_quality} kbps"
            )

            await self.bot.send_audio(
                chat_id=user_id,
                audio=audio_path,
                caption=caption,
                thumb=thumbnail_path,
                title=track_info["title"],
                performer=track_info["artist"],
                duration=track_info.get("duration", 0)
            )

            # Record download
            track_info["timestamp"] = message.date
            track_info["format"] = preferred_format
            track_info["quality"] = preferred_quality
            
            # Edit the status/progress message to success
            sent = await self.safe_edit_message(message, f"✅ Successfully downloaded **{track_info['title']}**!")

            # Record the download in DB (best-effort; does not block UI)
            try:
                db.record_download(user_id, track_info)
                # Log download
                await self.logger.log_download(user_id, track_info, f"{preferred_format} {preferred_quality}")
            except Exception as e:
                logger.warning(f"Failed to record download in DB for user {user_id}: {e}")

            # Schedule deletion after 5 minutes without blocking the handler
            if sent:
                async def _delete_later(msg):
                    try:
                        await asyncio.sleep(300)  # 5 minutes instead of 10
                        await msg.delete()
                    except Exception:
                        # ignore errors (already deleted, permissions, etc.)
                        pass

                # create a background task on the running event loop
                try:
                    asyncio.create_task(_delete_later(sent))
                except RuntimeError:
                    # If event loop isn't running, just ignore scheduling
                    pass

            return True

        except Exception as e:
            logger.error(f"Failed to send audio: {e}\n{traceback.format_exc()}")
            await self.safe_edit_message(message, "❌ Failed to send audio.")
            return False

        finally:
            # Clean up files
            try:
                if os.path.exists(audio_path):
                    os.remove(audio_path)
                if thumbnail_path and os.path.exists(thumbnail_path):
                    os.remove(thumbnail_path)
            except Exception as e:
                logger.error(f"Failed to clean up files: {e}")

    def extract_spotify_id(self, url_or_id):
        """Extract Spotify ID from various URL formats"""
        if not isinstance(url_or_id, str):
            return None
            
        # If it's already a simple ID
        if re.match(r'^[A-Za-z0-9]{22}$', url_or_id):
            return url_or_id
            
        # Try to extract from URL
        patterns = [
            r'spotify\.com/(?:track|album|playlist|artist)/([A-Za-z0-9]{22})',
            r'spotify\.com/(?:track|album|playlist|artist)/([A-Za-z0-9]+)',
            r'([A-Za-z0-9]{22})$'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url_or_id)
            if match:
                return match.group(1)
                
        return None

    def determine_spotify_content_type(self, url):
        """Determine if URL is track, album, playlist, or artist"""
        if "/track/" in url:
            return "track"
        elif "/album/" in url:
            return "album"
        elif "/playlist/" in url:
            return "playlist"
        elif "/artist/" in url:
            return "artist"
        return "track"  # Default to track

    async def handle_download_callback(self, client, callback_query: CallbackQuery):
        """Handle download callback queries"""
        data = callback_query.data
        user_id = callback_query.from_user.id

        if data.startswith("download_"):
            parts = data.split("_", 2)
            if len(parts) < 3:
                try:
                    await callback_query.answer("Invalid download request")
                except Exception as e:
                    logger.warning(f"Could not answer callback query: {e}")
                return

            provider = parts[1]
            track_id = parts[2]
            
            try:
                # Answer callback query first
                await callback_query.answer("Processing your request...")
                
                # Send new message instead of editing callback message
                message = await self.bot.send_message(
                    chat_id=user_id,
                    text="🔄 Processing your request..."
                )
                await self.download_track(provider, track_id, user_id, message)
                
            except Exception as e:
                logger.error(f"Error in handle_download_callback: {e}\n{traceback.format_exc()}")
                try:
                    await callback_query.message.reply_text("❌ Failed to process your request. Please try again.")
                except:
                    pass

    # === New methods for album/playlist support ===
    async def download_album(self, provider, album_id_or_url, user_id, message):
        """Download multiple tracks from an album/playlist. Returns True if at least one track downloaded."""
        try:
            track_items = []

            if provider == "spotify" or provider == 'sp':
                # Determine id and kind
                if str(album_id_or_url).startswith("http"):
                    if "/album/" in album_id_or_url:
                        album_id = album_id_or_url.split("/album/")[1].split("?")[0].split("/")[0]
                        kind = "album"
                    elif "/playlist/" in album_id_or_url:
                        album_id = album_id_or_url.split("/playlist/")[1].split("?")[0].split("/")[0]
                        kind = "playlist"
                    elif "/artist/" in album_id_or_url:
                        album_id = album_id_or_url.split("/artist/")[1].split("?")[0].split("/")[0]
                        kind = "artist"
                    else:
                        # default to album if unknown
                        album_id = album_id_or_url
                        kind = "album"
                else:
                    album_id = album_id_or_url
                    kind = "album"

                # Fetch track ids using spotipy (blocking in executor)
                def _extract_spotify_id(maybe_id_or_url: str):
                    """
                    Try to normalize a spotify id or full URL to a plain id string.
                    Returns (id, kind_hint) where kind_hint may be 'album'/'playlist'/'artist' or None.
                    """
                    if not isinstance(maybe_id_or_url, str):
                        return None, None
                    # if it's already a bare id (22+ chars), return it
                    simple = maybe_id_or_url.strip()
                    if re.fullmatch(r"[A-Za-z0-9]{10,}", simple):
                        return simple, None

                    # parse common open.spotify.com URL forms
                    m = re.search(r"open\.spotify\.com/(album|playlist|artist|track)/([A-Za-z0-9]+)", simple)
                    if m:
                        return m.group(2), m.group(1)

                    # sometimes URLs include /?si=... or other query params - strip them
                    if "/" in simple:
                        parts = simple.split("/")
                        possible = parts[-1].split("?")[0]
                        if re.fullmatch(r"[A-Za-z0-9]{10,}", possible):
                            return possible, None

                    return None, None

                def fetch_spotify_ids():
                    ids = []
                    try:
                        # normalize incoming identifier
                        album_id_raw = album_id  # from outer scope
                        normalized_id, kind_hint = _extract_spotify_id(album_id_raw)
                        if not normalized_id:
                            logger.error("Could not parse Spotify id from: %s", album_id_raw)
                            return ids

                        # choose kind using our earlier 'kind' if set, else hint from parse
                        effective_kind = kind if 'kind' in locals() and kind else kind_hint or "album"

                        sp_client = self.search_handler.get_spotify_client()
                        if sp_client:
                            if effective_kind == "album":
                                try:
                                    page = sp_client.album_tracks(normalized_id, limit=50, offset=0)
                                    items = page.get("items", []) if isinstance(page, dict) else []
                                    for it in items:
                                        track_obj = it.get("track", it) if isinstance(it, dict) else it
                                        tid = track_obj.get("id") if isinstance(track_obj, dict) else getattr(track_obj, "id", None)
                                        if tid:
                                            ids.append(tid)
                                    # pagination
                                    while page.get("next"):
                                        try:
                                            page = sp_client.next(page)
                                            items = page.get("items", [])
                                            for it in items:
                                                track_obj = it.get("track", it) if isinstance(it, dict) else it
                                                tid = track_obj.get("id") if isinstance(track_obj, dict) else getattr(track_obj, "id", None)
                                                if tid:
                                                    ids.append(tid)
                                        except SpotifyException as e:
                                            logger.warning("Spotify paging stopped for album %s: %s", normalized_id, e)
                                            break
                                except SpotifyException as e:
                                    logger.error("Spotify album fetch error for id %s: %s", normalized_id, e)

                            elif effective_kind == "playlist":
                                try:
                                    page = sp_client.playlist_items(normalized_id, limit=100, offset=0)
                                    items = page.get("items", []) if isinstance(page, dict) else []
                                    for it in items:
                                        track_obj = it.get("track", it) if isinstance(it, dict) else it
                                        tid = track_obj.get("id") if isinstance(track_obj, dict) else getattr(track_obj, "id", None)
                                        if tid:
                                            ids.append(tid)
                                    while page.get("next"):
                                        try:
                                            page = sp_client.next(page)
                                            items = page.get("items", [])
                                            for it in items:
                                                track_obj = it.get("track", it) if isinstance(it, dict) else it
                                                tid = track_obj.get("id") if isinstance(track_obj, dict) else getattr(track_obj, "id", None)
                                                if tid:
                                                    ids.append(tid)
                                        except SpotifyException as e:
                                            logger.warning("Spotify paging stopped for playlist %s: %s", normalized_id, e)
                                            break
                                except SpotifyException as e:
                                    logger.error("Spotify playlist fetch error for id %s: %s", normalized_id, e)

                            elif effective_kind == "artist":
                                try:
                                    top = sp_client.artist_top_tracks(normalized_id, country='US')
                                    items = top.get("tracks", []) if isinstance(top, dict) else []
                                    for tr in items:
                                        tid = tr.get("id") if isinstance(tr, dict) else getattr(tr, "id", None)
                                        if tid:
                                            ids.append(tid)
                                except SpotifyException as e:
                                    logger.error("Spotify artist top tracks error for id %s: %s", normalized_id, e)

                        # Embed scraping fallback if spotipy returned no tracks
                        if not ids:
                            try:
                                embed_url = f"https://open.spotify.com/embed/{effective_kind}/{normalized_id}"
                                headers = {
                                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                                }
                                req = urllib.request.Request(embed_url, headers=headers)
                                with urllib.request.urlopen(req, timeout=10) as resp:
                                    html = resp.read().decode('utf-8')
                                    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html)
                                    if m:
                                        data = json.loads(m.group(1))
                                        entity = data.get('props', {}).get('pageProps', {}).get('state', {}).get('data', {}).get('entity', {})
                                        track_list = entity.get('trackList', [])
                                        for t in track_list:
                                            tid = t.get('id') or (t.get('uri', '').split(':')[-1] if 'uri' in t else None)
                                            if tid:
                                                ids.append(tid)
                            except Exception as embed_e:
                                logger.error("Embed fallback failed for %s %s: %s", effective_kind, normalized_id, embed_e)

                    except Exception as e:
                        logger.error("Spotify paging/error fetching ids: %s", e)
                    return ids


                loop = asyncio.get_event_loop()
                track_ids = await loop.run_in_executor(None, fetch_spotify_ids)
                track_items = [("spotify", tid) for tid in track_ids if tid]

            elif provider == "youtube" or provider == 'yt':
                entries = await self._youtube_get_playlist_entries(album_id_or_url)
                if not entries:
                    await message.edit_text("❌ Could not extract YouTube playlist entries.")
                    return False
                track_items = [("youtube", e.get('webpage_url') or e.get('id')) for e in entries]

            else:
                await message.edit_text("❌ Multi-track downloads are not supported for this provider yet.")
                return False

            total = len(track_items)
            if total == 0:
                await message.edit_text("❌ No tracks found in the album/playlist.")
                return False

            success_count = 0
            fail_count = 0

            progress = await message.edit_text(f"⬇️ Preparing to download {total} tracks from album/playlist...\nProgress: 0/{total}")

            for idx, (prov, tid) in enumerate(track_items, start=1):
                await progress.edit_text(f"⬇️ Downloading {idx}/{total}...\nTrack: {tid}")
                try:
                    single_success = await self.download_track(prov, tid, user_id, progress)
                    if single_success:
                        success_count += 1
                    else:
                        fail_count += 1
                except Exception as e:
                    logger.error(f"Failed downloading track {tid}: {e}")
                    fail_count += 1

                await asyncio.sleep(1)
                await progress.edit_text(f"⬇️ Downloading {idx}/{total}...\nSuccessful: {success_count}  Failed: {fail_count}")

            await progress.edit_text(f"✅ Album/playlist download finished.\nSuccessful: {success_count}\nFailed: {fail_count}")
            return success_count > 0

        except Exception as e:
            logger.error(f"Unexpected error in download_album: {e}")
            await message.edit_text(f"❌ Unexpected error: {e}")
            return False

    async def _youtube_get_playlist_entries(self, playlist_url, max_items=200):
        """Return list of entries for a YouTube playlist using yt-dlp (sync call wrapped)"""
        try:
            ydl_opts = {'quiet': True, 'skip_download': True, 'extract_flat': True}
            def extract():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(playlist_url, download=False)
                    entries = info.get('entries', []) if info else []
                    return entries
            loop = asyncio.get_event_loop()
            entries = await loop.run_in_executor(None, extract)
            return entries[:max_items] if entries else []
        except Exception as e:
            logger.error(f"yt-dlp playlist extraction error: {e}")
            return []
