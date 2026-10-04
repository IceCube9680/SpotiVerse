# utils/branding.py
"""
Centralized Official Brand Identity & Provider Icon Registry for SpotiVerse.

Ensures every music service, download provider, and integrated platform has a
consistent, recognizable official brand identity across all UI surfaces (menus,
messages, captions, notifications, keyboards, admin panel, and documentation).

Rules:
- Authentic brand names, colors, official logo assets (SVG/PNG), and badges.
- Strict separation between Provider branding and Audio Format/Quality technical specs.
- Safe fallback for unknown providers without inventing fake or misleading icons.
- No substitution of random/generic Unicode emojis (🔴, 📦, 📻, 🟢, ⬛, 🔷) for official brand marks.
"""

import os
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# Base path for local vector and raster brand assets
BRAND_ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "branding")


class ProviderBranding:
    """Detailed specifications and brand guidelines for a provider."""
    def __init__(
        self,
        provider_id: str,
        display_name: str,
        brand_name: str,
        badge: str,
        tag: str,
        brand_color: str,
        official_url: str,
        logo_svg: str,
        logo_png: str,
        description: str,
        custom_emoji_id: Optional[str] = None
    ):
        self.provider_id = provider_id.lower().strip()
        self.display_name = display_name
        self.brand_name = brand_name
        self.badge = badge
        self.tag = tag
        self.brand_color = brand_color
        self.official_url = official_url
        self.logo_svg = logo_svg
        self.logo_png = logo_png
        self.description = description
        self.custom_emoji_id = custom_emoji_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.provider_id,
            "display_name": self.display_name,
            "name": self.display_name,
            "brand_name": self.brand_name,
            "badge": self.badge,
            "tag": self.tag,
            "brand_color": self.brand_color,
            "official_url": self.official_url,
            "logo_svg": self.logo_svg,
            "logo_png": self.logo_png,
            "description": self.description,
            "custom_emoji_id": self.custom_emoji_id,
            "asset_svg_exists": os.path.isfile(self.logo_svg) if self.logo_svg else False,
            "asset_png_exists": os.path.isfile(self.logo_png) if self.logo_png else False,
        }


# ==============================================================================
# OFFICIAL BRAND REGISTRY
# ==============================================================================

