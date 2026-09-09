<div align="center">

# 🎵 SpotiVerse

### Modular & Asynchronous Telegram Music Downloader Bot with Production-Grade Premium & Admin Ecosystem

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Pyrogram](https://img.shields.io/badge/Pyrogram-v2.0-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)](https://docs.pyrogram.org/)
[![MongoDB](https://img.shields.io/badge/MongoDB-Supported-47A248?style=for-the-badge&logo=mongodb&logoColor=white)](https://www.mongodb.com/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)
[![Maintenance](https://img.shields.io/badge/Maintained%3F-yes-brightgreen.svg?style=for-the-badge)](https://github.com/IceCube9680/SpotiVerse)

<p align="center">
  A feature-packed, high-performance Telegram music bot built with <b>Pyrogram v2</b>, <b>yt-dlp</b>, and <b>FFmpeg</b>.<br>
  Search, stream, and download tracks, albums, and playlists from <b>Spotify</b>, <b>YouTube</b>, <b>JioSaavn</b>, <b>SoundCloud</b>, and <b>Deezer</b> in high-fidelity <b>MP3</b> or lossless <b>FLAC</b> with complete metadata tagging.<br>
  Includes a centralized <b>Admin Panel</b>, <b>Interactive Premium Plans UI</b>, <b>Dynamic Feature Gates</b>, <b>Maintenance Mode</b>, and <b>Real-Time Statistics Dashboard</b>.
</p>

[**Explore Features**](#-key-features) • [**Admin Panel & Security**](#-admin-panel--security) • [**Premium Ecosystem**](#-premium-ecosystem) • [**Quickstart**](#-quickstart-guide) • [**Bot Commands**](#-bot-commands) • [**Configuration**](#-environment-variables) • [**Deployment**](#-deployment-options)

---

</div>

## 📑 Table of Contents

- [✨ Key Features](#-key-features)
- [🛡️ Admin Panel & Security](#️-admin-panel--security)
- [👑 Premium Ecosystem](#-premium-ecosystem)
- [🔌 Provider Management & Feature Gates](#-provider-management--feature-gates)
- [📊 Statistics Dashboard](#-statistics-dashboard)
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
  - [1. Local Deployment](#1-local-deployment)
  - [2. Docker Container](#2-docker-container)
- [🔧 Troubleshooting & FAQ](#-troubleshooting--faq)
- [⚖️ Legal & Disclaimer](#️-legal--disclaimer)
- [📄 License](#-license)

---

## ✨ Key Features

- **🔍 Multi-Platform Unified Search**
  Search across **Spotify**, **YouTube / YouTube Music**, **JioSaavn**, **SoundCloud**, and **Deezer** from a single search query or link.
- **🎵 Studio-Grade Multi-Format Audio Quality**
  Customizable audio formats and bitrates with non-upscaling source quality tracking:
  - **MP3**: 64 kbps, 128 kbps, 192 kbps, 256 kbps, and 320 kbps (CBR/VBR).
  - **FLAC**: Lossless audio conversion (Low, Medium, High compression).
  - **M4A**: 128 kbps, 192 kbps, 256 kbps, and 320 kbps (High-efficiency AAC).
  - **OGG**: 64 kbps, 96 kbps, 128 kbps, 160 kbps, 192 kbps, 256 kbps, and 320 kbps (Ogg Vorbis).
  - **WAV**: Uncompressed Studio Master PCM (16-bit 44.1kHz, 16-bit 48kHz, 24-bit 44.1kHz, 24-bit 48kHz, 24-bit 96kHz).
- **⚡ Zero-Credential Spotify Fallback**
  Works out of the box even without Spotify API credentials by using an automated anonymous web scraper and provider fallback mechanism.
- **🖼️ Complete Metadata & Cover Art Injection**
  Automatically embeds high-resolution cover artwork, title, artists, album name, track numbers, and release year into ID3 (MP3), Vorbis (FLAC/OGG), MP4 (M4A), and RIFF/ID3 (WAV) tags using `mutagen` and `Pillow`.
- **📀 Batch Playlist & Album Downloader**
  Download entire albums, playlists, and artist top tracks with real-time progress indicators, cancellation controls, and premium priority scheduling.
- **💎 Production-Grade Premium Subscription System**
  Configurable plans (1M, 3M, 6M, 1Y, Lifetime), non-hardcoded pricing, user status screens, and decoupled payment providers (Telegram Payments, UPI/QR verification).
- **🛠️ Telegram Admin Panel with Code Security**
  Interactive GUI panel with SHA-256 access code authentication, rate-limited lockout protection, session timeouts, and revalidated callback authorizations.
- **🔌 Live Provider Management**
  Toggle individual music providers (Spotify, YouTube, JioSaavn, SoundCloud, Deezer) ON/OFF directly from Telegram with instant backend routing enforcement.
- **⚙️ Dynamic Bot Settings & Maintenance Mode**
  Runtime feature gates for Premium System, Free Downloads, Premium Downloads, FLAC, Batch, Priority Queue, and Maintenance Mode with administrative bypass.
- **📊 Real-Time Multi-Period Statistics Dashboard**
  Real-time database-aggregated metrics across 24 hours, 7 days, 30 days, and All-Time with mathematically accurate platform share breakdowns and success rates.
- **🛡️ Dual-Layer Database Architecture**
  Primary storage via **MongoDB Atlas / Local MongoDB** with indexed collections (`users`, `bot_settings`, `provider_settings`, `premium_plans`, `download_records`, `admin_audit`) and an automated in-memory fallback.

---

## 🛡️ Admin Panel & Security

Access the centralized Admin Panel anytime using `/admin` (or `/panel`, `/dashboard`).

```plaintext
🛠 Admin Panel
┌───────────────────────────────┐
│ 📊 Statistics    👑 Premium   │
│ ⚙️ Bot Settings   🔌 Providers │
│ 🔧 Maintenance   👥 Users     │
│ 📢 Broadcast     📜 Logs      │
│ 🚪 Logout        ⬅️ Back      │
└───────────────────────────────┘
```

### Security Highlights
- **Role-Based Authorization**: Strict validation of `OWNER_ID`, `ADMINS`, and `SUDO_USERS` on every administrative action and callback query.
- **Complete Audit Trail**: Sensitive actions (`add_premium`, `toggle_provider`, `maintenance_mode`, `bot_settings`, `user_ban`, `broadcast`) are permanently audited in the database with timestamps and admin IDs.

---

## 👑 Premium Ecosystem

### User-Facing Premium UI
Users can view and manage their membership at any time using `/premium`, `/plans`, or `/profile`:
- **👑 Premium Member Screen**: Shows membership type, active plan, expiration date, remaining days countdown, and full entitlement checklist.
- **💳 Premium Plans Screen**: Features customizable plans (1 Month ₹99, 3 Months ₹249 *Most Popular*, 6 Months ₹399, 1 Year ₹699, Lifetime ₹1499) with savings percentages and instant purchase routing.
- **🛡️ Decoupled Payment Architecture**: Generates verified order IDs and instructions for UPI/Telegram Payments; premium activation occurs strictly upon verified payment or administrator action.

### Entitlements & Priority Queue
- **Free Users**: Configurable daily limits (`FREE_USER_DAILY_LIMIT=5`), MP3 quality, standard priority queue.
- **Premium Users**: Unlimited daily downloads, FLAC lossless format, batch playlist downloads, and weighted priority scheduling (`PREMIUM_PRIORITY_WEIGHT=3`) with fair concurrency reservation.

---

## 🔌 Provider Management & Feature Gates

Control the entire bot runtime without restarting the server:

- **Provider Management (`/admin -> 🔌 Providers`)**:
  - 🟢 Spotify • 🟢 YouTube • 🟢 JioSaavn • 🟢 SoundCloud • 🟢 Deezer
  - Disabling a provider immediately stops routing searches and downloads to that platform and returns user-friendly notice banners.
- **Bot Settings (`/admin -> ⚙️ Bot Settings`)**:
  - `Premium System`: Toggle enforcement of premium tiers.
  - `Free Download`: Master switch for free-tier downloads.
  - `Premium Download`: Master switch for premium downloads.
  - `Premium FLAC`: Toggle FLAC lossless transcoding permission.
  - `Premium Batch`: Toggle album/playlist batch downloading.
  - `Premium Priority`: Toggle weighted priority queuing.
- **Maintenance Mode (`/admin -> 🔧 Maintenance`)**:
  - Instantly pause new download requests with custom maintenance banners while allowing existing active downloads to finish smoothly.
  - Configurable bypass rules: `MAINTENANCE_ALLOW_ADMIN=True`, `MAINTENANCE_ALLOW_PREMIUM=False`.

---

## 📊 Statistics Dashboard

The interactive Statistics Dashboard aggregates real data directly in the database across **24 Hours**, **7 Days**, **30 Days**, and **All-Time**:

```plaintext
📊 Statistics (Last 30 Days)

👥 Users:
• Total Registered: 12,540
• Active: 4,120 | Premium: 842

📥 Downloads:
• Total Attempts: 93,412
• Successful: 90,050 | Failed: 3,362
• Success Rate: 96.4%

🎵 Formats & Queues:
• MP3 Downloads: 82,100 | FLAC Downloads: 7,950
• Active In-Flight: 2 | Queued: 0

🔥 Top Platforms (Successful):
• YouTube:    42,100 (46.8%)
• Spotify:    28,300 (31.4%)
• JioSaavn:   12,200 (13.5%)
• SoundCloud:  5,100 (5.7%)
• Deezer:      2,350 (2.6%)

⏱️ System:
• Uptime: 4d 12h 30m | DB: Connected
```

---

## 🏗️ Project Architecture

```plaintext
SpotiVerse/
├── bot.py                  # Bot lifecycle, uvloop init & startup tasks
├── config.py               # Centralized configuration & environment loader
├── info.py                 # Bot constants, premium plans & duration parser
├── Dockerfile              # Containerization definition with FFmpeg
├── requirements.txt        # Python dependency manifest
├── handlers/
│   ├── admin_panel.py      # Interactive Admin Panel, stats & settings
│   ├── commands.py         # User commands, plans screen, profile & callbacks
│   ├── downloads.py        # Priority queue downloader, FFmpeg & upload
│   └── search.py           # Multi-platform provider aggregators
├── utils/
│   ├── admin_security.py   # Code hashing, lockout rate limiter & sessions
│   ├── audio.py            # Audio transcoding & metadata/thumbnail embedding
│   ├── db.py               # MongoDB multi-collection layer & fallback store
│   ├── feature_gates.py    # 11-step centralized authorization pipeline
│   ├── logger.py           # Telegram channel logging & audit utilities
│   ├── payment.py          # Payment provider abstraction (Telegram & UPI)
│   ├── providers.py        # ProviderRegistry with persistent toggle states
│   ├── queue.py            # Priority-aware fair download scheduling queue
│   └── ytdlp_utils.py      # yt-dlp tuners & cookies loader
├── data/                   # Persistent storage (thumbnails, cache)
└── temp/                   # Temporary directory for audio processing
```

---

## 🚀 Quickstart Guide

### Prerequisites

- **Python**: Version `3.10` or higher (`python3 --version`)
- **FFmpeg**: Installed and available in system `$PATH` (`ffmpeg -version`)
- **Telegram Credentials**:
  - `API_ID` & `API_HASH` from [my.telegram.org](https://my.telegram.org)
  - `BOT_TOKEN` from [@BotFather](https://t.me/BotFather)
- **MongoDB Atlas**: Free cluster or local instance (Optional: In-memory fallback is automatic)

### Standard Installation

1. **Clone the Repository**
   ```bash
   git clone https://github.com/IceCube9680/SpotiVerse
   cd SpotiVerse
   ```

2. **Set Up Virtual Environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install Dependencies**
   ```bash
   sudo apt update && sudo apt install -y ffmpeg curl   # Debian / Ubuntu
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Configure Environment**
   ```bash
   cp .env.sample .env
   nano .env
   ```

5. **Run the Bot**
   ```bash
   python3 bot.py
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
| `MONGO_URI` | `String` | No | *In-Memory* | MongoDB Atlas connection URI (`mongodb+srv://...`). |
| `PREMIUM` / `PREMIUM_MODE` | `Boolean` | No | `True` | Global premium feature enforcement flag. |
| `FREE_USER_DAILY_LIMIT` | `Integer` | No | `5` | Daily download quota for free users (`0` to disable). |
| `PREMIUM_EXPIRY_WARNING_DAYS` | `Integer` | No | `7` | Threshold in days for the Admin *Expiring Soon* list. |
| `MAX_CONCURRENT_DOWNLOADS` | `Integer` | No | `3` | Global simultaneous download limit. |
| `MAX_PREMIUM_CONCURRENT_DOWNLOADS` | `Integer` | No | `5` | Concurrency limit for premium user queue. |
| `MAX_FREE_CONCURRENT_DOWNLOADS` | `Integer` | No | `2` | Concurrency limit for free user queue. |
| `PREMIUM_PRIORITY_WEIGHT` | `Integer` | No | `3` | Scheduling ratio for premium vs. free download tasks. |
| `FREE_AUDIO_FORMATS` | `List[String]` | No | `["mp3"]` | Allowed formats for free users. |
| `FREE_MP3_QUALITIES` | `List[Int]` | No | `[64, 128, 192, 256, 320]` | Allowed MP3 bitrates for free users. |
| `PREMIUM_AUDIO_FORMATS` | `List[String]` | No | `["mp3", "flac", "m4a", "ogg", "wav"]` | Allowed formats for premium users. |
| `PREMIUM_MP3_QUALITIES` | `List[Int]` | No | `[64, 128, 192, 256, 320]` | Allowed MP3 bitrates for premium users. |
| `PREMIUM_M4A_QUALITIES` | `List[Int]` | No | `[128, 192, 256, 320]` | Allowed M4A bitrates for premium users. |
| `PREMIUM_OGG_QUALITIES` | `List[Int]` | No | `[64, 96, 128, 160, 192, 256, 320]` | Allowed Ogg Vorbis bitrates for premium users. |
| `PREMIUM_WAV_BIT_DEPTHS` | `List[Int]` | No | `[16, 24]` | Allowed WAV PCM bit depths for premium users. |
| `PREMIUM_WAV_SAMPLE_RATES` | `List[Int]` | No | `[44100, 48000, 96000]` | Allowed WAV sample rates (Hz) for premium users. |
| `MAX_AUDIO_FILE_SIZE_MB` | `Integer` | No | `50` | Maximum audio upload file size before warning. |
| `PAYMENT_UPI_ID` | `String` | No | `icecube@upi` | UPI ID displayed for manual QR payments. |
| `PAYMENT_PROVIDER_TOKEN` | `String` | No | `""` | Telegram Payments Provider token for invoices. |

---

## 🤖 Bot Commands

### User Commands

| Command | Aliases | Parameters | Description |
| :--- | :--- | :--- | :--- |
| `/start` | — | None | Starts the bot, registers profile, and displays main menu. |
| `/search` | `/s`, `/find` | `<query>` | Unified multi-platform search with paginated inline buttons. |
| `/download` | `/dl`, `/d` | `<url>` or `<query>` | Directly download track, album, or playlist. |
| `/settings` | `/setting`, `/set` | None | Configure default format (MP3/FLAC) and bitrate (64k–320k). |
| `/profile` | `/userinfo`, `/me` | None | Displays membership tier, download stats, and remaining quota. |
| `/premium` | `/prem`, `/plans` | None | Interactive Premium Plans screen & membership upgrade options. |
| `/help` | `/h` | None | Displays interactive help manual and format specifications. |

### Admin & Owner Commands

| Command | Aliases | Parameters | Description |
| :--- | :--- | :--- | :--- |
| `/admin` | `/panel`, `/dashboard` | None | Opens the interactive Telegram Admin Panel. |
| `/stats` | `/stat` | None | Real-time system, user, and download statistics. |
| `/add_premium` | `/give_premium` | `<user_id>` `<duration>` | Grants premium status (`7d`, `30d`, `90d`, `180d`, `1y`, `lifetime`). |
| `/remove_premium` | `/unpremium` | `<user_id>` | Revokes premium status from a user. |
| `/ban` | `/unban` | `<user_id>` | Ban or unban a user from using the bot. |
| `/broadcast` | `/bc` | `<msg>` / Reply | Broadcasts message with progress and delivery stats. |
| `/logs` | `/log` | None | Exports live runtime log stream directly into chat. |

---

## 📦 Deployment Options

### 1. Local Deployment
```bash
# Clone & install dependencies
git clone https://github.com/IceCube9680/SpotiVerse
cd SpotiVerse
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Configure & run
cp .env.sample .env
python3 bot.py
```

### 2. Docker Container
```bash
docker build -t spotiverse:latest .
docker run -d \
  --name spotiverse_bot \
  --restart unless-stopped \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  spotiverse:latest
```

---

## 🔧 Troubleshooting & FAQ

<details>
<summary><b>1. Admin Panel access</b></summary>

- Only authorized Telegram users configured in `OWNER_ID`, `ADMINS`, or `SUDO_USERS` can access `/admin`.
</details>

<details>
<summary><b>2. YouTube bot detection (HTTP 429)</b></summary>

- Place an exported `cookies.txt` file in the project root to authenticate with YouTube.
</details>

<details>
<summary><b>3. Maintenance Mode behavior</b></summary>

- When Maintenance is enabled, new user downloads are immediately halted with an informative notice. In-flight downloads finish uninterrupted.
</details>

---

## ⚖️ Legal & Disclaimer

> [!IMPORTANT]
> **Educational & Personal Use Only**
> This software is intended for personal research and educational purposes. Ensure compliance with your local laws and third-party terms of service. All trademarks and logos belong to their respective owners.

---

## 📄 License

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for details.

<div align="center">
  <sub>Built with ❤️ by <a href="https://github.com/IceCube9680">IceCube</a> & <a href="https://github.com/priest9680">Priest Gamer</a></sub>
</div>
