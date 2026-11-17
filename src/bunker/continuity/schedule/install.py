from __future__ import annotations

import platform
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ScheduleSpec:
    interval_hours: int = 6
    bunker_cmd: str = "bunker"


def _project_root() -> Path:
    return Path.cwd()


def install_schedule(spec: ScheduleSpec) -> dict[str, str]:
    system = platform.system()
    if system == "Linux":
        return _install_systemd_user(spec)
    if system == "Darwin":
        return _install_launchd(spec)
    if system == "Windows":
        return _install_schtasks(spec)
    raise RuntimeError(f"Unsupported OS for scheduled sync: {system}")


def uninstall_schedule(spec: ScheduleSpec) -> dict[str, str]:
    system = platform.system()
    if system == "Linux":
        return _uninstall_systemd_user()
    if system == "Darwin":
        return _uninstall_launchd()
    if system == "Windows":
        return _uninstall_schtasks()
    raise RuntimeError(f"Unsupported OS: {system}")


def _bunker_bin(spec: ScheduleSpec) -> str:
    return spec.bunker_cmd or (sys.executable + " -m bunker.cli")


def _install_systemd_user(spec: ScheduleSpec) -> dict[str, str]:
    home = Path.home()
    unit_dir = home / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    service = unit_dir / "bunker-continuity-sync.service"
    timer = unit_dir / "bunker-continuity-sync.timer"
    root = _project_root()
    cmd = f"cd {root} && {spec.bunker_cmd} continuity sync"
    service.write_text(
        f"""[Unit]
Description=Bunker Continuity sync

[Service]
Type=oneshot
WorkingDirectory={root}
ExecStart=/bin/sh -lc '{cmd}'
""",
        encoding="utf-8",
    )
    timer.write_text(
        f"""[Unit]
Description=Bunker Continuity sync timer

[Timer]
OnBootSec=15min
OnUnitActiveSec={spec.interval_hours}h
Persistent=true

[Install]
WantedBy=timers.target
""",
        encoding="utf-8",
    )
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    subprocess.run(
        ["systemctl", "--user", "enable", "--now", "bunker-continuity-sync.timer"],
        check=False,
    )
    return {"platform": "linux", "timer": str(timer), "service": str(service)}


def _uninstall_systemd_user() -> dict[str, str]:
    subprocess.run(
        ["systemctl", "--user", "disable", "--now", "bunker-continuity-sync.timer"],
        check=False,
    )
    return {"platform": "linux", "status": "disabled"}


def _install_launchd(spec: ScheduleSpec) -> dict[str, str]:
    home = Path.home()
    plist = home / "Library" / "LaunchAgents" / "com.projectbunker.continuity-sync.plist"
    plist.parent.mkdir(parents=True, exist_ok=True)
    root = _project_root()
    interval = spec.interval_hours * 3600
    plist.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.projectbunker.continuity-sync</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/sh</string><string>-lc</string>
    <string>cd {root} &amp;&amp; {spec.bunker_cmd} continuity sync</string>
  </array>
  <key>StartInterval</key><integer>{interval}</integer>
  <key>RunAtLoad</key><true/>
</dict>
</plist>
""",
        encoding="utf-8",
    )
    subprocess.run(["launchctl", "load", str(plist)], check=False)
    return {"platform": "darwin", "plist": str(plist)}


def _uninstall_launchd() -> dict[str, str]:
    plist = Path.home() / "Library" / "LaunchAgents" / "com.projectbunker.continuity-sync.plist"
    subprocess.run(["launchctl", "unload", str(plist)], check=False)
    return {"platform": "darwin", "status": "unloaded"}


def _install_schtasks(spec: ScheduleSpec) -> dict[str, str]:
    root = _project_root()
    cmd = f'cd /d "{root}" && {spec.bunker_cmd} continuity sync'
    subprocess.run(
        [
            "schtasks",
            "/Create",
            "/F",
            "/SC",
            "HOURLY",
            "/MO",
            str(spec.interval_hours),
            "/TN",
            "BunkerContinuitySync",
            "/TR",
            cmd,
        ],
        check=False,
    )
    return {"platform": "windows", "task": "BunkerContinuitySync"}


def _uninstall_schtasks() -> dict[str, str]:
    subprocess.run(["schtasks", "/Delete", "/F", "/TN", "BunkerContinuitySync"], check=False)
    return {"platform": "windows", "status": "deleted"}