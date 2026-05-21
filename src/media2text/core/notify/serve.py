from __future__ import annotations

import socket
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def guess_lan_host() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def suggested_media_base_url(*, host: str, port: int) -> str:
    return f"http://{host}:{port}"


def run_workspace_http_server(
    *,
    workspace: Path,
    host: str = "0.0.0.0",
    port: int = 8765,
) -> None:
    root = workspace.resolve()
    root.mkdir(parents=True, exist_ok=True)
    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    server = ThreadingHTTPServer((host, port), handler)
    lan = guess_lan_host()
    print(f"Serving {root}")
    print(f"Local:  http://127.0.0.1:{port}/")
    print(f"LAN:    http://{lan}:{port}/")
    print(f"config.yaml → notify.feishu.media_base_url: {suggested_media_base_url(host=lan, port=port)}")
    print("Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
