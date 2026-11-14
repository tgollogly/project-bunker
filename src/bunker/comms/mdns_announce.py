from __future__ import annotations

import argparse
import socket
import sys
import time


def announce_without_deps(service_name: str = "bunker-sync", port: int = 41567) -> None:
    """
    Best-effort LAN announcement without external DNS.

    Uses UDP subnet broadcast; optional `mdns` extra installs zeroconf for standards-based discovery.
    """
    hostname = socket.gethostname()
    msg = f"BUNKER|M={service_name}|H={hostname}|P={port}".encode()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        while True:
            sock.sendto(msg, ("255.255.255.255", port))
            print(f"Announced {service_name} on :{port}", flush=True)
            time.sleep(30)
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()


def announce_zeroconf(service_name: str, port: int) -> None:
    from zeroconf import ServiceInfo, Zeroconf

    ip = socket.gethostbyname(socket.gethostname())
    info = ServiceInfo(
        "_bunker._tcp.local.",
        f"{service_name}._bunker._tcp.local.",
        addresses=[socket.inet_aton(ip)],
        port=port,
        properties={"txtvers": "1", "path": "/bunker_sync"},
    )
    zc = Zeroconf()
    zc.register_service(info)
    try:
        print("mDNS service registered (_bunker._tcp.local.) — Ctrl+C to stop", flush=True)
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        zc.unregister_service(info)
        zc.close()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Project Bunker LAN service announcement")
    p.add_argument("--name", default="bunker-sync")
    p.add_argument("--port", type=int, default=41567)
    p.add_argument("--zeroconf", action="store_true", help="Use zeroconf (pip install project-bunker[mdns])")
    args = p.parse_args(argv)
    if args.zeroconf:
        try:
            announce_zeroconf(args.name, args.port)
        except ImportError:
            print("zeroconf not installed; use: pip install 'project-bunker[mdns]'", file=sys.stderr)
            return 1
    else:
        announce_without_deps(args.name, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())