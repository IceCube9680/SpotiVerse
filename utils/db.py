# utils/db.py
import os
import time
import logging
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient, errors
from info import DEFAULT_SETTINGS

logger = logging.getLogger(__name__)

# Start timestamp for uptime calculation
BOT_START_TIME = time.time()

# Pull defaults from config.py if available
try:
    from config import Config
    _DEFAULT_MONGO_URI = getattr(Config, "MONGO_URI", "")
    _DEFAULT_DB_NAME = getattr(Config, "DB_NAME", "spotiverse_bot")
except Exception:
    _DEFAULT_MONGO_URI = ""
    _DEFAULT_DB_NAME = "spotiverse_bot"

MONGO_URI = os.environ.get("MONGO_URI", _DEFAULT_MONGO_URI)
DB_NAME = os.environ.get("MONGO_DBNAME", _DEFAULT_DB_NAME)

# Default Bot Feature Gates
DEFAULT_BOT_SETTINGS = {
    "premium_system": True,
    "free_download": True,
    "premium_download": True,
    "premium_flac": True,
    "premium_batch": True,
    "premium_priority": True,
    "maintenance_mode": False,
    "maintenance_allow_premium": False,
    "maintenance_allow_admin": True,
}

# Default Provider Statuses
DEFAULT_PROVIDER_SETTINGS = {
    "spotify": True,
    "youtube": True,
    "jiosaavn": True,
    "soundcloud": True,
    "deezer": True
}

