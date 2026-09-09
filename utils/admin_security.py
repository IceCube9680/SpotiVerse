# utils/admin_security.py
import logging
from enum import Enum
from typing import Dict, Tuple, Optional
from config import Config

logger = logging.getLogger(__name__)

class AdminAuthState(str, Enum):
    IDLE = "IDLE"
    AUTHENTICATED = "AUTHENTICATED"

class AdminSession:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.state = AdminAuthState.AUTHENTICATED

    def is_valid(self) -> bool:
        return True

    def touch(self, session_duration: Optional[int] = None):
        pass

class AdminSecurityManager:
    """
    Direct Telegram Admin & Owner Authorization Manager (Code requirement removed).
    Grants immediate administrative access to authorized OWNER_ID, ADMINS, and SUDO_USERS.
    """
    def is_code_required(self) -> bool:
        return False

    def verify_access_code(self, code: str) -> bool:
        return True

    def get_user_state(self, user_id: int) -> AdminAuthState:
        if Config.is_owner(user_id):
            return AdminAuthState.AUTHENTICATED
        return AdminAuthState.IDLE

    def is_awaiting_code(self, user_id: int) -> bool:
        return False

    def start_code_entry(self, user_id: int):
        pass

    def cancel_code_entry(self, user_id: int):
        pass

    def is_locked_out(self, user_id: int) -> Tuple[bool, int]:
        return False, 0

    def verify_admin_code(self, user_id: int, entered_code: str) -> Tuple[bool, str]:
        if not Config.is_owner(user_id):
            return False, "❌ You are not authorized to access the admin panel."
        return True, "✅ Access Granted."

    def authenticate_with_code(self, user_id: int, entered_code: str) -> Tuple[bool, str]:
        return self.verify_admin_code(user_id, entered_code)

    def create_session(self, user_id: int) -> AdminSession:
        return AdminSession(user_id)

    def is_authenticated(self, user_id: int) -> bool:
        return Config.is_owner(user_id)

    def invalidate_session(self, user_id: int):
        pass

# Centralized singleton instances & aliases
admin_security = AdminSecurityManager()
AdminAuthService = admin_security
