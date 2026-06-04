"""CORS for desktop WebView (Tauri/Vite dev) → loopback API."""

from __future__ import annotations

from fastapi.middleware.cors import CORSMiddleware

# Tauri dev (Vite :1420), bundled webview (tauri.localhost), loopback API ports.
_DESKTOP_ORIGIN_REGEX = (
    r"^https?://("
    r"localhost|127\.0\.0\.1|tauri\.localhost"
    r")(:\d+)?$"
    r"|^tauri://localhost$"
)


def install_desktop_cors(app) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=_DESKTOP_ORIGIN_REGEX,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
