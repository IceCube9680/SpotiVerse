# utils/db.py
import os
import time
import logging
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient, errors
from info import DEFAULT_SETTINGS

logger = logging.getLogger(__name__)

# Try to pull defaults from config.py if available
try:
    from config import Config
    _DEFAULT_MONGO_URI = getattr(Config, "MONGO_URI", "mongodb+srv://ice:mlovely9680@cluster0.y9czlat.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
    _DEFAULT_DB_NAME = getattr(Config, "DB_NAME", "spotiverse_bot")
except Exception:
    _DEFAULT_MONGO_URI = "mongodb+srv://ice:mlovely9680@cluster0.y9czlat.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
    _DEFAULT_DB_NAME = "spotiverse_bot"

MONGO_URI = os.environ.get("MONGO_URI", _DEFAULT_MONGO_URI)
DB_NAME = os.environ.get("MONGO_DBNAME", _DEFAULT_DB_NAME)

# Local in-memory fallback store (used only when MongoDB is unreachable)
_fallback_store = {
    "users": {},        # user_id -> user dict
    "downloads": []     # list of download records (dicts)
}

def _get_utc_now() -> datetime:
    """Return naive UTC datetime for pymongo compatibility while avoiding Python 3.12+ deprecation warnings."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

def _parse_datetime(val) -> datetime | None:
    """Parse various datetime representations (datetime object, ISO string, epoch float)."""
    if val is None:
        return None
    if isinstance(val, datetime):
        if val.tzinfo is not None:
            return val.astimezone(timezone.utc).replace(tzinfo=None)
        return val
    if isinstance(val, (int, float)):
        try:
            return datetime.fromtimestamp(val, tz=timezone.utc).replace(tzinfo=None)
        except Exception:
            return None
    if isinstance(val, str):
        val_clean = val.strip()
        # Try ISO format
        try:
            dt = datetime.fromisoformat(val_clean.replace("Z", "+00:00"))
            if dt.tzinfo is not None:
                return dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        except Exception:
            pass
        # Try standard formats
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d"):
            try:
                return datetime.strptime(val_clean, fmt)
            except Exception:
                pass
    return None

def _populate_user_defaults(user: dict) -> dict:
    """Ensure all expected fields exist on the user dict."""
    if not user:
        return user
    today_str = _get_utc_now().strftime("%Y-%m-%d")
    defaults = {
        "premium": False,
        "premium_until": None,
        "downloads_today": 0,
        "total_downloads": 0,
        "last_download_date": today_str,
        "preferred_format": DEFAULT_SETTINGS.get("preferred_format", "mp3"),
        "preferred_quality": DEFAULT_SETTINGS.get("preferred_quality", 64),
        "join_date": _get_utc_now()
    }
    for k, v in defaults.items():
        if k not in user or (user[k] is None and k not in ("premium_until",)):
            user[k] = v
    return user

class Database:
    def __init__(self, connect=True):
        self.client = None
        self.db = None
        self.users = None
        self.downloads = None
        self.available = False
        self.last_try = 0
        self.retry_interval = 10  # seconds between reconnect attempts
        # whether we've attempted to sync fallback after last successful connect
        self._synced_after_connect = False

        # Try initial connection if requested
        if connect:
            self._try_connect(initial=True)

    def _try_connect(self, initial=False):
        now = time.time()
        # avoid hammering reconnection attempts
        if not initial and now - self.last_try < self.retry_interval:
            return

        self.last_try = now

        # Clean up any existing client before attempting a new connection
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
            self.client = None

        if not MONGO_URI:
            logger.warning("MONGO_URI not set — using in-memory fallback DB.")
            self.available = False
            return

        try:
            # small timeout so bot can start quickly if DB is unreachable
            self.client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000, connectTimeoutMS=2000)
            # trigger a ping to ensure connectivity
            self.client.admin.command('ping')
            self.db = self.client[DB_NAME]
            self.users = self.db.get_collection("users")
            self.downloads = self.db.get_collection("downloads")
            self.available = True
            logger.info("Connected to MongoDB.")

            # After successful connect, attempt to sync fallback if needed
            if not self._synced_after_connect:
                try:
                    self._sync_fallback_to_mongo()
                    self._synced_after_connect = True
                except Exception as e:
                    logger.warning(f"Failed to sync fallback after connect: {e}")

        except Exception as e:
            logger.warning(f"MongoDB connection failed: {e}. Falling back to in-memory DB.")
            self.available = False
            # Clean up partial client immediately
            try:
                if self.client:
                    self.client.close()
            except Exception:
                pass
            self.client = None
            self.db = None
            self.users = None
            self.downloads = None

    def close(self):
        """Safely close MongoClient connection and free background resources."""
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
            self.client = None
        self.db = None
        self.users = None
        self.downloads = None
        self.available = False

    # --- Helper to ensure we have attempted reconnects ---
    def _ensure(self):
        if not self.available:
            self._try_connect()

    # === Sync fallback store to MongoDB ===
    def _sync_fallback_to_mongo(self):
        """
        Pushes in-memory fallback users and downloads into MongoDB.
        This is best-effort and idempotent for users (upsert).
        Downloads are inserted; to avoid duplicates we attach a 'synced_from_fallback' flag.
        After successful sync the fallback store is cleared.
        """
        if not self.available or self.users is None or self.downloads is None:
            logger.debug("Skipping sync: MongoDB not available.")
            return

        # Sync users: upsert all fallback users
        fallback_users = list(_fallback_store["users"].values())
        if fallback_users:
            logger.info(f"Syncing {len(fallback_users)} fallback users to MongoDB...")
            for user in fallback_users:
                try:
                    self.users.update_one({"user_id": user["user_id"]}, {"$set": user}, upsert=True)
                except Exception as e:
                    logger.warning(f"Failed to upsert fallback user {user.get('user_id')}: {e}")

        # Sync downloads: insert entries and mark them as synced
        fallback_downloads = list(_fallback_store["downloads"])
        if fallback_downloads:
            logger.info(f"Syncing {len(fallback_downloads)} fallback downloads to MongoDB...")
            docs_to_insert = []
            for entry in fallback_downloads:
                doc = dict(entry)
                doc["_synced_from_fallback"] = True
                if "timestamp" not in doc or doc["timestamp"] is None:
                    doc["timestamp"] = _get_utc_now()
                docs_to_insert.append(doc)
            try:
                if docs_to_insert:
                    self.downloads.insert_many(docs_to_insert)
            except Exception as e:
                logger.warning(f"Failed to insert fallback downloads: {e}")

        # If we reached here without raising, clear the fallback store
        _fallback_store["users"].clear()
        _fallback_store["downloads"].clear()
        logger.info("Fallback store synced to MongoDB and cleared.")

    # --- Public API used by the bot ---
    def _check_and_reset_daily(self, user: dict) -> dict:
        """Reset downloads_today if the calendar day has changed"""
        if not user:
            return user
        today_str = _get_utc_now().strftime("%Y-%m-%d")
        last_date = user.get("last_download_date")
        if last_date != today_str:
            user["downloads_today"] = 0
            user["last_download_date"] = today_str
            if self.available and self.users is not None:
                try:
                    self.users.update_one(
                        {"user_id": user["user_id"]},
                        {"$set": {"downloads_today": 0, "last_download_date": today_str}}
                    )
                except Exception:
                    pass
        return user

    def get_user(self, user_id: int):
        """
        Return a user dict. If DB is down, use in-memory fallback.
        """
        self._ensure()
        today_str = _get_utc_now().strftime("%Y-%m-%d")
        if self.available and self.users is not None:
            try:
                user = self.users.find_one({"user_id": user_id})
                if user:
                    return _populate_user_defaults(self._check_and_reset_daily(user))
                # create default user
                new_user = {
                    "user_id": user_id,
                    "premium": False,
                    "premium_until": None,
                    "downloads_today": 0,
                    "total_downloads": 0,
                    "last_download_date": today_str,
                    "preferred_format": DEFAULT_SETTINGS.get("preferred_format", "mp3"),
                    "preferred_quality": DEFAULT_SETTINGS.get("preferred_quality", 64),
                    "join_date": _get_utc_now()
                }
                self.users.insert_one(new_user)
                return new_user
            except errors.PyMongoError as e:
                logger.warning(f"Mongo error in get_user: {e} — using fallback store.")
                self.available = False
                return _populate_user_defaults(self._check_and_reset_daily(self._get_user_fallback(user_id)))
        else:
            return _populate_user_defaults(self._check_and_reset_daily(self._get_user_fallback(user_id)))

    def _get_user_fallback(self, user_id):
        user = _fallback_store["users"].get(user_id)
        if user:
            return user
        today_str = _get_utc_now().strftime("%Y-%m-%d")
        user = {
            "user_id": user_id,
            "premium": False,
            "premium_until": None,
            "downloads_today": 0,
            "total_downloads": 0,
            "last_download_date": today_str,
            "preferred_format": DEFAULT_SETTINGS.get("preferred_format", "mp3"),
            "preferred_quality": DEFAULT_SETTINGS.get("preferred_quality", 64),
            "join_date": _get_utc_now()
        }
        _fallback_store["users"][user_id] = user
        return user

    def update_user(self, user_id: int, data: dict):
        self._ensure()
        if self.available and self.users is not None:
            try:
                self.users.update_one({"user_id": user_id}, {"$set": data}, upsert=True)
                return True
            except errors.PyMongoError as e:
                logger.warning(f"Mongo error in update_user: {e} — applying to fallback.")
                self.available = False
        # fallback
        user = _fallback_store["users"].get(user_id) or self._get_user_fallback(user_id)
        user.update(data)
        _fallback_store["users"][user_id] = user
        return True

    def can_download(self, user_id: int):
        """
        Return (True, None) if allowed, (False, reason) if not.
        - Premium users, bot owners, and Config.PREMIUM_USERS list have UNLIMITED downloads.
        - Free users can download up to Config.FREE_USER_DAILY_LIMIT downloads per day.
        """
        self._ensure()

        if self.is_premium(user_id):
            return True, None

        from config import Config
        user = self.get_user(user_id)
        if not user:
            return True, None

        downloads_today = user.get("downloads_today", 0)
        daily_limit = getattr(Config, "FREE_USER_DAILY_LIMIT", 5)
        if downloads_today >= daily_limit:
            return False, f"Daily download limit reached ({downloads_today}/{daily_limit}). Upgrade to Premium for unlimited downloads."

        return True, None

    def get_premium_mode(self) -> bool:
        """
        Get the current premium enforcement mode.
        Returns:
            True: Premium mode is ON (only premium members get premium features).
            False: Premium mode is OFF (all features unlocked for everyone).
        """
        from config import Config
        self._ensure()
        if self.available and self.db is not None:
            try:
                settings_col = self.db.get_collection("bot_settings")
                doc = settings_col.find_one({"key": "premium_mode"})
                if doc and "value" in doc:
                    return bool(doc["value"])
            except Exception as e:
                logger.debug(f"Error reading premium_mode from DB: {e}")
        # fallback to in-memory store or Config
        if "premium_mode" in _fallback_store:
            return bool(_fallback_store["premium_mode"])
        return getattr(Config, "PREMIUM", getattr(Config, "PREMIUM_MODE", True))

    def set_premium_mode(self, mode: bool) -> bool:
        """
        Update the current premium enforcement mode dynamically in Config, DB and in-memory fallback.
        """
        from config import Config
        mode = bool(mode)
        Config.PREMIUM = mode
        Config.PREMIUM_MODE = mode
        _fallback_store["premium_mode"] = mode

        self._ensure()
        if self.available and self.db is not None:
            try:
                settings_col = self.db.get_collection("bot_settings")
                settings_col.update_one(
                    {"key": "premium_mode"},
                    {"$set": {"key": "premium_mode", "value": mode, "updated_at": _get_utc_now()}},
                    upsert=True
                )
            except Exception as e:
                logger.warning(f"Error persisting premium_mode in DB: {e}")
        return mode

    def is_premium(self, user_id: int) -> bool:
        """
        Check if user has active premium status.
        Handles:
        1. Global PREMIUM_MODE toggle: If PREMIUM_MODE is False (public mode), ALL users are considered premium.
        2. Bot owners (always True)
        3. Config.PREMIUM_USERS list (always True)
        4. Database active premium records (auto-expires if past premium_until)
        """
        if not user_id:
            return False

        # When premium mode is OFF (False), all features are enabled for everyone
        if not self.get_premium_mode():
            return True

        from config import Config
        if Config.is_owner(user_id) or user_id in getattr(Config, "PREMIUM_USERS", []):
            return True
        user = self.get_user(user_id)
        if not user or not user.get("premium"):
            return False
        until_dt = _parse_datetime(user.get("premium_until"))
        if until_dt and until_dt < _get_utc_now():
            self.update_user(user_id, {"premium": False, "premium_until": None})
            return False
        return True

    def get_effective_settings(self, user_id: int):
        """
        Return the settings to use for this user (do not mutate DB).
        Preserves stored preferences but returns free defaults for non-premium users.
        """
        user = self.get_user(user_id) or {}
        if self.is_premium(user_id):
            fmt = user.get("preferred_format", DEFAULT_SETTINGS.get("preferred_format", "mp3"))
            q  = user.get("preferred_quality", DEFAULT_SETTINGS.get("preferred_quality", 320))
            return {"preferred_format": fmt, "preferred_quality": q}

        # Non-premium -> return free defaults (do not overwrite DB)
        return {
            "preferred_format": DEFAULT_SETTINGS.get("preferred_format", "mp3"),
            "preferred_quality": DEFAULT_SETTINGS.get("preferred_quality", 64)
        }

    def increment_download(self, user_id: int):
        """Increment counters after successful download."""
        self._ensure()
        today_str = _get_utc_now().strftime("%Y-%m-%d")
        user = self.get_user(user_id)
        if user.get("last_download_date") != today_str:
            new_today = 1
        else:
            new_today = user.get("downloads_today", 0) + 1
        new_total = user.get("total_downloads", 0) + 1

        if self.available and self.users is not None:
            try:
                self.users.update_one(
                    {"user_id": user_id},
                    {"$set": {
                        "downloads_today": new_today,
                        "total_downloads": new_total,
                        "last_download_date": today_str
                    }}
                )
                return True
            except errors.PyMongoError as e:
                logger.warning(f"Mongo error in increment_download: {e} — applying to fallback.")
                self.available = False
        # fallback
        u = _fallback_store["users"].get(user_id) or self._get_user_fallback(user_id)
        u["downloads_today"] = new_today
        u["total_downloads"] = new_total
        u["last_download_date"] = today_str
        _fallback_store["users"][user_id] = u
        return True

    def record_download(self, user_id: int, track_info: dict, username: str = None):
        """Record a download (track_info should be serializable)"""
        self._ensure()
        uname = username or track_info.get("username")
        if not uname and hasattr(self, "get_user"):
            try:
                u = self.get_user(user_id)
                if u:
                    uname = u.get("username")
            except Exception:
                pass
        entry = {"user_id": user_id, "username": uname, "track_info": track_info, "timestamp": _get_utc_now()}
        if self.available and self.downloads is not None:
            try:
                self.downloads.insert_one(entry)
                self.increment_download(user_id)
                return True
            except errors.PyMongoError as e:
                logger.warning(f"Mongo error in record_download: {e} — saving to fallback.")
                self.available = False
        # fallback
        _fallback_store["downloads"].append(entry)
        self.increment_download(user_id)
        return True

    def add_premium(self, user_id: int, days: float):
        """Grant premium for days; return premium_until datetime"""
        self._ensure()
        now = _get_utc_now()
        current_user = self.get_user(user_id) if (self.available and self.users is not None) else (_fallback_store["users"].get(user_id) or self._get_user_fallback(user_id))
        
        # If user already has active premium in future, extend from that date
        existing_until = _parse_datetime(current_user.get("premium_until")) if current_user else None
        if existing_until and existing_until > now:
            base_time = existing_until
        else:
            base_time = now

        if days >= 36500:
            until = base_time + timedelta(days=36500)
        else:
            until = base_time + timedelta(days=days)

        if self.available and self.users is not None:
            try:
                self.users.update_one({"user_id": user_id}, {"$set": {"premium": True, "premium_until": until}}, upsert=True)
                return until
            except errors.PyMongoError as e:
                logger.warning(f"Mongo error in add_premium: {e} — applying to fallback.")
                self.available = False
        # fallback
        user = _fallback_store["users"].get(user_id) or self._get_user_fallback(user_id)
        user["premium"] = True
        user["premium_until"] = until
        _fallback_store["users"][user_id] = user
        return until

    def remove_premium(self, user_id: int):
        self._ensure()
        if self.available and self.users is not None:
            try:
                self.users.update_one(
                    {"user_id": user_id},
                    {"$set": {
                        "premium": False,
                        "premium_until": None,
                        "preferred_format": DEFAULT_SETTINGS.get("preferred_format", "mp3"),
                        "preferred_quality": DEFAULT_SETTINGS.get("preferred_quality", 64),
                    }},
                    upsert=True
                )
                return True
            except errors.PyMongoError as e:
                logger.warning(f"Mongo error in remove_premium: {e} — applying to fallback.")
                self.available = False
        # fallback
        user = _fallback_store["users"].get(user_id) or self._get_user_fallback(user_id)
        user["premium"] = False
        user["premium_until"] = None
        user["preferred_format"] = DEFAULT_SETTINGS.get("preferred_format", "mp3")
        user["preferred_quality"] = DEFAULT_SETTINGS.get("preferred_quality", 64)
        _fallback_store["users"][user_id] = user
        return True

    def get_user_stats(self):
        """Returns a dict with user statistics (total, premium, free, active_today, total_downloads)"""
        self._ensure()
        if self.available and self.users is not None and self.downloads is not None:
            try:
                total_users = self.users.count_documents({})
                premium_users = self.users.count_documents({"premium": True})
                active_today = self.users.count_documents({"downloads_today": {"$gt": 0}})
                total_downloads = self.downloads.count_documents({})
                free_users = max(0, total_users - premium_users)
                return {
                    "total_users": total_users,
                    "premium_users": premium_users,
                    "free_users": free_users,
                    "active_today": active_today,
                    "total_downloads": total_downloads
                }
            except errors.PyMongoError as e:
                logger.warning(f"Mongo error in get_user_stats: {e} — using fallback.")
                self.available = False

        # Fallback
        users = list(_fallback_store["users"].values())
        total_users = len(users)
        premium_users = sum(1 for u in users if u.get("premium"))
        active_today = sum(1 for u in users if u.get("downloads_today", 0) > 0)
        total_downloads = len(_fallback_store["downloads"])
        free_users = max(0, total_users - premium_users)
        return {
            "total_users": total_users,
            "premium_users": premium_users,
            "free_users": free_users,
            "active_today": active_today,
            "total_downloads": total_downloads
        }

    def get_recent_users(self, limit=10):
        """Return list of recently joined or updated users."""
        self._ensure()
        if self.available and self.users is not None:
            try:
                return list(self.users.find().sort("join_date", -1).limit(limit))
            except errors.PyMongoError as e:
                logger.warning(f"Mongo error in get_recent_users: {e}")
                self.available = False
        users = list(_fallback_store["users"].values())
        return sorted(users, key=lambda u: u.get("join_date") or datetime.min, reverse=True)[:limit]

    # --- Utility: expose fallback contents for debugging ---
    def debug_fallback(self):
        return {
            "users": dict(_fallback_store["users"]),
            "downloads": list(_fallback_store["downloads"])
        }

# Create global instance used by your code: from utils.db import db
db = Database()
import atexit
atexit.register(db.close)
