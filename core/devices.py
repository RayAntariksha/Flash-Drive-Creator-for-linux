"""
core/devices.py

Detects removable/USB block devices on Linux using `lsblk`, and provides
helpers to unmount any mounted partitions on a device before it is
overwritten.

Only devices that lsblk reports as removable (RM=1) and/or connected via
USB (TRAN=usb) are surfaced to the UI. This is a safety measure: internal
disks should never show up as candidates for writing.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field


class DeviceError(RuntimeError):
    pass


def _run(cmd: list[str], timeout: int = 15) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, check=False
    )


def _require(binary: str) -> None:
    if shutil.which(binary) is None:
        raise DeviceError(
            f"Required tool '{binary}' was not found on PATH. "
            f"Please install it (see README) and try again."
        )


def human_size(num_bytes: int) -> str:
    """Format a byte count as a human-readable string (binary units)."""
    value = float(num_bytes)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024.0 or unit == "TiB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} {unit}"
        value /= 1024.0
    return f"{num_bytes} B"


@dataclass
class Partition:
    path: str
    fstype: str | None
    mountpoint: str | None


@dataclass
class Drive:
    path: str          # e.g. /dev/sdb
    name: str           # e.g. sdb
    size_bytes: int
    model: str
    vendor: str
    transport: str      # usb, sata, nvme, mmc, ...
    removable: bool
    partitions: list[Partition] = field(default_factory=list)

    @property
    def label(self) -> str:
        size = human_size(self.size_bytes)
        model = self.model.strip() or "Unknown drive"
        vendor = self.vendor.strip()
        desc = f"{vendor} {model}".strip()
        return f"{self.path}  —  {desc}  ({size})"

    @property
    def mounted_partitions(self) -> list[Partition]:
        return [p for p in self.partitions if p.mountpoint]


def list_removable_drives() -> list[Drive]:
    """Return all disks lsblk considers removable and/or USB-attached."""
    _require("lsblk")

    proc = _run(
        [
            "lsblk",
            "-J",  # JSON output
            "-b",  # sizes in bytes
            "-o",
            "NAME,PATH,SIZE,MODEL,VENDOR,TRAN,RM,TYPE,FSTYPE,MOUNTPOINT",
        ]
    )
    if proc.returncode != 0:
        raise DeviceError(f"lsblk failed: {proc.stderr.strip()}")

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise DeviceError(f"Could not parse lsblk output: {exc}") from exc

    drives: list[Drive] = []

    for entry in data.get("blockdevices", []):
        if entry.get("type") != "disk":
            continue

        removable = str(entry.get("rm")).lower() in ("1", "true")
        transport = (entry.get("tran") or "").lower()

        # Only show drives that are removable OR explicitly USB-attached.
        # This intentionally excludes internal SATA/NVMe boot disks.
        if not removable and transport != "usb":
            continue

        partitions = []
        for child in entry.get("children", []) or []:
            partitions.append(
                Partition(
                    path=child.get("path") or f"/dev/{child.get('name')}",
                    fstype=child.get("fstype"),
                    mountpoint=child.get("mountpoint"),
                )
            )

        drives.append(
            Drive(
                path=entry.get("path") or f"/dev/{entry.get('name')}",
                name=entry.get("name", ""),
                size_bytes=int(entry.get("size") or 0),
                model=entry.get("model") or "",
                vendor=entry.get("vendor") or "",
                transport=transport or "unknown",
                removable=removable,
                partitions=partitions,
            )
        )

    return drives


def unmount_drive(drive: Drive) -> list[str]:
    """
    Unmount every mounted partition on a drive before writing.
    Returns a list of warning strings for anything that could not be
    unmounted cleanly (caller should decide whether to abort).
    """
    warnings: list[str] = []
    has_udisks = shutil.which("udisksctl") is not None

    for part in drive.mounted_partitions:
        ok = False
        if has_udisks:
            proc = _run(["udisksctl", "unmount", "-b", part.path], timeout=20)
            ok = proc.returncode == 0
            err = proc.stderr.strip()
        if not ok:
            proc = _run(["umount", part.path], timeout=20)
            ok = proc.returncode == 0
            err = proc.stderr.strip()
        if not ok:
            warnings.append(f"Could not unmount {part.path}: {err or 'unknown error'}")

    return warnings


_PART_SUFFIX_RE = re.compile(r"(p?\d+)$")


def is_mounted_anywhere(drive: Drive) -> bool:
    return len(drive.mounted_partitions) > 0
