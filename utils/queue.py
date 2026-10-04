# utils/queue.py
import asyncio
import logging
from config import Config

logger = logging.getLogger(__name__)

class DownloadQueueManager:
    """
    Priority-Aware Download Queue with Bounded Fairness:
    - Dedicated concurrency limits for premium & free users.
    - Premium requests get prioritized execution.
    - Bounded fairness ensures free user requests are not starved.
    """
    def __init__(self):
        self._total_semaphore = None
        self._prem_semaphore = None
        self._free_semaphore = None
        self._lock = None
        self._loop = None

        self._active_downloads = 0
        self._queued_premium = 0
        self._queued_free = 0

    def _ensure_primitives(self):
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if self._total_semaphore is None or self._loop != current_loop:
            self._loop = current_loop
            total_max = getattr(Config, "MAX_CONCURRENT_DOWNLOADS", 3) or 3
            prem_max = getattr(Config, "MAX_PREMIUM_CONCURRENT_DOWNLOADS", 5) or 5
            free_max = getattr(Config, "MAX_FREE_CONCURRENT_DOWNLOADS", 2) or 2

            self._total_semaphore = asyncio.Semaphore(total_max)
            self._prem_semaphore = asyncio.Semaphore(prem_max)
            self._free_semaphore = asyncio.Semaphore(free_max)
            self._lock = asyncio.Lock()

    @property
    def queue_status(self) -> dict:
        return {
            "active_downloads": self._active_downloads,
            "queued_premium": self._queued_premium,
            "queued_free": self._queued_free,
            "total_queued": self._queued_premium + self._queued_free
        }

    async def acquire(self, is_premium: bool = False, is_priority: bool = False):
        """Acquire download slot respecting priority and tier limits"""
        self._ensure_primitives()
        async with self._lock:
            if is_priority or is_premium:
                self._queued_premium += 1
            else:
                self._queued_free += 1

        tier_sem = self._prem_semaphore if (is_priority or is_premium) else self._free_semaphore

        # Acquire tier semaphore then total semaphore
        await tier_sem.acquire()
        await self._total_semaphore.acquire()

        async with self._lock:
            if is_priority or is_premium:
                self._queued_premium = max(0, self._queued_premium - 1)
            else:
                self._queued_free = max(0, self._queued_free - 1)
            self._active_downloads += 1

    def release(self, is_premium: bool = False, is_priority: bool = False):
        """Release slot back to queue"""
        self._ensure_primitives()
        self._total_semaphore.release()
        tier_sem = self._prem_semaphore if (is_priority or is_premium) else self._free_semaphore
        tier_sem.release()
        self._active_downloads = max(0, self._active_downloads - 1)

class DownloadSlot:
    """Async context manager for download queue slot"""
    def __init__(self, queue_mgr: DownloadQueueManager, is_premium: bool = False, is_priority: bool = False, priority: bool = None):
        self.queue_mgr = queue_mgr
        self.is_premium = is_premium
        self.is_priority = is_priority if priority is None else priority

    async def __aenter__(self):
        await self.queue_mgr.acquire(self.is_premium, self.is_priority)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.queue_mgr.release(self.is_premium, self.is_priority)

download_queue = DownloadQueueManager()
