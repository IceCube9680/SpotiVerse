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
    MONGO_URI = os.getenv("MONGO_URI", "")
    DB_NAME = "spotiverse_bot"

    # API Keys (Optional - Spotify keys default to anonymous web player fallback if omitted)
    SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
    SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
    YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")

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
        if getattr(callback_query, "from_user", None) and cls.is_owner(callback_query.from_user.id):
            return True
        if getattr(callback_query, "message", None) and cls.is_authorized(callback_query.message):
            return True
        return False

    # Download Settings
    MAX_CONCURRENT_DOWNLOADS = _int_env("MAX_CONCURRENT_DOWNLOADS", 3)
    TEMP_DOWNLOAD_DIR = "temp/"
    THUMBNAIL_DIR = "data/thumbnails/"
    COOKIES_FILE = os.getenv("COOKIES_FILE", "cookies.txt")

    # Free User Limits
    FREE_USER_DAILY_LIMIT = _int_env("FREE_USER_DAILY_LIMIT", 5)

    # Supported Formats
    SUPPORTED_FORMATS = {
        "mp3": [64, 128, 192, 256, 320],
        "flac": ["low", "medium", "high"]
    }
