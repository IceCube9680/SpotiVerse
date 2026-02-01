
# utils/db.py
import os
import time
import logging
from datetime import datetime, timedelta
from pymongo import MongoClient, errors
from info import DEFAULT_SETTINGS

logger = logging.getLogger(__name__)

MONGO_URI = os.environ.get("MONGO_URI", "")  # ensure this is set in .env
DB_NAME = os.environ.get("MONGO_DBNAME", "spotiverse")

# Local in-memory fallback store (used only when MongoDB is unreachable)
_fallback_store = {
    "users": {},        # user_id -> user dict
    "downloads": []     # list of download records (dicts)
}

class Database:
    def __init__(self):
        self.client = None
        self.db = None
        self.available = False
        self.last_try = 0
        self.retry_interval = 10  # seconds between reconnect attempts
        # whether we've attempted to sync fallback after last successful connect
        self._synced_after_connect = False

        # Try initial connection (short attempt)
        self._try_connect(initial=True)

    def _try_connect(self, initial=False):
        now = time.time()
        # avoid hammering reconnection attempts
        if not initial and now - self.last_try < self.retry_interval:
            return

        self.last_try = now
        if not MONGO_URI:
            logger.warning("MONGO_URI not set — using in-memory fallback DB.")
            self.available = False
            return

        try:
            # small timeout so bot can start quickly if DB is unreachable
            self.client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000)
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
            # Clean up any partial client
            try:
                if self.client:
                    self.client.close()
            except Exception:
                pass
            self.client = None
            self.db = None

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
        if not self.available:
            logger.debug("Skipping sync: MongoDB not available.")
            return

        # Sync users: upsert all fallback users
        fallback_users = list(_fallback_store["users"].values())
        if fallback_users:
            logger.info(f"Syncing {len(fallback_users)} fallback users to MongoDB...")
            for user in fallback_users:
                try:
                    # convert any datetime fields to naive UTC (pymongo handles datetime)
                    self.users.update_one({"user_id": user["user_id"]}, {"$set": user}, upsert=True)
                except Exception as e:
                    logger.warning(f"Failed to upsert fallback user {user.get('user_id')}: {e}")

        # Sync downloads: insert entries and mark them as synced
        fallback_downloads = list(_fallback_store["downloads"])
        if fallback_downloads:
            logger.info(f"Syncing {len(fallback_downloads)} fallback downloads to MongoDB...")
            docs_to_insert = []
            for entry in fallback_downloads:
                # annotate with origin so we can identify these later if needed
                doc = dict(entry)
                doc["_synced_from_fallback"] = True
                # ensure timestamp exists and is datetime
                if "timestamp" not in doc or doc["timestamp"] is None:
                    doc["timestamp"] = datetime.utcnow()
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
    def get_user(self, user_id: int):
        """
        Return a user dict. If DB is down, use in-memory fallback.
        """
        self._ensure()
        if self.available:
            try:
                user = self.users.find_one({"user_id": user_id})
                if user:
                    return user
                # create default user
                new_user = {
                    "user_id": user_id,
                    "premium": False,
                    "premium_until": None,
                    "downloads_today": 0,
                    "total_downloads": 0,
                    "preferred_format": "mp3",
                    "preferred_quality": 64,
                    "join_date": datetime.utcnow()
                }
                self.users.insert_one(new_user)
                return new_user
            except errors.PyMongoError as e:
                logger.warning(f"Mongo error in get_user: {e} — using fallback store.")
                self.available = False
                return self._get_user_fallback(user_id)
        else:
            return self._get_user_fallback(user_id)

    def _get_user_fallback(self, user_id):
        user = _fallback_store["users"].get(user_id)
        if user:
            return user
        user = {
            "user_id": user_id,
            "premium": False,
            "premium_until": None,
            "downloads_today": 0,
            "total_downloads": 0,
            "preferred_format": "mp3",
            "preferred_quality": 64,
            "join_date": datetime.utcnow()
        }
        _fallback_store["users"][user_id] = user
        return user

    def update_user(self, user_id: int, data: dict):
        self._ensure()
        if self.available:
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
        """
        from config import Config  # imported here to avoid circular import at module load
        self._ensure()
        user = self.get_user(user_id)

        # premium check
        if user.get("premium"):
            until = user.get("premium_until")
            if until and isinstance(until, datetime) and until < datetime.utcnow():
                # premium expired — mark and continue as free
                self.update_user(user_id, {"premium": False, "premium_until": None})
            else:
                return True, None

        # free user: enforce daily quota
        daily_limit = getattr(Config, "FREE_USER_DAILY_LIMIT", 5)
        try:
            daily_limit = int(daily_limit)
        except (TypeError, ValueError):
            logger.warning(f"Invalid FREE_USER_DAILY_LIMIT ({daily_limit}), falling back to 5")
            daily_limit = 5
        downloads_today = user.get("downloads_today", 0)
        if downloads_today >= daily_limit:
            return False, "Daily download limit reached."
        return True, None

    def get_effective_settings(self, user_id: int):
        """
        Return the settings to use for this user (do not mutate DB).
        Preserves stored preferences but returns free defaults for non-premium users.
        """
        user = self.get_user(user_id) or {}
        # check premium expiry first (this will also update premium flag if expired)
        # calling can_download will trigger expiry check; we ignore its reason
        try:
            self.can_download(user_id)
        except Exception:
            pass

        is_premium = user.get("premium", False)
        # If premium and has premium settings, use them
        if is_premium:
            fmt = user.get("preferred_format", DEFAULT_SETTINGS.get("preferred_format"))
            q  = user.get("preferred_quality", DEFAULT_SETTINGS.get("preferred_quality"))
            return {"preferred_format": fmt, "preferred_quality": q}

        # Non-premium -> return free defaults (do not overwrite DB)
        return {
            "preferred_format": DEFAULT_SETTINGS.get("preferred_format"),
            "preferred_quality": DEFAULT_SETTINGS.get("preferred_quality")
        }

    def increment_download(self, user_id: int):
        """Increment counters after successful download."""
        self._ensure()
        if self.available:
            try:
                self.users.update_one({"user_id": user_id}, {"$inc": {"downloads_today": 1, "total_downloads": 1}})
                return True
            except errors.PyMongoError as e:
                logger.warning(f"Mongo error in increment_download: {e} — applying to fallback.")
                self.available = False
        # fallback
        user = _fallback_store["users"].get(user_id) or self._get_user_fallback(user_id)
        user["downloads_today"] = user.get("downloads_today", 0) + 1
        user["total_downloads"] = user.get("total_downloads", 0) + 1
        _fallback_store["users"][user_id] = user
        return True

    def record_download(self, user_id: int, track_info: dict):
        """Record a download (track_info should be serializable)"""
        self._ensure()
        entry = {"user_id": user_id, "track_info": track_info, "timestamp": datetime.utcnow()}
        if self.available:
            try:
                self.downloads.insert_one(entry)
                # increment counters
                self.increment_download(user_id)
                return True
            except errors.PyMongoError as e:
                logger.warning(f"Mongo error in record_download: {e} — saving to fallback.")
                self.available = False
        # fallback
        _fallback_store["downloads"].append(entry)
        self.increment_download(user_id)
        return True

    def add_premium(self, user_id: int, days: int):
        """Grant premium for days; return premium_until datetime"""
        self._ensure()
        until = datetime.utcnow() + timedelta(days=days)
        if self.available:
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
        if self.available:
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


    # --- Utility: expose fallback contents for debugging ---
    def debug_fallback(self):
        return {
            "users": dict(_fallback_store["users"]),
            "downloads": list(_fallback_store["downloads"])
        }

# Create global instance used by your code: from utils.db import db
db = Database()
