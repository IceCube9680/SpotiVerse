# 🎵 SpotiVerse – Modular Telegram Music Downloader Bot

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-blue.svg)](https://core.telegram.org/bots)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A modular Telegram music downloader bot supporting unified search (Spotify, YouTube, JioSaavn), audio downloads (MP3/FLAC), premium/free user management with MongoDB persistence, logging channels, album/playlist downloads, and more. Designed to be maintainable and extensible.

---

## Note 🏷️

**• You can contact the developer**

[![Contact Developer](https://img.shields.io/badge/Portfolio-Visit-blue?logo=github)](https://priest9680.github.io) 

---

## ✨ Features

- **🔍 Unified Search** – Search across Spotify, YouTube, and JioSaavn from a single query
- **🎵 High-Quality Downloads** – MP3/FLAC format with configurable bitrate (64–320 kbps)
- **👥 User Management** – Premium/Free tiers with daily download limits, persisted via MongoDB
- **🛠️ Admin Controls** – Add/remove premium users, ban/unban, view user info
- **📢 Force Subscribe** – Optional channel membership requirement
- **📊 Logging** – Log first-time starts and downloads to Telegram channels
- **📀 Album/Playlist Support** – Download entire collections with progress tracking and cancel option
- **🖼️ Metadata Embedding** – Automatically embeds thumbnails, titles, artists, and album info
- **🧹 Auto Cleanup** – Temporary files removed after upload

---

## Structure

```
SpotiVerse/
├── bot.py                 # Main bot runner
├── config.py             # Configuration (API keys, settings)
├── info.py               # Constants and default settings
├── handlers/
│   ├── commands.py       # Command and callback handlers
│   ├── search.py         # Multi-platform search
│   └── downloads.py      # Audio download and processing
├── utils/
│   ├── db.py            # Database operations
│   ├── logger.py        # Logging utilities
│   ├── audio.py         # Audio processing
│   ├── expiry.py        # Premium expiry management
│   ├── scheduler.py     # Scheduled tasks
│   └── local_db.py      # Local JSON fallback
├── temp/                 # Temporary audio files
└── data/                # Persistent data (thumbnails, local DB)

```

## Quickstart

### Prerequisites

* Python 3.10+
* `ffmpeg` installed on the host
* MongoDB instance (Atlas or local)
* Telegram Bot Token from BotFather
* Optional: Spotify API credentials

### VPS Deployment

Install:

```bash
git clone https://github.com/priest9680/SpotiVerse.git
cd SpotiVerse
python -m pip install -r requirements.txt

python -m venv venv

# Windows:
venv\Scripts\activate

# Linux/macOS:
source venv/bin/activate

sudo apt update
sudo apt install -y ffmpeg

python bot.py
```

### Environment variables

Create a `.env` file in the project root or set environment variables in your host.
Example `.env`:

```ini
BOT_TOKEN=""
API_ID=""
API_HASH=""

MONGO_URI=""

# Spotify credentials are optional (uses automatic anonymous web player fallback if left empty)
SPOTIFY_CLIENT_ID=""
SPOTIFY_CLIENT_SECRET=""

FREE_USER_DAILY_LIMIT=100000
MAX_CONCURRENT_DOWNLOADS=3

LOG_CHANNEL=""
DOWNLOAD_LOG_CHANNEL=0
OWNER_ID=""
PREMIUM_USERS=""
```

**Notes**

* `ADD_PREMIUM=true` means the bot enforces free vs premium rules. Set to `false` to treat all users as premium (useful for testing).
* `LOG_CHANNEL` and `DOWNLOAD_LOG_CHANNEL` are optional. If omitted, respective logging is disabled.

---

## Commands (user-facing)

* `/start` — Welcome + force-subscribe check (if enabled).
* `/search <query>` — Unified search with paginated inline results and download buttons.
* `/download <link|query>` — Direct download by URL or query.
* Settings menu — change preferred audio format and quality.

## Admin / Owner commands

* `/add_premium <user_id> <duration>` — Grant premium (duration supports formats like `30d`, `12h`, `1y`).
* `/remove_premium <user_id>` — Revoke premium.
* `/user_info <user_id>` — Show user profile and download usage.
* `/ban <user_id>` and `/unban <user_id>` — Block or unblock a user.
* `/logs` — Show or export logs (requires `LOG_CHANNEL` configured).

---

## Troubleshooting

* ffmpeg errors: ensure `ffmpeg` installed and reachable via PATH (`ffmpeg -version`).
* Spotify errors: verify credentials, app status and rate limits.
* yt-dlp issues: update `yt-dlp` (`pip install -U yt-dlp`) when extractors break.
* JioSaavn: unofficial scrapers may break without warning.
* Logs not sent: confirm channel ID, bot permissions, and that the bot is an admin in the channel.

---

## Security & Legal

* Respect copyright and platform terms. Downloading copyrighted materials without permission may be illegal.
* Keep API keys and tokens private. Do not commit `.env` to public repos.

---

## Contributing

1. Fork the repository
2. Create a branch
3. Add features or fixes
4. Open a Pull Request with description and tests/manual steps

---

## License

MIT License — see `LICENSE` file for details.
