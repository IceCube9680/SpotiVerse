# utils/audio.py
import os
import time
import subprocess
import requests
import logging
import platform
import stat
import base64
from io import BytesIO
from typing import Optional, Dict, Any, Tuple, Union

from PIL import Image, ImageDraw, ImageFont
import mutagen
from mutagen import File
from mutagen.flac import FLAC, Picture
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TYER, TCON, APIC, ID3NoHeaderError
from mutagen.mp4 import MP4, MP4Cover
from mutagen.oggvorbis import OggVorbis
from mutagen.wave import WAVE

from config import Config
from utils.audio_formats import AudioFormat, AudioProfile

logger = logging.getLogger(__name__)

class AudioProcessor:
    def __init__(self):
        self.ffmpeg_path = self.get_ffmpeg_path()
        self.last_conversion_info: Dict[str, Any] = {}

    def get_ffmpeg_path(self) -> str:
        """Get FFmpeg path, download if not available"""
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
            return "ffmpeg"
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

        ffmpeg_dir = os.path.join(os.getcwd(), "ffmpeg")
        if platform.system() == "Windows":
            ffmpeg_exe = os.path.join(ffmpeg_dir, "bin", "ffmpeg.exe")
        else:
            ffmpeg_exe = os.path.join(ffmpeg_dir, "bin", "ffmpeg")

        if os.path.exists(ffmpeg_exe):
            if platform.system() == "Windows":
                try:
                    os.chmod(ffmpeg_exe, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
                except Exception as e:
                    logger.warning(f"Could not set permissions on ffmpeg: {e}")
            return ffmpeg_exe

        logger.warning("FFmpeg not found in PATH or local directory.")
        return "ffmpeg"

    def get_source_quality(self, input_path: str) -> Dict[str, Any]:
        """
        Probe input audio file to extract actual source bitrate, sample rate, channels, and format.
        """
        result = {
            "bitrate_kbps": 0,
            "sample_rate": 44100,
            "channels": 2,
            "format": "",
            "duration": 0
        }
        if not input_path or not os.path.exists(input_path):
            return result

        try:
            audio = File(input_path)
            if audio and getattr(audio, "info", None):
                info = audio.info
                bitrate = getattr(info, "bitrate", 0) or 0
                if bitrate > 0:
                    result["bitrate_kbps"] = int(bitrate // 1000)
                result["sample_rate"] = getattr(info, "sample_rate", 44100) or 44100
                result["channels"] = getattr(info, "channels", 2) or 2
                result["duration"] = int(getattr(info, "length", 0) or 0)
                result["format"] = audio.mime[0] if getattr(audio, "mime", None) else ""
        except Exception as e:
            logger.debug(f"Mutagen probe error on {input_path}: {e}")

        # If mutagen couldn't get bitrate, try ffprobe if available
        if result["bitrate_kbps"] == 0:
            try:
                cmd = [
                    "ffprobe", "-v", "error",
                    "-show_entries", "stream=bit_rate,sample_rate,channels:format=bit_rate,duration",
                    "-of", "default=noprint_wrappers=1", input_path
                ]
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if proc.returncode == 0:
                    for line in proc.stdout.splitlines():
                        if "=" in line:
                            k, v = line.split("=", 1)
                            if k.strip() == "bit_rate" and v.strip().isdigit() and int(v.strip()) > 0:
                                result["bitrate_kbps"] = int(v.strip()) // 1000
                            elif k.strip() == "sample_rate" and v.strip().isdigit():
                                result["sample_rate"] = int(v.strip())
                            elif k.strip() == "channels" and v.strip().isdigit():
                                result["channels"] = int(v.strip())
            except Exception as e:
                logger.debug(f"ffprobe probe error on {input_path}: {e}")

        return result

    def convert_audio(self, input_path: str, output_path: str,
                      format_type: str, quality: Union[int, str]) -> bool:
        """
        Convert audio to desired format and quality using FFmpeg.
        Performs source quality probing, non-upscaling logging, timing measurement,
        and output validation.
        """
        start_time = time.time()
        fmt = str(format_type).lower().strip()
        self.last_conversion_info = {
            "input_path": input_path,
            "output_path": output_path,
            "format": fmt,
            "requested_quality": quality,
            "source_quality": None,
            "conversion_duration_sec": 0.0,
            "success": False,
            "error": None
        }

        try:
            if not os.path.exists(input_path):
                logger.error(f"Input file does not exist: {input_path}")
                self.last_conversion_info["error"] = "Input file missing"
                return False

            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

            # Probe source quality
            src_info = self.get_source_quality(input_path)
            self.last_conversion_info["source_quality"] = src_info
            src_bitrate = src_info.get("bitrate_kbps", 0)

            # Check if requested output exceeds source quality without claiming upscaled source
            req_bitrate = 0
            if str(quality).isdigit():
                req_bitrate = int(quality)
            if src_bitrate > 0 and req_bitrate > 0 and req_bitrate > src_bitrate:
                logger.info(
                    f"Notice: Source audio bitrate ({src_bitrate} kbps) is lower than requested output "
                    f"({req_bitrate} kbps). Transcoding to target format at best technical standard without upscaling source fidelity."
                )

            # If input file is already target format and identical path, skip conversion
            if input_path == output_path:
                self.last_conversion_info["success"] = True
                self.last_conversion_info["conversion_duration_sec"] = 0.0
                return True

            # Build safe FFmpeg arguments using centralized AudioProfile
            cmd = AudioProfile.get_ffmpeg_args(
                self.ffmpeg_path,
                input_path,
                output_path,
                fmt,
                quality
            )

            logger.info(f"Executing FFmpeg transcoding: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )

            duration = round(time.time() - start_time, 2)
            self.last_conversion_info["conversion_duration_sec"] = duration

            if result.returncode != 0:
                logger.error(f"FFmpeg conversion failed (code {result.returncode}): {result.stderr}")
                if os.path.exists(output_path):
                    try:
                        os.remove(output_path)
                    except Exception:
                        pass
                self.last_conversion_info["error"] = result.stderr
                return False

            # Verify output exists and is non-empty
            if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                logger.error(f"Output file was not created or empty: {output_path}")
                self.last_conversion_info["error"] = "Output file empty or missing"
                return False

            self.last_conversion_info["success"] = True
            logger.info(f"Audio conversion completed in {duration}s -> {output_path}")
            return True

        except subprocess.TimeoutExpired:
            logger.error("FFmpeg conversion timed out after 5 minutes")
            self.last_conversion_info["error"] = "FFmpeg conversion timed out"
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except Exception:
                    pass
            return False
        except Exception as e:
            logger.error(f"Unexpected error in audio conversion: {e}")
            self.last_conversion_info["error"] = str(e)
            return False

    @staticmethod
    def validate_file_size(file_path: str, max_mb: int = None) -> Tuple[bool, float]:
        """
        Verify if generated audio file is within the maximum allowed Telegram upload size.
        Returns: (is_valid: bool, size_in_mb: float)
        """
        if not file_path:
            return False, 0.0
        if not os.path.exists(file_path):
            return True, 0.0
        limit_mb = max_mb or getattr(Config, "MAX_AUDIO_FILE_SIZE_MB", 50)
        size_bytes = os.path.getsize(file_path)
        size_mb = round(size_bytes / (1024 * 1024), 2)
        return size_mb <= limit_mb, size_mb

    @staticmethod
    def add_metadata(audio_path: str, metadata: dict, thumbnail_url: str = None) -> bool:
        """
        Embed standardized metadata (title, artist, album, year, genre) and cover art
        across all supported formats (MP3, FLAC, M4A, OGG, WAV).
        """
        if not audio_path or not os.path.exists(audio_path):
            return False

        try:
            meta = metadata or {}
            title = str(meta.get("title") or "Unknown Title")
            artist = str(meta.get("artist") or "Unknown Artist")
            album = str(meta.get("album") or "Unknown Album")
            year = str(meta.get("year") or "2024")
            genre = str(meta.get("genre") or "Music")

            # Load thumbnail bytes if provided
            img_data = None
            if thumbnail_url:
                try:
                    if os.path.exists(str(thumbnail_url)):
                        with open(thumbnail_url, "rb") as f:
                            img_data = f.read()
                    elif str(thumbnail_url).startswith(("http://", "https://")):
                        resp = requests.get(thumbnail_url, timeout=10)
                        if resp.status_code == 200:
                            img_data = resp.content
                except Exception as e:
                    logger.debug(f"Could not load thumbnail for metadata: {e}")

            ext = os.path.splitext(audio_path)[1].lower()

            # 1. MP3 Tagging (ID3v2)
            if ext == ".mp3":
                try:
                    audio = ID3(audio_path)
                except ID3NoHeaderError:
                    audio = ID3()
                    audio.save(audio_path)
                    audio = ID3(audio_path)

                audio["TIT2"] = TIT2(encoding=3, text=title)
                audio["TPE1"] = TPE1(encoding=3, text=artist)
                audio["TALB"] = TALB(encoding=3, text=album)
                audio["TYER"] = TYER(encoding=3, text=year)
                audio["TCON"] = TCON(encoding=3, text=genre)

                if img_data:
                    audio["APIC"] = APIC(
                        encoding=3,
                        mime='image/jpeg',
                        type=3,  # Cover front
                        desc='Cover',
                        data=img_data
                    )
                audio.save(v2_version=3)

            # 2. FLAC Tagging (Vorbis + Picture)
            elif ext == ".flac":
                audio = FLAC(audio_path)
                audio["title"] = title
                audio["artist"] = artist
                audio["album"] = album
                audio["date"] = year
                audio["genre"] = genre

                if img_data:
                    pic = Picture()
                    pic.type = 3
                    pic.mime = 'image/jpeg'
                    pic.desc = 'Cover'
                    pic.data = img_data
                    audio.clear_pictures()
                    audio.add_picture(pic)
                audio.save()

            # 3. M4A / AAC Tagging (MP4 Tags)
            elif ext in (".m4a", ".mp4", ".aac"):
                audio = MP4(audio_path)
                if audio.tags is None:
                    audio.add_tags()
                audio.tags["\xa9nam"] = [title]
                audio.tags["\xa9ART"] = [artist]
                audio.tags["\xa9alb"] = [album]
                audio.tags["\xa9day"] = [year]
                audio.tags["\xa9gen"] = [genre]

                if img_data:
                    audio.tags["covr"] = [MP4Cover(img_data, imageformat=MP4Cover.FORMAT_JPEG)]
                audio.save()

            # 4. OGG Tagging (Ogg Vorbis)
            elif ext in (".ogg", ".oga"):
                audio = OggVorbis(audio_path)
                audio["title"] = [title]
                audio["artist"] = [artist]
                audio["album"] = [album]
                audio["date"] = [year]
                audio["genre"] = [genre]

                if img_data:
                    pic = Picture()
                    pic.type = 3
                    pic.mime = 'image/jpeg'
                    pic.desc = 'Cover'
                    pic.data = img_data
                    encoded_pic = base64.b64encode(pic.write()).decode("ascii")
                    audio["metadata_block_picture"] = [encoded_pic]
                audio.save()

            # 5. WAV Tagging (ID3 chunk if supported)
            elif ext == ".wav":
                try:
                    audio = WAVE(audio_path)
                    if audio.tags is None:
                        audio.add_tags()
                    audio.tags["TIT2"] = TIT2(encoding=3, text=title)
                    audio.tags["TPE1"] = TPE1(encoding=3, text=artist)
                    audio.tags["TALB"] = TALB(encoding=3, text=album)
                    audio.tags["TYER"] = TYER(encoding=3, text=year)
                    audio.save()
                except Exception as wave_e:
                    logger.debug(f"WAV tagging note: {wave_e}")

            return True

        except Exception as e:
            logger.error(f"Metadata addition failed for {audio_path}: {e}")
            return False

    @staticmethod
    def generate_thumbnail(title: str, artist: str, size: Tuple[int, int] = (500, 500)) -> Optional[str]:
        """Generate a clean cover art thumbnail with title and artist"""
        try:
            safe_t = str(title or "Unknown Title")
            safe_a = str(artist or "Unknown Artist")

            img = Image.new('RGB', size, color=(41, 128, 185))
            draw = ImageDraw.Draw(img)

            try:
                title_font = ImageFont.truetype("arialbd.ttf", 40)
                artist_font = ImageFont.truetype("arial.ttf", 30)
            except Exception:
                title_font = ImageFont.load_default()
                artist_font = ImageFont.load_default()

            title_bbox = draw.textbbox((0, 0), safe_t, font=title_font)
            artist_bbox = draw.textbbox((0, 0), safe_a, font=artist_font)

            title_width = title_bbox[2] - title_bbox[0]
            title_height = title_bbox[3] - title_bbox[1]
            artist_width = artist_bbox[2] - artist_bbox[0]
            artist_height = artist_bbox[3] - artist_bbox[1]

            title_x = (size[0] - title_width) // 2
            title_y = (size[1] - title_height - artist_height - 20) // 2

            artist_x = (size[0] - artist_width) // 2
            artist_y = title_y + title_height + 20

            draw.text((title_x, title_y), safe_t, font=title_font, fill=(255, 255, 255))
            draw.text((artist_x, artist_y), safe_a, font=artist_font, fill=(236, 240, 241))

            import re
            file_t = re.sub(r'[^\w\s-]', '', safe_t).strip() or "title"
            file_a = re.sub(r'[^\w\s-]', '', safe_a).strip() or "artist"
            thumbnail_path = f"data/thumbnails/{file_t}_{file_a}.jpg"
            os.makedirs(os.path.dirname(thumbnail_path), exist_ok=True)
            img.save(thumbnail_path)
            return thumbnail_path

        except Exception as e:
            logger.error(f"Thumbnail generation failed: {e}")
            return None
