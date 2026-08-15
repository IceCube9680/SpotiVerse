import os
from dotenv import load_dotenv

load_dotenv()

def _int_env(var_name, default):
    val = os.getenv(var_name)
    if val is None or val.strip() == "":
        return default
    try:
        return int(val)
    except ValueError:
        # log or fallback silently
        return default
        
class Config:
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

    # Owner ID
    OWNER_ID = _int_env("OWNER_ID", 0)

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
