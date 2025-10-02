# Meshtastic Firmware Upgrade Helper

## Quick Start (Recommended)

Make the script executable once:
```bash
chmod +x ./meshtastic_upgrade.py
```

Then run (alpha prerelease, ESP32-S3, include change-mode, explicit port & board):
```bash
./meshtastic_upgrade.py --firmware esp32s3 --change-mode --port /dev/ttyACM0 --alpha --board tlora-t3s3-v1
```


A Python-first, verification-friendly helper to download and flash **Meshtastic** firmware bundles.

- Fetches the **latest Stable** release by default, or **latest Alpha** with `--alpha`.
- Supports `--previous` to select the prior release within the chosen channel (Stable/Alpha).
- Downloads the correct **platform bundle** (e.g. `esp32s3`) from GitHub releases.
- Lists all `*-update.bin` images in the bundle.
- **Optional `--board`**: provide an exact board slug (e.g., `tlora-t3s3-v1`) to auto-select its image.
- Honors `ESPTOOL_PORT` and passes it through to `device-update.sh`.
- Checks for `esptool` and suggests `pipx install esptool` if missing.
- Optional `--change-mode` step for boards that require it.
- Supports `--dry-run` and `--verbose` for safe previews.

> **Who is this for?**  
> This tool is intended for **advanced users** who already know which **platform** (esp32, esp32s3, nrf52, rp2040) and **board slug** (e.g., `tlora-t3s3-v1`) they need. Meshtastic does **not** maintain a canonical “device name → firmware image” mapping page; the correct image names are visible inside each release bundle.

## Requirements

- Python 3.8+
- `esptool` in `PATH`  
  ```bash
  pipx install esptool
  # or
  python3 -m pip install --user esptool
  ```
- Serial port path (e.g., `/dev/ttyACM0` or `/dev/ttyUSB0`).

## Quick Start

```bash
# Choose your serial port:
python3 meshtastic_upgrade.py --firmware esp32s3 --port /dev/ttyACM0

# Or via environment:
export ESPTOOL_PORT=/dev/ttyACM0
python3 meshtastic_upgrade.py --firmware esp32s3
```

### Alpha / Previous / Tag

```bash
# Latest alpha (prerelease)
python3 meshtastic_upgrade.py --firmware esp32s3 --alpha --port /dev/ttyACM0

# Previous stable
python3 meshtastic_upgrade.py --firmware esp32s3 --previous --port /dev/ttyACM0

# Specific tag
python3 meshtastic_upgrade.py --firmware esp32s3 --tag v2.7.11.ee68575 --port /dev/ttyACM0
```

### Selecting the Correct Image

After download and extraction, the tool lists all `*-update.bin` images in the platform bundle.

- **If you know your board slug**, you can **skip the prompt**:
  ```bash
  python3 meshtastic_upgrade.py --firmware esp32s3 --board tlora-t3s3-v1 --port /dev/ttyACM0
  ```
  The tool will look for a filename like:
  `firmware-<board>-<version>-update.bin`, e.g. `firmware-tlora-t3s3-v1-2.7.11.ee68575-update.bin`.

- **Otherwise**, copy/paste the exact filename from the list when prompted.

> **Note:** There is no official centralized mapping between “device model names” and Meshtastic **board slugs**. Verify your specific board slug from the release assets or your hardware documentation.

### Change Mode (Optional)

Some boards require a change-mode step before flashing.

```bash
python3 meshtastic_upgrade.py --firmware esp32s3 --board tlora-t3s3-v1 --port /dev/ttyACM0 --change-mode
```

If `--change-mode` fails, the tool **aborts** (no flashing).

### BOOT/Download Mode

> For some boards (t3s3, etc), you may need to **hold the BOOT (or 0) button while powering on**.

The tool pauses before flashing so you can prepare the device.

### Dry Run / Verbose

```bash
python3 meshtastic_upgrade.py --firmware esp32s3 --dry-run --verbose
```

Prints the selected release, paths, and exact commands without flashing.

## Troubleshooting

- **`ESPTOOL_PORT is not set`**: use `--port /dev/ttyACM0` or `export ESPTOOL_PORT=/dev/ttyACM0`.
- **`esptool not found`**: `pipx install esptool`.
- **`device-update.sh` not found**: ensure you’re using an official release bundle.
- **Board not found** with `--board`: re-run without `--board` and select the image interactively.

## Safety & Idempotence

- Two-step flash with optional `--change-mode` first.
- No writes occur with `--dry-run`.
- Uses a cache directory (`.meshtastic_firmware_cache/`) to avoid repeated downloads.
