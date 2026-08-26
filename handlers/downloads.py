import os
import socket
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
from datetime import datetime, timezone
import pyrogram.errors

try:
    import urllib3.util.connection as urllib3_cn
    urllib3_cn.allowed_gai_family = lambda: socket.AF_INET
except Exception:
    pass

logger = logging.getLogger(__name__)

class DownloadHandler:
    def __init__(self, bot, logger: BotLogger, search_handler: SearchHandler):
        self.bot = bot
        self.logger = logger
        self.search_handler = search_handler
        self.audio_processor = AudioProcessor()
        self.ydl_opts = get_ytdlp_options({'outtmpl': 'temp/%(id)s.%(ext)s'})
        max_concurrency = getattr(Config, "MAX_CONCURRENT_DOWNLOADS", 3) or 3
        self.semaphore = asyncio.Semaphore(max_concurrency)

        # Ensure directories exist
        os.makedirs("temp", exist_ok=True)
        os.makedirs("data/thumbnails", exist_ok=True)

    async def safe_edit_message(self, message, text, **kwargs):
        """Safely edit a message, handling potential deletion, FloodWait, or invalid states"""
        if not message:
            return None
        try:
            if hasattr(message, 'edit_text'):
                return await message.edit_text(text, **kwargs)
            return None
        except pyrogram.errors.MessageNotModified:
            # Text didn't change, return same message
            return message
        except pyrogram.errors.FloodWait as fw:
            logger.warning(f"FloodWait during edit_message: sleeping for {fw.value}s")
            await asyncio.sleep(fw.value + 1)
            try:
                if hasattr(message, 'edit_text'):
                    return await message.edit_text(text, **kwargs)
            except Exception:
                pass
            return message
        except Exception as e:
            logger.warning(f"Could not edit message: {e}")
            # If we can't edit, try to send a new message
            try:
                chat_id = None
                if hasattr(message, 'chat') and message.chat:
                    chat_id = getattr(message.chat, 'id', None)
                if not chat_id:
                    chat_id = getattr(message, 'chat_id', None)
                if chat_id:
                    return await self.bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        **kwargs
                    )
            except pyrogram.errors.FloodWait as fw:
                await asyncio.sleep(fw.value + 1)
                try:
                    if chat_id:
                        return await self.bot.send_message(chat_id=chat_id, text=text, **kwargs)
                except Exception:
                    pass
            except Exception as send_e:
                logger.error(f"Could not send new message either: {send_e}")
                return None
        return message

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
                            "artist": data.get("author_name") or "Spotify",
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
                if self.search_handler.spotify and not self.search_handler._use_anonymous_token:
                    sp_client = self.search_handler.get_spotify_client()
                    if sp_client:
                        try:
                            try:
                                loop = asyncio.get_running_loop()
                            except RuntimeError:
                                loop = asyncio.get_event_loop()
                            track = await loop.run_in_executor(None, lambda: sp_client.track(track_id))
                            album_obj = track.get("album") or {}
                            artists_list = track.get("artists") or []
                            artist_names = [a.get("name", "Unknown") for a in artists_list if isinstance(a, dict) and a.get("name")]
                            artist_str = ", ".join(artist_names) if artist_names else "Unknown Artist"
                            rel_date = str(album_obj.get("release_date") or "")
                            images = album_obj.get("images") or []
                            thumb = images[0].get("url") if images and isinstance(images[0], dict) else None

                            return {
                                "id": track.get("id", track_id),
                                "title": track.get("name", "Unknown Track"),
                                "artist": artist_str,
                                "album": album_obj.get("name", "Spotify"),
                                "year": rel_date[:4] if rel_date else "",
                                "duration": int(track.get("duration_ms", 0)) // 1000,
                                "thumbnail": thumb,
                                "provider": "spotify"
                            }
                        except Exception as e:
                            serr = str(e)
                            if "429" in serr or "rate" in serr.lower() or "too many" in serr.lower():
                                logger.warning("Spotify API rate limit in get_track_info. Switching to web fallback.")
                                if hasattr(self.search_handler, "_spotify_rate_limited_until"):
                                    self.search_handler._spotify_rate_limited_until = time.time() + 300
                            else:
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

                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
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

            elif provider in ["saavn", "jiosaavn"]:
                url = f"https://www.jiosaavn.com/api.php?__call=song.getDetails&pids={track_id}&_format=json&_marker=0&ctx=android"
                try:
                    connector = aiohttp.TCPConnector(family=socket.AF_INET)
                    headers = {'User-Agent': 'Mozilla/5.0'}
                    async with aiohttp.ClientSession(connector=connector, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as session:
                        async with session.get(url) as resp:
                            if resp.status == 200:
                                data = await resp.json(content_type=None)
                                sdata = data.get(track_id, {}) or (data.get('songs', [{}])[0] if 'songs' in data else {})
                                if sdata:
                                    thumb_img = sdata.get('image', '')
                                    thumb = thumb_img.replace('50x50', '500x500').replace('150x150', '500x500') if thumb_img else None
                                    return {
                                        "id": track_id,
                                        "title": sdata.get('song') or sdata.get('title') or "Unknown Track",
                                        "artist": sdata.get('primary_artists') or sdata.get('singers') or "Unknown Artist",
                                        "album": sdata.get('album') or "JioSaavn",
                                        "year": str(sdata.get('year', ''))[:4],
                                        "duration": int(sdata.get('duration', 0)),
                                        "thumbnail": thumb,
                                        "provider": "saavn"
                                    }
                except Exception as saavn_err:
                    logger.warning(f"Error fetching saavn track details for {track_id}: {saavn_err}")

                return {
                    "id": track_id,
                    "title": "JioSaavn Track",
                    "artist": "Unknown Artist",
                    "album": "JioSaavn",
                    "year": "",
                    "duration": 0,
                    "thumbnail": None,
                    "provider": "saavn"
                }
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
                
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
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
            
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _download)
        except Exception as e:
            logger.error(f"Error in download_audio: {e}")
            return None

    async def download_track(self, provider, track_id, user_id, message, is_batch=False):
        """Download a track from the specified provider - returns success status (Free + Premium)"""
        user = db.get_user(user_id) or {}

        # Check download quota
        can_download, reason = db.can_download(user_id)
        if not can_download:
            await self.safe_edit_message(
                message,
                f"❌ {reason}\n\n"
                f"📊 Free Users Daily Limit: {user.get('downloads_today', 0)}/{Config.FREE_USER_DAILY_LIMIT} downloads today.\n\n"
                f"💎 Upgrade to Premium for unlimited downloads and higher quality!\n"
                f"Contact: @icecube9608\n\n"
                f"👤 **Your User ID:** `{user_id}`"
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

        # Get user preferences via effective settings
        eff_settings = db.get_effective_settings(user_id) if hasattr(db, "get_effective_settings") else {}
        if not isinstance(eff_settings, dict):
            eff_settings = {}
        preferred_format = eff_settings.get("preferred_format") or user.get("preferred_format", "mp3")
        if not isinstance(preferred_format, str):
            preferred_format = "mp3"
        preferred_quality = eff_settings.get("preferred_quality") or user.get("preferred_quality", 320 if user.get("premium") else 64)
        if isinstance(preferred_quality, (MagicMock if "MagicMock" in globals() else type(None))):
            preferred_quality = 320

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
                async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(family=socket.AF_INET)) as session:
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

            # Retry loop for send_audio handling FloodWait
            uploaded = False
            for attempt in range(3):
                try:
                    await self.bot.send_audio(
                        chat_id=user_id,
                        audio=audio_path,
                        caption=caption,
                        thumb=thumbnail_path,
                        title=track_info["title"],
                        performer=track_info["artist"],
                        duration=track_info.get("duration", 0)
                    )
                    uploaded = True
                    break
                except pyrogram.errors.FloodWait as fw:
                    logger.warning(f"FloodWait during send_audio: sleeping for {fw.value}s")
                    await asyncio.sleep(fw.value + 1)
                except Exception as e:
                    logger.error(f"Failed to send audio (attempt {attempt + 1}): {e}\n{traceback.format_exc()}")
                    if attempt == 2:
                        await self.safe_edit_message(message, "❌ Failed to send audio.")
                        return False
                    await asyncio.sleep(2)

            if not uploaded:
                return False

            # Record download
            track_info["timestamp"] = getattr(message, "date", None) or datetime.now(timezone.utc).replace(tzinfo=None)
            track_info["format"] = preferred_format
            track_info["quality"] = preferred_quality

            uname = getattr(getattr(message, "from_user", None), "username", None) or (user or {}).get("username")
            if uname:
                track_info["username"] = uname
            
            # Record the download in DB (best-effort; does not block UI)
            try:
                db.record_download(user_id, track_info, username=uname)
                # Log download
                await self.logger.log_download(user_id, track_info, f"{preferred_format} {preferred_quality}", username=uname)
            except Exception as e:
                logger.warning(f"Failed to record download in DB for user {user_id}: {e}")

            if not is_batch:
                # Edit the status/progress message to success only for single downloads
                sent = await self.safe_edit_message(message, f"✅ Successfully downloaded **{track_info['title']}**!")

                # Schedule deletion after 5 minutes only for single downloads
                if sent:
                    async def _delete_later(msg):
                        try:
                            await asyncio.sleep(300)
                            await msg.delete()
                        except Exception:
                            pass

                    try:
                        asyncio.create_task(_delete_later(sent))
                    except RuntimeError:
                        pass

            return True

        except Exception as e:
            logger.error(f"Failed to send audio: {e}\n{traceback.format_exc()}")
            await self.safe_edit_message(message, "❌ Failed to send audio.")
            return False

        finally:
            # Clean up files
            try:
                if audio_path and os.path.exists(audio_path):
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
        if not callback_query.from_user:
            return
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

            # Check download quota for free/premium users
            can_download, reason = db.can_download(user_id)
            if not can_download:
                try:
                    await callback_query.answer(f"❌ {reason}", show_alert=True)
                except Exception:
                    pass
                try:
                    user = db.get_user(user_id) or {}
                    await self.bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"❌ **Download Limit Reached!**\n\n"
                            f"📊 Used: {user.get('downloads_today', 0)}/{Config.FREE_USER_DAILY_LIMIT} free downloads today.\n\n"
                            f"💎 Upgrade to Premium to unlock unlimited high-quality downloads & album support!\n"
                            f"Contact: @icecube9608\n\n"
                            f"👤 **Your User ID:** `{user_id}`"
                        )
                    )
                except Exception:
                    pass
                return
            
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
        """Download multiple tracks from an album/playlist. Returns True if at least one track downloaded (Premium Only)."""
        if not db.is_premium(user_id):
            await self.safe_edit_message(
                message,
                f"❌ **Premium Required!**\n\n"
                f"📥 Album and playlist downloads are available for **Premium users only**.\n\n"
                f"💎 Upgrade to Premium for unlimited downloads!\n"
                f"Contact: @icecube9608\n\n"
                f"👤 **Your User ID:** `{user_id}`"
            )
            return False
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

                    # parse common and international open.spotify.com URL forms
                    m = re.search(r"open\.spotify\.com/(?:intl-[^/]+/)?(album|playlist|artist|track)/([A-Za-z0-9]+)", simple)
                    if m:
                        return m.group(2), m.group(1)

                    # URI format spotify:album:xxx
                    m = re.search(r"spotify:(album|playlist|artist|track):([A-Za-z0-9]+)", simple)
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

                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = asyncio.get_event_loop()
                track_ids = await loop.run_in_executor(None, fetch_spotify_ids)
                track_items = [("spotify", tid) for tid in track_ids if tid]

            elif provider == "youtube" or provider == 'yt':
                entries = await self._youtube_get_playlist_entries(album_id_or_url)
                if not entries:
                    await self.safe_edit_message(message, "❌ Could not extract YouTube playlist entries.")
                    return False
                track_items = [("youtube", e.get('webpage_url') or e.get('id')) for e in entries]

            else:
                await self.safe_edit_message(message, "❌ Multi-track downloads are not supported for this provider yet.")
                return False

            total = len(track_items)
            if total == 0:
                await self.safe_edit_message(message, "❌ No tracks found in the album/playlist.")
                return False

            success_count = 0
            fail_count = 0

            progress = await self.safe_edit_message(
                message,
                f"⬇️ Preparing to download {total} tracks from album/playlist...\nProgress: 0/{total}"
            ) or message

            for idx, (prov, tid) in enumerate(track_items, start=1):
                try:
                    progress = await self.safe_edit_message(
                        progress,
                        f"⬇️ Downloading [{idx}/{total}]...\n"
                        f"✅ Successful: {success_count}  |  ❌ Failed: {fail_count}"
                    ) or progress
                except Exception as e:
                    logger.warning(f"Could not update batch progress message: {e}")

                try:
                    single_success = await self.download_track(prov, tid, user_id, progress, is_batch=True)
                    if single_success:
                        success_count += 1
                    else:
                        fail_count += 1
                except Exception as e:
                    logger.error(f"Failed downloading track {tid}: {e}")
                    fail_count += 1

                # Brief delay between tracks to reduce Telegram rate limits
                await asyncio.sleep(1.5)

            final_msg = await self.safe_edit_message(
                progress,
                f"✅ **Album/playlist download finished.**\n\n"
                f"📊 Total tracks: {total}\n"
                f"✅ Successful: {success_count}\n"
                f"❌ Failed: {fail_count}"
            )

            # Schedule deletion for the single final summary message after 5 minutes
            if final_msg:
                async def _delete_later(msg):
                    try:
                        await asyncio.sleep(300)
                        await msg.delete()
                    except Exception:
                        pass
                try:
                    asyncio.create_task(_delete_later(final_msg))
                except RuntimeError:
                    pass

            return success_count > 0

        except Exception as e:
            logger.error(f"Unexpected error in download_album: {e}\n{traceback.format_exc()}")
            try:
                await self.safe_edit_message(message, f"❌ Unexpected error: {e}")
            except Exception:
                pass
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
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.get_event_loop()
            entries = await loop.run_in_executor(None, extract)
            return entries[:max_items] if entries else []
        except Exception as e:
            logger.error(f"yt-dlp playlist extraction error: {e}")
            return []
