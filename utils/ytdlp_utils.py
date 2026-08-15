import os
import shutil
import logging
from config import Config

logger = logging.getLogger(__name__)

def get_ytdlp_options(extra_opts=None, player_clients=None):
    """
    Constructs a robust yt-dlp options dictionary with anti-bot configurations:
    - YouTube player_client sequence fallback (e.g. ios, android, mweb, web)
    - Automatic detection and usage of cookies file (Config.COOKIES_FILE or cookies.txt)
    - JS Runtime binding (Node.js if available)
    - Geo-bypass and certificate verification settings
    """
    if player_clients is None:
        player_clients = ['ios', 'android', 'mweb', 'web']

    opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'nocheckcertificate': True,
        'geo_bypass': True,
        'extractor_args': {
            'youtube': {
                'player_client': player_clients
            }
        }
    }

    # Bind Node.js as JS runtime if present to prevent warnings and enable JS evaluation
    if shutil.which('node'):
        opts['js_runtimes'] = {'node': {}}

    # Check for cookies file configuration
    cookies_path = getattr(Config, 'COOKIES_FILE', 'cookies.txt')
    if cookies_path and os.path.exists(cookies_path):
        opts['cookiefile'] = cookies_path
        logger.debug(f"Using cookies file: {cookies_path}")
    elif os.path.exists('cookies.txt'):
        opts['cookiefile'] = 'cookies.txt'
        logger.debug("Using default cookies file: cookies.txt")

    if extra_opts:
        opts.update(extra_opts)

    return opts
