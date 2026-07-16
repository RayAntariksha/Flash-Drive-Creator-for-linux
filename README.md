# Flash Drive Creator

A simple, working, Rufus-like tool for writing ISO/IMG files to USB flash
drives on Linux. This is a from-scratch reimplementation inspired by
[RayAntariksha/Flash-Drive-Creator-for-linux](https://github.com/RayAntariksha/Flash-Drive-Creator-for-linux),
built to actually run out of the box with a clear, hard-to-misuse GUI.

![status](https://img.shields.io/badge/status-working-brightgreen)

## Features

- **Simple 3-step GUI**: pick an image, pick a drive, confirm and write.
- **Only shows removable/USB drives** — internal disks never appear in the
  list, so you can't accidentally select your system disk.
- **Requires typing "ERASE"** before the write button is enabled, on top of
  a confirmation dialog naming the exact drive and image.
- **Live progress**, transfer speed, and ETA while writing.
- **Optional SHA-256 verification** after writing, to confirm the drive
  actually matches the source image.
- **Auto-unmounts** any mounted partitions on the target drive first.
- **Cancel button** that stops the write cleanly.
- Pure Python standard library (Tkinter) — no pip packages required.

## How it works

Under the hood this uses the same tools Linux already ships with:

- `lsblk` to enumerate removable/USB block devices
- `udisksctl` / `umount` to unmount partitions before writing
- `dd` (run via `pkexec` or `sudo`) to perform the actual raw write, with
  `status=progress` parsed live to drive the progress bar
- Python's `hashlib` to verify the write against the source image

## Requirements

- Linux with `python3` and `python3-tk`
- `lsblk`, `dd`, `umount` (from `util-linux` / `coreutils`, present on
  virtually every distro)
- `pkexec` (polkit) or `sudo`, to grant permission to write to the device

## Install

```bash
git clone <this-repo>
cd flash-drive-creator
./install.sh
```

`install.sh` checks for missing dependencies (and tells you the exact
package to install per distro), installs a `flash-drive-creator` command
into `~/.local/bin`, and adds an entry to your application menu.

## Run without installing

```bash
python3 flash_drive_creator.py
```

## Usage

1. Click **Browse…** and select an `.iso` or `.img` file.
2. Choose the target USB drive from the dropdown (click **Refresh** if it
   was just plugged in). Only removable/USB drives are listed.
3. Type `ERASE` into the confirmation box, review the warning dialog
   carefully (it names the exact drive and image), and click
   **Write to drive**.
4. Watch the progress bar. When finished, verification (if enabled) will
   run automatically.

## Safety notes

⚠️ **Writing an image to a drive erases everything on it.** Double-check
the drive path, size, and model shown in the dropdown before confirming.
This tool intentionally hides non-removable disks, but always verify you
have the right device — especially if you have multiple USB drives
plugged in.

The authors and contributors of this project are not responsible for any
data loss. Always back up important data before using disk-imaging tools.

## Project layout

```
flash-drive-creator/
├── flash_drive_creator.py   # GUI entry point (Tkinter)
├── core/
│   ├── devices.py           # drive detection & unmounting (lsblk/udisks)
│   └── writer.py            # image writing + verification (dd/hashlib)
├── install.sh                # dependency check + desktop launcher setup
├── flash-drive-creator.desktop
└── README.md
```

## License

MIT — do whatever you like with it, no warranty.
