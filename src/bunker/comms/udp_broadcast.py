from __future__ import annotations

import argparse
import os
import socket

from bunker.comms.mesh_auth import pack_alert, unpack_and_verify

DEFAULT_PORT = 41567
BROADCAST_ADDR = "255.255.255.255"
MAX_DGRAM = 65535


def _mesh_key() -> bytes:
    raw = os.environ.get("BUNKER_MESH_KEY", "").encode("utf-8")
    if len(raw) < 16:
        raise RuntimeError("Set BUNKER_MESH_KEY (16+ bytes) for signed LAN alerts")
    return raw


def send_alert(message: str, port: int = DEFAULT_PORT) -> None:
    payload = pack_alert(message, key=_mesh_key())
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(payload, (BROADCAST_ADDR, port))
    finally:
        sock.close()


def listen(port: int = DEFAULT_PORT) -> None:
    key = _mesh_key()
    seen: dict[str, float] = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", port))
    print(f"Listening for signed bunker-mesh UDP on port {port}...", flush=True)
    while True:
        data, addr = sock.recvfrom(MAX_DGRAM)
        ok, detail = unpack_and_verify(data, key=key, seen_nonces=seen)
        if ok:
            print(f"[{addr[0]}] {detail!r}", flush=True)
        else:
            print(f"[{addr[0]}] REJECTED: {detail}", flush=True)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Signed Project Bunker LAN UDP alerts (no DNS)")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("send", help="Broadcast a signed alert")
    s.add_argument("message")
    s.add_argument("--port", type=int, default=DEFAULT_PORT)
    listen_p = sub.add_parser("listen", help="Listen for signed alerts")
    listen_p.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = p.parse_args(argv)
    if args.cmd == "send":
        send_alert(args.message, port=args.port)
        return 0
    listen(port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())