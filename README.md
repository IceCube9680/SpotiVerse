<div align="center">

# 🎵 SpotiVerse

### Modular & Asynchronous Telegram Music Downloader Bot

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Pyrogram](https://img.shields.io/badge/Pyrogram-v2.0-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)](https://docs.pyrogram.org/)
[![MongoDB](https://img.shields.io/badge/MongoDB-Supported-47A248?style=for-the-badge&logo=mongodb&logoColor=white)](https://www.mongodb.com/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)
[![Maintenance](https://img.shields.io/badge/Maintained%3F-yes-brightgreen.svg?style=for-the-badge)](https://github.com/priest9680/SpotiVerse)

<p align="center">
  A feature-packed, high-performance Telegram music bot built with <b>Pyrogram v2</b>, <b>yt-dlp</b>, and <b>FFmpeg</b>.<br>
  Search, stream, and download tracks, albums, and playlists from <b>Spotify</b>, <b>YouTube</b>, <b>JioSaavn</b>, <b>SoundCloud</b>, and <b>Deezer</b> in high-fidelity <b>MP3</b> or lossless <b>FLAC</b> with complete metadata tagging.
</p>

[**Explore Features**](#-key-features) • [**Quickstart**](#-quickstart-guide) • [**Bot Commands**](#-bot-commands) • [**Configuration**](#-environment-variables) • [**Deployment**](#-deployment-options)

---

</div>

## 📑 Table of Contents

- [✨ Key Features](#-key-features)
- [🏗️ Project Architecture](#️-project-architecture)
- [🚀 Quickstart Guide](#-quickstart-guide)
  - [Prerequisites](#prerequisites)
  - [Standard Installation](#standard-installation)
- [⚙️ Environment Variables](#️-environment-variables)
- [🤖 Bot Commands](#-bot-commands)
  - [User Commands](#user-commands)
  - [Admin & Owner Commands](#admin--owner-commands)
  - [Direct Chat & Inline Features](#direct-chat--inline-features)
- [📦 Deployment Options](#-deployment-options)
  - [1. CLI Management Script (`spotiverse.sh`)](#1-cli-management-script-spotiversesh)
  - [2. Systemd Service (Linux Daemon)](#2-systemd-service-linux-daemon)
  - [3. Docker Container](#3-docker-container)
- [🧪 Running Tests](#-running-tests)
- [🔧 Troubleshooting & FAQ](#-troubleshooting--faq)
- [⚖️ Legal & Disclaimer](#️-legal--disclaimer)
- [📄 License](#-license)

---

## ✨ Key Features

- **🔍 Multi-Platform Unified Search**
  Search across **Spotify**, **YouTube / YouTube Music**, **JioSaavn**, **SoundCloud**, and **Deezer** from a single search query or link.
- **🎵 Studio-Grade Audio Quality**
  Customizable audio formats and bitrates:
  - **MP3**: 64 kbps, 128 kbps, 192 kbps, 256 kbps, and 320 kbps (CBR/VBR).
  - **FLAC**: Lossless audio conversion (Low, Medium, High compression).
- **⚡ Zero-Credential Spotify Fallback**
  Works out of the box even without Spotify API credentials by using an automated anonymous web scraper and provider fallback mechanism.
- **🖼️ Complete Metadata & Cover Art Injection**
  Automatically embeds high-resolution cover artwork, title, artists, album name, track numbers, and release year into ID3 (MP3) and Vorbis (FLAC) tags using `mutagen` and `Pillow`.
- **📀 Batch Playlist & Album Downloader**
  Download entire albums, playlists, and artist top tracks with real-time progress indicators and cancellation controls.
- **💎 Tiered User & Subscription Management**
  Built-in free tier with customizable daily limits and a flexible premium tier supporting custom durations (`7d`, `30d`, `1y`, `lifetime`).
- **🛡️ Dual-Layer Database Architecture**
  Primary storage via **MongoDB Atlas / Local MongoDB** with an automated **SQLite/JSON fallback** that auto-syncs when reconnecting.
- **⚡ High-Throughput Async Engine**
  Powered by `uvloop`, non-blocking async FFmpeg transcoders, and download concurrency semaphores to prevent server saturation.
- **📢 Real-Time Channel Logging**
  Dedicated Telegram logging channels for new user onboardings, download audits, error tracking, and startup alerts.
- **🛠️ Full Administrator Toolset**
  User inspection, ban/unban controls, system metrics, log export, and broadcast messaging to all active users.

---

## 🏗️ Project Architecture

```plaintext
SpotiVerse/
├── bot.py                  # Bot entry point, lifecycle management & event loop
├── config.py               # Centralized configuration & environment loader
├── info.py                 # Bot constants, premium plans & default settings
├── spotiverse.sh           # CLI service controller (start, stop, restart, logs)
├── spotiverse.service      # Systemd service unit template for Linux servers
├── Dockerfile              # Containerization definition with FFmpeg pre-installed
├── requirements.txt        # Python dependency manifest
├── handlers/
│   ├── commands.py         # Command routers, callback queries & inline buttons
│   ├── search.py           # Multi-platform search provider aggregators
│   └── downloads.py        # Audio extraction, batch queue, FFmpeg processing & upload
├── utils/
│   ├── audio.py            # Audio transcoding & metadata/thumbnail embedding
│   ├── db.py               # MongoDB database layer with local fallback & auto-sync
│   ├── logger.py           # Telegram channel logging and audit utilities
│   └── ytdlp_utils.py      # yt-dlp configuration, cookies loader & network tuners
├── tests/                  # Automated unit test suite
│   ├── test_bot.py
│   ├── test_commands.py
│   ├── test_config.py
│   ├── test_downloads.py
│   ├── test_search.py
│   ├── test_search_and_premium.py
│   └── test_ytdlp.py
├── data/                   # Persistent storage (thumbnails, SQLite fallback cache)
└── temp/                   # Temporary directory for processing audio downloads
```

---

## 🚀 Quickstart Guide

### Prerequisites

Before setting up the bot, ensure your environment meets the following requirements:

- **Python**: Version `3.10` or higher (`python3 --version`)
- **FFmpeg**: Installed and available in your system `$PATH` (`ffmpeg -version`)
- **Telegram Account**:
  - `API_ID` & `API_HASH` from [my.telegram.org](https://my.telegram.org)
  - `BOT_TOKEN` from [@BotFather](https://t.me/BotFather)
- **MongoDB Database**: MongoDB Atlas URI or local instance (Optional: Falls back to local database if omitted)

### Standard Installation

1. **Clone the Repository**
   ```bash
   git clone https://github.com/priest9680/SpotiVerse.git
   cd SpotiVerse
   ```

2. **Set Up a Virtual Environment**
   ```bash
   python3 -m venv venv

   # On Linux/macOS:
   source venv/bin/activate

   # On Windows (PowerShell):
   .\venv\Scripts\Activate.ps1
   ```

3. **Install System Dependencies (FFmpeg)**
   ```bash
   # Debian / Ubuntu / Raspberry Pi OS:
   sudo apt update && sudo apt install -y ffmpeg curl

   # Arch Linux:
   sudo pacman -S ffmpeg

   # macOS (Homebrew):
   brew install ffmpeg

   # Windows (Chocolatey / Scoop):
   choco install ffmpeg
   ```

4. **Install Python Packages**
   ```bash
   pip install --upgrade pip setuptools wheel
   pip install -r requirements.txt
   ```

5. **Configure Environment Variables**
   ```bash
   cp .env.sample .env
   nano .env
   ```

6. **Run the Bot**
   ```bash
   python bot.py
   ```

---

## ⚙️ Environment Variables

Configure your `.env` file using the parameters below:

| Variable | Type | Required | Default | Description |
| :--- | :---: | :---: | :---: | :--- |
| `BOT_TOKEN` | `String` | **Yes** | — | Telegram Bot token obtained from [@BotFather](https://t.me/BotFather). |
| `API_ID` | `Integer` | **Yes** | — | Telegram API ID from [my.telegram.org](https://my.telegram.org). |
| `API_HASH` | `String` | **Yes** | — | Telegram API Hash from [my.telegram.org](https://my.telegram.org). |
| `OWNER_ID` | `Integer` | **Yes** | `0` | Telegram user ID of the primary bot owner. |
| `ADMINS` / `SUDO_USERS` | `List[Int]` | No | `[]` | Comma or space-separated list of admin Telegram user IDs. |
| `MONGO_URI` | `String` | No | *Local DB* | MongoDB connection string (e.g. `mongodb+srv://...`). |
| `SPOTIFY_CLIENT_ID` | `String` | No | `""` | Spotify Developer API Client ID (falls back to anonymous web scraper if empty). |
| `SPOTIFY_CLIENT_SECRET` | `String` | No | `""` | Spotify Developer API Client Secret. |
| `YOUTUBE_API_KEY` | `String` | No | `""` | Optional YouTube Data API v3 key. |
| `LOG_CHANNEL` | `Integer` | No | `0` | Telegram Channel ID (e.g. `-100...`) for user onboarding & system logs. |
| `DOWNLOAD_LOG_CHANNEL` | `Integer` | No | `0` | Telegram Channel ID for download audit logs. |
| `FREE_USER_DAILY_LIMIT` | `Integer` | No | `5` | Daily download quota for free users (`0` or large number to disable). |
| `MAX_CONCURRENT_DOWNLOADS` | `Integer` | No | `3` | Maximum simultaneous download threads. |
| `COOKIES_FILE` | `String` | No | `cookies.txt` | Path to exported YouTube Netscape cookies to bypass bot blocks. |
| `PREMIUM_USERS` | `List[Int]` | No | `[]` | Initial list of Telegram user IDs granted permanent premium status. |

---

## 🤖 Bot Commands

### User Commands

| Command | Aliases | Parameters | Description |
| :--- | :--- | :--- | :--- |
| `/start` | — | None | Starts the bot, verifies user status, and shows the interactive main menu. |
| `/search` | `/s`, `/find` | `<query>` | Performs a unified search across platforms with paginated inline buttons. |
| `/download` | `/dl`, `/d` | `<url>` or `<query>` | Downloads a single track, album, or playlist directly. |
| `/settings` | `/setting`, `/set` | None | Opens the interactive settings menu to switch audio format (MP3/FLAC) & bitrate. |
| `/userinfo` | `/user_info`, `/info`, `/me`, `/myinfo` | None | Displays your account status, membership tier, and daily download quota. |
| `/premium` | `/prem`, `/plan` | None | Displays premium subscription benefits and upgrade instructions. |
| `/help` | `/h` | None | Displays a comprehensive help manual and usage examples. |

### Admin & Owner Commands

| Command | Aliases | Parameters | Description |
| :--- | :--- | :--- | :--- |
| `/add_premium` | `/give_premium`, `/set_premium` | `<user_id>` `<duration>` | Grants premium status to a user (e.g., `7d`, `30d`, `1y`, `lifetime`). |
| `/remove_premium` | `/del_premium`, `/unpremium` | `<user_id>` | Revokes premium status from a specific user. |
| `/stats` | `/stat` | None | Displays real-time bot statistics (active users, total downloads, DB status). |
| `/users` | `/user`, `/totalusers` | None | Summarizes registered users and provides an export list. |
| `/broadcast` | `/bc` | `<message>` / Reply | Broadcasts a text or media message to all registered users with delivery statistics. |
| `/logs` | `/log` | None | Fetches recent application runtime logs directly in chat or as a document. |

### Direct Chat & Inline Features

- **Direct Messages**: Simply type any song title or paste a music link into the private chat—the bot will automatically start searching or downloading.
- **Inline Audio Quality Toggler**: Quickly toggle between MP3 (64k–320k) and FLAC in real-time from the `/settings` keyboard.
- **Interactive Batch Downloader**: When downloading playlists or albums, interact with the inline **Cancel** button at any point to stop remaining tracks.

---

## 📦 Deployment Options

### 1. CLI Management Script (`spotiverse.sh`)

A production-ready control script is included in the root directory for easy process management:

```bash
# Make the script executable
chmod +x spotiverse.sh

# Start the bot in the background (detached with PID tracking)
./spotiverse.sh start

# Check running status
./spotiverse.sh status

# View live streaming logs
./spotiverse.sh logs

# Restart the bot
./spotiverse.sh restart

# Stop the background bot process
./spotiverse.sh stop

# Run directly in foreground (debug mode)
./spotiverse.sh run
```

### 2. Systemd Service (Linux Daemon)

To keep SpotiVerse running continuously and restart automatically on server reboots:

1. **Edit the Service File**
   ```bash
   nano spotiverse.service
   ```
   *Ensure the `User`, `WorkingDirectory`, and `ExecStart` paths match your server's configuration.*

2. **Install and Enable the Unit**
   ```bash
   sudo cp spotiverse.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable spotiverse
   sudo systemctl start spotiverse
   ```

3. **Manage the Service**
   ```bash
   # Check service status:
   sudo systemctl status spotiverse

   # View system journal logs:
   sudo journalctl -u spotiverse -f
   ```

### 3. Docker Container

Build and deploy SpotiVerse in an isolated container with all system dependencies pre-configured:

1. **Build the Docker Image**
   ```bash
   docker build -t spotiverse:latest .
   ```

2. **Run the Container**
   ```bash
   docker run -d \
     --name spotiverse_bot \
     --restart unless-stopped \
     --env-file .env \
     -v $(pwd)/data:/app/data \
     spotiverse:latest
   ```

3. **Check Container Logs**
   ```bash
   docker logs -f spotiverse_bot
   ```

---

## 🧪 Running Tests

SpotiVerse includes a unit test suite covering configuration validation, command routers, download flows, database fallbacks, and search scrapers.

To execute the test suite:

```bash
# Run all tests using unittest:
python3 -m unittest discover tests

# Or run tests using pytest (if installed):
pytest -v
```

---

## 🔧 Troubleshooting & FAQ

<details>
<summary><b>1. FFmpeg is not detected or audio conversion fails</b></summary>

- Verify FFmpeg is installed and accessible in your environment path by running:
  ```bash
  ffmpeg -version
  ```
- If running under a custom user or cron/systemd service, ensure `/usr/bin` or `/usr/local/bin` is in the `PATH` environment variable.
</details>

<details>
<summary><b>2. YouTube throws "Sign in to confirm you’re not a bot" (HTTP 429)</b></summary>

- YouTube frequently rate-limits datacenter IPs. To resolve this:
  1. Export cookies from your browser using a browser extension (such as *Get cookies.txt LOCALLY*).
  2. Place the exported file as `cookies.txt` in the root project folder.
  3. Ensure `COOKIES_FILE=cookies.txt` is set in your `.env` file.
</details>

<details>
<summary><b>3. Bot does not log to Telegram channels</b></summary>

- Ensure your bot is added to your target channel as an **Administrator** with *Post Messages* and *Edit Messages* permissions.
- Make sure your channel ID includes the `-100` prefix (e.g., `-1001234567890`).
</details>

<details>
<summary><b>4. Telegram FloodWait error</b></summary>

- SpotiVerse contains built-in throttling for progress bars and message edits. If FloodWait is triggered during heavy traffic, the bot will automatically sleep for the requested duration and safely resume.
</details>

---

## ⚖️ Legal & Disclaimer

> [!IMPORTANT]
> **Educational & Personal Use Only**
> This repository is intended strictly for educational, archival, and personal research purposes. 
> - Downloading copyrighted material without permission from the respective copyright owner may infringe local laws and third-party terms of service.
> - The developers and contributors of this repository are not responsible for any misuse of this software.
> - All trademarks, logos, and brand names are the property of their respective owners.

---

## 📄 License

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for complete details.

---

<div align="center">
  <sub>Built with ❤️ by <a href="https://github.com/priest9680">Priest Gamer</a></sub>
</div>
