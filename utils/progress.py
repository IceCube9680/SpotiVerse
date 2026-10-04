# utils/progress.py
import time
import math
import asyncio
import logging
from typing import Optional, Callable, Any, Union

logger = logging.getLogger(__name__)

def format_bytes(bytes_count: float) -> str:
    """Format bytes into a human-readable string (e.g. 5.4 MB)"""
    if bytes_count is None or bytes_count <= 0 or math.isnan(bytes_count):
        return "0.0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    val = float(bytes_count)
    while val >= 1024.0 and i < len(units) - 1:
        val /= 1024.0
        i += 1
    return f"{val:.1f} {units[i]}"

def format_speed(bytes_per_sec: float) -> str:
    """Format download/upload speed (e.g. 1.8 MB/s)"""
    if bytes_per_sec is None or bytes_per_sec <= 0 or math.isnan(bytes_per_sec):
        return "0.0 B/s"
    return f"{format_bytes(bytes_per_sec)}/s"

def format_eta(seconds: Optional[float]) -> str:
    """Format seconds into human-readable ETA (e.g. 15s, 2m 30s, 1h 15m)"""
    if seconds is None or seconds < 0 or math.isnan(seconds) or math.isinf(seconds):
        return "--:--"
    sec = int(round(seconds))
    if sec == 0:
        return "0s"
    if sec < 60:
        return f"{sec}s"
    if sec < 3600:
        mins = sec // 60
        rem_sec = sec % 60
        return f"{mins}m {rem_sec:02d}s"
    hours = sec // 3600
    rem_mins = (sec % 3600) // 60
    return f"{hours}h {rem_mins:02d}m"

def format_duration(seconds: Optional[Union[int, float]]) -> str:
    """Format track duration into MM:SS or HH:MM:SS"""
    if seconds is None or seconds <= 0 or math.isnan(seconds):
        return ""
    sec = int(round(seconds))
    mins = sec // 60
    rem_sec = sec % 60
    if mins >= 60:
        hours = mins // 60
        rem_mins = mins % 60
        return f"{hours}:{rem_mins:02d}:{rem_sec:02d}"
    return f"{mins}:{rem_sec:02d}"

def render_progress_bar(current: float, total: float, length: int = 10) -> str:
    """
    Render a visual Unicode progress bar.
    Example: [██████░░░░] 60.0%
    """
    if total is None or total <= 0 or current is None or current < 0:
        return f"[{'░' * length}] 0.0%"
    
    pct = min(100.0, max(0.0, (float(current) / float(total)) * 100.0))
    filled_len = int(round(length * (pct / 100.0)))
    filled_len = max(0, min(length, filled_len))
    bar = "█" * filled_len + "░" * (length - filled_len)
    return f"[{bar}] {pct:.1f}%"


class BatchProgressTracker:
    """
    Tracks overall progress and total ETA for batch operations (album, playlist, artist).
    """
    def __init__(self, kind: str = "album", title: str = "Collection", total_tracks: int = 0):
        self.kind = kind
        self.title = title
        self.total_tracks = max(0, total_tracks)
        self.current_index = 0
        self.success_count = 0
        self.fail_count = 0
        self.start_time = time.time()
        self.track_start_time = time.time()
        self.completed_durations = []
        self.last_edit_time = 0.0
        self.edit_interval = 2.5  # seconds throttle between message updates

    def start_track(self, index: int, title: str = ""):
        """Mark start of a new track in the batch"""
        self.current_index = index
        self.track_start_time = time.time()

    def record_track_result(self, success: bool):
        """Record completion of current track"""
        duration = time.time() - self.track_start_time
        self.completed_durations.append(max(0.5, duration))
        if success:
            self.success_count += 1
        else:
            self.fail_count += 1

    @property
    def completed_tracks(self) -> int:
        return self.success_count + self.fail_count

    def get_total_eta(self, current_track_fraction: float = 0.0) -> float:
        """
        Calculate estimated remaining time for all remaining tracks in the batch.
        """
        if self.total_tracks <= 0:
            return 0.0
        
        completed_eff = self.completed_tracks + current_track_fraction
        remaining_tracks = max(0.0, self.total_tracks - completed_eff)
        if remaining_tracks <= 0.0:
            return 0.0

        elapsed = time.time() - self.start_time
        if completed_eff > 0 and elapsed > 0:
            avg_per_track = elapsed / completed_eff
        elif self.completed_durations:
            avg_per_track = sum(self.completed_durations) / len(self.completed_durations)
        else:
            # Default heuristic fallback: ~15 seconds per track
            avg_per_track = 15.0

        return remaining_tracks * avg_per_track

    def render_header(self, current_track_fraction: float = 0.0) -> str:
        """Render the batch header status block"""
        completed_eff = self.completed_tracks + current_track_fraction
        batch_bar = render_progress_bar(completed_eff, self.total_tracks, length=10)
        total_eta = self.get_total_eta(current_track_fraction)
        eta_str = format_eta(total_eta)

        icon = "💿" if self.kind == "album" else ("👤" if self.kind == "artist" else "📋")
        kind_label = self.kind.title() if self.kind else "Collection"

        lines = [
            f"{icon} **{kind_label} Download:** {self.title}",
            f"📦 **Batch Progress:** {batch_bar} Track {self.current_index}/{self.total_tracks}",
            f"✅ **Success:** {self.success_count}  |  ❌ **Failed:** {self.fail_count}",
            f"⏳ **Total ETA:** {eta_str}",
            ""
        ]
        return "\n".join(lines)


