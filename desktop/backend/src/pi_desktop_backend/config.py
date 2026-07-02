"""Backend configuration and port management."""
from __future__ import annotations

import os
import socket

DEFAULT_PORT = 9876


def get_port() -> int:
    """Get the port to listen on.
    - PI_DESKTOP_PORT=0 -> random free port (used by Electron shell)
    - PI_DESKTOP_PORT=N  -> use port N
    - not set           -> use default 9876
    """
    env_port = os.environ.get("PI_DESKTOP_PORT")
    if env_port is not None:
        try:
            p = int(env_port)
            if p == 0:
                return find_free_port()
            return p
        except ValueError:
            pass
    return DEFAULT_PORT


def find_free_port() -> int:
    """Find a free port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
