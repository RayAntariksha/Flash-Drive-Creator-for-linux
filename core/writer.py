"""
core/writer.py

Writes an ISO/IMG file to a block device, reporting progress back to the
caller via a callback. Uses `dd` (run through `pkexec` for privilege
escalation) because it is present on every Linux system and its
`status=progress` output gives reliable, parseable progress information
without needing extra dependencies.

The write is run in a subprocess so it can be cancelled cleanly, and a
hash-based verification pass is offered afterward.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional


class WriteError(RuntimeError):
    pass


class WriteCancelled(RuntimeError):
    pass


@dataclass
class Progress:
    bytes_written: int
    total_bytes: int
    speed_bytes_per_sec: float
    elapsed_sec: float

    @property
    def fraction(self) -> float:
        if self.total_bytes <= 0:
            return 0.0
        return min(1.0, self.bytes_written / self.total_bytes)

    @property
    def eta_sec(self) -> float | None:
        if self.speed_bytes_per_sec <= 0:
            return None
        remaining = max(0, self.total_bytes - self.bytes_written)
        return remaining / self.speed_bytes_per_sec


ProgressCallback = Callable[[Progress], None]

_DD_BYTES_RE = re.compile(r"^(\d+)\s+bytes")


def _pick_privilege_helper() -> list[str]:
    """Pick whichever privilege-escalation tool is available."""
    if shutil.which("pkexec"):
        return ["pkexec"]
    if shutil.which("sudo"):
        return ["sudo"]
    raise WriteError(
        "Neither 'pkexec' nor 'sudo' is available. Install PolicyKit "
        "(pkexec) or sudo to allow this tool to write to the device."
    )


class ImageWriter:
    def __init__(self, image_path: str, device_path: str, block_size: str = "4M"):
        self.image_path = image_path
        self.device_path = device_path
        self.block_size = block_size
        self._proc: Optional[subprocess.Popen] = None
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()

    def write(self, on_progress: Optional[ProgressCallback] = None) -> None:
        if not os.path.isfile(self.image_path):
            raise WriteError(f"Image file not found: {self.image_path}")

        total_bytes = os.path.getsize(self.image_path)
        helper = _pick_privilege_helper()

        dd_cmd = [
            "dd",
            f"if={self.image_path}",
            f"of={self.device_path}",
            f"bs={self.block_size}",
            "conv=fsync,noerror",
            "status=progress",
        ]
        cmd = helper + dd_cmd

        start = time.monotonic()
        last_bytes = 0
        last_time = start

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError as exc:
            raise WriteError(f"Could not start dd: {exc}") from exc

        assert self._proc.stderr is not None
        buf = ""
        while True:
            chunk = self._proc.stderr.read(256)
            if chunk == "" and self._proc.poll() is not None:
                break
            if self._cancelled.is_set():
                self._proc.terminate()
                raise WriteCancelled("Write cancelled by user.")
            if not chunk:
                continue
            buf += chunk
            # dd's status=progress writes updates separated by \r
            while "\r" in buf or "\n" in buf:
                sep_idx = min(
                    (i for i in (buf.find("\r"), buf.find("\n")) if i != -1),
                    default=-1,
                )
                if sep_idx == -1:
                    break
                line, buf = buf[:sep_idx], buf[sep_idx + 1 :]
                match = _DD_BYTES_RE.match(line.strip())
                if match and on_progress:
                    written = int(match.group(1))
                    now = time.monotonic()
                    dt = now - last_time
                    speed = (written - last_bytes) / dt if dt > 0 else 0.0
                    last_bytes, last_time = written, now
                    on_progress(
                        Progress(
                            bytes_written=written,
                            total_bytes=total_bytes,
                            speed_bytes_per_sec=speed,
                            elapsed_sec=now - start,
                        )
                    )

        returncode = self._proc.wait()
        if returncode != 0:
            stderr_tail = buf.strip()
            raise WriteError(
                f"dd exited with code {returncode}. {stderr_tail or 'See terminal output.'}"
            )

        # Final progress update: report completion.
        if on_progress:
            now = time.monotonic()
            on_progress(
                Progress(
                    bytes_written=total_bytes,
                    total_bytes=total_bytes,
                    speed_bytes_per_sec=0.0,
                    elapsed_sec=now - start,
                )
            )

    def verify(self, on_progress: Optional[ProgressCallback] = None,
               chunk_size: int = 4 * 1024 * 1024) -> bool:
        """
        Compare a SHA-256 hash of the source image against the first
        len(image) bytes written to the device. Requires read access to
        the device, so it is also run through the privilege helper by
        re-invoking this script is unnecessary: reading block devices is
        usually permitted for the disk group, but we fall back to sudo
        cat piped through hashlib if a direct open() fails.
        """
        total_bytes = os.path.getsize(self.image_path)

        src_hash = hashlib.sha256()
        with open(self.image_path, "rb") as f:
            read = 0
            while True:
                if self._cancelled.is_set():
                    raise WriteCancelled("Verification cancelled by user.")
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                src_hash.update(chunk)
                read += len(chunk)
                if on_progress:
                    on_progress(Progress(read, total_bytes, 0.0, 0.0))

        dst_hash = hashlib.sha256()
        try:
            dev_fd = os.open(self.device_path, os.O_RDONLY)
        except PermissionError:
            # Fall back to a privileged read via dd piped to this process.
            helper = _pick_privilege_helper()
            cmd = helper + ["dd", f"if={self.device_path}", f"bs={chunk_size}",
                             f"count={-(-total_bytes // chunk_size)}",
                             "status=none"]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
            assert proc.stdout is not None
            read = 0
            while read < total_bytes:
                chunk = proc.stdout.read(min(chunk_size, total_bytes - read))
                if not chunk:
                    break
                dst_hash.update(chunk)
                read += len(chunk)
                if on_progress:
                    on_progress(Progress(read, total_bytes, 0.0, 0.0))
            proc.stdout.close()
            proc.wait()
        else:
            try:
                read = 0
                while read < total_bytes:
                    chunk = os.read(dev_fd, min(chunk_size, total_bytes - read))
                    if not chunk:
                        break
                    dst_hash.update(chunk)
                    read += len(chunk)
                    if on_progress:
                        on_progress(Progress(read, total_bytes, 0.0, 0.0))
            finally:
                os.close(dev_fd)

        return src_hash.hexdigest() == dst_hash.hexdigest()