class ProgressTracker:
    """
    Manages live downloading and uploading progress, song metadata details,
    file-level ETA, transfer speed, and message updates.
    Integrates with BatchProgressTracker when operating inside a batch.
    """
    def __init__(
        self,
        bot: Any,
        message: Any,
        title: str = "Audio",
        artist: str = "Unknown Artist",
        album: Optional[str] = None,
        duration: Optional[Union[int, float]] = None,
        year: Optional[str] = None,
        provider: Optional[str] = None,
        format_name: Optional[str] = None,
        quality: Optional[Union[int, str]] = None,
        batch_tracker: Optional[BatchProgressTracker] = None,
        safe_edit_fn: Optional[Callable] = None
    ):
        self.bot = bot
        self.message = message
        self.title = title
        self.artist = artist
        self.album = album
        self.duration = duration
        self.year = str(year) if year else None
        self.provider = provider
        self.format_name = format_name
        self.quality = quality
        self.batch_tracker = batch_tracker
        self.safe_edit_fn = safe_edit_fn

        # Download tracking state
        self.download_start_time = time.time()
        self.download_last_bytes = 0
        self.download_last_time = time.time()
        self.download_speed_smoothed = 0.0

        # Upload tracking state
        self.upload_start_time = time.time()
        self.upload_last_bytes = 0
        self.upload_last_time = time.time()
        self.upload_speed_smoothed = 0.0

        # Throttling state
        self.last_edit_time = 0.0
        self.last_edit_text = ""
        self.min_interval = 2.0  # seconds between edits to protect against FloodWait
        self._lock = asyncio.Lock()

    def render_song_details(self) -> str:
        """Render rich song details block showing title, artist, album, duration, format & bitrate"""
        lines = []
        if self.title:
            lines.append(f"🎵 **Song:** {self.title}")
        if self.artist and self.artist != "Unknown Artist":
            lines.append(f"👤 **Artist:** {self.artist}")
        if self.album and self.album not in ("Spotify", "YouTube", "JioSaavn", "Deezer", "SoundCloud", "Unknown Album", "Unknown"):
            lines.append(f"💿 **Album:** {self.album}")

        dur_str = format_duration(self.duration)
        if dur_str:
            lines.append(f"⏱️ **Duration:** `{dur_str}`")

        if self.format_name:
            fmt_upper = str(self.format_name).upper()
            if self.quality and str(self.quality) not in ("0", ""):
                q_str = f" ({self.quality}kbps)" if str(self.quality).isdigit() else f" ({self.quality})"
            else:
                q_str = ""
            lines.append(f"🎧 **Format:** `{fmt_upper}{q_str}`")

        if self.year:
            lines.append(f"📅 **Year:** `{self.year}`")

        return "\n".join(lines)

    async def _safe_edit(self, text: str, force: bool = False):
        """Safely edit the progress message with throttling and duplicate suppression"""
        if not self.message or not text:
            return

        now = time.time()
        if not force and (now - self.last_edit_time < self.min_interval):
            return

        if text == self.last_edit_text:
            return

        async with self._lock:
            # Re-check inside lock
            now = time.time()
            if not force and (now - self.last_edit_time < self.min_interval):
                return
            if text == self.last_edit_text:
                return

            self.last_edit_time = now
            self.last_edit_text = text

            if self.safe_edit_fn:
                new_msg = await self.safe_edit_fn(self.message, text)
                if new_msg:
                    self.message = new_msg
            elif hasattr(self.message, 'edit_text'):
                try:
                    res = await self.message.edit_text(text)
                    if res:
                        self.message = res
                except Exception as e:
                    logger.debug(f"ProgressTracker edit_text error: {e}")

    async def update_download(
        self,
        downloaded: int,
        total: Optional[int],
        speed: Optional[float] = None,
        eta: Optional[float] = None,
        force: bool = False
    ):
        """Update download progress, bar, speed, song details, and ETA"""
        now = time.time()
        total_bytes = total if total and total > 0 else 0
        current_bytes = downloaded or 0

        # Calculate / smooth speed
        if speed is not None and speed > 0:
            current_speed = speed
        else:
            time_delta = now - self.download_last_time
            bytes_delta = current_bytes - self.download_last_bytes
            if time_delta > 0.3 and bytes_delta >= 0:
                current_speed = bytes_delta / time_delta
                self.download_last_time = now
                self.download_last_bytes = current_bytes
            else:
                current_speed = self.download_speed_smoothed

        if self.download_speed_smoothed == 0.0:
            self.download_speed_smoothed = current_speed
        else:
            self.download_speed_smoothed = 0.7 * self.download_speed_smoothed + 0.3 * current_speed

        # Calculate ETA
        if eta is not None and eta >= 0:
            file_eta = eta
        elif total_bytes > 0 and self.download_speed_smoothed > 0:
            rem_bytes = max(0, total_bytes - current_bytes)
            file_eta = rem_bytes / self.download_speed_smoothed
        else:
            file_eta = None

        bar = render_progress_bar(current_bytes, total_bytes, length=10)
        speed_str = format_speed(self.download_speed_smoothed)
        eta_str = format_eta(file_eta)
        size_str = f"{format_bytes(current_bytes)} / {format_bytes(total_bytes)}" if total_bytes > 0 else format_bytes(current_bytes)

        fraction = (current_bytes / total_bytes * 0.5) if total_bytes > 0 else 0.0
        details = self.render_song_details()
        details_block = f"{details}\n\n" if details else ""

        if self.batch_tracker:
            batch_header = self.batch_tracker.render_header(current_track_fraction=fraction)
            text = (
                f"{batch_header}"
                f"⬇️ **Downloading Track [{self.batch_tracker.current_index}/{self.batch_tracker.total_tracks}]...**\n\n"
                f"{details_block}"
                f"{bar}\n"
                f"⚡ **Speed:** {speed_str}  |  ⏳ **ETA:** {eta_str}\n"
                f"💾 **Size:** {size_str}"
            )
        else:
            text = (
                f"⬇️ **Downloading Audio...**\n\n"
                f"{details_block}"
                f"{bar}\n"
                f"⚡ **Speed:** {speed_str}  |  ⏳ **ETA:** {eta_str}\n"
                f"💾 **Size:** {size_str}"
            )

        is_done = total_bytes > 0 and current_bytes >= total_bytes
        await self._safe_edit(text, force=force or is_done)

    async def update_upload(self, current: int, total: int, force: bool = False):
        """Update upload progress, bar, speed, song details, and ETA during Telegram file dispatch"""
        now = time.time()
        current_bytes = current or 0
        total_bytes = total or 0

        # Calculate upload speed
        time_delta = now - self.upload_start_time
        if time_delta > 0 and current_bytes > 0:
            upload_speed = current_bytes / time_delta
        else:
            upload_speed = 0.0

        if total_bytes > 0 and upload_speed > 0:
            rem_bytes = max(0, total_bytes - current_bytes)
            upload_eta = rem_bytes / upload_speed
        else:
            upload_eta = None

        bar = render_progress_bar(current_bytes, total_bytes, length=10)
        speed_str = format_speed(upload_speed)
        eta_str = format_eta(upload_eta)
        size_str = f"{format_bytes(current_bytes)} / {format_bytes(total_bytes)}" if total_bytes > 0 else format_bytes(current_bytes)

        fraction = 0.5 + ((current_bytes / total_bytes * 0.5) if total_bytes > 0 else 0.0)
        details = self.render_song_details()
        details_block = f"{details}\n\n" if details else ""

        if self.batch_tracker:
            batch_header = self.batch_tracker.render_header(current_track_fraction=fraction)
            text = (
                f"{batch_header}"
                f"📤 **Uploading Track [{self.batch_tracker.current_index}/{self.batch_tracker.total_tracks}] to Telegram...**\n\n"
                f"{details_block}"
                f"{bar}\n"
                f"⚡ **Speed:** {speed_str}  |  ⏳ **ETA:** {eta_str}\n"
                f"💾 **Size:** {size_str}"
            )
        else:
            text = (
                f"📤 **Uploading Audio to Telegram...**\n\n"
                f"{details_block}"
                f"{bar}\n"
                f"⚡ **Speed:** {speed_str}  |  ⏳ **ETA:** {eta_str}\n"
                f"💾 **Size:** {size_str}"
            )

        is_done = total_bytes > 0 and current_bytes >= total_bytes
        await self._safe_edit(text, force=force or is_done)

    async def update_status(self, status_text: str, force: bool = False):
        """Update general status message with song details and batch header"""
        details = self.render_song_details()
        details_block = f"\n\n{details}" if details else ""
        if self.batch_tracker:
            batch_header = self.batch_tracker.render_header(current_track_fraction=0.5)
            text = f"{batch_header}{status_text}{details_block}"
        else:
            text = f"{status_text}{details_block}"
        await self._safe_edit(text, force=force)
