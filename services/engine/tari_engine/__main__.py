"""Entry point: ``python -m tari_engine``.

Binds to loopback only. The auth token comes from TARI_ENGINE_TOKEN (set by
the desktop supervisor) or --dev-token for manual runs. Once ready, prints
``TARI_ENGINE_READY {"port": N, ...}`` on stdout.
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
from pathlib import Path

import uvicorn

from .app import create_app
from .config import EngineConfig, default_data_dir
from .logging_setup import configure_logging


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tari_engine")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--data-dir", type=Path, default=None)
    ap.add_argument("--dev-token", default=None, help="token for manual runs (prefer TARI_ENGINE_TOKEN)")
    ap.add_argument("--log-level", default="info")
    ap.add_argument("--max-frame-age-ms", type=float, default=250.0)
    ap.add_argument("--no-persistence", action="store_true")
    args = ap.parse_args(argv)

    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print("refusing to bind a non-loopback address", file=sys.stderr)
        return 2
    token = os.environ.get("TARI_ENGINE_TOKEN") or args.dev_token
    if not token:
        print("TARI_ENGINE_TOKEN is not set (or pass --dev-token)", file=sys.stderr)
        return 2
    data_dir = args.data_dir or default_data_dir()
    configure_logging(args.log_level, data_dir / "logs")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((args.host if args.host != "localhost" else "127.0.0.1", args.port))
    port = sock.getsockname()[1]

    config = EngineConfig(token=token, host=args.host, port=port, data_dir=data_dir,
                          max_frame_age_ms=args.max_frame_age_ms, persistence=not args.no_persistence)
    app = create_app(config, announce_port=port)
    server = uvicorn.Server(uvicorn.Config(
        app, log_config=None, ws_max_size=64 * 1024 * 1024, ws_per_message_deflate=False,
        ws_ping_interval=20.0, ws_ping_timeout=20.0, lifespan="on",
    ))
    server.run(sockets=[sock])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
