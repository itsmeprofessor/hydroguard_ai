"""
HydroGuard-AI — Rate limiter with real-IP extraction.
Extracts client IP from X-Forwarded-For (first non-private hop)
so per-IP limits work correctly behind nginx.
"""
from __future__ import annotations

import ipaddress

from slowapi import Limiter
from slowapi.util import get_remote_address


def _get_real_ip(request) -> str:
    """
    Extract the real client IP from X-Forwarded-For.
    Returns the first non-private IP found; falls back to
    REMOTE_ADDR (get_remote_address) when header is absent or all-private.
    """
    xff = request.headers.get("X-Forwarded-For", "")
    for ip_str in (s.strip() for s in xff.split(",") if s.strip()):
        try:
            ip = ipaddress.ip_address(ip_str)
            if not ip.is_private and not ip.is_loopback:
                return str(ip)
        except ValueError:
            continue
    return get_remote_address(request)


limiter = Limiter(key_func=_get_real_ip)
