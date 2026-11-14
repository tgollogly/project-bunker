from __future__ import annotations

import argparse
import json
import socket
from datetime import datetime, timezone

DEFAULT_PORT = 41567
BROADCAST_ADDR = "255.255.255.255"


def send_alert(message: str, port: int = DEFAULT_PORT, ttl_hops: int = 2) -> None:
    payload = json.dumps(
        {
            "proto": "bunker-mesh/1",
            "ts": datetime.now(timezone.utc).isoformat(),
            "message": message,
        }
    ).encode("utf-8")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl_hops)
        sock.sendto(payload, (BROADCAST_ADDR, port))
    finally:
        sock.close()


def listen(port: int = DEFAULT_PORT) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", port))
    print(f"Listening for bunker-mesh UDP on port {port}...", flush=True)
    while True:
        data, addr = sock.recvfrom(65535)
        try:
            doc = json.loads(data.decode("utf-8"))
            print(f"[{addr[0]}] {doc.get('message', data)!r}", flush=True)
        except json.JSONDecodeError:
            print(f"[{addr[0]}] {data!r}", flush=True)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Project Bunker LAN UDP mesh alerts (no DNS required)")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("send", help="Broadcast an alert")
    s.add_argument("message")
    s.add_argument("--port", type=int, default=DEFAULT_PORT)
    listen_p = sub.add_parser("listen", help="Listen for alerts")
    listen_p.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = p.parse_args(argv)
    if args.cmd == "send":
        send_alert(args.message, port=args.port)
        return 0
    listen(port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())