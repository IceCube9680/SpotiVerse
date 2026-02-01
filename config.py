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
    API_ID = int(os.getenv("API_ID", 0))
    API_HASH = os.getenv("API_HASH", "")

    # Bot Token (REQUIRED)
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")

    # MongoDB Configuration
    MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://ice:mlovely9680@cluster0.y9czlat.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
    DB_NAME = "spotiverse_bot"

    # API Keys
    SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
    SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
    YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")

    # Logging Channels (Optional - set to 0 to disable)
    LOG_CHANNEL = int(os.getenv("LOG_CHANNEL", 0)) if os.getenv("LOG_CHANNEL") and os.getenv("LOG_CHANNEL").strip() != "" else 0
    DOWNLOAD_LOG_CHANNEL = int(os.getenv("DOWNLOAD_LOG_CHANNEL", 0)) if os.getenv("DOWNLOAD_LOG_CHANNEL") and os.getenv("DOWNLOAD_LOG_CHANNEL").strip() != "" else 0

    # Owner ID
    OWNER_ID = int(os.getenv("OWNER_ID", 0))

    # Download Settings
    MAX_CONCURRENT_DOWNLOADS = os.getenv("MAX_CONCURRENT_DOWNLOADS", "")
    TEMP_DOWNLOAD_DIR = "temp/"
    THUMBNAIL_DIR = "data/thumbnails/"

    # Free User Limits
    FREE_USER_DAILY_LIMIT = os.getenv("FREE_USER_DAILY_LIMIT", "")

    # Supported Formats
    SUPPORTED_FORMATS = {
        "mp3": [64, 128, 192, 256, 320],
        "flac": ["low", "medium", "high"]
    }
