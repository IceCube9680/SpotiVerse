try:
    from info import DEFAULT_SETTINGS
except ImportError:
    DEFAULT_SETTINGS = {
        "preferred_format": "mp3",
        "preferred_quality": 64,
    }

PREMIUM_PLANS = {
    "weekly": {"price": 3, "days": 7, "emoji": "🟢"},
    "monthly": {"price": 10, "days": 30, "emoji": "🟡"},
    "yearly": {"price": 100, "days": 365, "emoji": "🔴"}
}

SEARCH_PROVIDERS = ["spotify", "youtube", "deezer", "soundcloud", "jiosaavn"]
DEFAULT_SEARCH_PROVIDER = "spotify"

# Default user settings
DEFAULT_SETTINGS = {
    "preferred_format": "mp3",
    "preferred_quality": 64,
    "downloads_today": 0,
    "total_downloads": 0,
    "premium": False,
    "premium_until": None,
    "join_date": None
}