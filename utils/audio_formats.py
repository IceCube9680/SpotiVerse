# utils/audio_formats.py
import subprocess
import shutil
import logging
from typing import List, Tuple, Union, Optional, Dict, Any
from config import Config

logger = logging.getLogger(__name__)

class AudioFormat:
    # Standard Formats
    MP3 = "mp3"
    FLAC = "flac"
    M4A = "m4a"          # Default AAC container/codec
    M4A_AAC = "m4a_aac"
    M4A_ALAC = "m4a_alac"
    AAC = "aac"
    ALAC = "alac"
    OGG = "ogg"          # Default Vorbis container/codec
    OGG_VORBIS = "ogg_vorbis"
    OGG_OPUS = "ogg_opus"
    OPUS = "opus"
    WAV = "wav"
    AIFF = "aiff"
    WAVPACK = "wavpack"
    WV = "wv"
    APE = "ape"
    AC3 = "ac3"
    EAC3 = "eac3"

    ALL_FORMATS = [
        MP3, FLAC, M4A, M4A_AAC, M4A_ALAC, AAC, ALAC,
        OGG, OGG_VORBIS, OGG_OPUS, OPUS, WAV, AIFF,
        WAVPACK, WV, APE, AC3, EAC3
    ]

class AudioCodec:
    MP3 = "mp3"
    FLAC = "flac"
    AAC = "aac"
    ALAC = "alac"
    VORBIS = "vorbis"
    OPUS = "opus"
    PCM = "pcm"
    WAVPACK = "wavpack"
    APE = "ape"
    AC3 = "ac3"
    EAC3 = "eac3"


class AudioContainer:
    MP3 = "mp3"
    FLAC = "flac"
    M4A = "m4a"
    MP4 = "mp4"
    OGG = "ogg"
    OPUS = "opus"
    WAV = "wav"
    AIFF = "aiff"
    WV = "wv"
    APE = "ape"
    AC3 = "ac3"
    EAC3 = "eac3"


class FormatRegistry:
    """Helper registry interface for accessing format specs and encoders."""
    @classmethod
    def get_all_specs(cls) -> Dict[str, Any]:
        return AudioProfile.FORMAT_SPECS

    @classmethod
    def get_spec(cls, format_id: str) -> Optional[Any]:
        return AudioProfile.get_format_spec(format_id)

    @classmethod
    def get_available_encoders(cls) -> set:
        return AudioProfile.get_available_encoders()


class FormatSpec:
    """Detailed technical specification for an audio format/container/codec."""
    def __init__(self, format_id: str, display_name: str, extension: str,
                 container: str, codec: str, ffmpeg_encoder: str, mime_type: str,
                 is_lossless: bool, default_quality: Union[int, str],
                 supported_qualities: List[Union[int, str]]):
        self.format_id = format_id.lower().strip()
        self.display_name = display_name
        self.extension = extension
        self.container = container
        self.codec = codec
        self.ffmpeg_encoder = ffmpeg_encoder
        self.mime_type = mime_type
        self.is_lossless = is_lossless
        self.default_quality = default_quality
        self.supported_qualities = supported_qualities

    def to_dict(self) -> dict:
        return {
            "format_id": self.format_id,
            "display_name": self.display_name,
            "extension": self.extension,
            "container": self.container,
            "codec": self.codec,
            "ffmpeg_encoder": self.ffmpeg_encoder,
            "mime_type": self.mime_type,
            "is_lossless": self.is_lossless,
            "default_quality": self.default_quality,
            "supported_qualities": self.supported_qualities
        }


