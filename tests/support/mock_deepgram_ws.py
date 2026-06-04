"""Local Deepgram listen.v1 WebSocket mock for offline streaming STT tests."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from websockets.sync.server import WebSocketServer, serve


def deepgram_results_payload(
    *,
    transcript: str,
    is_final: bool = True,
    start: float = 0.0,
    duration: float = 1.5,
    request_id: str = "mock-request-id",
) -> dict[str, Any]:
    return {
        "type": "Results",
        "channel_index": [0, 1],
        "duration": duration,
        "start": start,
        "is_final": is_final,
        "channel": {
            "alternatives": [
                {
                    "transcript": transcript,
                    "confidence": 0.99,
                    "words": [],
                }
            ]
        },
        "metadata": {
            "request_id": request_id,
            "model_info": {"name": "nova-3", "version": "1.0.0", "arch": "nova-3"},
            "model_uuid": "00000000-0000-0000-0000-000000000001",
        },
    }


@dataclass
class MockDeepgramWsServer:
    """Accept PCM frames and emit scripted Deepgram Results JSON messages."""

    on_pcm_bytes: Callable[[int], Iterable[dict[str, Any]]] | None = None
    _host: str = "127.0.0.1"
    _port: int = 0
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _server: WebSocketServer | None = field(default=None, init=False, repr=False)
    _ready: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    pcm_bytes_received: int = field(default=0, init=False)

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port

    @property
    def ws_base(self) -> str:
        return f"ws://{self._host}:{self._port}"

    def start(self, *, timeout: float = 5.0) -> None:
        if self._thread is not None:
            return

        def run() -> None:
            with serve(self._handler, self._host, 0) as server:
                self._server = server
                self._port = server.socket.getsockname()[1]
                self._ready.set()
                server.serve_forever()

        self._thread = threading.Thread(target=run, daemon=True, name="mock-deepgram-ws")
        self._thread.start()
        if not self._ready.wait(timeout=timeout):
            raise RuntimeError("mock Deepgram WS server failed to start")

    def stop(self) -> None:
        server = self._server
        if server is not None:
            server.shutdown()
            self._server = None
        thread = self._thread
        if thread is not None:
            thread.join(timeout=5.0)
            self._thread = None
        self._ready.clear()

    def __enter__(self) -> MockDeepgramWsServer:
        self.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.stop()

    def _handler(self, websocket) -> None:  # noqa: ANN001
        pcm_total = 0
        sent_payloads: set[str] = set()
        for message in websocket:
            if isinstance(message, bytes):
                pcm_total += len(message)
                self.pcm_bytes_received = pcm_total
                if self.on_pcm_bytes is None:
                    continue
                for payload in self.on_pcm_bytes(pcm_total):
                    key = json.dumps(payload, sort_keys=True)
                    if key in sent_payloads:
                        continue
                    sent_payloads.add(key)
                    websocket.send(json.dumps(payload))
                continue
            if isinstance(message, str) and "CloseStream" in message:
                break
