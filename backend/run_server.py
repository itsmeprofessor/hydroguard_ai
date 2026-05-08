#!/usr/bin/env python3
"""
HydroGuard-AI — API Server Launcher

Usage:
    python run_server.py
    python run_server.py --port 8080 --host 0.0.0.0
    python run_server.py --reload          # development hot-reload
    python run_server.py --workers 4       # production (PostgreSQL only)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Force UTF-8 on stdout/stderr so Unicode log characters (arrows, checkmarks, etc.)
# do not crash on Windows consoles with cp1252 default encoding.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import uvicorn
from app.core.config import APIConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="Run HydroGuard-AI API Server")
    parser.add_argument("--host",    type=str, default=APIConfig.HOST)
    parser.add_argument("--port", "-p", type=int, default=APIConfig.PORT)
    parser.add_argument("--reload", "-r", action="store_true",
                        help="Enable auto-reload (development only)")
    parser.add_argument("--workers", "-w", type=int, default=1,
                        help="Worker processes. Keep at 1 for SQLite.")
    args = parser.parse_args()

    if args.workers > 1 and "sqlite" in APIConfig.__dict__.get("DATABASE_URL", "sqlite").lower():
        print("⚠  WARNING: SQLite + multiple workers → DB lock errors. Use --workers 1 or PostgreSQL.")

    print("=" * 60)
    print("  HydroGuard-AI  —  Weather Anomaly Detection API")
    print("=" * 60)
    print(f"  Server    : http://{args.host}:{args.port}")
    print(f"  Swagger   : http://127.0.0.1:{args.port}/docs")
    print(f"  Dashboard : http://127.0.0.1:{args.port}/frontend")
    print(f"  Workers   : {args.workers}")
    print("=" * 60)

    uvicorn.run(
        "app.main:app",
        host      = args.host,
        port      = args.port,
        reload    = args.reload,
        workers   = args.workers,
        log_level = "info",
    )


if __name__ == "__main__":
    main()