OFFICIAL_PROVIDER_BRANDING: Dict[str, ProviderBranding] = {
    "spotify": ProviderBranding(
        provider_id="spotify",
        display_name="Spotify",
        brand_name="Spotify",
        badge="[Spotify]",
        tag="SPOTIFY",
        brand_color="#1DB954",
        official_url="https://www.spotify.com",
        logo_svg=os.path.join(BRAND_ASSETS_DIR, "spotify.svg"),
        logo_png=os.path.join(BRAND_ASSETS_DIR, "spotify.png"),
        description="Official Spotify digital music service and metadata catalog."
    ),
    "youtubemusic": ProviderBranding(
        provider_id="youtubemusic",
        display_name="YouTube Music",
        brand_name="YouTube Music",
        badge="[YouTube Music]",
        tag="YT MUSIC",
        brand_color="#FF0000",
        official_url="https://music.youtube.com",
        logo_svg=os.path.join(BRAND_ASSETS_DIR, "youtube_music.svg"),
        logo_png=os.path.join(BRAND_ASSETS_DIR, "youtube_music.png"),
        description="Official YouTube Music streaming platform."
    ),
    "youtube": ProviderBranding(
        provider_id="youtube",
        display_name="YouTube",
        brand_name="YouTube",
        badge="[YouTube]",
        tag="YOUTUBE",
        brand_color="#FF0000",
        official_url="https://www.youtube.com",
        logo_svg=os.path.join(BRAND_ASSETS_DIR, "youtube.svg"),
        logo_png=os.path.join(BRAND_ASSETS_DIR, "youtube.png"),
        description="Official YouTube video and audio platform."
    ),
    "deezer": ProviderBranding(
        provider_id="deezer",
        display_name="Deezer",
        brand_name="Deezer",
        badge="[Deezer]",
        tag="DEEZER",
        brand_color="#A238FF",
        official_url="https://www.deezer.com",
        logo_svg=os.path.join(BRAND_ASSETS_DIR, "deezer.svg"),
        logo_png=os.path.join(BRAND_ASSETS_DIR, "deezer.png"),
        description="Official Deezer High-Fidelity music platform with 16-bit FLAC audio."
    ),
    "applemusic": ProviderBranding(
        provider_id="applemusic",
        display_name="Apple Music",
        brand_name="Apple Music",
        badge="[Apple Music]",
        tag="APPLE MUSIC",
        brand_color="#FA243C",
        official_url="https://music.apple.com",
        logo_svg=os.path.join(BRAND_ASSETS_DIR, "apple_music.svg"),
        logo_png=os.path.join(BRAND_ASSETS_DIR, "apple_music.png"),
        description="Official Apple Music streaming platform with ALAC lossless and spatial audio."
    ),
    "tidal": ProviderBranding(
        provider_id="tidal",
        display_name="TIDAL",
        brand_name="TIDAL",
        badge="[TIDAL]",
        tag="TIDAL",
        brand_color="#00FFFF",
        official_url="https://tidal.com",
        logo_svg=os.path.join(BRAND_ASSETS_DIR, "tidal.svg"),
        logo_png=os.path.join(BRAND_ASSETS_DIR, "tidal.png"),
        description="Official TIDAL Hi-Res Lossless & Max audio platform."
    ),
    "qobuz": ProviderBranding(
        provider_id="qobuz",
        display_name="Qobuz",
        brand_name="Qobuz",
        badge="[Qobuz]",
        tag="QOBUZ",
        brand_color="#24548A",
        official_url="https://www.qobuz.com",
        logo_svg=os.path.join(BRAND_ASSETS_DIR, "qobuz.svg"),
        logo_png=os.path.join(BRAND_ASSETS_DIR, "qobuz.png"),
        description="Official Qobuz 24-bit Hi-Res audio platform."
    ),
    "amazonmusic": ProviderBranding(
        provider_id="amazonmusic",
        display_name="Amazon Music",
        brand_name="Amazon Music",
        badge="[Amazon Music]",
        tag="AMAZON MUSIC",
        brand_color="#00A8E1",
        official_url="https://music.amazon.com",
        logo_svg=os.path.join(BRAND_ASSETS_DIR, "amazon_music.svg"),
        logo_png=os.path.join(BRAND_ASSETS_DIR, "amazon_music.png"),
        description="Official Amazon Music HD and Ultra HD streaming service."
    ),
    "soundcloud": ProviderBranding(
        provider_id="soundcloud",
        display_name="SoundCloud",
        brand_name="SoundCloud",
        badge="[SoundCloud]",
        tag="SOUNDCLOUD",
        brand_color="#FF5500",
        official_url="https://soundcloud.com",
        logo_svg=os.path.join(BRAND_ASSETS_DIR, "soundcloud.svg"),
        logo_png=os.path.join(BRAND_ASSETS_DIR, "soundcloud.png"),
        description="Official SoundCloud creator and direct stream platform."
    ),
    "pandora": ProviderBranding(
        provider_id="pandora",
        display_name="Pandora",
        brand_name="Pandora",
        badge="[Pandora]",
        tag="PANDORA",
        brand_color="#005483",
        official_url="https://www.pandora.com",
        logo_svg=os.path.join(BRAND_ASSETS_DIR, "pandora.svg"),
        logo_png=os.path.join(BRAND_ASSETS_DIR, "pandora.png"),
        description="Official Pandora Radio & personalized music streaming service."
    ),
    "jiosaavn": ProviderBranding(
        provider_id="jiosaavn",
        display_name="JioSaavn",
        brand_name="JioSaavn",
        badge="[JioSaavn]",
        tag="JIOSAAVN",
        brand_color="#2BC5B4",
        official_url="https://www.jiosaavn.com",
        logo_svg=os.path.join(BRAND_ASSETS_DIR, "jiosaavn.svg"),
        logo_png=os.path.join(BRAND_ASSETS_DIR, "jiosaavn.png"),
        description="Official JioSaavn Indian and international music streaming service."
    ),
    "bandcamp": ProviderBranding(
        provider_id="bandcamp",
        display_name="Bandcamp",
        brand_name="Bandcamp",
        badge="[Bandcamp]",
        tag="BANDCAMP",
        brand_color="#629AA9",
        official_url="https://bandcamp.com",
        logo_svg=os.path.join(BRAND_ASSETS_DIR, "bandcamp.svg"),
        logo_png=os.path.join(BRAND_ASSETS_DIR, "bandcamp.png"),
        description="Official Bandcamp independent artist music discovery platform."
    ),
    "archive": ProviderBranding(
        provider_id="archive",
        display_name="Internet Archive",
        brand_name="Internet Archive",
        badge="[Internet Archive]",
        tag="ARCHIVE",
        brand_color="#666666",
        official_url="https://archive.org",
        logo_svg=os.path.join(BRAND_ASSETS_DIR, "archive.svg"),
        logo_png=os.path.join(BRAND_ASSETS_DIR, "archive.png"),
        description="Official Internet Archive Live Music Archive & public audio library."
    ),
    "auto": ProviderBranding(
        provider_id="auto",
        display_name="Auto Select",
        brand_name="Auto Select",
        badge="[Auto Select]",
        tag="AUTO",
        brand_color="#4A90E2",
        official_url="https://github.com/IceCube9680/SpotiVerse",
        logo_svg=os.path.join(BRAND_ASSETS_DIR, "auto.svg"),
        logo_png=os.path.join(BRAND_ASSETS_DIR, "auto.png"),
        description="Intelligent multi-provider routing based on audio quality and availability."
    ),
}