# Local in-memory fallback store (used when MongoDB is unreachable)
_fallback_store = {
    "users": {},              # user_id -> user dict
    "bot_settings": dict(DEFAULT_BOT_SETTINGS),
    "provider_settings": dict(DEFAULT_PROVIDER_SETTINGS),
    "downloads": [],          # list of download record dicts
    "admin_audit": []         # list of admin audit dicts
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
        try:
            dt = datetime.fromisoformat(val_clean.replace("Z", "+00:00"))
            if dt.tzinfo is not None:
                return dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        except Exception:
            pass
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
    now_dt = _get_utc_now()
    defaults = {
        "premium": False,
        "premium_plan": None,
        "premium_started_at": None,
        "premium_until": None,
        "lifetime_premium": False,
        "banned": False,
        "download_count": user.get("total_downloads", 0),
        "successful_downloads": user.get("total_downloads", 0),
        "failed_downloads": 0,
        "downloads_today": 0,
        "total_downloads": 0,
        "last_download_date": today_str,
        "preferred_format": DEFAULT_SETTINGS.get("preferred_format", "mp3"),
        "preferred_quality": DEFAULT_SETTINGS.get("preferred_quality", 64),
        "join_date": now_dt,
        "created_at": now_dt,
        "updated_at": now_dt,
        "last_seen": now_dt
    }
    for k, v in defaults.items():
        if k not in user or (user[k] is None and k not in ("premium_until", "premium_plan", "premium_started_at")):
            user[k] = v
    return user

class Database:
    def __init__(self, connect=True):
        self.client = None
        self.db = None
        self.users = None
        self.bot_settings = None
        self.provider_settings = None
        self.downloads = None
        self.admin_audit = None
        self.available = False
        self.last_try = 0
        self.retry_interval = 10  # seconds between reconnect attempts
        self._synced_after_connect = False

        if connect:
            self._try_connect(initial=True)

    def _try_connect(self, initial=False):
        now = time.time()
        if not initial and now - self.last_try < self.retry_interval:
            return

        self.last_try = now

        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
            self.client = None

        if not MONGO_URI:
            logger.info("MONGO_URI not configured — operating in-memory fallback mode.")
            self.available = False
            return

        try:
            self.client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000, connectTimeoutMS=2000)
            self.client.admin.command('ping')
            self.db = self.client[DB_NAME]
            self.users = self.db.get_collection("users")
            self.bot_settings = self.db.get_collection("bot_settings")
            self.provider_settings = self.db.get_collection("provider_settings")
            self.downloads = self.db.get_collection("downloads")
            self.admin_audit = self.db.get_collection("admin_audit")
            self.available = True
            logger.info("Connected to MongoDB successfully.")

            # Create performance indexes
            self._create_indexes()

            # Sync fallback if needed
            if not self._synced_after_connect:
                try:
                    self._sync_fallback_to_mongo()
                    self._synced_after_connect = True
                except Exception as e:
                    logger.warning(f"Failed to sync fallback after connect: {e}")

        except Exception as e:
            logger.warning(f"MongoDB connection failed: {e}. Operating in-memory DB fallback.")
            self.available = False
            try:
                if self.client:
                    self.client.close()
            except Exception:
                pass
            self.client = None
            self.db = None
            self.users = None
            self.bot_settings = None
            self.provider_settings = None
            self.downloads = None
            self.admin_audit = None

    def _create_indexes(self):
        """Create indexes for high performance querying"""
        if not self.available or self.db is None:
            return
        try:
            # Users indexes
            self.users.create_index("user_id", unique=True)
            self.users.create_index("premium")
            self.users.create_index("premium_until")
            self.users.create_index("banned")
            self.users.create_index("created_at")

            # Downloads indexes
            self.downloads.create_index("user_id")
            self.downloads.create_index("timestamp")
            self.downloads.create_index("provider")
            self.downloads.create_index("status")
            self.downloads.create_index([("provider", 1), ("status", 1)])

            # Settings indexes
            self.bot_settings.create_index("key", unique=True)
            self.provider_settings.create_index("provider", unique=True)
            self.admin_audit.create_index("timestamp")
        except Exception as e:
            logger.warning(f"Could not create Mongo indexes: {e}")

    def close(self):
        """Safely close MongoClient connection."""
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
            self.client = None
        self.db = None
        self.users = None
        self.bot_settings = None
        self.provider_settings = None
        self.downloads = None
        self.admin_audit = None
        self.available = False

    def _ensure(self):
        if not self.available:
            self._try_connect()

    # === Sync fallback store to MongoDB ===
    def _sync_fallback_to_mongo(self):
        if not self.available or self.users is None or self.downloads is None:
            return

        fallback_users = list(_fallback_store["users"].values())
        if fallback_users:
            logger.info(f"Syncing {len(fallback_users)} fallback users to MongoDB...")
            for user in fallback_users:
                try:
                    self.users.update_one({"user_id": user["user_id"]}, {"$set": user}, upsert=True)
                except Exception as e:
                    logger.warning(f"Failed to upsert fallback user {user.get('user_id')}: {e}")

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

        _fallback_store["users"].clear()
        _fallback_store["downloads"].clear()
        logger.info("Fallback store synced to MongoDB.")

    # === User Management ===
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
        """Return a user dict with defaults. Fallback if DB unreachable."""
        self._ensure()
        today_str = _get_utc_now().strftime("%Y-%m-%d")
        now_dt = _get_utc_now()
        if self.available and self.users is not None:
            try:
                user = self.users.find_one({"user_id": user_id})
                if user:
                    return _populate_user_defaults(self._check_and_reset_daily(user))
                new_user = {
                    "user_id": user_id,
                    "premium": False,
                    "premium_plan": None,
                    "premium_started_at": None,
                    "premium_until": None,
                    "lifetime_premium": False,
                    "banned": False,
                    "download_count": 0,
                    "successful_downloads": 0,
                    "failed_downloads": 0,
                    "downloads_today": 0,
                    "total_downloads": 0,
                    "last_download_date": today_str,
                    "preferred_format": DEFAULT_SETTINGS.get("preferred_format", "mp3"),
                    "preferred_quality": DEFAULT_SETTINGS.get("preferred_quality", 64),
                    "join_date": now_dt,
                    "created_at": now_dt,
                    "updated_at": now_dt,
                    "last_seen": now_dt
                }
                self.users.insert_one(new_user)
                return new_user
            except errors.PyMongoError as e:
                logger.warning(f"Mongo error in get_user: {e} — using fallback.")
                self.available = False
                return _populate_user_defaults(self._check_and_reset_daily(self._get_user_fallback(user_id)))
        else:
            return _populate_user_defaults(self._check_and_reset_daily(self._get_user_fallback(user_id)))

    def _get_user_fallback(self, user_id: int):
        user = _fallback_store["users"].get(user_id)
        if user:
            return user
        today_str = _get_utc_now().strftime("%Y-%m-%d")
        now_dt = _get_utc_now()
        user = {
            "user_id": user_id,
            "premium": False,
            "premium_plan": None,
            "premium_started_at": None,
            "premium_until": None,
            "lifetime_premium": False,
            "banned": False,
            "download_count": 0,
            "successful_downloads": 0,
            "failed_downloads": 0,
            "downloads_today": 0,
            "total_downloads": 0,
            "last_download_date": today_str,
            "preferred_format": DEFAULT_SETTINGS.get("preferred_format", "mp3"),
            "preferred_quality": DEFAULT_SETTINGS.get("preferred_quality", 64),
            "join_date": now_dt,
            "created_at": now_dt,
            "updated_at": now_dt,
            "last_seen": now_dt
        }
        _fallback_store["users"][user_id] = user
        return user

    def update_user(self, user_id: int, data: dict):
        self._ensure()
        data["updated_at"] = _get_utc_now()
        data["last_seen"] = _get_utc_now()
        if self.available and self.users is not None:
            try:
                self.users.update_one({"user_id": user_id}, {"$set": data}, upsert=True)
                return True
            except errors.PyMongoError as e:
                logger.warning(f"Mongo error in update_user: {e} — applying to fallback.")
                self.available = False
        user = _fallback_store["users"].get(user_id) or self._get_user_fallback(user_id)
        user.update(data)
        _fallback_store["users"][user_id] = user
        return True

    def ban_user(self, user_id: int, admin_id: int = None) -> bool:
        """Ban user from bot usage."""
        self.update_user(user_id, {"banned": True})
        if admin_id:
            self.log_admin_action(admin_id, "ban_user", target=user_id, details="User banned")
        return True

    def unban_user(self, user_id: int, admin_id: int = None) -> bool:
        """Unban user from bot usage."""
        self.update_user(user_id, {"banned": False})
        if admin_id:
            self.log_admin_action(admin_id, "unban_user", target=user_id, details="User unbanned")
        return True

    def is_banned(self, user_id: int) -> bool:
        user = self.get_user(user_id)
        return bool(user.get("banned", False))

    # === Bot Settings Management ===
    def get_bot_setting(self, key: str, default=None):
        """Retrieve a bot setting with DB persistence and fallback"""
        self._ensure()
        if self.available and self.bot_settings is not None:
            try:
                doc = self.bot_settings.find_one({"key": key})
                if doc and "value" in doc:
                    return doc["value"]
            except Exception as e:
                logger.debug(f"Error reading bot_setting {key}: {e}")

        if key in _fallback_store["bot_settings"]:
            return _fallback_store["bot_settings"][key]
        return DEFAULT_BOT_SETTINGS.get(key, default)

    def set_bot_setting(self, key: str, value, admin_id: int = None) -> bool:
        """Set a bot setting persistently in DB and fallback store"""
        old_val = self.get_bot_setting(key)
        _fallback_store["bot_settings"][key] = value

        # Sync with Config if applicable
        from config import Config
        if key == "premium_system":
            Config.PREMIUM = bool(value)
            Config.PREMIUM_MODE = bool(value)

        self._ensure()
        if self.available and self.bot_settings is not None:
            try:
                self.bot_settings.update_one(
                    {"key": key},
                    {"$set": {"key": key, "value": value, "updated_at": _get_utc_now(), "updated_by": admin_id}},
                    upsert=True
                )
            except Exception as e:
                logger.warning(f"Error persisting bot_setting {key}: {e}")

        if admin_id and old_val != value:
            self.log_admin_action(admin_id, "set_bot_setting", target=key, old_val=str(old_val), new_val=str(value))
        return True

    def get_all_bot_settings(self) -> dict:
        """Return dict of all current bot settings"""
        settings = dict(DEFAULT_BOT_SETTINGS)
        self._ensure()
        if self.available and self.bot_settings is not None:
            try:
                for doc in self.bot_settings.find():
                    if "key" in doc and "value" in doc:
                        settings[doc["key"]] = doc["value"]
                return settings
            except Exception as e:
                logger.debug(f"Error getting all bot settings: {e}")
        settings.update(_fallback_store["bot_settings"])
        return settings

    # Backward compatibility for get_premium_mode / set_premium_mode
    def get_premium_mode(self) -> bool:
        return bool(self.get_bot_setting("premium_system", True))

    def set_premium_mode(self, mode: bool) -> bool:
        return self.set_bot_setting("premium_system", bool(mode))

    # === Provider Settings Management ===
    def get_provider_setting(self, provider: str, default: bool = True) -> bool:
        """Get enabled state of provider"""
        self._ensure()
        prov_key = provider.lower()
        if self.available and self.provider_settings is not None:
            try:
                doc = self.provider_settings.find_one({"provider": prov_key})
                if doc and "enabled" in doc:
                    return bool(doc["enabled"])
            except Exception as e:
                logger.debug(f"Error reading provider setting {prov_key}: {e}")

        if prov_key in _fallback_store["provider_settings"]:
            return bool(_fallback_store["provider_settings"][prov_key])
        return DEFAULT_PROVIDER_SETTINGS.get(prov_key, default)

    def set_provider_setting(self, provider: str, enabled: bool, admin_id: int = None) -> bool:
        """Set enabled state of provider persistently"""
        prov_key = provider.lower()
        old_val = self.get_provider_setting(prov_key)
        _fallback_store["provider_settings"][prov_key] = bool(enabled)

        self._ensure()
        if self.available and self.provider_settings is not None:
            try:
                self.provider_settings.update_one(
                    {"provider": prov_key},
                    {"$set": {"provider": prov_key, "enabled": bool(enabled), "updated_at": _get_utc_now(), "updated_by": admin_id}},
                    upsert=True
                )
            except Exception as e:
                logger.warning(f"Error persisting provider setting {prov_key}: {e}")

        if admin_id and old_val != enabled:
            self.log_admin_action(admin_id, f"provider_{'enable' if enabled else 'disable'}", target=prov_key, old_val=str(old_val), new_val=str(enabled))
        return True

    def get_all_provider_settings(self) -> dict:
        """Return dict of all provider enabled states"""
        settings = dict(DEFAULT_PROVIDER_SETTINGS)
        self._ensure()
        if self.available and self.provider_settings is not None:
            try:
                for doc in self.provider_settings.find():
                    if "provider" in doc and "enabled" in doc:
                        settings[doc["provider"]] = bool(doc["enabled"])
                return settings
            except Exception as e:
                logger.debug(f"Error getting all provider settings: {e}")
        settings.update(_fallback_store["provider_settings"])
        return settings

    # === Admin Audit Logging ===
    def log_admin_action(self, admin_id: int, action: str, target=None, old_val=None, new_val=None,
                         details: str = None, target_user=None, old_value=None, new_value=None):
        """Record an admin action in the audit log"""
        if target_user is not None and target is None:
            target = target_user
        if old_value is not None and old_val is None:
            old_val = old_value
        if new_value is not None and new_val is None:
            new_val = new_value

        entry = {
            "admin_id": admin_id,
            "action": action,
            "target": str(target) if target is not None else None,
            "target_user": target,
            "old_value": str(old_val) if old_val is not None else None,
            "new_value": str(new_val) if new_val is not None else None,
            "details": details,
            "timestamp": _get_utc_now()
        }
        self._ensure()
        if self.available and self.admin_audit is not None:
            try:
                self.admin_audit.insert_one(entry)
                return True
            except Exception as e:
                logger.warning(f"Error inserting audit log: {e}")
        _fallback_store["admin_audit"].append(entry)
        return True

    def get_audit_logs(self, limit=20):
        """Retrieve latest admin audit log entries"""
        self._ensure()
        if self.available and self.admin_audit is not None:
            try:
                return list(self.admin_audit.find().sort("timestamp", -1).limit(limit))
            except Exception as e:
                logger.warning(f"Error getting audit logs: {e}")
        logs = list(_fallback_store["admin_audit"])
        return sorted(logs, key=lambda l: l.get("timestamp") or datetime.min, reverse=True)[:limit]

    def get_admin_audit_logs(self, limit=20):
        return self.get_audit_logs(limit=limit)

    # === Premium Authorization & Management ===
    def is_premium(self, user_id: int) -> bool:
        """
        Check if user has active premium status.
        1. If global premium_system is False (Public Mode), all users get premium privileges.
        2. Bot owners / Config.PREMIUM_USERS always True.
        3. Database active premium records (auto-expires if past premium_until).
        """
        if not user_id:
            return False

        if not self.get_premium_mode():
            return True

        from config import Config
        if Config.is_owner(user_id) or user_id in getattr(Config, "PREMIUM_USERS", []):
            return True

        user = self.get_user(user_id)
        if not user or not user.get("premium"):
            return False

        if user.get("lifetime_premium"):
            return True

        until_dt = _parse_datetime(user.get("premium_until"))
        if until_dt and until_dt < _get_utc_now():
            self.update_user(user_id, {
                "premium": False,
                "premium_until": None,
                "premium_plan": None
            })
            return False
        return True

    def add_premium(self, user_id: int, days: float, plan_name: str = None, admin_id: int = None):
        """Grant premium for days; return premium_until datetime"""
        self._ensure()
        now = _get_utc_now()
        current_user = self.get_user(user_id)
        
        existing_until = _parse_datetime(current_user.get("premium_until")) if current_user else None
        if existing_until and existing_until > now and not current_user.get("lifetime_premium"):
            base_time = existing_until
        else:
            base_time = now

        num_days = 30.0
        is_lifetime = False
        if isinstance(days, str):
            if days.lower() in ("lifetime", "perm", "forever", "infinity"):
                is_lifetime = True
                num_days = 36500.0
            elif days.lower().endswith("d"):
                try:
                    num_days = float(days[:-1])
                except ValueError:
                    num_days = 30.0
            elif days.lower().endswith("m"):
                try:
                    num_days = float(days[:-1]) * 30
                except ValueError:
                    num_days = 30.0
            elif days.lower().endswith("y"):
                try:
                    num_days = float(days[:-1]) * 365
                except ValueError:
                    num_days = 365.0
            else:
                try:
                    num_days = float(days)
                except ValueError:
                    num_days = 30.0
        elif isinstance(days, (int, float)):
            num_days = float(days)
            is_lifetime = num_days >= 36500

        if is_lifetime or num_days >= 36500:
            is_lifetime = True
            until = base_time + timedelta(days=36500)
            plan = plan_name or "Lifetime"
        else:
            until = base_time + timedelta(days=num_days)
            plan = plan_name or f"{int(num_days) if num_days.is_integer() else num_days}d"

        update_payload = {
            "premium": True,
            "premium_plan": plan,
            "premium_started_at": now,
            "premium_until": until,
            "lifetime_premium": is_lifetime
        }
        self.update_user(user_id, update_payload)

        if admin_id:
            self.log_admin_action(admin_id, "add_premium", target=user_id, new_val=plan, details=f"Duration: {days} days")
        return until

    def remove_premium(self, user_id: int, admin_id: int = None):
        """Revoke premium access from user."""
        self._ensure()
        update_payload = {
            "premium": False,
            "premium_plan": None,
            "premium_until": None,
            "lifetime_premium": False,
            "preferred_format": DEFAULT_SETTINGS.get("preferred_format", "mp3"),
            "preferred_quality": DEFAULT_SETTINGS.get("preferred_quality", 64),
        }
        self.update_user(user_id, update_payload)
        if admin_id:
            self.log_admin_action(admin_id, "remove_premium", target=user_id, details="Premium removed")
        return True

    def can_download(self, user_id: int):
        """
        Quota checker for downloads.
        Returns (True, None) if allowed, (False, reason) if quota reached.
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

    def get_effective_settings(self, user_id: int):
        """Return download preferences (preserves custom format if premium)."""
        user = self.get_user(user_id) or {}
        if self.is_premium(user_id):
            fmt = user.get("preferred_format", DEFAULT_SETTINGS.get("preferred_format", "mp3"))
            q  = user.get("preferred_quality", DEFAULT_SETTINGS.get("preferred_quality", 320))
            return {"preferred_format": fmt, "preferred_quality": q}

        return {
            "preferred_format": DEFAULT_SETTINGS.get("preferred_format", "mp3"),
            "preferred_quality": DEFAULT_SETTINGS.get("preferred_quality", 64)
        }

    # === User Queries for Admin Panel ===
    def get_premium_users(self, page: int = 0, per_page: int = 10):
        """Return paginated list of active premium users and total count"""
        self._ensure()
        now = _get_utc_now()
        query = {
            "$or": [
                {"lifetime_premium": True},
                {"premium": True, "premium_until": {"$gt": now}}
            ]
        }
        if self.available and self.users is not None:
            try:
                total = self.users.count_documents(query)
                cursor = self.users.find(query).sort("premium_until", -1).skip(page * per_page).limit(per_page)
                return list(cursor), total
            except Exception as e:
                logger.warning(f"Error in get_premium_users: {e}")

        # Fallback
        all_users = list(_fallback_store["users"].values())
        prem_users = []
        for u in all_users:
            if u.get("lifetime_premium"):
                prem_users.append(u)
            elif u.get("premium"):
                pu = _parse_datetime(u.get("premium_until"))
                if pu and pu > now:
                    prem_users.append(u)
        total = len(prem_users)
        start = page * per_page
        return prem_users[start:start + per_page], total

    def get_expiring_soon_users(self, days: int = 7, warning_days: int = None, page: int = 0, per_page: int = 10):
        """Return paginated list of users whose premium expires within warning days"""
        if warning_days is not None:
            days = warning_days
        self._ensure()
        now = _get_utc_now()
        target_date = now + timedelta(days=days)
        query = {
            "premium": True,
            "lifetime_premium": {"$ne": True},
            "premium_until": {"$gt": now, "$lte": target_date}
        }
        if self.available and self.users is not None:
            try:
                total = self.users.count_documents(query)
                cursor = self.users.find(query).sort("premium_until", 1).skip(page * per_page).limit(per_page)
                return list(cursor), total
            except Exception as e:
                logger.warning(f"Error in get_expiring_soon_users: {e}")

        # Fallback
        all_users = list(_fallback_store["users"].values())
        exp_users = []
        for u in all_users:
            if u.get("premium") and not u.get("lifetime_premium"):
                pu = _parse_datetime(u.get("premium_until"))
                if pu and now < pu <= target_date:
                    exp_users.append(u)
        exp_users.sort(key=lambda u: _parse_datetime(u.get("premium_until")) or datetime.max)
        total = len(exp_users)
        start = page * per_page
        return exp_users[start:start + per_page], total

    def get_users_paginated(self, page: int = 0, per_page: int = 10):
        """Return paginated list of all users and total count"""
        self._ensure()
        if self.available and self.users is not None:
            try:
                total = self.users.count_documents({})
                cursor = self.users.find().sort("join_date", -1).skip(page * per_page).limit(per_page)
                return list(cursor), total
            except Exception as e:
                logger.warning(f"Error in get_users_paginated: {e}")

        all_users = list(_fallback_store["users"].values())
        all_users.sort(key=lambda u: _parse_datetime(u.get("join_date")) or datetime.min, reverse=True)
        total = len(all_users)
        start = page * per_page
        return all_users[start:start + per_page], total

    # === Download Auditing & Recording ===
    def increment_download(self, user_id: int, successful: bool = True):
        """Increment counters after download attempt."""
        self._ensure()
        today_str = _get_utc_now().strftime("%Y-%m-%d")
        user = self.get_user(user_id)
        if user.get("last_download_date") != today_str:
            new_today = 1 if successful else 0
        else:
            new_today = user.get("downloads_today", 0) + (1 if successful else 0)

        new_total = user.get("total_downloads", 0) + (1 if successful else 0)
        new_dl_count = user.get("download_count", 0) + 1
        new_succ = user.get("successful_downloads", 0) + (1 if successful else 0)
        new_fail = user.get("failed_downloads", 0) + (0 if successful else 1)

        updates = {
            "downloads_today": new_today,
            "total_downloads": new_total,
            "download_count": new_dl_count,
            "successful_downloads": new_succ,
            "failed_downloads": new_fail,
            "last_download_date": today_str
        }
        self.update_user(user_id, updates)

    def record_download_attempt(self, user_id: int, provider: str, track_info: dict = None,
                                status: str = "queued", format_used: str = "mp3", quality=320,
                                is_premium: bool = False, priority: bool = False,
                                file_size: int = 0, duration: int = 0, error: str = None,
                                track: str = None, format: str = None, bitrate=None, premium: bool = None,
                                source_quality: dict = None, conversion_duration: float = 0.0) -> dict:
        """
        Record a comprehensive download lifecycle entry.
        Status states: queued, processing, success, failed, cancelled.
        """
        self._ensure()
        if track is not None and track_info is None:
            track_info = track
        if format is not None:
            format_used = format
        if bitrate is not None:
            quality = bitrate
        if premium is not None:
            is_premium = premium

        user_doc = self.get_user(user_id) or {}
        if isinstance(track_info, str):
            tid = track_info
            title = track_info
            t_obj = {"id": tid, "title": title}
            uname = user_doc.get("username")
        elif isinstance(track_info, dict):
            tid = str(track_info.get("id", ""))
            title = track_info.get("title", "Unknown Track")
            t_obj = track_info
            uname = track_info.get("username") or user_doc.get("username")
        else:
            tid = ""
            title = "Unknown Track"
            t_obj = {}
            uname = user_doc.get("username")

        now = _get_utc_now()

        entry = {
            "user_id": user_id,
            "username": uname,
            "provider": (provider or "unknown").lower(),
            "track_id": tid,
            "track_title": title,
            "artist": t_obj.get("artist", "Unknown Artist"),
            "status": status,  # queued, processing, success, failed, cancelled
            "format": str(format_used).lower(),
            "quality": quality,
            "source_quality": source_quality or {},
            "conversion_duration": float(conversion_duration or 0.0),
            "is_premium": is_premium,
            "priority": priority,
            "file_size": file_size or 0,
            "duration": duration or 0,
            "error": error,
            "started_at": now,
            "completed_at": now if status in ("success", "failed", "cancelled") else None,
            "timestamp": now,
            "track_info": t_obj
        }

        if self.available and self.downloads is not None:
            try:
                res = self.downloads.insert_one(entry)
                entry["_id"] = res.inserted_id
            except Exception as e:
                logger.warning(f"Error inserting download record: {e}")
                _fallback_store["downloads"].append(entry)
        else:
            _fallback_store["downloads"].append(entry)

        if status == "success":
            self.increment_download(user_id, successful=True)
        elif status == "failed":
            self.increment_download(user_id, successful=False)

        return entry

    def update_download_record(self, entry: dict, status: str, duration: int = None,
                               file_size: int = None, error: str = None,
                               source_quality: dict = None, conversion_duration: float = None,
                               format_used: str = None, quality = None):
        """Update existing download record status (processing -> success/failed)"""
        now = _get_utc_now()
        updates = {"status": status, "completed_at": now}
        if duration is not None:
            updates["duration"] = duration
        if file_size is not None:
            updates["file_size"] = file_size
        if error is not None:
            updates["error"] = error
        if source_quality is not None:
            updates["source_quality"] = source_quality
        if conversion_duration is not None:
            updates["conversion_duration"] = float(conversion_duration)
        if format_used is not None:
            updates["format"] = str(format_used).lower()
        if quality is not None:
            updates["quality"] = quality

        if isinstance(entry, dict):
            entry.update(updates)
            if "_id" in entry and self.available and self.downloads is not None:
                try:
                    self.downloads.update_one({"_id": entry["_id"]}, {"$set": updates})
                except Exception as e:
                    logger.debug(f"Error updating download record: {e}")

        user_id = entry.get("user_id") if isinstance(entry, dict) else None
        if user_id:
            if status == "success":
                self.increment_download(user_id, successful=True)
            elif status in ("failed", "cancelled"):
                self.increment_download(user_id, successful=False)

    def record_download(self, user_id: int, track_info: dict, username: str = None):
        """Legacy compatibility wrapper for record_download"""
        prov = (track_info or {}).get("provider", "spotify")
        fmt = (track_info or {}).get("format", "mp3")
        q = (track_info or {}).get("quality", 320)
        is_prem = self.is_premium(user_id)
        return self.record_download_attempt(
            user_id=user_id,
            provider=prov,
            track_info=track_info,
            status="success",
            format_used=fmt,
            quality=q,
            is_premium=is_prem
        )

    # === Advanced Database Statistics Dashboard ===
    def get_statistics(self, timeframe: str = "30d", period: str = None) -> dict:
        """
        Calculate mathematically accurate bot statistics from actual database records.
        Supports timeframes: '24h', '7d', '30d', 'all'.
        Uses efficient MongoDB aggregation pipelines or in-memory fallback aggregation.
        """
        if period is not None:
            timeframe = period
        self._ensure()
        now = _get_utc_now()

        # Determine cutoff datetime
        if timeframe == "24h":
            cutoff = now - timedelta(hours=24)
            label = "Last 24 Hours"
        elif timeframe == "7d":
            cutoff = now - timedelta(days=7)
            label = "Last 7 Days"
        elif timeframe == "30d":
            cutoff = now - timedelta(days=30)
            label = "Last 30 Days"
        else:
            cutoff = datetime.min
            label = "All Time"

        # Initialize default metrics
        stats = {
            "timeframe": timeframe,
            "label": label,
            "total_users": 0,
            "premium_users": 0,
            "free_users": 0,
            "active_users": 0,
            "new_users": 0,
            "total_downloads": 0,
            "successful_downloads": 0,
            "failed_downloads": 0,
            "cancelled_downloads": 0,
            "success_rate": 0.0,
            "total_audio_bytes": 0,
            "total_audio_mb": 0.0,
            "avg_duration_sec": 0.0,
            "avg_conversion_duration_sec": 0.0,
            "avg_output_size_mb": 0.0,
            "platform_usage": {
                "youtube": 0,
                "spotify": 0,
                "jiosaavn": 0,
                "soundcloud": 0,
                "deezer": 0
            },
            "platform_percentages": {
                "youtube": 0.0,
                "spotify": 0.0,
                "jiosaavn": 0.0,
                "soundcloud": 0.0,
                "deezer": 0.0
            },
            "top_platforms": {},
            "format_usage": {"mp3": 0, "flac": 0, "m4a": 0, "ogg": 0, "wav": 0},
            "quality_usage": {},
            "failed_conversions_by_format": {"mp3": 0, "flac": 0, "m4a": 0, "ogg": 0, "wav": 0},
            "provider_format_usage": {
                "youtube": {"mp3": 0, "flac": 0, "m4a": 0, "ogg": 0, "wav": 0},
                "spotify": {"mp3": 0, "flac": 0, "m4a": 0, "ogg": 0, "wav": 0},
                "jiosaavn": {"mp3": 0, "flac": 0, "m4a": 0, "ogg": 0, "wav": 0},
                "soundcloud": {"mp3": 0, "flac": 0, "m4a": 0, "ogg": 0, "wav": 0},
                "deezer": {"mp3": 0, "flac": 0, "m4a": 0, "ogg": 0, "wav": 0}
            },
            "source_quality_stats": {"lower_than_requested": 0, "equal_or_higher": 0},
            "user_tier_downloads": {"free": 0, "premium": 0},
            "provider_failures": {"youtube": 0, "spotify": 0, "jiosaavn": 0, "soundcloud": 0, "deezer": 0},
            "db_status": "MongoDB (Connected)" if self.available else "In-Memory Fallback",
            "bot_uptime_seconds": int(time.time() - BOT_START_TIME)
        }

        total_conv_time = 0.0
        conv_time_count = 0

        # --- MongoDB Aggregation Path ---
        if self.available and self.users is not None and self.downloads is not None:
            try:
                # User counts
                stats["total_users"] = self.users.count_documents({})
                prem_query = {"$or": [{"lifetime_premium": True}, {"premium": True, "premium_until": {"$gt": now}}]}
                stats["premium_users"] = self.users.count_documents(prem_query)
                stats["free_users"] = max(0, stats["total_users"] - stats["premium_users"])

                if cutoff != datetime.min:
                    stats["new_users"] = self.users.count_documents({"join_date": {"$gte": cutoff}})
                else:
                    stats["new_users"] = stats["total_users"]

                # Downloads query
                match_filter = {}
                if cutoff != datetime.min:
                    match_filter["timestamp"] = {"$gte": cutoff}

                # Status aggregation
                status_pipeline = [
                    {"$match": match_filter},
                    {"$group": {
                        "_id": "$status",
                        "count": {"$sum": 1},
                        "total_size": {"$sum": "$file_size"},
                        "total_duration": {"$sum": "$duration"},
                        "total_conv_duration": {"$sum": "$conversion_duration"}
                    }}
                ]
                for doc in self.downloads.aggregate(status_pipeline):
                    st = (doc["_id"] or "success").lower()
                    cnt = doc["count"]
                    if st == "success":
                        stats["successful_downloads"] += cnt
                        stats["total_audio_bytes"] += doc.get("total_size", 0)
                        total_conv_time += doc.get("total_conv_duration", 0.0)
                        conv_time_count += cnt
                    elif st in ("failed", "fail", "error"):
                        stats["failed_downloads"] += cnt
                    elif st in ("cancelled", "canceled"):
                        stats["cancelled_downloads"] += cnt
                    stats["total_downloads"] += cnt

                # Active users in timeframe (distinct user_ids)
                active_uids = self.downloads.distinct("user_id", match_filter)
                stats["active_users"] = len(active_uids)

                # Platform breakdown for successful downloads
                succ_match = dict(match_filter)
                succ_match["status"] = {"$in": ["success", None]}
                platform_pipeline = [
                    {"$match": succ_match},
                    {"$group": {"_id": "$provider", "count": {"$sum": 1}}}
                ]
                total_succ_platform = 0
                for doc in self.downloads.aggregate(platform_pipeline):
                    prov = (doc["_id"] or "youtube").lower()
                    if prov in ("saavn", "jio_saavn"):
                        prov = "jiosaavn"
                    elif prov == "sp":
                        prov = "spotify"
                    elif prov == "yt":
                        prov = "youtube"
                    if prov in stats["platform_usage"]:
                        stats["platform_usage"][prov] += doc["count"]
                        total_succ_platform += doc["count"]

                # Provider failures
                fail_match = dict(match_filter)
                fail_match["status"] = {"$in": ["failed", "fail", "error"]}
                fail_pipeline = [
                    {"$match": fail_match},
                    {"$group": {"_id": "$provider", "count": {"$sum": 1}}}
                ]
                for doc in self.downloads.aggregate(fail_pipeline):
                    prov = (doc["_id"] or "youtube").lower()
                    if prov in ("saavn", "jio_saavn"):
                        prov = "jiosaavn"
                    elif prov == "sp":
                        prov = "spotify"
                    elif prov == "yt":
                        prov = "youtube"
                    if prov in stats["provider_failures"]:
                        stats["provider_failures"][prov] += doc["count"]

                # Format breakdown
                format_pipeline = [
                    {"$match": succ_match},
                    {"$group": {"_id": "$format", "count": {"$sum": 1}}}
                ]
                for doc in self.downloads.aggregate(format_pipeline):
                    fmt = (doc["_id"] or "mp3").lower()
                    if fmt in stats["format_usage"]:
                        stats["format_usage"][fmt] += doc["count"]
                    elif "flac" in fmt:
                        stats["format_usage"]["flac"] += doc["count"]
                    else:
                        stats["format_usage"]["mp3"] += doc["count"]

                # Quality breakdown
                quality_pipeline = [
                    {"$match": succ_match},
                    {"$group": {"_id": "$quality", "count": {"$sum": 1}}}
                ]
                for doc in self.downloads.aggregate(quality_pipeline):
                    q_val = str(doc["_id"] or "320")
                    stats["quality_usage"][q_val] = doc["count"]

                # Failed conversions by format
                fail_fmt_pipeline = [
                    {"$match": fail_match},
                    {"$group": {"_id": "$format", "count": {"$sum": 1}}}
                ]
                for doc in self.downloads.aggregate(fail_fmt_pipeline):
                    fmt = (doc["_id"] or "mp3").lower()
                    if fmt in stats["failed_conversions_by_format"]:
                        stats["failed_conversions_by_format"][fmt] += doc["count"]
                    else:
                        stats["failed_conversions_by_format"]["mp3"] += doc["count"]

                # Provider -> Format breakdown
                prov_fmt_pipeline = [
                    {"$match": succ_match},
                    {"$group": {
                        "_id": {"provider": "$provider", "format": "$format"},
                        "count": {"$sum": 1}
                    }}
                ]
                for doc in self.downloads.aggregate(prov_fmt_pipeline):
                    p_id = (doc["_id"].get("provider") or "youtube").lower()
                    if p_id in ("saavn", "jio_saavn"):
                        p_id = "jiosaavn"
                    elif p_id == "sp":
                        p_id = "spotify"
                    elif p_id == "yt":
                        p_id = "youtube"
                    f_id = (doc["_id"].get("format") or "mp3").lower()
                    if p_id in stats["provider_format_usage"]:
                        if f_id in stats["provider_format_usage"][p_id]:
                            stats["provider_format_usage"][p_id][f_id] += doc["count"]

                # Tier breakdown
                tier_pipeline = [
                    {"$match": match_filter},
                    {"$group": {"_id": "$is_premium", "count": {"$sum": 1}}}
                ]
                for doc in self.downloads.aggregate(tier_pipeline):
                    is_prem = bool(doc["_id"])
                    if is_prem:
                        stats["user_tier_downloads"]["premium"] += doc["count"]
                    else:
                        stats["user_tier_downloads"]["free"] += doc["count"]

            except Exception as e:
                logger.warning(f"Mongo aggregation error in get_statistics: {e} — falling back.")
                self.available = False

        # --- Fallback Store In-Memory Aggregation ---
        if not self.available or stats["total_users"] == 0:
            users_list = list(_fallback_store["users"].values())
            stats["total_users"] = len(users_list)
            stats["premium_users"] = sum(1 for u in users_list if u.get("lifetime_premium") or (u.get("premium") and (_parse_datetime(u.get("premium_until")) or now) > now))
            stats["free_users"] = max(0, stats["total_users"] - stats["premium_users"])

            if cutoff != datetime.min:
                stats["new_users"] = sum(1 for u in users_list if (_parse_datetime(u.get("join_date")) or now) >= cutoff)
            else:
                stats["new_users"] = stats["total_users"]

            all_dl = _fallback_store["downloads"]
            filtered_dl = []
            for d in all_dl:
                ts = _parse_datetime(d.get("timestamp")) or now
                if cutoff == datetime.min or ts >= cutoff:
                    filtered_dl.append(d)

            stats["total_downloads"] = len(filtered_dl)
            active_uids = set()
            total_succ_platform = 0

            for d in filtered_dl:
                st = (d.get("status") or "success").lower()
                uid = d.get("user_id")
                if uid:
                    active_uids.add(uid)

                prov = (d.get("provider") or "youtube").lower()
                if prov in ("saavn", "jio_saavn"):
                    prov = "jiosaavn"
                elif prov == "sp":
                    prov = "spotify"
                elif prov == "yt":
                    prov = "youtube"

                fmt = str(d.get("format") or "mp3").lower()
                q_val = str(d.get("quality") or "320")

                if st == "success":
                    stats["successful_downloads"] += 1
                    f_size = d.get("file_size", 0)
                    stats["total_audio_bytes"] += f_size
                    conv_dur = float(d.get("conversion_duration") or 0.0)
                    if conv_dur > 0:
                        total_conv_time += conv_dur
                        conv_time_count += 1

                    if prov in stats["platform_usage"]:
                        stats["platform_usage"][prov] += 1
                        total_succ_platform += 1

                    if fmt in stats["format_usage"]:
                        stats["format_usage"][fmt] += 1
                    elif "flac" in fmt:
                        stats["format_usage"]["flac"] += 1
                    else:
                        stats["format_usage"]["mp3"] += 1

                    stats["quality_usage"][q_val] = stats["quality_usage"].get(q_val, 0) + 1

                    if prov in stats["provider_format_usage"]:
                        if fmt in stats["provider_format_usage"][prov]:
                            stats["provider_format_usage"][prov][fmt] += 1

                    # Check source quality vs requested
                    src_q = d.get("source_quality") or {}
                    src_br = src_q.get("bitrate_kbps", 0)
                    req_br = int(q_val) if q_val.isdigit() else 0
                    if src_br > 0 and req_br > 0:
                        if req_br > src_br:
                            stats["source_quality_stats"]["lower_than_requested"] += 1
                        else:
                            stats["source_quality_stats"]["equal_or_higher"] += 1

                elif st in ("failed", "fail", "error"):
                    stats["failed_downloads"] += 1
                    if prov in stats["provider_failures"]:
                        stats["provider_failures"][prov] += 1
                    if fmt in stats["failed_conversions_by_format"]:
                        stats["failed_conversions_by_format"][fmt] += 1
                    else:
                        stats["failed_conversions_by_format"]["mp3"] += 1

                elif st in ("cancelled", "canceled"):
                    stats["cancelled_downloads"] += 1

                if d.get("is_premium"):
                    stats["user_tier_downloads"]["premium"] += 1
                else:
                    stats["user_tier_downloads"]["free"] += 1

            stats["active_users"] = len(active_uids)

        # --- Math & Percentage Post-Processing ---
        completed = stats["successful_downloads"] + stats["failed_downloads"]
        if completed > 0:
            stats["success_rate"] = round((stats["successful_downloads"] / completed) * 100.0, 1)
        else:
            stats["success_rate"] = 0.0

        stats["total_audio_mb"] = round(stats["total_audio_bytes"] / (1024 * 1024), 2)
        stats["audio_volume_mb"] = stats["total_audio_mb"]

        if stats["successful_downloads"] > 0:
            stats["avg_output_size_mb"] = round(stats["total_audio_mb"] / stats["successful_downloads"], 2)
        else:
            stats["avg_output_size_mb"] = 0.0

        if conv_time_count > 0:
            stats["avg_conversion_duration_sec"] = round(total_conv_time / conv_time_count, 2)
        else:
            stats["avg_conversion_duration_sec"] = 0.0

        succ_total = stats["successful_downloads"]
        display_map = {"youtube": "YouTube", "spotify": "Spotify", "jiosaavn": "JioSaavn", "soundcloud": "SoundCloud", "deezer": "Deezer"}
        if succ_total > 0:
            for prov in stats["platform_usage"]:
                pct = round((stats["platform_usage"][prov] / succ_total) * 100.0, 1)
                stats["platform_percentages"][prov] = pct
                if pct > 0:
                    d_name = display_map.get(prov, prov.title())
                    stats["top_platforms"][d_name] = pct
        else:
            for prov in stats["platform_usage"]:
                stats["platform_percentages"][prov] = 0.0

        # Convenience counters
        stats["mp3_count"] = stats["format_usage"].get("mp3", 0)
        stats["flac_count"] = stats["format_usage"].get("flac", 0)
        stats["premium_downloads"] = stats["user_tier_downloads"].get("premium", 0)
        stats["free_downloads"] = stats["user_tier_downloads"].get("free", 0)

        return stats

    def get_user_stats(self):
        """Returns a quick summary dict (total, premium, free, active_today, total_downloads)"""
        s = self.get_statistics("24h")
        return {
            "total_users": s["total_users"],
            "premium_users": s["premium_users"],
            "free_users": s["free_users"],
            "active_today": s["active_users"],
            "total_downloads": s["total_downloads"]
        }

    def get_recent_users(self, limit=10):
        """Return list of recently joined users."""
        self._ensure()
        if self.available and self.users is not None:
            try:
                return list(self.users.find().sort("join_date", -1).limit(limit))
            except errors.PyMongoError as e:
                logger.warning(f"Mongo error in get_recent_users: {e}")
                self.available = False
        users = list(_fallback_store["users"].values())
        return sorted(users, key=lambda u: _parse_datetime(u.get("join_date")) or datetime.min, reverse=True)[:limit]

    def debug_fallback(self):
        return {
            "users": dict(_fallback_store["users"]),
            "bot_settings": dict(_fallback_store["bot_settings"]),
            "provider_settings": dict(_fallback_store["provider_settings"]),
            "downloads": list(_fallback_store["downloads"]),
            "admin_audit": list(_fallback_store["admin_audit"])
        }

# Global DB singleton
db = Database()
import atexit
atexit.register(db.close)