class AudioProfile:
    """
    Centralized configuration, encoder discovery, and parameter resolution for all supported
    audio formats, codecs, containers, bitrates, bit depths, sample rates, and quality profiles.
    """

    # Comprehensive Format Specifications Registry
    FORMAT_SPECS: Dict[str, FormatSpec] = {
        AudioFormat.MP3: FormatSpec(
            format_id=AudioFormat.MP3,
            display_name="MP3 (MPEG Layer 3)",
            extension=".mp3",
            container="mp3",
            codec="mp3",
            ffmpeg_encoder="libmp3lame",
            mime_type="audio/mpeg",
            is_lossless=False,
            default_quality=320,
            supported_qualities=[64, 96, 128, 160, 192, 224, 256, 320]
        ),
        AudioFormat.FLAC: FormatSpec(
            format_id=AudioFormat.FLAC,
            display_name="FLAC (Free Lossless Audio Codec)",
            extension=".flac",
            container="flac",
            codec="flac",
            ffmpeg_encoder="flac",
            mime_type="audio/flac",
            is_lossless=True,
            default_quality="24-bit 48kHz",
            supported_qualities=[
                "16-bit 44.1kHz",
                "16-bit 48kHz",
                "24-bit 44.1kHz",
                "24-bit 48kHz",
                "24-bit 88.2kHz",
                "24-bit 96kHz",
                "24-bit 176.4kHz",
                "24-bit 192kHz",
                "low", "medium", "high"
            ]
        ),
        AudioFormat.M4A: FormatSpec(
            format_id=AudioFormat.M4A,
            display_name="M4A (AAC Audio)",
            extension=".m4a",
            container="m4a",
            codec="aac",
            ffmpeg_encoder="aac",
            mime_type="audio/mp4",
            is_lossless=False,
            default_quality=256,
            supported_qualities=[64, 96, 128, 160, 192, 224, 256, 320]
        ),
        AudioFormat.M4A_AAC: FormatSpec(
            format_id=AudioFormat.M4A_AAC,
            display_name="M4A (AAC Audio)",
            extension=".m4a",
            container="m4a",
            codec="aac",
            ffmpeg_encoder="aac",
            mime_type="audio/mp4",
            is_lossless=False,
            default_quality=256,
            supported_qualities=[64, 96, 128, 160, 192, 224, 256, 320]
        ),
        AudioFormat.AAC: FormatSpec(
            format_id=AudioFormat.AAC,
            display_name="AAC (Advanced Audio Coding)",
            extension=".aac",
            container="adts",
            codec="aac",
            ffmpeg_encoder="aac",
            mime_type="audio/aac",
            is_lossless=False,
            default_quality=256,
            supported_qualities=[64, 96, 128, 160, 192, 224, 256, 320]
        ),
        AudioFormat.ALAC: FormatSpec(
            format_id=AudioFormat.ALAC,
            display_name="M4A (Apple Lossless ALAC)",
            extension=".m4a",
            container="m4a",
            codec="alac",
            ffmpeg_encoder="alac",
            mime_type="audio/mp4",
            is_lossless=True,
            default_quality="24-bit 48kHz",
            supported_qualities=[
                "16-bit 44.1kHz",
                "16-bit 48kHz",
                "24-bit 44.1kHz",
                "24-bit 48kHz",
                "24-bit 96kHz",
                "24-bit 192kHz"
            ]
        ),
        AudioFormat.M4A_ALAC: FormatSpec(
            format_id=AudioFormat.M4A_ALAC,
            display_name="M4A (Apple Lossless ALAC)",
            extension=".m4a",
            container="m4a",
            codec="alac",
            ffmpeg_encoder="alac",
            mime_type="audio/mp4",
            is_lossless=True,
            default_quality="24-bit 48kHz",
            supported_qualities=[
                "16-bit 44.1kHz",
                "16-bit 48kHz",
                "24-bit 44.1kHz",
                "24-bit 48kHz",
                "24-bit 96kHz",
                "24-bit 192kHz"
            ]
        ),
        AudioFormat.OPUS: FormatSpec(
            format_id=AudioFormat.OPUS,
            display_name="Opus (Interactive Audio Codec)",
            extension=".opus",
            container="ogg",
            codec="opus",
            ffmpeg_encoder="libopus",
            mime_type="audio/opus",
            is_lossless=False,
            default_quality=160,
            supported_qualities=[32, 48, 64, 96, 128, 160, 192, 256, 320]
        ),
        AudioFormat.OGG: FormatSpec(
            format_id=AudioFormat.OGG,
            display_name="OGG (Vorbis Audio)",
            extension=".ogg",
            container="ogg",
            codec="vorbis",
            ffmpeg_encoder="libvorbis",
            mime_type="audio/ogg",
            is_lossless=False,
            default_quality=192,
            supported_qualities=[64, 96, 128, 160, 192, 256, 320, 500]
        ),
        AudioFormat.OGG_VORBIS: FormatSpec(
            format_id=AudioFormat.OGG_VORBIS,
            display_name="OGG (Vorbis Audio)",
            extension=".ogg",
            container="ogg",
            codec="vorbis",
            ffmpeg_encoder="libvorbis",
            mime_type="audio/ogg",
            is_lossless=False,
            default_quality=192,
            supported_qualities=[64, 96, 128, 160, 192, 256, 320, 500]
        ),
        AudioFormat.OGG_OPUS: FormatSpec(
            format_id=AudioFormat.OGG_OPUS,
            display_name="OGG (Opus Audio)",
            extension=".ogg",
            container="ogg",
            codec="opus",
            ffmpeg_encoder="libopus",
            mime_type="audio/ogg",
            is_lossless=False,
            default_quality=160,
            supported_qualities=[32, 48, 64, 96, 128, 160, 192, 256, 320]
        ),
        AudioFormat.WAV: FormatSpec(
            format_id=AudioFormat.WAV,
            display_name="WAV (Uncompressed PCM)",
            extension=".wav",
            container="wav",
            codec="pcm",
            ffmpeg_encoder="pcm_s16le",
            mime_type="audio/wav",
            is_lossless=True,
            default_quality="24-bit 48kHz",
            supported_qualities=[
                "16-bit 44.1kHz",
                "16-bit 48kHz",
                "24-bit 44.1kHz",
                "24-bit 48kHz",
                "24-bit 96kHz",
                "24-bit 176.4kHz",
                "24-bit 192kHz",
                "32-bit Float 48kHz",
                "32-bit Float 96kHz",
                "32-bit Float 192kHz"
            ]
        ),
        AudioFormat.AIFF: FormatSpec(
            format_id=AudioFormat.AIFF,
            display_name="AIFF (Audio Interchange File Format)",
            extension=".aiff",
            container="aiff",
            codec="pcm",
            ffmpeg_encoder="pcm_s16be",
            mime_type="audio/aiff",
            is_lossless=True,
            default_quality="24-bit 48kHz",
            supported_qualities=[
                "16-bit 44.1kHz",
                "16-bit 48kHz",
                "24-bit 44.1kHz",
                "24-bit 48kHz",
                "24-bit 96kHz",
                "24-bit 176.4kHz",
                "24-bit 192kHz",
                "32-bit Float 48kHz",
                "32-bit Float 96kHz",
                "32-bit Float 192kHz"
            ]
        ),
        AudioFormat.WAVPACK: FormatSpec(
            format_id=AudioFormat.WAVPACK,
            display_name="WavPack (Hybrid Lossless)",
            extension=".wv",
            container="wavpack",
            codec="wavpack",
            ffmpeg_encoder="wavpack",
            mime_type="audio/x-wavpack",
            is_lossless=True,
            default_quality="normal",
            supported_qualities=[
                "fast", "normal", "high", "extra high",
                "16-bit 44.1kHz", "24-bit 96kHz"
            ]
        ),
        AudioFormat.WV: FormatSpec(
            format_id=AudioFormat.WV,
            display_name="WavPack (Hybrid Lossless)",
            extension=".wv",
            container="wavpack",
            codec="wavpack",
            ffmpeg_encoder="wavpack",
            mime_type="audio/x-wavpack",
            is_lossless=True,
            default_quality="normal",
            supported_qualities=[
                "fast", "normal", "high", "extra high",
                "16-bit 44.1kHz", "24-bit 96kHz"
            ]
        ),
        AudioFormat.APE: FormatSpec(
            format_id=AudioFormat.APE,
            display_name="Monkey's Audio (APE)",
            extension=".ape",
            container="ape",
            codec="ape",
            ffmpeg_encoder="ape",
            mime_type="audio/x-ape",
            is_lossless=True,
            default_quality="normal",
            supported_qualities=["fast", "normal", "high", "extra high"]
        ),
        AudioFormat.AC3: FormatSpec(
            format_id=AudioFormat.AC3,
            display_name="AC3 (Dolby Digital)",
            extension=".ac3",
            container="ac3",
            codec="ac3",
            ffmpeg_encoder="ac3",
            mime_type="audio/ac3",
            is_lossless=False,
            default_quality=384,
            supported_qualities=[192, 256, 320, 384, 448, 640]
        ),
        AudioFormat.EAC3: FormatSpec(
            format_id=AudioFormat.EAC3,
            display_name="E-AC3 (Dolby Digital Plus)",
            extension=".eac3",
            container="eac3",
            codec="eac3",
            ffmpeg_encoder="eac3",
            mime_type="audio/eac3",
            is_lossless=False,
            default_quality=448,
            supported_qualities=[192, 256, 320, 384, 448, 640]
        )
    }

    # Format extensions and MIME mapping for backwards compatibility
    FORMAT_EXTENSIONS = {k: v.extension for k, v in FORMAT_SPECS.items()}
    MIME_TYPES = {k: v.mime_type for k, v in FORMAT_SPECS.items()}

    # Standard quality tiers
    MP3_QUALITIES = [64, 128, 192, 256, 320]
    ALL_MP3_QUALITIES = [64, 96, 128, 160, 192, 224, 256, 320]

    FLAC_QUALITIES = ["low", "medium", "high"]
    ALL_FLAC_QUALITIES = [
        "16-bit 44.1kHz", "16-bit 48kHz", "24-bit 44.1kHz", "24-bit 48kHz",
        "24-bit 88.2kHz", "24-bit 96kHz", "24-bit 176.4kHz", "24-bit 192kHz",
        "low", "medium", "high"
    ]

    M4A_QUALITIES = [128, 192, 256, 320]
    ALL_M4A_QUALITIES = [64, 96, 128, 160, 192, 224, 256, 320]

    OPUS_QUALITIES = [32, 48, 64, 96, 128, 160, 192, 256, 320]

    OGG_QUALITIES = [64, 96, 128, 160, 192, 256, 320]
    ALL_OGG_QUALITIES = [64, 96, 128, 160, 192, 256, 320, 500]

    WAV_QUALITIES = [
        "16-bit 44.1kHz",
        "16-bit 48kHz",
        "24-bit 44.1kHz",
        "24-bit 48kHz",
        "24-bit 96kHz",
    ]
    ALL_WAV_QUALITIES = [
        "16-bit 44.1kHz", "16-bit 48kHz",
        "24-bit 44.1kHz", "24-bit 48kHz",
        "24-bit 96kHz", "24-bit 176.4kHz",
        "24-bit 192kHz", "32-bit Float 48kHz",
        "32-bit Float 96kHz", "32-bit Float 192kHz"
    ]

    AIFF_QUALITIES = list(ALL_WAV_QUALITIES)
    AC3_QUALITIES = [192, 256, 320, 384, 448, 640]
    EAC3_QUALITIES = [192, 256, 320, 384, 448, 640]
    WAVPACK_QUALITIES = ["fast", "normal", "high", "extra high", "16-bit 44.1kHz", "24-bit 96kHz"]
    APE_QUALITIES = ["fast", "normal", "high", "extra high"]

    # WAV & PCM parameter mapping
    WAV_PARAMS = {
        "16-bit 44.1kHz": (16, 44100),
        "16-bit 48kHz": (16, 48000),
        "24-bit 44.1kHz": (24, 44100),
        "24-bit 48kHz": (24, 48000),
        "24-bit 88.2kHz": (24, 88200),
        "24-bit 96kHz": (24, 96000),
        "24-bit 176.4kHz": (24, 176400),
        "24-bit 192kHz": (24, 192000),
        "32-bit Float 48kHz": (32, 48000),
        "32-bit Float 96kHz": (32, 96000),
        "32-bit Float 192kHz": (32, 192000),
    }

    # Cache for detected FFmpeg encoders
    _AVAILABLE_ENCODERS_CACHE: Optional[set] = None

    @classmethod
    def get_available_ffmpeg_encoders(cls, ffmpeg_bin: str = "ffmpeg") -> set:
        """Query FFmpeg once to detect which audio encoders are compiled and available."""
        if cls._AVAILABLE_ENCODERS_CACHE is not None:
            return cls._AVAILABLE_ENCODERS_CACHE

        available = set()
        try:
            cmd = [ffmpeg_bin, "-encoders"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    parts = line.strip().split()
                    if len(parts) >= 2 and parts[0].startswith("A"):
                        available.add(parts[1].lower())
        except Exception as e:
            logger.debug(f"Could not probe ffmpeg encoders: {e}")
            # Fallback to standard known encoders
            available = {
                "libmp3lame", "flac", "aac", "alac", "libopus", "opus",
                "libvorbis", "vorbis", "pcm_s16le", "pcm_s24le", "pcm_f32le",
                "pcm_s16be", "pcm_s24be", "pcm_f32be", "wavpack", "ac3", "eac3"
            }

        cls._AVAILABLE_ENCODERS_CACHE = available
        return cls._AVAILABLE_ENCODERS_CACHE

    @classmethod
    def is_encoder_available(cls, encoder_name: str, ffmpeg_bin: str = "ffmpeg") -> bool:
        """Check if a specific FFmpeg audio encoder is supported on the host."""
        if not encoder_name:
            return True
        enc = encoder_name.lower().strip()
        available = cls.get_available_ffmpeg_encoders(ffmpeg_bin)
        if enc in available:
            return True
        known = {
            "libmp3lame", "mp3", "flac", "aac", "alac", "libopus", "opus",
            "libvorbis", "vorbis", "pcm_s16le", "pcm_s24le", "pcm_f32le",
            "pcm_s16be", "pcm_s24be", "pcm_f32be", "wavpack", "wv", "ape", "ac3", "eac3"
        }
        return enc in known

    @classmethod
    def normalize_format(cls, format_type: str) -> str:
        """Normalize format aliases (e.g. 'alac' -> 'alac', 'opus' -> 'opus', 'wv' -> 'wavpack')."""
        fmt = str(format_type).lower().strip()
        if fmt in ("m4a_aac", "aac"):
            return AudioFormat.M4A
        if fmt in ("m4a_alac", "alac"):
            return AudioFormat.ALAC
        if fmt in ("ogg_vorbis", "vorbis"):
            return AudioFormat.OGG
        if fmt in ("ogg_opus",):
            return AudioFormat.OPUS
        if fmt in ("wv",):
            return AudioFormat.WAVPACK
        return fmt

    @classmethod
    def get_spec(cls, format_type: str) -> Optional[FormatSpec]:
        fmt = cls.normalize_format(format_type)
        return cls.FORMAT_SPECS.get(fmt) or cls.FORMAT_SPECS.get(str(format_type).lower().strip())

    @classmethod
    def get_extension(cls, format_type: str) -> str:
        spec = cls.get_spec(format_type)
        if spec:
            return spec.extension
        fmt = str(format_type).lower().strip()
        return cls.FORMAT_EXTENSIONS.get(fmt, f".{fmt}")

    @classmethod
    def get_mime_type(cls, format_type: str) -> str:
        spec = cls.get_spec(format_type)
        if spec:
            return spec.mime_type
        fmt = str(format_type).lower().strip()
        return cls.MIME_TYPES.get(fmt, "audio/mpeg")

    @classmethod
    def is_lossless(cls, format_type: str) -> bool:
        spec = cls.get_spec(format_type)
        return bool(spec and spec.is_lossless)

    @classmethod
    def get_allowed_formats(cls, is_premium: bool = False) -> List[str]:
        """Return allowed audio formats based on user tier and configuration."""
        if is_premium:
            configured = getattr(Config, "PREMIUM_AUDIO_FORMATS", None)
            if configured and isinstance(configured, list):
                result = []
                for f in configured:
                    clean = cls.normalize_format(f)
                    if clean in cls.FORMAT_SPECS and clean not in result:
                        result.append(clean)
                if result:
                    return result
            # Standard premium supported formats
            return [
                AudioFormat.MP3, AudioFormat.FLAC, AudioFormat.M4A, AudioFormat.ALAC,
                AudioFormat.OPUS, AudioFormat.OGG, AudioFormat.WAV, AudioFormat.AIFF,
                AudioFormat.WAVPACK, AudioFormat.APE, AudioFormat.AC3, AudioFormat.EAC3
            ]
        else:
            configured = getattr(Config, "FREE_AUDIO_FORMATS", None)
            if configured and isinstance(configured, list):
                result = [cls.normalize_format(f) for f in configured if cls.normalize_format(f) in cls.FORMAT_SPECS]
                if result:
                    return result
            return [AudioFormat.MP3]

    @classmethod
    def get_allowed_qualities(cls, format_type: str, is_premium: bool = False) -> List[Union[int, str]]:
        """Return allowed quality levels for a given format and user tier."""
        fmt = cls.normalize_format(format_type)

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
            if is_premium:
                return list(cls.FLAC_QUALITIES)
            return ["low"]

        elif fmt in (AudioFormat.M4A, AudioFormat.M4A_AAC, AudioFormat.AAC):
            if is_premium:
                configured = getattr(Config, "PREMIUM_M4A_QUALITIES", None)
                if configured and isinstance(configured, list):
                    return [int(q) for q in configured if str(q).isdigit()]
                return list(cls.M4A_QUALITIES)
            return [128]

        elif fmt in (AudioFormat.ALAC, AudioFormat.M4A_ALAC):
            if is_premium:
                return [
                    "16-bit 44.1kHz", "16-bit 48kHz",
                    "24-bit 44.1kHz", "24-bit 48kHz",
                    "24-bit 96kHz", "24-bit 192kHz"
                ]
            return ["16-bit 44.1kHz"]

        elif fmt in (AudioFormat.OPUS, AudioFormat.OGG_OPUS):
            if is_premium:
                return list(cls.OPUS_QUALITIES)
            return [128]

        elif fmt in (AudioFormat.OGG, AudioFormat.OGG_VORBIS):
            if is_premium:
                configured = getattr(Config, "PREMIUM_OGG_QUALITIES", None)
                if configured and isinstance(configured, list):
                    return [int(q) for q in configured if str(q).isdigit()]
                return list(cls.OGG_QUALITIES)
            return [128]

        elif fmt in (AudioFormat.WAV, AudioFormat.AIFF):
            if is_premium:
                return list(cls.WAV_QUALITIES)
            return ["16-bit 44.1kHz"]

        elif fmt in (AudioFormat.WAVPACK, AudioFormat.WV):
            if is_premium:
                return list(cls.WAVPACK_QUALITIES)
            return ["fast"]

        elif fmt == AudioFormat.APE:
            if is_premium:
                return list(cls.APE_QUALITIES)
            return ["fast"]

        elif fmt in (AudioFormat.AC3, AudioFormat.EAC3):
            if is_premium:
                return list(cls.AC3_QUALITIES)
            return [192]

        spec = cls.get_spec(fmt)
        if spec:
            return list(spec.supported_qualities)
        return [cls.get_default_quality(fmt, is_premium)]

    # UI Formats Definition for 2-step interactive keyboard
    FORMAT_UI_LIST = [
        (AudioFormat.MP3, "MP3"),
        (AudioFormat.FLAC, "FLAC"),
        (AudioFormat.M4A_AAC, "M4A AAC"),
        (AudioFormat.M4A_ALAC, "M4A ALAC"),
        (AudioFormat.OGG, "OGG"),
        (AudioFormat.OPUS, "OPUS"),
        (AudioFormat.WAV, "WAV"),
        (AudioFormat.AIFF, "AIFF"),
        (AudioFormat.WAVPACK, "WAVPACK"),
        (AudioFormat.APE, "APE"),
        (AudioFormat.AC3, "AC3"),
        (AudioFormat.EAC3, "E-AC3")
    ]

    # Detailed quality profiles for each format: (internal_val, display_label, callback_slug)
    QUALITY_UI_REGISTRY: Dict[str, List[Tuple[Union[int, str], str, str]]] = {
        AudioFormat.MP3: [
            ("best", "Best Available", "best"),
            (320, "320 kbps", "320"),
            (256, "256 kbps", "256"),
            (224, "224 kbps", "224"),
            (192, "192 kbps", "192"),
            (160, "160 kbps", "160"),
            (128, "128 kbps", "128"),
            (96, "96 kbps", "96"),
            (64, "64 kbps", "64"),
        ],
        AudioFormat.FLAC: [
            ("best", "Best Available", "best"),
            ("preserve", "Preserve Original", "pres"),
            ("24-bit / 192 kHz", "24-bit / 192 kHz", "24_192"),
            ("24-bit / 176.4 kHz", "24-bit / 176.4 kHz", "24_1764"),
            ("24-bit / 96 kHz", "24-bit / 96 kHz", "24_96"),
            ("24-bit / 88.2 kHz", "24-bit / 88.2 kHz", "24_882"),
            ("24-bit / 48 kHz", "24-bit / 48 kHz", "24_48"),
            ("24-bit / 44.1 kHz", "24-bit / 44.1 kHz", "24_441"),
            ("16-bit / 48 kHz", "16-bit / 48 kHz", "16_48"),
            ("16-bit / 44.1 kHz", "16-bit / 44.1 kHz", "16_441"),
        ],
        AudioFormat.M4A_AAC: [
            ("best", "Best Available", "best"),
            (320, "320 kbps", "320"),
            (256, "256 kbps", "256"),
            (224, "224 kbps", "224"),
            (192, "192 kbps", "192"),
            (160, "160 kbps", "160"),
            (128, "128 kbps", "128"),
            (96, "96 kbps", "96"),
            (64, "64 kbps", "64"),
        ],
        AudioFormat.M4A: [
            ("best", "Best Available", "best"),
            (320, "320 kbps", "320"),
            (256, "256 kbps", "256"),
            (224, "224 kbps", "224"),
            (192, "192 kbps", "192"),
            (160, "160 kbps", "160"),
            (128, "128 kbps", "128"),
            (96, "96 kbps", "96"),
            (64, "64 kbps", "64"),
        ],
        AudioFormat.M4A_ALAC: [
            ("best", "Best Available", "best"),
            ("preserve", "Preserve Original", "pres"),
            ("24-bit / 192 kHz", "24-bit / 192 kHz", "24_192"),
            ("24-bit / 96 kHz", "24-bit / 96 kHz", "24_96"),
            ("24-bit / 48 kHz", "24-bit / 48 kHz", "24_48"),
            ("24-bit / 44.1 kHz", "24-bit / 44.1 kHz", "24_441"),
            ("16-bit / 48 kHz", "16-bit / 48 kHz", "16_48"),
            ("16-bit / 44.1 kHz", "16-bit / 44.1 kHz", "16_441"),
        ],
        AudioFormat.ALAC: [
            ("best", "Best Available", "best"),
            ("preserve", "Preserve Original", "pres"),
            ("24-bit / 192 kHz", "24-bit / 192 kHz", "24_192"),
            ("24-bit / 96 kHz", "24-bit / 96 kHz", "24_96"),
            ("24-bit / 48 kHz", "24-bit / 48 kHz", "24_48"),
            ("24-bit / 44.1 kHz", "24-bit / 44.1 kHz", "24_441"),
            ("16-bit / 48 kHz", "16-bit / 48 kHz", "16_48"),
            ("16-bit / 44.1 kHz", "16-bit / 44.1 kHz", "16_441"),
        ],
        AudioFormat.OPUS: [
            ("best", "Best Available", "best"),
            (320, "320 kbps", "320"),
            (256, "256 kbps", "256"),
            (192, "192 kbps", "192"),
            (160, "160 kbps", "160"),
            (128, "128 kbps", "128"),
            (96, "96 kbps", "96"),
            (64, "64 kbps", "64"),
            (48, "48 kbps", "48"),
            (32, "32 kbps", "32"),
        ],
        AudioFormat.OGG: [
            ("best", "Best Available", "best"),
            (500, "500 kbps", "500"),
            (320, "320 kbps", "320"),
            (256, "256 kbps", "256"),
            (224, "224 kbps", "224"),
            (192, "192 kbps", "192"),
            (160, "160 kbps", "160"),
            (128, "128 kbps", "128"),
            (96, "96 kbps", "96"),
            (64, "64 kbps", "64"),
        ],
        AudioFormat.OGG_VORBIS: [
            ("best", "Best Available", "best"),
            (500, "500 kbps", "500"),
            (320, "320 kbps", "320"),
            (256, "256 kbps", "256"),
            (224, "224 kbps", "224"),
            (192, "192 kbps", "192"),
            (160, "160 kbps", "160"),
            (128, "128 kbps", "128"),
            (96, "96 kbps", "96"),
            (64, "64 kbps", "64"),
        ],
        AudioFormat.WAV: [
            ("best", "Best Available", "best"),
            ("preserve", "Preserve Original", "pres"),
            ("32-bit Float / 192 kHz", "32-bit Float / 192 kHz", "32f_192"),
            ("32-bit Float / 96 kHz", "32-bit Float / 96 kHz", "32f_96"),
            ("32-bit Float / 48 kHz", "32-bit Float / 48 kHz", "32f_48"),
            ("24-bit / 192 kHz", "24-bit / 192 kHz", "24_192"),
            ("24-bit / 176.4 kHz", "24-bit / 176.4 kHz", "24_1764"),
            ("24-bit / 96 kHz", "24-bit / 96 kHz", "24_96"),
            ("24-bit / 48 kHz", "24-bit / 48 kHz", "24_48"),
            ("24-bit / 44.1 kHz", "24-bit / 44.1 kHz", "24_441"),
            ("16-bit / 48 kHz", "16-bit / 48 kHz", "16_48"),
            ("16-bit / 44.1 kHz", "16-bit / 44.1 kHz", "16_441"),
        ],
        AudioFormat.AIFF: [
            ("best", "Best Available", "best"),
            ("preserve", "Preserve Original", "pres"),
            ("32-bit Float / 192 kHz", "32-bit Float / 192 kHz", "32f_192"),
            ("32-bit Float / 96 kHz", "32-bit Float / 96 kHz", "32f_96"),
            ("32-bit Float / 48 kHz", "32-bit Float / 48 kHz", "32f_48"),
            ("24-bit / 192 kHz", "24-bit / 192 kHz", "24_192"),
            ("24-bit / 176.4 kHz", "24-bit / 176.4 kHz", "24_1764"),
            ("24-bit / 96 kHz", "24-bit / 96 kHz", "24_96"),
            ("24-bit / 48 kHz", "24-bit / 48 kHz", "24_48"),
            ("24-bit / 44.1 kHz", "24-bit / 44.1 kHz", "24_441"),
            ("16-bit / 48 kHz", "16-bit / 48 kHz", "16_48"),
            ("16-bit / 44.1 kHz", "16-bit / 44.1 kHz", "16_441"),
        ],
        AudioFormat.WAVPACK: [
            ("best", "Best Available", "best"),
            ("preserve", "Preserve Original", "pres"),
            ("lossless", "Lossless", "lossless"),
            ("hybrid", "Hybrid", "hybrid"),
        ],
        AudioFormat.WV: [
            ("best", "Best Available", "best"),
            ("preserve", "Preserve Original", "pres"),
            ("lossless", "Lossless", "lossless"),
            ("hybrid", "Hybrid", "hybrid"),
        ],
        AudioFormat.APE: [
            ("best", "Best Available", "best"),
            ("preserve", "Preserve Original", "pres"),
            ("insane", "Insane", "insane"),
            ("extra high", "Extra High", "extra_high"),
            ("high", "High", "high"),
            ("normal", "Normal", "normal"),
            ("fast", "Fast", "fast"),
        ],
        AudioFormat.AC3: [
            ("best", "Best Available", "best"),
            (640, "640 kbps", "640"),
            (448, "448 kbps", "448"),
            (384, "384 kbps", "384"),
            (256, "256 kbps", "256"),
            (224, "224 kbps", "224"),
            (192, "192 kbps", "192"),
        ],
        AudioFormat.EAC3: [
            ("best", "Best Available", "best"),
            (1024, "1024 kbps", "1024"),
            (640, "640 kbps", "640"),
            (448, "448 kbps", "448"),
            (384, "384 kbps", "384"),
            (256, "256 kbps", "256"),
            (224, "224 kbps", "224"),
        ]
    }

    @classmethod
    def get_ui_formats(cls, is_premium: bool = True, provider_id: Optional[str] = None) -> List[Tuple[str, str]]:
        """Return format tuples (format_key, button_label) available for UI display."""
        if provider_id:
            return DownloadCompatibilityEngine.get_supported_formats(provider_id, is_premium=is_premium)

        allowed = cls.get_allowed_formats(is_premium=is_premium)
        res = []
        for fmt_key, label in cls.FORMAT_UI_LIST:
            clean = cls.normalize_format(fmt_key)
            is_allowed = (
                clean in allowed
                or fmt_key in allowed
                or not is_premium
                or (fmt_key in (AudioFormat.M4A_AAC, AudioFormat.M4A_ALAC, AudioFormat.ALAC) and (AudioFormat.M4A in allowed or AudioFormat.ALAC in allowed))
                or (fmt_key == AudioFormat.WAVPACK and (AudioFormat.WV in allowed or AudioFormat.WAVPACK in allowed))
            )
            if is_allowed:
                # Check encoder availability
                spec = cls.get_spec(fmt_key)
                if spec and not cls.is_encoder_available(spec.ffmpeg_encoder):
                    continue
                res.append((fmt_key, label))
        if not res:
            res = [(AudioFormat.MP3, "MP3")]
        return res

    @classmethod
    def get_ui_qualities(cls, format_type: str, is_premium: bool = True, provider_id: Optional[str] = None) -> List[Tuple[Union[int, str], str, str]]:
        """Return list of (quality_value, display_label, callback_slug) for the given format and optional provider."""
        if provider_id:
            return DownloadCompatibilityEngine.resolve_quality_profiles(provider_id, format_type, is_premium=is_premium)

        fmt = cls.normalize_format(format_type)
        items = cls.QUALITY_UI_REGISTRY.get(fmt)
        if not items:
            items = cls.QUALITY_UI_REGISTRY.get(str(format_type).lower().strip(), [])
        if not items:
            return [("best", "Best Available", "best"), (320, "320 kbps", "320")]

        if not is_premium:
            # Filter qualities according to free configuration if applicable
            allowed = cls.get_allowed_qualities(fmt, is_premium=False)
            filtered = []
            for q_val, label, slug in items:
                if str(q_val).isdigit() and int(q_val) in allowed:
                    filtered.append((q_val, label, slug))
                elif q_val in allowed or q_val == "best":
                    filtered.append((q_val, label, slug))
            return filtered or items
        return items

    @classmethod
    def get_quality_by_slug(cls, format_type: str, slug: str) -> Union[int, str]:
        """Convert a callback slug back to its canonical quality value."""
        fmt = cls.normalize_format(format_type)
        items = cls.get_ui_qualities(fmt, is_premium=True)
        clean_slug = str(slug).strip().lower()
        for q_val, label, s in items:
            if s.lower() == clean_slug:
                return q_val
        if clean_slug.isdigit():
            return int(clean_slug)
        return "best"

    @classmethod
    def get_slug_by_quality(cls, format_type: str, quality_value: Union[int, str]) -> str:
        """Convert a quality value to its callback slug."""
        fmt = cls.normalize_format(format_type)
        items = cls.get_ui_qualities(fmt, is_premium=True)
        q_norm = cls.normalize_quality(fmt, quality_value)
        for q_val, label, s in items:
            if cls.are_qualities_equal(q_val, q_norm):
                return s
        if str(quality_value).isdigit():
            return str(quality_value)
        return "best"

    @classmethod
    def _extract_scalar_quality(cls, q_dict: dict) -> Any:
        """Extract canonical scalar or string quality representation from structured quality dict."""
        if not isinstance(q_dict, dict):
            return q_dict
        mode = q_dict.get("mode")
        if mode in ("preserve", "preserveoriginal", "original"):
            return "preserve"
        if mode in ("auto", "best", "bestavailable"):
            return "best"
        if "bit_depth" in q_dict and "sample_rate" in q_dict:
            depth = q_dict["bit_depth"]
            rate = q_dict["sample_rate"]
            if rate % 1000 == 0:
                rate_str = f"{rate // 1000} kHz" if rate >= 1000 else f"{rate} Hz"
            else:
                rate_str = f"{rate / 1000:g} kHz"
            return f"{depth}-bit / {rate_str}"
        if "bitrate_kbps" in q_dict:
            return q_dict["bitrate_kbps"]
        if "bitrate" in q_dict:
            return q_dict["bitrate"]
        if "compression" in q_dict:
            return q_dict["compression"]
        return "best"

    @classmethod
    def are_qualities_equal(cls, q1: Any, q2: Any) -> bool:
        """Robust comparison between two quality values (handling dicts, spacing, slashes, kbps suffixes)."""
        if q1 is None or q2 is None:
            return q1 == q2
        if isinstance(q1, dict):
            q1 = cls._extract_scalar_quality(q1)
        if isinstance(q2, dict):
            q2 = cls._extract_scalar_quality(q2)
        if str(q1).isdigit() and str(q2).isdigit():
            return int(q1) == int(q2)
        s1 = str(q1).lower().replace(" ", "").replace("/", "").replace("kbps", "").replace("-", "")
        s2 = str(q2).lower().replace(" ", "").replace("/", "").replace("kbps", "").replace("-", "")
        if s1 in ("best", "bestavailable") and s2 in ("best", "bestavailable"):
            return True
        if s1 in ("preserve", "preserveoriginal", "original") and s2 in ("preserve", "preserveoriginal", "original"):
            return True
        return s1 == s2

    @classmethod
    def is_quality_compatible(cls, format_type: str, quality: Any) -> bool:
        """Check if a quality value is valid and supported for a given format."""
        if quality is None:
            return False
        if isinstance(quality, dict):
            quality = cls._extract_scalar_quality(quality)
        fmt = cls.normalize_format(format_type)
        items = cls.get_ui_qualities(fmt, is_premium=True)
        for q_val, label, slug in items:
            if cls.are_qualities_equal(q_val, quality):
                return True
        return False

    @classmethod
    def normalize_quality(cls, format_type: str, quality: Any) -> Union[int, str]:
        """Normalize quality value to the canonical representation in QUALITY_UI_REGISTRY."""
        if isinstance(quality, dict):
            quality = cls._extract_scalar_quality(quality)
        fmt = cls.normalize_format(format_type)
        items = cls.get_ui_qualities(fmt, is_premium=True)
        for q_val, label, slug in items:
            if cls.are_qualities_equal(q_val, quality):
                return q_val
        if str(quality).isdigit():
            return int(quality)
        return cls.get_default_quality(fmt, is_premium=True)

    @classmethod
    def build_quality_profile_slug(cls, format_type: str, quality: Any) -> str:
        """Build canonical quality profile slug (e.g., flac_24bit_96khz, mp3_320kbps)."""
        fmt = cls.normalize_format(format_type)
        if isinstance(quality, dict):
            quality = cls._extract_scalar_quality(quality)
        q_norm = cls.normalize_quality(fmt, quality)
        q_str = str(q_norm).strip().lower()

        if fmt in (AudioFormat.FLAC, AudioFormat.WAV, AudioFormat.AIFF, AudioFormat.ALAC, AudioFormat.M4A_ALAC):
            if q_str in ("preserve", "pres", "original"):
                return f"{fmt}_preserve_original"
            if q_str in ("best", "best available"):
                return f"{fmt}_best_available"
            depth, rate = cls.parse_wav_quality(str(q_norm))
            if rate % 1000 == 0:
                rate_str = f"{rate // 1000}khz"
            else:
                rate_str = f"{rate / 1000:g}khz"
            return f"{fmt}_{depth}bit_{rate_str}"
        elif fmt in (AudioFormat.APE, AudioFormat.WAVPACK, AudioFormat.WV):
            slug = cls.get_slug_by_quality(fmt, q_norm)
            return f"{fmt}_{slug}"
        else:
            if q_str in ("best", "best available"):
                return f"{fmt}_best_available"
            if q_str in ("preserve", "pres", "original"):
                return f"{fmt}_preserve_original"
            br = int(q_norm) if str(q_norm).isdigit() else 320
            return f"{fmt}_{br}kbps"

    @classmethod
    def build_structured_quality(cls, format_type: str, quality: Any) -> Dict[str, Any]:
        """Build structured audio_quality dictionary (e.g. {'mode': 'fixed', 'bit_depth': 24, 'sample_rate': 96000})."""
        fmt = cls.normalize_format(format_type)
        if isinstance(quality, dict):
            quality = cls._extract_scalar_quality(quality)
        q_norm = cls.normalize_quality(fmt, quality)
        q_str = str(q_norm).strip().lower()

        if fmt in (AudioFormat.FLAC, AudioFormat.WAV, AudioFormat.AIFF, AudioFormat.ALAC, AudioFormat.M4A_ALAC):
            if q_str in ("preserve", "pres", "original"):
                return {"mode": "preserve", "bit_depth": 24, "sample_rate": 48000}
            if q_str in ("best", "best available"):
                return {"mode": "auto", "bit_depth": 24, "sample_rate": 48000}
            depth, rate = cls.parse_wav_quality(str(q_norm))
            return {
                "mode": "fixed",
                "bit_depth": depth,
                "sample_rate": rate
            }
        elif fmt in (AudioFormat.APE, AudioFormat.WAVPACK, AudioFormat.WV):
            if q_str in ("preserve", "pres", "original"):
                return {"mode": "preserve", "compression": "lossless", "lossless": True}
            if q_str in ("best", "best available"):
                return {"mode": "auto", "compression": "lossless", "lossless": True}
            return {
                "mode": "fixed",
                "compression": q_str,
                "lossless": True
            }
        else:
            if q_str in ("best", "best available"):
                return {"mode": "auto", "bitrate_kbps": 320, "sample_rate": 44100}
            if q_str in ("preserve", "pres", "original"):
                return {"mode": "preserve", "bitrate_kbps": 320, "sample_rate": 44100}
            br = int(q_norm) if str(q_norm).isdigit() else 320
            return {
                "mode": "fixed",
                "bitrate_kbps": br,
                "sample_rate": 44100
            }

    @classmethod
    def validate_and_normalize(cls, format_type: str, quality: Any, is_premium: bool = True) -> Tuple[str, Union[int, str], str, str]:
        """
        Validate format and quality combination.
        Returns: (normalized_format, normalized_quality, codec, quality_profile_slug)
        """
        if isinstance(quality, dict):
            quality = cls._extract_scalar_quality(quality)
        norm_fmt = cls.normalize_format(format_type)
        spec = cls.get_spec(norm_fmt)
        codec = spec.codec if spec else norm_fmt

        if not cls.is_quality_compatible(norm_fmt, quality):
            norm_q = cls.get_default_quality(norm_fmt, is_premium=is_premium)
        else:
            norm_q = cls.normalize_quality(norm_fmt, quality)

        profile_slug = cls.build_quality_profile_slug(norm_fmt, norm_q)
        return norm_fmt, norm_q, codec, profile_slug

    @classmethod
    def get_default_quality(cls, format_type: str, is_premium: bool = False) -> Union[int, str]:
        """Return default quality level for a format and user tier."""
        fmt = cls.normalize_format(format_type)
        spec = cls.get_spec(fmt)

        if fmt in (AudioFormat.MP3, AudioFormat.M4A, AudioFormat.M4A_AAC, AudioFormat.AAC):
            return 320 if is_premium else 128
        elif fmt in (AudioFormat.FLAC, AudioFormat.ALAC, AudioFormat.M4A_ALAC, AudioFormat.WAV, AudioFormat.AIFF):
            return "24-bit / 48 kHz" if is_premium else "16-bit / 44.1 kHz"
        elif fmt in (AudioFormat.OPUS, AudioFormat.OGG_OPUS):
            return 160 if is_premium else 128
        elif fmt in (AudioFormat.OGG, AudioFormat.OGG_VORBIS):
            return 256 if is_premium else 128
        elif fmt in (AudioFormat.WAVPACK, AudioFormat.WV):
            return "lossless"
        elif fmt == AudioFormat.APE:
            return "high" if is_premium else "normal"
        elif fmt in (AudioFormat.AC3, AudioFormat.EAC3):
            return 384 if is_premium else 192

        if spec:
            return spec.default_quality
        return 320

    @classmethod
    def is_format_allowed(cls, format_type: str, is_premium: bool = False) -> bool:
        allowed = cls.get_allowed_formats(is_premium=is_premium)
        clean = cls.normalize_format(format_type)
        return clean in allowed or str(format_type).lower().strip() in allowed

    @classmethod
    def is_quality_allowed(cls, format_type: str, quality, is_premium: bool = False) -> bool:
        return cls.is_quality_compatible(format_type, quality)

    @classmethod
    def parse_wav_quality(cls, quality_str: str) -> Tuple[int, int]:
        """
        Parse WAV/AIFF/FLAC/ALAC quality string into (bit_depth, sample_rate).
        Examples: '16-bit / 44.1 kHz' -> (16, 44100), '24-bit / 96 kHz' -> (24, 96000), '32-bit Float / 192 kHz' -> (32, 192000).
        """
        q_str = str(quality_str).strip()
        q_clean = q_str.replace(" / ", " ").replace("/", " ")
        if q_str in cls.WAV_PARAMS:
            return cls.WAV_PARAMS[q_str]
        if q_clean in cls.WAV_PARAMS:
            return cls.WAV_PARAMS[q_clean]

        for k, v in cls.WAV_PARAMS.items():
            if k.lower() == q_clean.lower() or k.lower() == q_str.lower():
                return v

        # Fallback parsing
        bit_depth = 32 if "32" in q_str else (24 if "24" in q_str else 16)
        if "192" in q_str or "192000" in q_str:
            sample_rate = 192000
        elif "176" in q_str or "176400" in q_str:
            sample_rate = 176400
        elif "96" in q_str or "96000" in q_str:
            sample_rate = 96000
        elif "88" in q_str or "88200" in q_str:
            sample_rate = 88200
        elif "48" in q_str or "48000" in q_str:
            sample_rate = 48000
        else:
            sample_rate = 44100

        return bit_depth, sample_rate

    @classmethod
    def format_quality_label(cls, format_type: str, quality: Union[int, str, dict]) -> str:
        """Returns clean human-readable quality label for Telegram UI."""
        if isinstance(quality, dict):
            quality = cls._extract_scalar_quality(quality)
        elif isinstance(quality, str) and quality.strip().startswith("{") and quality.strip().endswith("}"):
            try:
                import ast
                parsed = ast.literal_eval(quality.strip())
                if isinstance(parsed, dict):
                    quality = cls._extract_scalar_quality(parsed)
            except Exception:
                quality = ""

        fmt = cls.normalize_format(format_type)
        q_str = str(quality).strip()

        if q_str.lower() in ("best", "best available"):
            return "Best Available ✨"
        if q_str.lower() in ("original", "preserve", "preserve original", "pres"):
            return "Preserve Original 🎯"

        items = cls.get_ui_qualities(fmt, is_premium=True)
        for q_val, label, slug in items:
            if cls.are_qualities_equal(q_val, quality):
                return label

        if str(quality).isdigit():
            return f"{quality} kbps"
        if "{" in q_str or "}" in q_str or q_str.lower() in ("none", "null", "{}"):
            return ""
        return str(quality)


    @classmethod
    def get_ffmpeg_args(cls, ffmpeg_bin: str, input_path: str, output_path: str,
                        format_type: str, quality: Union[int, str, dict]) -> List[str]:
        """
        Generate safe, structured list of arguments for FFmpeg conversion without shell=True.
        Supports extended audio formats, Hi-Res sampling, bit depths, and codecs.
        """
        if isinstance(quality, dict):
            quality = cls._extract_scalar_quality(quality)
        fmt = cls.normalize_format(format_type)
        base_cmd = [ffmpeg_bin, "-y", "-i", input_path]
        q_str = str(quality).strip().lower()

        # 1. MP3 Transcoding (libmp3lame)
        if fmt == AudioFormat.MP3:
            bitrate = f"{quality}k" if str(quality).isdigit() else "320k"
            return base_cmd + [
                "-codec:a", "libmp3lame",
                "-b:a", bitrate,
                "-q:a", "0",
                "-vn", output_path
            ]

        # 2. FLAC Transcoding
        elif fmt == AudioFormat.FLAC:
            compression = "5"
            cmd_opts = ["-codec:a", "flac"]

            if q_str in ("low", "1"):
                compression = "1"
            elif q_str in ("high", "8"):
                compression = "8"
            elif q_str.isdigit() and int(q_str) <= 8:
                compression = str(q_str)
            elif "bit" in q_str:
                depth, rate = cls.parse_wav_quality(q_str)
                sample_fmt = "s32" if depth == 24 else "s16"
                cmd_opts.extend(["-sample_fmt", sample_fmt, "-ar", str(rate)])
                compression = "8"

            cmd_opts.extend(["-compression_level", compression, "-vn", output_path])
            return base_cmd + cmd_opts

        # 3. M4A / AAC Transcoding
        elif fmt in (AudioFormat.M4A, AudioFormat.M4A_AAC, AudioFormat.AAC):
            bitrate = f"{quality}k" if str(quality).isdigit() else "256k"
            return base_cmd + [
                "-codec:a", "aac",
                "-b:a", bitrate,
                "-vn", output_path
            ]

        # 4. ALAC Transcoding (Apple Lossless in M4A/MP4)
        elif fmt in (AudioFormat.ALAC, AudioFormat.M4A_ALAC):
            cmd_opts = ["-codec:a", "alac"]
            if "bit" in q_str:
                depth, rate = cls.parse_wav_quality(q_str)
                sample_fmt = "s32p" if depth == 24 else "s16p"
                cmd_opts.extend(["-sample_fmt", sample_fmt, "-ar", str(rate)])
            cmd_opts.extend(["-vn", output_path])
            return base_cmd + cmd_opts

        # 5. Opus Transcoding (libopus in .opus or .ogg)
        elif fmt in (AudioFormat.OPUS, AudioFormat.OGG_OPUS):
            bitrate = f"{quality}k" if str(quality).isdigit() else "160k"
            return base_cmd + [
                "-codec:a", "libopus",
                "-b:a", bitrate,
                "-vbr", "on",
                "-vn", output_path
            ]

        # 6. OGG Vorbis Transcoding (libvorbis)
        elif fmt in (AudioFormat.OGG, AudioFormat.OGG_VORBIS):
            q_map = {
                64: "1",
                96: "2",
                128: "4",
                160: "5",
                192: "6",
                256: "8",
                320: "10",
                500: "10"
            }
            q_int = int(quality) if str(quality).isdigit() else 192
            q_scale = q_map.get(q_int, "6")
            return base_cmd + [
                "-codec:a", "libvorbis",
                "-q:a", q_scale,
                "-vn", output_path
            ]

        # 7. WAV Transcoding (PCM Little-Endian)
        elif fmt == AudioFormat.WAV:
            bit_depth, sample_rate = cls.parse_wav_quality(str(quality))
            if "float" in q_str or bit_depth == 32:
                codec = "pcm_f32le"
            elif bit_depth == 24:
                codec = "pcm_s24le"
            else:
                codec = "pcm_s16le"

            return base_cmd + [
                "-codec:a", codec,
                "-ar", str(sample_rate),
                "-vn", output_path
            ]

        # 8. AIFF Transcoding (PCM Big-Endian)
        elif fmt == AudioFormat.AIFF:
            bit_depth, sample_rate = cls.parse_wav_quality(str(quality))
            if "float" in q_str or bit_depth == 32:
                codec = "pcm_f32be"
            elif bit_depth == 24:
                codec = "pcm_s24be"
            else:
                codec = "pcm_s16be"

            return base_cmd + [
                "-codec:a", codec,
                "-ar", str(sample_rate),
                "-vn", output_path
            ]

        # 9. WavPack Transcoding
        elif fmt in (AudioFormat.WAVPACK, AudioFormat.WV):
            return base_cmd + [
                "-codec:a", "wavpack",
                "-vn", output_path
            ]

        # 10. Monkey's Audio (APE)
        elif fmt == AudioFormat.APE:
            # If native ape encoder is present in ffmpeg, use it; otherwise fallback to flac / wavpack
            encoders = cls.get_available_ffmpeg_encoders(ffmpeg_bin)
            codec = "ape" if "ape" in encoders else "flac"
            return base_cmd + [
                "-codec:a", codec,
                "-vn", output_path
            ]

        # 11. AC3 (Dolby Digital)
        elif fmt == AudioFormat.AC3:
            bitrate = f"{quality}k" if str(quality).isdigit() else "384k"
            return base_cmd + [
                "-codec:a", "ac3",
                "-b:a", bitrate,
                "-vn", output_path
            ]

        # 12. E-AC3 (Dolby Digital Plus)
        elif fmt == AudioFormat.EAC3:
            bitrate = f"{quality}k" if str(quality).isdigit() else "448k"
            return base_cmd + [
                "-codec:a", "eac3",
                "-b:a", bitrate,
                "-vn", output_path
            ]

        # Default fallback to MP3
        else:
            return base_cmd + [
                "-codec:a", "libmp3lame",
                "-b:a", "320k",
                "-vn", output_path
            ]

    get_format_spec = get_spec
    get_available_encoders = get_available_ffmpeg_encoders

    @classmethod
    def build_ffmpeg_args(cls, input_path: str, output_path: str,
                           format_type: str, quality: Union[int, str] = None,
                           ffmpeg_bin: str = "ffmpeg") -> List[str]:
        return cls.get_ffmpeg_args(ffmpeg_bin, input_path, output_path, format_type, quality)

    @classmethod
    def generate_safe_filename(cls, title: str, format_type: str) -> str:
        import re
        ext = cls.get_extension(format_type)
        clean_title = re.sub(r'[\\/*?:"<>|]', "", title).strip()
        if not clean_title:
            clean_title = "audio"
        return f"{clean_title}{ext}"


class DownloadCompatibilityEngine:
    """
    Centralized Compatibility Engine & Single Source of Truth for:
    - Implemented Provider Registry & Availability Status
    - Provider-Specific Supported Audio Formats & Encoders
    - Format & Provider Compatible Audio Quality Profiles
    - Download Configuration Validation & Capability Introspection
    """

    PROVIDER_SPECS: Dict[str, Dict[str, Any]] = {
        "auto": {
            "display_name": "Auto Select",
            "emoji": "",
            "is_lossless": True,
            "max_sample_rate": 192000,
            "max_bit_depth": 24,
            "default_format": AudioFormat.MP3,
            "default_quality": 320,
            "source_formats": ["flac", "wav", "mp3", "opus", "aac", "ogg"]
        },
        "spotify": {
            "display_name": "Spotify",
            "emoji": "",
            "is_lossless": False,
            "max_sample_rate": 48000,
            "max_bit_depth": 16,
            "default_format": AudioFormat.MP3,
            "default_quality": 320,
            "source_formats": ["ogg", "aac"]
        },
        "youtubemusic": {
            "display_name": "YouTube Music",
            "emoji": "",
            "is_lossless": False,
            "max_sample_rate": 48000,
            "max_bit_depth": 16,
            "default_format": AudioFormat.MP3,
            "default_quality": 320,
            "source_formats": ["opus", "aac"]
        },
        "youtube": {
            "display_name": "YouTube",
            "emoji": "",
            "is_lossless": False,
            "max_sample_rate": 48000,
            "max_bit_depth": 16,
            "default_format": AudioFormat.MP3,
            "default_quality": 320,
            "source_formats": ["opus", "aac"]
        },
        "deezer": {
            "display_name": "Deezer",
            "emoji": "",
            "is_lossless": True,
            "max_sample_rate": 48000,
            "max_bit_depth": 16,
            "default_format": AudioFormat.FLAC,
            "default_quality": "16-bit / 44.1 kHz",
            "source_formats": ["flac", "mp3"]
        },
        "applemusic": {
            "display_name": "Apple Music",
            "emoji": "",
            "is_lossless": True,
            "max_sample_rate": 48000,
            "max_bit_depth": 24,
            "default_format": AudioFormat.M4A_ALAC,
            "default_quality": "24-bit / 48 kHz",
            "source_formats": ["alac", "aac"]
        },
        "tidal": {
            "display_name": "TIDAL",
            "emoji": "",
            "is_lossless": True,
            "max_sample_rate": 192000,
            "max_bit_depth": 24,
            "default_format": AudioFormat.FLAC,
            "default_quality": "24-bit / 96 kHz",
            "source_formats": ["flac", "mqa", "aac"]
        },
        "qobuz": {
            "display_name": "Qobuz",
            "emoji": "",
            "is_lossless": True,
            "max_sample_rate": 192000,
            "max_bit_depth": 24,
            "default_format": AudioFormat.FLAC,
            "default_quality": "24-bit / 96 kHz",
            "source_formats": ["flac", "mp3"]
        },
        "amazonmusic": {
            "display_name": "Amazon Music",
            "emoji": "",
            "is_lossless": True,
            "max_sample_rate": 192000,
            "max_bit_depth": 24,
            "default_format": AudioFormat.FLAC,
            "default_quality": "24-bit / 96 kHz",
            "source_formats": ["flac", "opus", "mp3"]
        },
        "soundcloud": {
            "display_name": "SoundCloud",
            "emoji": "",
            "is_lossless": False,
            "max_sample_rate": 48000,
            "max_bit_depth": 16,
            "default_format": AudioFormat.MP3,
            "default_quality": 320,
            "source_formats": ["mp3", "opus"]
        },
        "jiosaavn": {
            "display_name": "JioSaavn",
            "emoji": "",
            "is_lossless": False,
            "max_sample_rate": 48000,
            "max_bit_depth": 16,
            "default_format": AudioFormat.M4A_AAC,
            "default_quality": 320,
            "source_formats": ["aac", "mp3"]
        },
        "pandora": {
            "display_name": "Pandora",
            "emoji": "",
            "is_lossless": False,
            "max_sample_rate": 48000,
            "max_bit_depth": 16,
            "default_format": AudioFormat.MP3,
            "default_quality": 192,
            "source_formats": ["aac", "mp3"]
        },
        "archive": {
            "display_name": "Internet Archive",
            "emoji": "",
            "is_lossless": True,
            "max_sample_rate": 48000,
            "max_bit_depth": 16,
            "default_format": AudioFormat.FLAC,
            "default_quality": "16-bit / 44.1 kHz",
            "source_formats": ["flac", "wav", "mp3"]
        },
        "bandcamp": {
            "display_name": "Bandcamp",
            "emoji": "",
            "is_lossless": True,
            "max_sample_rate": 48000,
            "max_bit_depth": 24,
            "default_format": AudioFormat.FLAC,
            "default_quality": "24-bit / 48 kHz",
            "source_formats": ["flac", "aiff", "wav", "mp3"]
        },
    }

    PROVIDERS = PROVIDER_SPECS
    PROVIDER_CAPABILITIES = PROVIDER_SPECS

    PROVIDER_ALIASES = {
        "sp": "spotify",
        "spotify_web": "spotify",
        "spotifyweb": "spotify",
        "yt": "youtube",
        "ytm": "youtubemusic",
        "ytmusic": "youtubemusic",
        "youtube_music": "youtubemusic",
        "dz": "deezer",
        "apple": "applemusic",
        "itunes": "applemusic",
        "apple_music": "applemusic",
        "amazon": "amazonmusic",
        "amz": "amazonmusic",
        "amazon_music": "amazonmusic",
        "sc": "soundcloud",
        "saavn": "jiosaavn",
        "jio_saavn": "jiosaavn",
        "ia": "archive",
        "archive_org": "archive",
        "internet_archive": "archive",
        "internetarchive": "archive",
        "bc": "bandcamp",
        "automatic": "auto",
        "smart": "auto"
    }

    @classmethod
    def normalize_provider_id(cls, provider_id: Optional[str]) -> str:
        """Normalize provider identifier to canonical key."""
        if not provider_id:
            return "auto"
        clean = str(provider_id).strip().lower()
        return cls.PROVIDER_ALIASES.get(clean, clean)

    @classmethod
    def get_provider_spec(cls, provider_id: str) -> Dict[str, Any]:
        """Get capability and metadata specification for a provider."""
        p_id = cls.normalize_provider_id(provider_id)
        if p_id in cls.PROVIDER_SPECS:
            return cls.PROVIDER_SPECS[p_id]
        from utils.branding import get_provider_display_name
        return {
            "display_name": get_provider_display_name(p_id),
            "emoji": "",
            "is_lossless": False,
            "max_sample_rate": 48000,
            "max_bit_depth": 16,
            "default_format": AudioFormat.MP3,
            "default_quality": 320,
            "source_formats": ["mp3"]
        }

    @classmethod
    def get_display_name(cls, provider_id: str) -> str:
        """Return human-readable display name for provider."""
        from utils.branding import get_provider_display_name
        return get_provider_display_name(provider_id)

    @classmethod
    def is_provider_usable(cls, provider_id: str) -> bool:
        """Validate if provider is implemented, registered, and currently enabled."""
        p_id = cls.normalize_provider_id(provider_id)
        if p_id == "auto":
            return True
        try:
            from utils.providers.registry import ProviderRegistry
            return ProviderRegistry.is_registered(p_id) and ProviderRegistry.is_enabled(p_id)
        except Exception:
            return p_id in cls.PROVIDER_SPECS

    @classmethod
    def get_available_providers(cls, is_premium: bool = True) -> List[Tuple[str, str, str, bool]]:
        """
        Return list of all available candidate providers:
        [(provider_id, display_name, emoji, is_usable)]
        Orders prioritized candidate providers first.
        """
        # Desired UI candidate order
        ordered_candidates = [
            "spotify", "youtubemusic", "deezer", "applemusic",
            "tidal", "qobuz", "amazonmusic", "soundcloud",
            "pandora", "jiosaavn", "bandcamp", "archive", "youtube", "auto"
        ]

        result = []
        for p_id in ordered_candidates:
            spec = cls.get_provider_spec(p_id)
            usable = cls.is_provider_usable(p_id)
            result.append((p_id, spec["display_name"], spec.get("emoji", ""), usable))

        return result

    @classmethod
    def get_supported_formats(cls, provider_id: str, is_premium: bool = True) -> List[Tuple[str, str]]:
        """
        Return list of supported audio formats (format_id, display_label) for the given provider.
        Distinguishes lossless vs lossy capabilities and verifies host FFmpeg encoder support.
        """
        p_id = cls.normalize_provider_id(provider_id)
        spec = cls.get_provider_spec(p_id)

        if not is_premium:
            # Free tier: restricted formats (MP3 by default)
            allowed = AudioProfile.get_allowed_formats(is_premium=False)
            res = []
            for fmt_key, label in AudioProfile.FORMAT_UI_LIST:
                if AudioProfile.normalize_format(fmt_key) in allowed or fmt_key in allowed:
                    f_spec = AudioProfile.get_spec(fmt_key)
                    if f_spec and AudioProfile.is_encoder_available(f_spec.ffmpeg_encoder):
                        res.append((fmt_key, label))
            return res or [(AudioFormat.MP3, "MP3")]

        # Premium Tier: provider-specific format resolution
        formats = []
        for fmt_key, label in AudioProfile.FORMAT_UI_LIST:
            norm_fmt = AudioProfile.normalize_format(fmt_key)
            f_spec = AudioProfile.get_spec(fmt_key)

            # Check FFmpeg encoder availability
            if f_spec and not AudioProfile.is_encoder_available(f_spec.ffmpeg_encoder):
                continue

            # Provider-specific format filtering:
            # Apple Music prioritizes M4A ALAC & M4A AAC
            if p_id == "applemusic" and fmt_key in (AudioFormat.WAVPACK, AudioFormat.APE):
                continue
            # Pandora / SoundCloud lossy sources omit specialized niche lossless containers
            if p_id in ("pandora", "soundcloud") and fmt_key in (AudioFormat.WAVPACK, AudioFormat.APE, AudioFormat.AIFF, AudioFormat.EAC3):
                continue

            formats.append((fmt_key, label))

        if not formats:
            formats = [(AudioFormat.MP3, "MP3"), (AudioFormat.FLAC, "FLAC"), (AudioFormat.M4A_AAC, "M4A AAC")]
        return formats

    @classmethod
    def resolve_quality_profiles(cls, provider_id: str, format_type: str, is_premium: bool = True) -> List[Tuple[Union[int, str], str, str]]:
        """
        Dynamically resolve compatible quality profiles for a given provider and output format.
        Prevents advertising genuine Hi-Res (24/192) for lossy-only sources.
        """
        p_id = cls.normalize_provider_id(provider_id)
        spec = cls.get_provider_spec(p_id)
        fmt = AudioProfile.normalize_format(format_type)
        items = AudioProfile.QUALITY_UI_REGISTRY.get(fmt, [])
        if not items:
            items = AudioProfile.QUALITY_UI_REGISTRY.get(str(format_type).lower().strip(), [])

        if not items:
            return [("best", "Best Available", "best"), (320, "320 kbps", "320")]

        if not is_premium:
            allowed = AudioProfile.get_allowed_qualities(fmt, is_premium=False)
            filtered = []
            for q_val, label, slug in items:
                if str(q_val).isdigit() and int(q_val) in allowed:
                    filtered.append((q_val, label, slug))
                elif q_val in allowed or q_val == "best":
                    filtered.append((q_val, label, slug))
            return filtered or items

        # Lossless containers: FLAC, WAV, AIFF, ALAC, M4A_ALAC
        if fmt in (AudioFormat.FLAC, AudioFormat.WAV, AudioFormat.AIFF, AudioFormat.ALAC, AudioFormat.M4A_ALAC):
            max_rate = spec.get("max_sample_rate", 48000)
            is_lossless_src = spec.get("is_lossless", False)

            resolved = []
            for q_val, label, slug in items:
                # Always allow Best Available and Preserve Original
                if slug in ("best", "pres"):
                    resolved.append((q_val, label, slug))
                    continue

                if "bit" in str(q_val):
                    depth, rate = AudioProfile.parse_wav_quality(str(q_val))
                    # For lossy sources (e.g. Spotify, YouTube, SoundCloud), cap quality display to 16-bit 48kHz / 44.1kHz
                    if not is_lossless_src and (depth > 16 or rate > 48000):
                        continue
                    # For CD quality sources (e.g. Deezer), cap to max_rate (48kHz)
                    if rate > max_rate:
                        continue
                    resolved.append((q_val, label, slug))
                else:
                    resolved.append((q_val, label, slug))

            return resolved or items

        # Lossy containers: MP3, M4A, OPUS, OGG, AC3, EAC3
        # Pandora source is max 192k
        if p_id == "pandora" and fmt == AudioFormat.MP3:
            return [(q, l, s) for q, l, s in items if (str(q).isdigit() and int(q) <= 192) or s == "best"]

        return items

    @classmethod
    def resolve_download_capabilities(cls, provider_id: str, output_format: Optional[str] = None) -> Dict[str, Any]:
        """
        Inspect complete download capabilities for a provider and optional format.
        """
        p_id = cls.normalize_provider_id(provider_id)
        spec = cls.get_provider_spec(p_id)
        supported_formats = cls.get_supported_formats(p_id, is_premium=True)
        available_encoders = AudioProfile.get_available_ffmpeg_encoders()

        caps = {
            "provider_id": p_id,
            "display_name": spec.get("display_name"),
            "emoji": spec.get("emoji"),
            "is_lossless_source": spec.get("is_lossless"),
            "max_sample_rate": spec.get("max_sample_rate"),
            "max_bit_depth": spec.get("max_bit_depth"),
            "source_formats": spec.get("source_formats", []),
            "supported_formats": [fmt for fmt, _ in supported_formats],
            "default_format": spec.get("default_format", AudioFormat.MP3),
            "default_quality": spec.get("default_quality", 320),
            "encoder_capabilities": list(available_encoders),
            "is_usable": cls.is_provider_usable(p_id)
        }

        if output_format:
            norm_fmt = AudioProfile.normalize_format(output_format)
            caps["selected_format"] = norm_fmt
            caps["quality_profiles"] = cls.resolve_quality_profiles(p_id, norm_fmt, is_premium=True)

        return caps

    @classmethod
    def validate_download_configuration(cls, provider_id: str, output_format: str,
                                         quality_profile: Any, is_premium: bool = True) -> Tuple[bool, Optional[str]]:
        """
        Centralized validation for a full (provider, format, quality) tuple.
        Returns: (is_valid, error_reason)
        """
        p_id = cls.normalize_provider_id(provider_id)

        # 1. Validate Provider Usability
        if not cls.is_provider_usable(p_id):
            disp = cls.get_display_name(p_id)
            return False, f"Provider '{disp}' is currently offline or disabled."

        # 2. Validate Output Format
        clean_fmt = AudioProfile.normalize_format(output_format)
        if not is_premium and not AudioProfile.is_format_allowed(clean_fmt, is_premium=False):
            return False, f"Audio format '{output_format.upper()}' requires SpotiVerse Premium."

        supported_fmts = [fmt for fmt, _ in cls.get_supported_formats(p_id, is_premium=is_premium)]
        if clean_fmt not in supported_fmts and output_format not in supported_fmts:
            return False, f"Audio format '{output_format.upper()}' is not supported by provider '{cls.get_display_name(p_id)}'."

        # 3. Validate Host Encoder
        f_spec = AudioProfile.get_spec(clean_fmt)
        if f_spec and not AudioProfile.is_encoder_available(f_spec.ffmpeg_encoder):
            return False, f"FFmpeg encoder '{f_spec.ffmpeg_encoder}' is not available on this server."

        # 4. Validate Quality Profile
        compat_qualities = cls.resolve_quality_profiles(p_id, clean_fmt, is_premium=is_premium)
        is_compat = False
        for q_val, label, slug in compat_qualities:
            if AudioProfile.are_qualities_equal(q_val, quality_profile) or slug == str(quality_profile).lower():
                is_compat = True
                break

        if not is_compat:
            return False, f"Quality '{quality_profile}' is not compatible with {cls.get_display_name(p_id)} and {clean_fmt.upper()}."

        return True, None


# Canonical format display name mapping
FORMAT_DISPLAY_NAMES: Dict[str, str] = {
    "mp3": "MP3",
    "flac": "FLAC",
    "aac": "AAC",
    "m4a": "M4A",
    "m4a_aac": "M4A",
    "m4a_alac": "M4A ALAC",
    "alac": "ALAC",
    "ogg": "OGG",
    "ogg_vorbis": "OGG",
    "ogg_opus": "OPUS",
    "opus": "OPUS",
    "wav": "WAV",
    "aiff": "AIFF",
    "wavpack": "WAVPACK",
    "wv": "WAVPACK",
    "ape": "APE",
    "ac3": "AC3",
    "eac3": "E-AC3",
}


def format_audio_quality(format_type: Any, quality: Any = None) -> str:
    """
    Centralized display formatter for audio format and quality.
    Accepts format and quality configuration in any representation (strings, ints, dicts, enums, combined strings)
    and returns a clean, normalized, user-friendly display string.

    Examples:
        format_audio_quality("mp3", {"mode": "fixed", "bitrate_kbps": 320, "sample_rate": 44100}) -> "MP3 (320 kbps)"
        format_audio_quality("mp3", 320) -> "MP3 (320 kbps)"
        format_audio_quality("flac", "Lossless") -> "FLAC (Lossless)"
        format_audio_quality("wav", "PCM") -> "WAV (PCM)"
        format_audio_quality("opus", 160) -> "OPUS (160 kbps)"
        format_audio_quality("aac", 256) -> "AAC (256 kbps)"
    """
    import ast

    # 1. Handle dict passed as format_type (e.g. download preferences or user dict)
    if isinstance(format_type, dict):
        q_val = quality if quality is not None else (
            format_type.get("quality") or format_type.get("audio_quality") or format_type.get("preferred_quality")
        )
        f_val = (
            format_type.get("format") or format_type.get("audio_format") or
            format_type.get("preferred_format") or "MP3"
        )
        format_type = f_val
        quality = q_val

    # Handle enum objects
    if hasattr(format_type, "value"):
        format_type = format_type.value

    # Parse single combined string if quality is not provided
    if quality is None and isinstance(format_type, str):
        f_str = format_type.strip()
        if "{" in f_str and "}" in f_str:
            idx1 = f_str.find("{")
            idx2 = f_str.rfind("}")
            fmt_part = f_str[:idx1].strip()
            q_part = f_str[idx1:idx2 + 1].strip()
            try:
                parsed = ast.literal_eval(q_part)
                if isinstance(parsed, dict):
                    format_type = fmt_part
                    quality = parsed
            except Exception:
                format_type = fmt_part
                quality = None
        elif "(" in f_str and f_str.endswith(")"):
            idx = f_str.find("(")
            format_type = f_str[:idx].strip()
            quality = f_str[idx + 1:-1].strip()
        elif " " in f_str:
            parts = f_str.split(" ", 1)
            format_type = parts[0].strip()
            quality = parts[1].strip()

    # If quality is a stringified dict, parse it safely
    if isinstance(quality, str) and quality.strip().startswith("{") and quality.strip().endswith("}"):
        try:
            parsed = ast.literal_eval(quality.strip())
            if isinstance(parsed, dict):
                quality = parsed
        except Exception:
            quality = None

    # 2. Format name normalization
    clean_fmt = str(format_type or "").strip().lower()
    clean_fmt = clean_fmt.strip("():`*_ ")
    fmt_display = FORMAT_DISPLAY_NAMES.get(clean_fmt)
    if not fmt_display:
        if clean_fmt in ("m4a_aac", "m4aaac"):
            fmt_display = "M4A"
        elif clean_fmt in ("m4a_alac", "m4aalac"):
            fmt_display = "M4A ALAC"
        elif clean_fmt in ("ogg_vorbis", "oggvorbis"):
            fmt_display = "OGG"
        elif clean_fmt in ("ogg_opus", "oggopus"):
            fmt_display = "OPUS"
        else:
            fmt_display = clean_fmt.upper() if clean_fmt else "MP3"

    # 3. Quality label extraction
    q_label = ""
    if isinstance(quality, dict):
        mode = str(quality.get("mode") or "").strip().lower()
        if mode in ("variable", "vbr") or "vbr" in quality:
            br = quality.get("bitrate_kbps") or quality.get("bitrate")
            q_label = f"{br} kbps VBR" if br else "VBR"
        elif mode in ("source", "source_quality", "sourcequality"):
            q_label = "Source Quality"
        elif mode in ("auto", "best", "bestavailable"):
            q_label = "Best Available"
        elif mode in ("preserve", "preserveoriginal", "original"):
            if clean_fmt in ("flac", "wav", "aiff", "alac", "m4a_alac", "wavpack", "wv", "ape"):
                q_label = "Lossless" if quality.get("lossless") else "Preserve Original"
            else:
                q_label = "Preserve Original"
        elif "bit_depth" in quality and "sample_rate" in quality:
            depth = quality["bit_depth"]
            rate = quality["sample_rate"]
            if rate % 1000 == 0:
                rate_str = f"{rate // 1000} kHz" if rate >= 1000 else f"{rate} Hz"
            else:
                rate_str = f"{rate / 1000:g} kHz"
            q_label = f"{depth}-bit / {rate_str}"
        elif quality.get("bitrate_kbps"):
            q_label = f"{quality['bitrate_kbps']} kbps"
        elif quality.get("bitrate"):
            q_label = f"{quality['bitrate']} kbps"
        elif quality.get("compression"):
            comp = str(quality["compression"]).strip()
            q_label = "Lossless" if comp.lower() == "lossless" else comp.title()

    elif isinstance(quality, (int, float)) and quality > 0:
        q_label = f"{int(quality)} kbps"

    elif isinstance(quality, str):
        q_str = quality.strip().strip("():`*_ ")
        for emoji in ("✨", "🎯", "💎", "🔥"):
            q_str = q_str.replace(emoji, "").strip()

        q_lower = q_str.lower()
        if q_lower in ("lossless", "flac lossless", "lossless compression"):
            q_label = "Lossless"
        elif q_lower in ("pcm", "uncompressed pcm", "wav pcm", "wav (pcm)"):
            q_label = "PCM"
        elif q_lower in ("best", "best available", "bestavailable"):
            q_label = "Best Available"
        elif q_lower in ("preserve", "preserve original", "preserveoriginal", "original"):
            q_label = "Preserve Original"
        elif q_lower in ("source", "source quality", "sourcequality", "source-quality"):
            q_label = "Source Quality"
        elif q_lower in ("variable", "vbr"):
            q_label = "VBR"
        elif q_str.isdigit():
            q_label = f"{int(q_str)} kbps" if int(q_str) > 0 else ""
        elif q_lower.endswith("kbps") and q_lower[:-4].strip().isdigit():
            q_label = f"{q_lower[:-4].strip()} kbps"
        elif q_lower.endswith("k") and q_lower[:-1].isdigit():
            q_label = f"{q_lower[:-1]} kbps"
        elif "bit" in q_lower and ("khz" in q_lower or "hz" in q_lower):
            norm_wav = q_str.replace(" / ", "/").replace(" /", "/").replace("/ ", "/")
            parts = norm_wav.split("/")
            if len(parts) == 2:
                q_label = f"{parts[0].strip()} / {parts[1].strip()}"
            else:
                q_label = q_str
        elif q_lower in ("none", "null", "{}", "", "0"):
            q_label = ""
        elif "{" in q_str or "}" in q_str or "<" in q_str or ">" in q_str:
            q_label = ""
        else:
            q_label = q_str

    if q_label:
        return f"{fmt_display} ({q_label})"
    return fmt_display


AudioProfile.format_audio_quality = staticmethod(format_audio_quality)



