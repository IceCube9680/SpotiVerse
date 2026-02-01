# handlers/download_handler.py
"""
Compatibility shim so code that does `from handlers.download_handler import DownloadHandler`
will work while the canonical implementation lives in handlers/downloads.py.
"""

try:
    from handlers.downloads import DownloadHandler  # type: ignore
except Exception as e:
    # Helpful error if the real module fails to import (syntax error, missing deps, etc.)
    raise ImportError(
        "Failed to import DownloadHandler from handlers.downloads. "
        "Make sure handlers/downloads.py exists and is error-free."
    ) from e

__all__ = ["DownloadHandler"]
