"""Production entry point: `python -m edgefront_api.serve`.

Railway private networking (dual stack) needs the API to accept IPv6 and IPv4. `uvicorn --host ::`
is not enough: asyncio sets IPV6_V6ONLY on IPv6 sockets, so it would answer IPv6 only. This binds
one socket on `::` with IPV6_V6ONLY switched off (IPv4 arrives as ::ffff:a.b.c.d) and hands it to
uvicorn. PORT comes from the environment (Railway sets it).
"""

from __future__ import annotations

import os
import socket

import uvicorn


def dual_stack_socket(port: int, host: str = "::") -> socket.socket:
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    sock.bind((host, port))
    sock.set_inheritable(True)
    return sock


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    config = uvicorn.Config(
        "edgefront_api.main:build",
        factory=True,
        proxy_headers=True,
        forwarded_allow_ips="*",  # only Railway's private network can reach this service
        log_config=None,  # the app configures JSON logging itself
        access_log=False,
    )
    uvicorn.Server(config).run(sockets=[dual_stack_socket(port)])


if __name__ == "__main__":
    main()
