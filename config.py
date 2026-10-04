import os
from dotenv import load_dotenv

load_dotenv()

def _int_env(var_name, default):
    val = os.getenv(var_name)
    if val is None or val.strip() == "":
        return default
    try:
        clean = val.replace(",", " ").split()
        return int(clean[0]) if clean else default
    except (ValueError, IndexError):
        return default

def _list_int_env(var_name, default=None):
    val = os.getenv(var_name)
    if not val:
        return default or []
    items = []
    for x in val.replace(",", " ").split():
        try:
            items.append(int(x))
        except ValueError:
            pass
    return items or (default or [])

def _bool_env(var_name, default=True):
    val = os.getenv(var_name)
    if val is None or val.strip() == "":
        return default
    return val.strip().lower() in ("true", "1", "yes", "on", "t")

def _list_str_env(var_name, default=None):
    val = os.getenv(var_name)
    if not val:
        return default or []
    items = [x.strip().lower() for x in val.replace(",", " ").split() if x.strip()]
    return items or (default or [])
        
class Config:
    # Premium Feature Enforcement (True = Premium members only; False = All features unlocked for everyone)
    PREMIUM = _bool_env("PREMIUM", _bool_env("PREMIUM_MODE", True))
    PREMIUM_MODE = PREMIUM


    # Pyrogram API credentials (REQUIRED)
    API_ID = _int_env("API_ID", 0)
    API_HASH = os.getenv("API_HASH", "")

    # Bot Token (REQUIRED)
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")

    # MongoDB Configuration
    MONGO_URI = "" if os.getenv("TESTING") == "1" or os.getenv("PYTEST_CURRENT_TEST") else os.getenv("MONGO_URI", "")
    DB_NAME = "spotiverse_bot"

    # API Keys (Optional - Spotify keys default to anonymous web player fallback if omitted)
    SPOTIFY_CLIENT_ID = "" if os.getenv("TESTING") == "1" or os.getenv("PYTEST_CURRENT_TEST") else os.getenv("SPOTIFY_CLIENT_ID", "")
    SPOTIFY_CLIENT_SECRET = "" if os.getenv("TESTING") == "1" or os.getenv("PYTEST_CURRENT_TEST") else os.getenv("SPOTIFY_CLIENT_SECRET", "")
    YOUTUBE_API_KEY = "" if os.getenv("TESTING") == "1" or os.getenv("PYTEST_CURRENT_TEST") else os.getenv("YOUTUBE_API_KEY", "")

    # Logging Channels (Optional - set to 0 to disable)
    LOG_CHANNEL = _int_env("LOG_CHANNEL", 0)
    DOWNLOAD_LOG_CHANNEL = _int_env("DOWNLOAD_LOG_CHANNEL", 0)

    # Owner & Admin IDs
    OWNER_ID = _int_env("OWNER_ID", 0)
    OWNER_IDS = _list_int_env("OWNER_ID", [])
    ADMINS = _list_int_env("ADMINS", []) + _list_int_env("SUDO_USERS", [])
    PREMIUM_USERS = _list_int_env("PREMIUM_USERS", [])

    @classmethod
    def is_owner(cls, user_id: int) -> bool:
        if not user_id:
            return False
        return (
            user_id == cls.OWNER_ID
            or user_id in cls.OWNER_IDS
            or user_id in cls.ADMINS
        )

    @classmethod
    def is_authorized(cls, message) -> bool:
        """Check if message is from an owner/admin user OR sent in the log channel (channel posts)."""
        if not message:
            return False
        # 1. From a recognized owner/admin
        if getattr(message, "from_user", None) and cls.is_owner(message.from_user.id):
            return True
        # 2. Sent directly in the LOG_CHANNEL or DOWNLOAD_LOG_CHANNEL (channel post)
        if cls.LOG_CHANNEL and getattr(message, "chat", None) and message.chat.id == cls.LOG_CHANNEL:
            return True
        if cls.DOWNLOAD_LOG_CHANNEL and getattr(message, "chat", None) and message.chat.id == cls.DOWNLOAD_LOG_CHANNEL:
            return True
        if cls.LOG_CHANNEL and getattr(message, "sender_chat", None) and message.sender_chat.id == cls.LOG_CHANNEL:
            return True
        return False

    @classmethod
    def is_authorized_callback(cls, callback_query) -> bool:
        if not callback_query:
            return False
        from_u = getattr(callback_query, "from_user", None)
        if not from_u:
            return False
        if cls.is_owner(from_u.id):
            return True
        msg = getattr(callback_query, "message", None)
        if msg:
            if cls.is_authorized(msg):
                return True
            chat = getattr(msg, "chat", None)
            if chat:
                if getattr(chat, "type", None) == "private" or getattr(chat, "id", None) == from_u.id:
                    return True
                reply_to = getattr(msg, "reply_to_message", None)
                if reply_to and getattr(reply_to, "from_user", None) and reply_to.from_user.id == from_u.id:
                    return True
        return False

    # Download Settings
    MAX_CONCURRENT_DOWNLOADS = _int_env("MAX_CONCURRENT_DOWNLOADS", 3)
    MAX_PREMIUM_CONCURRENT_DOWNLOADS = _int_env("MAX_PREMIUM_CONCURRENT_DOWNLOADS", 5)
    MAX_FREE_CONCURRENT_DOWNLOADS = _int_env("MAX_FREE_CONCURRENT_DOWNLOADS", 2)
    PREMIUM_PRIORITY_WEIGHT = _int_env("PREMIUM_PRIORITY_WEIGHT", 3)
    TEMP_DOWNLOAD_DIR = "temp/"
    THUMBNAIL_DIR = "data/thumbnails/"
    COOKIES_FILE = os.getenv("COOKIES_FILE", "cookies.txt")

    # Free User Limits
    FREE_USER_DAILY_LIMIT = _int_env("FREE_USER_DAILY_LIMIT", 5)

    # Maintenance Mode Rules
    MAINTENANCE_ALLOW_PREMIUM = _bool_env("MAINTENANCE_ALLOW_PREMIUM", False)
    MAINTENANCE_ALLOW_ADMIN = _bool_env("MAINTENANCE_ALLOW_ADMIN", True)

    # Expiry Warning
    PREMIUM_EXPIRY_WARNING_DAYS = _int_env("PREMIUM_EXPIRY_WARNING_DAYS", 7)

    # Payment Provider Credentials (Optional)
    PAYMENT_PROVIDER_TOKEN = os.getenv("PAYMENT_PROVIDER_TOKEN", "")
    PAYMENT_UPI_ID = os.getenv("PAYMENT_UPI_ID", "icecube@upi")

    # Provider Enablement Flags
    ENABLE_SPOTIFY = _bool_env("ENABLE_SPOTIFY", True)
    ENABLE_YOUTUBE = _bool_env("ENABLE_YOUTUBE", True)
    ENABLE_YTMUSIC = _bool_env("ENABLE_YTMUSIC", True)
    ENABLE_JIOSAAVN = _bool_env("ENABLE_JIOSAAVN", True)
    ENABLE_SOUNDCLOUD = _bool_env("ENABLE_SOUNDCLOUD", True)
    ENABLE_DEEZER = _bool_env("ENABLE_DEEZER", True)
    ENABLE_APPLE_MUSIC = _bool_env("ENABLE_APPLE_MUSIC", True)
    ENABLE_TIDAL = _bool_env("ENABLE_TIDAL", True)
    ENABLE_QOBUZ = _bool_env("ENABLE_QOBUZ", True)
    ENABLE_AMAZON_MUSIC = _bool_env("ENABLE_AMAZON_MUSIC", True)
    ENABLE_PANDORA = _bool_env("ENABLE_PANDORA", True)
    ENABLE_BANDCAMP = _bool_env("ENABLE_BANDCAMP", True)
    ENABLE_INTERNET_ARCHIVE = _bool_env("ENABLE_INTERNET_ARCHIVE", True)

    # Supported Formats & Qualities
    SUPPORTED_FORMATS = {
        "mp3": [64, 96, 128, 160, 192, 224, 256, 320],
        "flac": ["16-bit 44.1kHz", "16-bit 48kHz", "24-bit 44.1kHz", "24-bit 48kHz", "24-bit 88.2kHz", "24-bit 96kHz", "24-bit 176.4kHz", "24-bit 192kHz"],
        "m4a": [64, 96, 128, 160, 192, 224, 256, 320],
        "ogg": [64, 96, 128, 160, 192, 224, 256, 320, 500],
        "opus": [32, 48, 64, 96, 128, 160, 192, 256, 320],
        "wav": ["16-bit 44.1kHz", "16-bit 48kHz", "24-bit 44.1kHz", "24-bit 48kHz", "24-bit 96kHz", "24-bit 176.4kHz", "24-bit 192kHz", "32-bit Float 48kHz", "32-bit Float 96kHz", "32-bit Float 192kHz"],
        "aiff": ["16-bit 44.1kHz", "16-bit 48kHz", "24-bit 44.1kHz", "24-bit 48kHz", "24-bit 96kHz", "24-bit 176.4kHz", "24-bit 192kHz"],
        "wv": ["lossless", "hybrid-320k", "hybrid-500k"],
        "ape": ["fast", "normal", "high", "extra-high", "insane"],
        "ac3": [192, 384, 448, 640],
        "eac3": [192, 384, 448, 640, 1024, 1536]
    }

    # Audio Entitlements & Quality Limits
    FREE_AUDIO_FORMATS = _list_str_env("FREE_AUDIO_FORMATS", ["mp3"])
    FREE_MP3_QUALITIES = _list_int_env("FREE_MP3_QUALITIES", [64, 128, 192, 256, 320])

    PREMIUM_AUDIO_FORMATS = _list_str_env("PREMIUM_AUDIO_FORMATS", ["mp3", "flac", "m4a", "ogg", "opus", "wav", "aiff", "wv", "ape", "ac3", "eac3"])
    PREMIUM_MP3_QUALITIES = _list_int_env("PREMIUM_MP3_QUALITIES", [64, 96, 128, 160, 192, 224, 256, 320])
    PREMIUM_M4A_QUALITIES = _list_int_env("PREMIUM_M4A_QUALITIES", [64, 96, 128, 160, 192, 224, 256, 320])
    PREMIUM_OGG_QUALITIES = _list_int_env("PREMIUM_OGG_QUALITIES", [64, 96, 128, 160, 192, 224, 256, 320, 500])
    PREMIUM_OPUS_QUALITIES = _list_int_env("PREMIUM_OPUS_QUALITIES", [32, 48, 64, 96, 128, 160, 192, 256, 320])
    PREMIUM_WAV_BIT_DEPTHS = _list_int_env("PREMIUM_WAV_BIT_DEPTHS", [16, 24, 32])
    PREMIUM_WAV_SAMPLE_RATES = _list_int_env("PREMIUM_WAV_SAMPLE_RATES", [44100, 48000, 88200, 96000, 176400, 192000])

    # File Size Limits (Telegram standard bot limit is 50MB)
    MAX_AUDIO_FILE_SIZE_MB = _int_env("MAX_AUDIO_FILE_SIZE_MB", 50)
