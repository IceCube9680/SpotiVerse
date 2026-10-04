import os
os.environ["TESTING"] = "1"
os.environ["MONGO_URI"] = ""

import pytest
from utils.db import db, _fallback_store

@pytest.fixture(autouse=True)
def clean_db_store():
    _fallback_store["users"].clear()
    _fallback_store["downloads"].clear()
    _fallback_store["bot_settings"].clear()
    _fallback_store["provider_settings"].clear()
    _fallback_store["admin_audit"].clear()
    db.available = False
    yield