# Provider key canonical aliases
BRAND_ALIASES: Dict[str, str] = {
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


# ==============================================================================
# BRANDING RESOLVERS & PUBLIC API
# ==============================================================================

def normalize_provider_id(provider_id: Optional[str]) -> str:
    """Normalize arbitrary provider key to canonical registry identifier."""
    if not provider_id:
        return "auto"
    clean = str(provider_id).strip().lower()
    return BRAND_ALIASES.get(clean, clean)


def get_provider_branding(provider_id: Optional[str]) -> Dict[str, Any]:
    """
    Retrieve full branding specification dict for the provider.
    Falls back gracefully to a neutral branded format for unknown providers.
    """
    p_id = normalize_provider_id(provider_id)
    if p_id in OFFICIAL_PROVIDER_BRANDING:
        return OFFICIAL_PROVIDER_BRANDING[p_id].to_dict()

    # Neutral fallback for unlisted / dynamically added providers
    display = p_id.title() if p_id else "Provider"
    return {
        "id": p_id,
        "display_name": display,
        "name": display,
        "brand_name": display,
        "badge": f"[{display}]",
        "tag": display.upper(),
        "brand_color": "#888888",
        "official_url": "",
        "logo_svg": "",
        "logo_png": "",
        "description": f"Custom {display} audio provider.",
        "custom_emoji_id": None,
        "asset_svg_exists": False,
        "asset_png_exists": False,
    }


def get_provider_display_name(provider_id: Optional[str]) -> str:
    """Return the official brand name for display (e.g. 'Spotify', 'YouTube Music', 'Apple Music')."""
    return get_provider_branding(provider_id).get("display_name", "Unknown")


def get_provider_badge(provider_id: Optional[str]) -> str:
    """Return standardized text badge for headers / message cards (e.g. '[Spotify]', '[Apple Music]')."""
    return get_provider_branding(provider_id).get("badge", "[Music]")


def get_provider_color(provider_id: Optional[str]) -> str:
    """Return official brand hex color (e.g. '#1DB954' for Spotify, '#FF0000' for YouTube)."""
    return get_provider_branding(provider_id).get("brand_color", "#888888")


def get_provider_icon(provider_id: Optional[str], context: str = "button") -> str:
    """
    Return the best supported brand representation for the target Telegram context.

    Contexts:
    - 'button': Telegram inline buttons. Returns the clean official brand name
      (or custom emoji tag if configured). Does NOT return unrelated Unicode emojis.
    - 'message': Message cards and text headers. Returns official text badge or brand name.
    - 'badge': Formatted [BrandName] tag.
    """
    b = get_provider_branding(provider_id)
    if b.get("custom_emoji_id"):
        return f"<tg-emoji emoji-id='{b['custom_emoji_id']}'>{b['display_name']}</tg-emoji>"

    if context == "badge":
        return b.get("badge", f"[{b.get('display_name', 'Music')}]")
    elif context == "message":
        return b.get("display_name", "Music")
    else:
        # For inline buttons: Clean official display name
        return b.get("display_name", "Music")


def get_all_branding() -> Dict[str, Dict[str, Any]]:
    """Return complete branding registry for all registered providers."""
    return {k: v.to_dict() for k, v in OFFICIAL_PROVIDER_BRANDING.items()}
