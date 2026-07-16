#!/usr/bin/env python3
"""
Flash Drive Creator — a simple, safe ISO/IMG-to-USB writer for Linux.

A from-scratch, working reimplementation in the spirit of
https://github.com/RayAntariksha/Flash-Drive-Creator-for-linux
(a Rufus-like tool for Linux), built with a focus on:
  - actually working out of the box (stdlib only, no build step)
  - a clear, hard-to-misuse GUI
  - strong safeguards against writing to the wrong disk

Run with:  python3 flash_drive_creator.py
"""

from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.devices import (  # noqa: E402
    Drive,
    DeviceError,
    human_size,
    list_removable_drives,
    unmount_drive,
)
from core.writer import (  # noqa: E402
    ImageWriter,
    Progress,
    WriteCancelled,
    WriteError,
)

APP_TITLE = "Flash Drive Creator"
CONFIRM_PHRASE = "ERASE"


class FlashDriveCreatorApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("620x520")
        self.minsize(560, 480)
        self.resizable(True, True)

        self.image_path: str | None = None
        self.image_size: int = 0
        self.drives: list[Drive] = []
        self.selected_drive: Drive | None = None
        self.writer: ImageWriter | None = None
        self.worker_thread: threading.Thread | None = None
        self.ui_queue: "queue.Queue[tuple]" = queue.Queue()
        self.is_writing = False

        self._build_style()
        self._build_widgets()
        self.refresh_drives()
        self.after(150, self._poll_queue)

    # ------------------------------------------------------------------ UI

    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Danger.TButton", foreground="#b00020")
        style.configure("Header.TLabel", font=("Sans", 14, "bold"))
        style.configure("Sub.TLabel", foreground="#666666")

    def _build_widgets(self) -> None:
        pad = {"padx": 14, "pady": 8}

        header = ttk.Label(self, text=APP_TITLE, style="Header.TLabel")
        header.pack(anchor="w", **pad)

        subtitle = ttk.Label(
            self,
            text="Write an ISO or IMG file to a USB flash drive.",
            style="Sub.TLabel",
        )
        subtitle.pack(anchor="w", padx=14)

        # --- Step 1: image file -----------------------------------------
        file_frame = ttk.LabelFrame(self, text="1. Choose an image (.iso / .img)")
        file_frame.pack(fill="x", **pad)

        row = ttk.Frame(file_frame)
        row.pack(fill="x", padx=10, pady=10)
        self.image_label = ttk.Label(row, text="No file selected", anchor="w")
        self.image_label.pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Browse…", command=self.choose_image).pack(side="right")

        # --- Step 2: target drive -----------------------------------------
        drive_frame = ttk.LabelFrame(self, text="2. Choose a target drive")
        drive_frame.pack(fill="x", **pad)

        drow = ttk.Frame(drive_frame)
        drow.pack(fill="x", padx=10, pady=10)
        self.drive_combo = ttk.Combobox(drow, state="readonly", values=[])
        self.drive_combo.pack(side="left", fill="x", expand=True)
        self.drive_combo.bind("<<ComboboxSelected>>", self._on_drive_selected)
        ttk.Button(drow, text="Refresh", command=self.refresh_drives).pack(
            side="right", padx=(8, 0)
        )

        self.drive_warning = ttk.Label(
            drive_frame,
            text="Only removable / USB drives are listed. Internal disks are hidden for safety.",
            style="Sub.TLabel",
        )
        self.drive_warning.pack(anchor="w", padx=10, pady=(0, 10))

        # --- Step 3: confirm & write -----------------------------------
        confirm_frame = ttk.LabelFrame(self, text="3. Confirm and write")
        confirm_frame.pack(fill="x", **pad)

        self.verify_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            confirm_frame,
            text="Verify after writing (recommended, checks a SHA-256 hash)",
            variable=self.verify_var,
        ).pack(anchor="w", padx=10, pady=(10, 0))

        crow = ttk.Frame(confirm_frame)
        crow.pack(fill="x", padx=10, pady=10)
        ttk.Label(crow, text=f'Type "{CONFIRM_PHRASE}" to enable writing:').pack(
            side="left"
        )
        self.confirm_var = tk.StringVar()
        self.confirm_var.trace_add("write", lambda *_: self._update_write_button())
        confirm_entry = ttk.Entry(crow, textvariable=self.confirm_var, width=12)
        confirm_entry.pack(side="left", padx=(8, 0))

        self.write_button = ttk.Button(
            confirm_frame,
            text="Write to drive",
            style="Danger.TButton",
            command=self.start_write,
            state="disabled",
        )
        self.write_button.pack(fill="x", padx=10, pady=(0, 10))

        # --- Progress -----------------------------------------------------
        prog_frame = ttk.LabelFrame(self, text="Progress")
        prog_frame.pack(fill="both", expand=True, **pad)

        self.progress_bar = ttk.Progressbar(
            prog_frame, orient="horizontal", mode="determinate", maximum=1000
        )
        self.progress_bar.pack(fill="x", padx=10, pady=(10, 4))

        self.status_label = ttk.Label(prog_frame, text="Idle.")
        self.status_label.pack(anchor="w", padx=10)

        self.cancel_button = ttk.Button(
            prog_frame, text="Cancel", command=self.cancel_write, state="disabled"
        )
        self.cancel_button.pack(anchor="e", padx=10, pady=10)

    # --------------------------------------------------------------- logic

    def choose_image(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose an ISO or IMG file",
            filetypes=[
                ("Disk images", "*.iso *.img *.iso.xz *.img.xz"),
                ("All files", "*"),
            ],
        )
        if not path:
            return
        if not os.path.isfile(path):
            messagebox.showerror(APP_TITLE, "That file could not be found.")
            return
        self.image_path = path
        self.image_size = os.path.getsize(path)
        self.image_label.config(
            text=f"{os.path.basename(path)}  ({human_size(self.image_size)})"
        )
        self._update_write_button()

    def refresh_drives(self) -> None:
        try:
            self.drives = list_removable_drives()
        except DeviceError as exc:
            self.drives = []
            messagebox.showerror(APP_TITLE, str(exc))

        labels = [d.label for d in self.drives]
        self.drive_combo["values"] = labels
        if not labels:
            self.drive_combo.set("")
            self.selected_drive = None
            self.drive_warning.config(
                text="No removable/USB drives detected. Plug one in and click Refresh."
            )
        else:
            self.drive_warning.config(
                text="Only removable / USB drives are listed. Internal disks are hidden for safety."
            )
            # Preserve selection if the same drive is still present.
            if self.selected_drive and self.selected_drive.path in [
                d.path for d in self.drives
            ]:
                idx = [d.path for d in self.drives].index(self.selected_drive.path)
                self.drive_combo.current(idx)
                self.selected_drive = self.drives[idx]
            else:
                self.drive_combo.set("")
                self.selected_drive = None
        self._update_write_button()

    def _on_drive_selected(self, _event=None) -> None:
        idx = self.drive_combo.current()
        if 0 <= idx < len(self.drives):
            self.selected_drive = self.drives[idx]
        self._update_write_button()

    def _update_write_button(self) -> None:
        ready = (
            self.image_path is not None
            and self.selected_drive is not None
            and self.confirm_var.get() == CONFIRM_PHRASE
            and not self.is_writing
        )
        self.write_button.config(state="normal" if ready else "disabled")

    # ------------------------------------------------------------- writing

    def start_write(self) -> None:
        if not self.image_path or not self.selected_drive:
            return

        drive = self.selected_drive

        if drive.size_bytes and self.image_size > drive.size_bytes:
            messagebox.showerror(
                APP_TITLE,
                "The selected image is larger than the target drive. Choose a "
                "different drive or a smaller image.",
            )
            return

        confirm_text = (
            f"This will PERMANENTLY ERASE all data on:\n\n"
            f"    {drive.label}\n\n"
            f"and replace it with the contents of:\n\n"
            f"    {os.path.basename(self.image_path)}\n\n"
            f"This cannot be undone. Continue?"
        )
        if not messagebox.askyesno(APP_TITLE, confirm_text, icon="warning"):
            return

        self.is_writing = True
        self.write_button.config(state="disabled")
        self.cancel_button.config(state="normal")
        self.progress_bar["value"] = 0
        self.status_label.config(text="Preparing…")

        self.writer = ImageWriter(self.image_path, drive.path)
        self.worker_thread = threading.Thread(
            target=self._write_worker, args=(drive,), daemon=True
        )
        self.worker_thread.start()

    def _write_worker(self, drive: Drive) -> None:
        try:
            self.ui_queue.put(("status", "Unmounting partitions…"))
            warnings = unmount_drive(drive)
            if warnings:
                self.ui_queue.put(("unmount_warning", "\n".join(warnings)))

            self.ui_queue.put(("status", "Writing image to device…"))

            def on_write_progress(p: Progress) -> None:
                self.ui_queue.put(("write_progress", p))

            assert self.writer is not None
            self.writer.write(on_progress=on_write_progress)

            if self.verify_var.get():
                self.ui_queue.put(("status", "Verifying written data…"))

                def on_verify_progress(p: Progress) -> None:
                    self.ui_queue.put(("verify_progress", p))

                ok = self.writer.verify(on_progress=on_verify_progress)
                if ok:
                    self.ui_queue.put(("done", "Write complete and verified successfully."))
                else:
                    self.ui_queue.put(
                        ("error", "Write finished, but verification FAILED. "
                                  "The drive may be faulty or the write was corrupted.")
                    )
            else:
                self.ui_queue.put(("done", "Write complete."))

        except WriteCancelled:
            self.ui_queue.put(("cancelled", "Write cancelled."))
        except (WriteError, DeviceError) as exc:
            self.ui_queue.put(("error", str(exc)))
        except Exception as exc:  # noqa: BLE001 - surface unexpected errors to the UI
            self.ui_queue.put(("error", f"Unexpected error: {exc}"))

    def cancel_write(self) -> None:
        if self.writer:
            self.writer.cancel()
        self.status_label.config(text="Cancelling…")
        self.cancel_button.config(state="disabled")

    # ----------------------------------------------------------- UI pump

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.ui_queue.get_nowait()
                self._handle_event(kind, payload)
        except queue.Empty:
            pass
        self.after(150, self._poll_queue)

    def _handle_event(self, kind: str, payload) -> None:
        if kind == "status":
            self.status_label.config(text=payload)

        elif kind == "unmount_warning":
            messagebox.showwarning(
                APP_TITLE,
                "Some partitions could not be unmounted automatically:\n\n"
                f"{payload}\n\nThe write will still be attempted.",
            )

        elif kind in ("write_progress", "verify_progress"):
            p: Progress = payload
            self.progress_bar["value"] = p.fraction * 1000
            prefix = "Writing" if kind == "write_progress" else "Verifying"
            speed_txt = (
                f"{human_size(int(p.speed_bytes_per_sec))}/s"
                if p.speed_bytes_per_sec > 0
                else ""
            )
            eta_txt = ""
            if kind == "write_progress" and p.eta_sec is not None:
                eta_txt = f" — ETA {int(p.eta_sec)}s"
            self.status_label.config(
                text=(
                    f"{prefix}: {human_size(p.bytes_written)} / "
                    f"{human_size(p.total_bytes)}"
                    + (f"  ({speed_txt})" if speed_txt else "")
                    + eta_txt
                )
            )

        elif kind == "done":
            self._finish(success=True, message=payload)

        elif kind == "error":
            self._finish(success=False, message=payload)

        elif kind == "cancelled":
            self._finish(success=False, message=payload, cancelled=True)

    def _finish(self, success: bool, message: str, cancelled: bool = False) -> None:
        self.is_writing = False
        self.cancel_button.config(state="disabled")
        self.confirm_var.set("")
        self._update_write_button()
        self.status_label.config(text=message)
        if success:
            self.progress_bar["value"] = 1000
            messagebox.showinfo(APP_TITLE, message)
        elif cancelled:
            self.progress_bar["value"] = 0
            messagebox.showinfo(APP_TITLE, message)
        else:
            messagebox.showerror(APP_TITLE, message)


def main() -> None:
    if sys.platform != "linux":
        print("This tool is designed for Linux. Continuing anyway…", file=sys.stderr)
    app = FlashDriveCreatorApp()
    app.mainloop()


if __name__ == "__main__":
    main()
