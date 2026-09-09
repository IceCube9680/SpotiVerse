# utils/audio_formats.py
import logging
from typing import List, Tuple, Union, Optional
from config import Config

logger = logging.getLogger(__name__)

class AudioFormat:
    MP3 = "mp3"
    FLAC = "flac"
    M4A = "m4a"
    OGG = "ogg"
    WAV = "wav"

    ALL_FORMATS = [MP3, FLAC, M4A, OGG, WAV]


class AudioProfile:
    """
    Centralized configuration and parameter resolution for all supported audio formats,
    bitrates, compression levels, bit depths, and sample rates.
    """

    # Format specifications
    FORMAT_EXTENSIONS = {
        AudioFormat.MP3: ".mp3",
        AudioFormat.FLAC: ".flac",
        AudioFormat.M4A: ".m4a",
        AudioFormat.OGG: ".ogg",
        AudioFormat.WAV: ".wav",
    }

    MIME_TYPES = {
        AudioFormat.MP3: "audio/mpeg",
        AudioFormat.FLAC: "audio/flac",
        AudioFormat.M4A: "audio/mp4",
        AudioFormat.OGG: "audio/ogg",
        AudioFormat.WAV: "audio/wav",
    }

    # Standard quality tiers
    MP3_QUALITIES = [64, 128, 192, 256, 320]
    FLAC_QUALITIES = ["low", "medium", "high"]
    M4A_QUALITIES = [128, 192, 256, 320]
    OGG_QUALITIES = [64, 96, 128, 160, 192, 256, 320]
    WAV_QUALITIES = [
        "16-bit 44.1kHz",
        "16-bit 48kHz",
        "24-bit 44.1kHz",
        "24-bit 48kHz",
        "24-bit 96kHz",
    ]

    # WAV parameter mapping
    WAV_PARAMS = {
        "16-bit 44.1kHz": (16, 44100),
        "16-bit 48kHz": (16, 48000),
        "24-bit 44.1kHz": (24, 44100),
        "24-bit 48kHz": (24, 48000),
        "24-bit 96kHz": (24, 96000),
    }

    @classmethod
    def get_extension(cls, format_type: str) -> str:
        fmt = str(format_type).lower().strip()
        return cls.FORMAT_EXTENSIONS.get(fmt, f".{fmt}")

    @classmethod
    def get_mime_type(cls, format_type: str) -> str:
        fmt = str(format_type).lower().strip()
        return cls.MIME_TYPES.get(fmt, "audio/mpeg")

    @classmethod
    def get_allowed_formats(cls, is_premium: bool = False) -> List[str]:
        """Return allowed audio formats based on user tier and configuration."""
        if is_premium:
            configured = getattr(Config, "PREMIUM_AUDIO_FORMATS", None)
            if configured and isinstance(configured, list):
                return [f.lower() for f in configured if f.lower() in cls.FORMAT_EXTENSIONS]
            return [AudioFormat.MP3, AudioFormat.FLAC, AudioFormat.M4A, AudioFormat.OGG, AudioFormat.WAV]
        else:
            configured = getattr(Config, "FREE_AUDIO_FORMATS", None)
            if configured and isinstance(configured, list):
                return [f.lower() for f in configured if f.lower() in cls.FORMAT_EXTENSIONS]
            return [AudioFormat.MP3]

    @classmethod
    def get_allowed_qualities(cls, format_type: str, is_premium: bool = False) -> List[Union[int, str]]:
        """Return allowed quality levels for a given format and user tier."""
        fmt = str(format_type).lower().strip()
        if fmt == AudioFormat.MP3:
            if is_premium:
                configured = getattr(Config, "PREMIUM_MP3_QUALITIES", None)
                if configured and isinstance(configured, list):
                    return [int(q) for q in configured if str(q).isdigit()]
                return list(cls.MP3_QUALITIES)
            else:
                configured = getattr(Config, "FREE_MP3_QUALITIES", None)
                if configured and isinstance(configured, list):
                    return [int(q) for q in configured if str(q).isdigit()]
                return list(cls.MP3_QUALITIES)

        elif fmt == AudioFormat.FLAC:
            return list(cls.FLAC_QUALITIES)

        elif fmt == AudioFormat.M4A:
            if is_premium:
                configured = getattr(Config, "PREMIUM_M4A_QUALITIES", None)
                if configured and isinstance(configured, list):
                    return [int(q) for q in configured if str(q).isdigit()]
                return list(cls.M4A_QUALITIES)
            return [128]

        elif fmt == AudioFormat.OGG:
            if is_premium:
                configured = getattr(Config, "PREMIUM_OGG_QUALITIES", None)
                if configured and isinstance(configured, list):
                    return [int(q) for q in configured if str(q).isdigit()]
                return list(cls.OGG_QUALITIES)
            return [128]

        elif fmt == AudioFormat.WAV:
            if is_premium:
                return list(cls.WAV_QUALITIES)
            return ["16-bit 44.1kHz"]

        return [cls.get_default_quality(fmt, is_premium)]

    @classmethod
    def get_default_quality(cls, format_type: str, is_premium: bool = False) -> Union[int, str]:
        """Return default quality level for a format and user tier."""
        fmt = str(format_type).lower().strip()
        if fmt == AudioFormat.MP3:
            return 320 if is_premium else 128
        elif fmt == AudioFormat.FLAC:
            return "high"
        elif fmt == AudioFormat.M4A:
            return 256 if is_premium else 128
        elif fmt == AudioFormat.OGG:
            return 256 if is_premium else 128
        elif fmt == AudioFormat.WAV:
            return "24-bit 48kHz" if is_premium else "16-bit 44.1kHz"
        return 320

    @classmethod
    def is_format_allowed(cls, format_type: str, is_premium: bool = False) -> bool:
        allowed = cls.get_allowed_formats(is_premium=is_premium)
        return str(format_type).lower().strip() in allowed

    @classmethod
    def is_quality_allowed(cls, format_type: str, quality, is_premium: bool = False) -> bool:
        allowed_qualities = cls.get_allowed_qualities(format_type, is_premium=is_premium)
        fmt = str(format_type).lower().strip()
        if fmt in (AudioFormat.MP3, AudioFormat.M4A, AudioFormat.OGG):
            try:
                q_int = int(quality)
                return q_int in [int(x) for x in allowed_qualities if str(x).isdigit()]
            except (ValueError, TypeError):
                return False
        return str(quality).strip().lower() in [str(x).strip().lower() for x in allowed_qualities]

    @classmethod
    def parse_wav_quality(cls, quality_str: str) -> Tuple[int, int]:
        """
        Parse WAV quality string into (bit_depth, sample_rate).
        Examples: '16-bit 44.1kHz' -> (16, 44100), '24-bit 96kHz' -> (24, 96000).
        """
        q_str = str(quality_str).strip()
        if q_str in cls.WAV_PARAMS:
            return cls.WAV_PARAMS[q_str]

        # Case-insensitive lookup
        for k, v in cls.WAV_PARAMS.items():
            if k.lower() == q_str.lower():
                return v

        # Fallback parsing
        bit_depth = 24 if "24" in q_str else 16
        if "96" in q_str or "96000" in q_str:
            sample_rate = 96000
        elif "48" in q_str or "48000" in q_str:
            sample_rate = 48000
        else:
            sample_rate = 44100

        return bit_depth, sample_rate

    @classmethod
    def format_quality_label(cls, format_type: str, quality: Union[int, str]) -> str:
        """Returns clean human-readable quality label for Telegram UI."""
        fmt = str(format_type).lower().strip()
        if fmt == AudioFormat.MP3:
            return f"{quality} kbps"
        elif fmt == AudioFormat.FLAC:
            return f"Lossless ({str(quality).capitalize()})"
        elif fmt == AudioFormat.M4A:
            return f"{quality} kbps (AAC)"
        elif fmt == AudioFormat.OGG:
            return f"{quality} kbps (Vorbis)"
        elif fmt == AudioFormat.WAV:
            return str(quality)
        return str(quality)

    @classmethod
    def get_ffmpeg_args(cls, ffmpeg_bin: str, input_path: str, output_path: str,
                        format_type: str, quality: Union[int, str]) -> List[str]:
        """
        Generate safe, structured list of arguments for FFmpeg conversion without shell=True.
        """
        fmt = str(format_type).lower().strip()
        base_cmd = [ffmpeg_bin, "-y", "-i", input_path]

        if fmt == AudioFormat.MP3:
            bitrate = f"{quality}k" if str(quality).isdigit() else "320k"
            return base_cmd + [
                "-codec:a", "libmp3lame",
                "-b:a", bitrate,
                "-q:a", "0",
                "-vn", output_path
            ]

        elif fmt == AudioFormat.FLAC:
            compression = "5"
            q_str = str(quality).lower()
            if q_str == "low":
                compression = "1"
            elif q_str == "high":
                compression = "8"
            elif q_str.isdigit():
                compression = str(min(8, max(0, int(q_str))))

            return base_cmd + [
                "-codec:a", "flac",
                "-compression_level", compression,
                "-vn", output_path
            ]

        elif fmt == AudioFormat.M4A:
            bitrate = f"{quality}k" if str(quality).isdigit() else "256k"
            return base_cmd + [
                "-codec:a", "aac",
                "-b:a", bitrate,
                "-vn", output_path
            ]

        elif fmt == AudioFormat.OGG:
            q_map = {
                64: "1",
                96: "2",
                128: "4",
                160: "5",
                192: "6",
                256: "8",
                320: "10"
            }
            q_int = int(quality) if str(quality).isdigit() else 192
            q_scale = q_map.get(q_int, "6")
            return base_cmd + [
                "-codec:a", "libvorbis",
                "-q:a", q_scale,
                "-vn", output_path
            ]

        elif fmt == AudioFormat.WAV:
            bit_depth, sample_rate = cls.parse_wav_quality(str(quality))
            codec = "pcm_s24le" if bit_depth == 24 else "pcm_s16le"
            return base_cmd + [
                "-codec:a", codec,
                "-ar", str(sample_rate),
                "-vn", output_path
            ]

        else:
            # Fallback to mp3
            return base_cmd + [
                "-codec:a", "libmp3lame",
                "-b:a", "320k",
                "-vn", output_path
            ]
