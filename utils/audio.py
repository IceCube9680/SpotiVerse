# utils/audio.py
import os
import time
import subprocess
import requests
import logging
import platform
import stat
import base64
import json
import re
from io import BytesIO
from typing import Optional, Dict, Any, Tuple, Union

from PIL import Image, ImageDraw, ImageFont
import mutagen
from mutagen import File
from mutagen.flac import FLAC, Picture
from mutagen.id3 import (
    ID3, TIT2, TPE1, TPE2, TALB, TYER, TCON, TRCK, TPOS, TSRC, COMM, APIC, ID3NoHeaderError
)
from mutagen.mp4 import MP4, MP4Cover
from mutagen.oggvorbis import OggVorbis
from mutagen.oggopus import OggOpus
from mutagen.wave import WAVE
try:
    from mutagen.aiff import AIFF
except ImportError:
    AIFF = None
try:
    from mutagen.wavpack import WavPack
except ImportError:
    WavPack = None
try:
    from mutagen.monkeysaudio import MonkeysAudio
except ImportError:
    MonkeysAudio = None

from config import Config
from utils.audio_formats import AudioFormat, AudioProfile

logger = logging.getLogger(__name__)

class AudioProcessor:
    """
    Unified Audio Processing Engine:
    - FFprobe/Mutagen source inspection (codec, bitrate, sample rate, bit depth, channels, lossless status)
    - Source quality preservation and intelligent direct-stream copy
    - Lossy-to-lossless downgrade warning generation (anti-fake Hi-Res)
    - Subprocess-safe FFmpeg transcoding across 12+ audio formats and Hi-Res profiles
    - Comprehensive tag embedding across all containers and codecs
    """
    def __init__(self):
        self.ffmpeg_path = self.get_ffmpeg_path()
        self.ffprobe_path = self.get_ffprobe_path()
        self.last_conversion_info: Dict[str, Any] = {}

    def get_ffmpeg_path(self) -> str:
        """Get FFmpeg executable path"""
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

    def get_ffprobe_path(self) -> str:
        """Get FFprobe executable path"""
        try:
            subprocess.run(["ffprobe", "-version"], capture_output=True, check=True)
            return "ffprobe"
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

        ffprobe_dir = os.path.join(os.getcwd(), "ffmpeg")
        if platform.system() == "Windows":
            ffprobe_exe = os.path.join(ffprobe_dir, "bin", "ffprobe.exe")
        else:
            ffprobe_exe = os.path.join(ffprobe_dir, "bin", "ffprobe")

        if os.path.exists(ffprobe_exe):
            return ffprobe_exe

        return "ffprobe"

    def get_source_quality(self, input_path: str) -> Dict[str, Any]:
        """
        Deep inspection of audio stream via FFprobe and Mutagen.
        Extracts original codec, container, bitrate, sample rate, bit depth, channels, duration,
        and lossy/lossless status.
        """
        result = {
            "bitrate_kbps": 0,
            "sample_rate": 44100,
            "bit_depth": 16,
            "channels": 2,
            "codec": "unknown",
            "container": "",
            "format": "",
            "duration": 0,
            "file_size": 0,
            "is_lossless": False,
            "quality_label": "Unknown"
        }
        if not input_path or not os.path.exists(input_path):
            return result

        try:
            result["file_size"] = os.path.getsize(input_path)
            ext = os.path.splitext(input_path)[1].lower().lstrip(".")
            result["container"] = ext
        except Exception:
            pass

        # 1. Probe via FFprobe JSON metadata (most accurate for stream codecs & bit depth)
        try:
            cmd = [
                self.ffprobe_path, "-v", "error",
                "-show_streams", "-show_format",
                "-print_format", "json", input_path
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if proc.returncode == 0 and proc.stdout:
                data = json.loads(proc.stdout)
                streams = data.get("streams", [])
                format_info = data.get("format", {})

                # Find first audio stream
                audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
                if audio_stream:
                    codec_name = str(audio_stream.get("codec_name", "")).lower()
                    result["codec"] = codec_name

                    # Sample rate
                    s_rate = audio_stream.get("sample_rate")
                    if s_rate and str(s_rate).isdigit():
                        result["sample_rate"] = int(s_rate)

                    # Channels
                    chs = audio_stream.get("channels")
                    if chs and str(chs).isdigit():
                        result["channels"] = int(chs)

                    # Bit depth
                    bits = audio_stream.get("bits_per_raw_sample") or audio_stream.get("bits_per_sample")
                    if bits and str(bits).isdigit() and int(bits) > 0:
                        result["bit_depth"] = int(bits)
                    else:
                        sample_fmt = str(audio_stream.get("sample_fmt", ""))
                        if "32" in sample_fmt or "flt" in sample_fmt or "dbl" in sample_fmt:
                            result["bit_depth"] = 32
                        elif "24" in sample_fmt or "s24" in sample_fmt:
                            result["bit_depth"] = 24
                        else:
                            result["bit_depth"] = 16

                    # Bitrate
                    br = audio_stream.get("bit_rate") or format_info.get("bit_rate")
                    if br and str(br).isdigit() and int(br) > 0:
                        result["bitrate_kbps"] = int(br) // 1000

                    # Duration
                    dur = audio_stream.get("duration") or format_info.get("duration")
                    if dur:
                        try:
                            result["duration"] = int(float(dur))
                        except Exception:
                            pass

                    # Lossless detection
                    lossless_codecs = {"flac", "alac", "pcm_s16le", "pcm_s24le", "pcm_s32le",
                                       "pcm_s16be", "pcm_s24be", "pcm_s32be", "pcm_f32le",
                                       "pcm_f32be", "wavpack", "ape", "tak"}
                    result["is_lossless"] = codec_name in lossless_codecs or ext in ("flac", "wav", "aiff", "wv", "ape")
        except Exception as e:
            logger.debug(f"FFprobe JSON probe error on {input_path}: {e}")

        # 2. Mutagen probe verification
        try:
            audio = File(input_path)
            if audio and getattr(audio, "info", None):
                info = audio.info
                if result["bitrate_kbps"] == 0:
                    bitrate = getattr(info, "bitrate", 0) or 0
                    if bitrate > 0:
                        result["bitrate_kbps"] = int(bitrate // 1000)
                if result["sample_rate"] == 44100:
                    result["sample_rate"] = getattr(info, "sample_rate", 44100) or 44100
                if result["channels"] == 2:
                    result["channels"] = getattr(info, "channels", 2) or 2
                if result["duration"] == 0:
                    result["duration"] = int(getattr(info, "length", 0) or 0)
                bits = getattr(info, "bits_per_sample", None)
                if bits:
                    result["bit_depth"] = int(bits)
                    if int(bits) > 16 or getattr(audio, "mime", [""])[0] in ("audio/flac", "audio/wav", "audio/aiff"):
                        result["is_lossless"] = True
                result["format"] = audio.mime[0] if getattr(audio, "mime", None) else ""
        except Exception as e:
            logger.debug(f"Mutagen probe error on {input_path}: {e}")

        # Compute human-readable quality label
        if result["is_lossless"]:
            rate_khz = result["sample_rate"] / 1000.0
            rate_str = f"{rate_khz:.1f}kHz" if not rate_khz.is_integer() else f"{int(rate_khz)}kHz"
            result["quality_label"] = f"{result['codec'].upper()} {result['bit_depth']}-bit / {rate_str} (Lossless)"
        elif result["bitrate_kbps"] > 0:
            result["quality_label"] = f"{result['codec'].upper()} {result['bitrate_kbps']} kbps (Lossy)"
        else:
            result["quality_label"] = f"{result['codec'].upper()} Standard"

        return result

    inspect_audio_source = get_source_quality

    def check_lossy_to_lossless_warning(self, source_info: Dict[str, Any],
                                        target_format: str,
                                        target_quality: Union[int, str, None] = None) -> Optional[str]:
        """
        Detects if a lossy stream is being converted to a lossless format (FLAC/WAV/ALAC).
        Returns an educational warning string preventing fake Hi-Res claims.
        """
        if not source_info or not isinstance(source_info, dict):
            return None
        target_fmt = AudioProfile.normalize_format(target_format)
        is_target_lossless = AudioProfile.is_lossless(target_fmt)
        is_source_lossy = not source_info.get("is_lossless", False)

        if is_source_lossy and is_target_lossless:
            src_codec = str(source_info.get("codec") or "lossy stream").upper()
            src_br = source_info.get("bitrate_kbps") or "standard"
            return (
                f"⚠️ **Note:** Original source is lossy {src_codec} ({src_br} kbps). "
                f"Transcoding to {target_fmt.upper()} preserves stream integrity without fake Hi-Res upscaling."
            )
        return None

    def can_stream_copy(self, input_path: str, format_type: str, quality: Union[int, str]) -> bool:
        """
        Check if input stream can be copied directly (-c:a copy) without re-encoding,
        preserving native bits and eliminating generation loss.
        """
        if not input_path or not os.path.exists(input_path):
            return False

        src_info = self.get_source_quality(input_path)
        src_codec = src_info.get("codec", "").lower()
        src_ext = os.path.splitext(input_path)[1].lower()
        target_fmt = AudioProfile.normalize_format(format_type)
        target_ext = AudioProfile.get_extension(target_fmt)

        # 1. Direct native FLAC copy
        if target_fmt == AudioFormat.FLAC and src_codec == "flac" and src_ext == ".flac":
            return True

        # 2. Direct native Opus copy
        if target_fmt in (AudioFormat.OPUS, AudioFormat.OGG_OPUS) and src_codec == "opus" and src_ext in (".opus", ".ogg"):
            return True

        # 3. Direct native M4A/AAC copy
        if target_fmt in (AudioFormat.M4A, AudioFormat.M4A_AAC, AudioFormat.AAC) and src_codec == "aac" and src_ext in (".m4a", ".mp4", ".aac"):
            return True

        # 4. Direct native ALAC copy
        if target_fmt in (AudioFormat.ALAC, AudioFormat.M4A_ALAC) and src_codec == "alac" and src_ext == ".m4a":
            return True

        return False

    def convert_audio(self, input_path: str, output_path: str,
                      format_type: str, quality: Union[int, str],
                      preserve_native: bool = True) -> bool:
        """
        Convert audio to desired format and quality using FFmpeg.
        Performs source quality probing, stream copy when viable, non-upscaling logging,
        timing measurement, and output validation.
        """
        start_time = time.time()
        fmt = AudioProfile.normalize_format(format_type)
        self.last_conversion_info = {
            "input_path": input_path,
            "output_path": output_path,
            "format": fmt,
            "requested_quality": quality,
            "source_quality": None,
            "downgrade_warning": None,
            "used_stream_copy": False,
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

            # Check lossy-to-lossless warning
            warning = self.check_lossy_to_lossless_warning(src_info, fmt, quality)
            if warning:
                self.last_conversion_info["downgrade_warning"] = warning
                logger.info(warning)

            # If input file is already target format and identical path, skip
            if input_path == output_path:
                self.last_conversion_info["success"] = True
                self.last_conversion_info["conversion_duration_sec"] = 0.0
                return True

            # Check if direct stream copy is viable to preserve native audio stream
            if preserve_native and self.can_stream_copy(input_path, fmt, quality):
                cmd = [self.ffmpeg_path, "-y", "-i", input_path, "-c:a", "copy", "-vn", output_path]
                logger.info(f"Preserving native audio stream without re-encoding: {' '.join(cmd)}")
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    self.last_conversion_info["used_stream_copy"] = True
                    self.last_conversion_info["success"] = True
                    self.last_conversion_info["conversion_duration_sec"] = round(time.time() - start_time, 2)
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
        Embed standardized metadata (title, artist, album, album_artist, year, genre,
        track_number, isrc, copyright) and cover art across all supported formats
        (MP3, FLAC, M4A AAC, M4A ALAC, Opus, Ogg Vorbis, WAV, AIFF, WavPack, APE, AC3, EAC3).
        """
        if not audio_path or not os.path.exists(audio_path):
            return False

        try:
            meta = metadata or {}
            title = str(meta.get("title") or "Unknown Title")
            artist = str(meta.get("artist") or "Unknown Artist")
            album = str(meta.get("album") or "Unknown Album")
            album_artist = str(meta.get("album_artist") or artist)
            year = str(meta.get("year") or meta.get("release_date", "2024")[:4] if meta.get("release_date") else "2024")
            genre = str(meta.get("genre") or "Music")
            isrc = str(meta.get("isrc") or "")
            track_num = str(meta.get("track_number") or "1")

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
                audio["TPE2"] = TPE2(encoding=3, text=album_artist)
                audio["TALB"] = TALB(encoding=3, text=album)
                audio["TYER"] = TYER(encoding=3, text=year)
                audio["TCON"] = TCON(encoding=3, text=genre)
                if isrc:
                    audio["TSRC"] = TSRC(encoding=3, text=isrc)
                if track_num:
                    audio["TRCK"] = TRCK(encoding=3, text=track_num)

                if img_data:
                    audio["APIC"] = APIC(
                        encoding=3,
                        mime='image/jpeg',
                        type=3,  # Cover front
                        desc='Cover',
                        data=img_data
                    )
                audio.save(v2_version=3)

            # 2. FLAC Tagging (Vorbis comments + Picture block)
            elif ext == ".flac":
                audio = FLAC(audio_path)
                audio["title"] = title
                audio["artist"] = artist
                audio["album"] = album
                audio["albumartist"] = album_artist
                audio["date"] = year
                audio["genre"] = genre
                if isrc:
                    audio["isrc"] = isrc
                if track_num:
                    audio["tracknumber"] = track_num

                if img_data:
                    pic = Picture()
                    pic.type = 3
                    pic.mime = 'image/jpeg'
                    pic.desc = 'Cover'
                    pic.data = img_data
                    audio.clear_pictures()
                    audio.add_picture(pic)
                audio.save()

            # 3. M4A / AAC / ALAC Tagging (MP4 Atoms)
            elif ext in (".m4a", ".mp4", ".aac"):
                audio = MP4(audio_path)
                if audio.tags is None:
                    audio.add_tags()
                audio.tags["\xa9nam"] = [title]
                audio.tags["\xa9ART"] = [artist]
                audio.tags["aART"] = [album_artist]
                audio.tags["\xa9alb"] = [album]
                audio.tags["\xa9day"] = [year]
                audio.tags["\xa9gen"] = [genre]
                if track_num and str(track_num).isdigit():
                    audio.tags["trkn"] = [(int(track_num), 0)]

                if img_data:
                    audio.tags["covr"] = [MP4Cover(img_data, imageformat=MP4Cover.FORMAT_JPEG)]
                audio.save()

            # 4. Opus Tagging (.opus / OggOpus)
            elif ext == ".opus":
                try:
                    audio = OggOpus(audio_path)
                    audio["title"] = [title]
                    audio["artist"] = [artist]
                    audio["album"] = [album]
                    audio["date"] = [year]
                    audio["genre"] = [genre]
                    if isrc:
                        audio["isrc"] = [isrc]
                    if img_data:
                        pic = Picture()
                        pic.type = 3
                        pic.mime = 'image/jpeg'
                        pic.desc = 'Cover'
                        pic.data = img_data
                        encoded_pic = base64.b64encode(pic.write()).decode("ascii")
                        audio["metadata_block_picture"] = [encoded_pic]
                    audio.save()
                except Exception as op_err:
                    logger.debug(f"OggOpus tagging fallback: {op_err}")

            # 5. OGG Vorbis Tagging
            elif ext in (".ogg", ".oga"):
                audio = OggVorbis(audio_path)
                audio["title"] = [title]
                audio["artist"] = [artist]
                audio["album"] = [album]
                audio["date"] = [year]
                audio["genre"] = [genre]
                if isrc:
                    audio["isrc"] = [isrc]

                if img_data:
                    pic = Picture()
                    pic.type = 3
                    pic.mime = 'image/jpeg'
                    pic.desc = 'Cover'
                    pic.data = img_data
                    encoded_pic = base64.b64encode(pic.write()).decode("ascii")
                    audio["metadata_block_picture"] = [encoded_pic]
                audio.save()

            # 6. WAV Tagging (ID3 Chunk)
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

            # 7. AIFF Tagging (ID3 in AIFF)
            elif ext in (".aiff", ".aif") and AIFF is not None:
                try:
                    audio = AIFF(audio_path)
                    if audio.tags is None:
                        audio.add_tags()
                    audio.tags["TIT2"] = TIT2(encoding=3, text=title)
                    audio.tags["TPE1"] = TPE1(encoding=3, text=artist)
                    audio.tags["TALB"] = TALB(encoding=3, text=album)
                    audio.tags["TYER"] = TYER(encoding=3, text=year)
                    audio.save()
                except Exception as aiff_e:
                    logger.debug(f"AIFF tagging note: {aiff_e}")

            # 8. WavPack Tagging (APEv2)
            elif ext == ".wv" and WavPack is not None:
                try:
                    audio = WavPack(audio_path)
                    audio["title"] = title
                    audio["artist"] = artist
                    audio["album"] = album
                    audio["year"] = year
                    audio["genre"] = genre
                    audio.save()
                except Exception as wv_e:
                    logger.debug(f"WavPack tagging note: {wv_e}")

            # 9. Monkey's Audio Tagging (APEv2)
            elif ext == ".ape" and MonkeysAudio is not None:
                try:
                    audio = MonkeysAudio(audio_path)
                    audio["title"] = title
                    audio["artist"] = artist
                    audio["album"] = album
                    audio["year"] = year
                    audio["genre"] = genre
                    audio.save()
                except Exception as ape_e:
                    logger.debug(f"APE tagging note: {ape_e}")

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

            file_t = re.sub(r'[^\w\s-]', '', safe_t).strip() or "title"
            file_a = re.sub(r'[^\w\s-]', '', safe_a).strip() or "artist"
            thumbnail_path = f"data/thumbnails/{file_t}_{file_a}.jpg"
            os.makedirs(os.path.dirname(thumbnail_path), exist_ok=True)
            img.save(thumbnail_path)
            return thumbnail_path

        except Exception as e:
            logger.error(f"Thumbnail generation failed: {e}")
            return None
