"""Static file serving with SPA fallback to index.html for client-side routes."""
from __future__ import annotations

import os

from starlette.staticfiles import StaticFiles


class SpaStaticFiles(StaticFiles):
    """
    When html=True and the requested path has no matching file, serve index.html
    so Vue Router can handle /rankings, /genre, etc.
    """

    def lookup_path(self, path: str) -> tuple[str, os.stat_result | None]:
        full_path, stat_result = super().lookup_path(path)
        if stat_result is None and self.html:
            return super().lookup_path("index.html")
        return full_path, stat_result
