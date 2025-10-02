#!/usr/bin/env python3
"""
Meshtastic Firmware Upgrade Helper (interactive image selection + optional --board)

- Defaults to the latest *stable* release from https://github.com/meshtastic/firmware
- Use --alpha for the latest prerelease/alpha. Use --previous for previous in the chosen channel.
- Downloads the platform bundle ZIP (e.g., firmware-esp32s3-<ver>.zip)
- Lists all available "*-update.bin" images.
- If --board is provided (e.g., --board tlora-t3s3-v1), selects its matching image automatically.
  Otherwise, prompts to paste the exact filename.
- Honors ESPTOOL_PORT (from env) or --port to set/override it.
- Checks for esptool in PATH; suggests `pipx install esptool` if missing.
- Optional `--change-mode` step before flashing (required for some devices).
- Runs device-update.sh for the actual flash.

Examples
--------
# Make script executable once:
#   chmod +x ./meshtastic_upgrade.py
# Quick start (alpha, esp32s3, change-mode, explicit port & board):
#   ./meshtastic_upgrade.py --firmware esp32s3 --change-mode --port /dev/ttyACM0 --alpha --board tlora-t3s3-v1

# Latest stable, esp32s3, select board automatically
python3 meshtastic_upgrade.py --firmware esp32s3 --board tlora-t3s3-v1 --port /dev/ttyACM0

# Latest alpha (prerelease), interactive selection
python3 meshtastic_upgrade.py --firmware esp32s3 --alpha --port /dev/ttyACM0

# Previous stable
python3 meshtastic_upgrade.py --firmware esp32s3 --previous --port /dev/ttyUSB0

# Include change-mode step
python3 meshtastic_upgrade.py --firmware esp32s3 --board tlora-t3s3-v1 --port /dev/ttyACM0 --change-mode

# Dry-run (no flashing)
python3 meshtastic_upgrade.py --firmware esp32s3 --dry-run --verbose
"""
from __future__ import annotations
import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional
from urllib.request import urlopen, Request

GITHUB_API = "https://api.github.com/repos/meshtastic/firmware"
UA = "meshtastic-upgrade-script/1.4 (+https://github.com/meshtastic/firmware)"

SUPPORTED_PLATFORMS = {"esp32", "esp32s3", "nrf52", "rp2040"}

def http_json(url: str):
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
    with urlopen(req) as r:
        return json.load(r)

def http_download(url: str, dest: Path, chunk: int = 1024 * 1024):
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req) as r, open(dest, "wb") as f:
        while True:
            b = r.read(chunk)
            if not b:
                break
            f.write(b)

def find_release(previous: bool, alpha: bool, tag: Optional[str] = None) -> Dict:
    if tag:
        return http_json(f"{GITHUB_API}/releases/tags/{tag}")
    releases = http_json(f"{GITHUB_API}/releases?per_page=100")
    if alpha:
        candidates = [r for r in releases if r.get("prerelease") and not r.get("draft")]
    else:
        candidates = [r for r in releases if not r.get("prerelease") and not r.get("draft")]
    if not candidates:
        raise SystemExit("No suitable releases found on Meshtastic/firmware.")
    candidates.sort(key=lambda r: r.get("created_at") or r.get("published_at"), reverse=True)
    idx = 1 if previous else 0
    if idx >= len(candidates):
        raise SystemExit("Requested release (previous) not found (not enough releases).")
    return candidates[idx]

def pick_asset_for_platform(release: Dict, platform: str) -> Dict:
    assets = release.get("assets", [])
    pat = re.compile(rf"^firmware-{re.escape(platform)}-.*\.zip$", re.IGNORECASE)
    matches = [a for a in assets if pat.match(a.get("name",""))]
    if not matches:
        raise SystemExit(f"No firmware bundle found for platform '{platform}' in release {release.get('tag_name')}")
    matches.sort(key=lambda a: a.get("size", 0), reverse=True)  # prefer largest
    return matches[0]

def ensure_esptool_in_path() -> Optional[str]:
    for name in ("esptool.py", "esptool"):
        p = shutil.which(name)
        if p:
            return p
    return None

def chmod_plus_x(path: Path):
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

def find_device_update_sh(extract_dir: Path) -> Path:
    candidate = extract_dir / "device-update.sh"
    if candidate.exists():
        return candidate
    for p in extract_dir.rglob("device-update.sh"):
        return p
    raise SystemExit("device-update.sh not found in extracted firmware bundle.")

def list_update_bins(extract_dir: Path) -> List[Path]:
    bins = sorted(extract_dir.rglob("*-update.bin"))
    if not bins:
        raise SystemExit("No '*-update.bin' images were found inside the firmware bundle.")
    return bins

def resolve_board_image(images: List[Path], board: str, tag_name: str) -> Optional[Path]:
    # Try strict match with tag version first: firmware-<board>-<version>-update.bin
    version = (tag_name or "").lstrip("v")
    strict = re.compile(rf"^firmware-{re.escape(board)}-{re.escape(version)}-update\.bin$", re.IGNORECASE) if version else None
    if strict:
        for p in images:
            if strict.match(p.name):
                return p
    # Fallback: any update bin that starts with firmware-<board>- and ends with -update.bin
    loose = re.compile(rf"^firmware-{re.escape(board)}-.*-update\.bin$", re.IGNORECASE)
    candidates = [p for p in images if loose.match(p.name)]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        # If multiple (unusual within a single bundle), prefer one containing the version string if present
        if version:
            for p in candidates:
                if version in p.name:
                    return p
        # otherwise return None and let interactive prompt handle it
    return None

def run(cmd: List[str], env: dict, dry_run: bool, verbose: bool) -> int:
    if verbose or dry_run:
        print("+", " ".join(cmd))
    if dry_run:
        return 0
    proc = subprocess.run(cmd, env=env, check=False)
    return proc.returncode

def main():
    parser = argparse.ArgumentParser(
        description="Download and flash Meshtastic firmware using device-update.sh (honors ESPTOOL_PORT).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--firmware", required=True, choices=sorted(SUPPORTED_PLATFORMS),
                        help="Target platform bundle to download (e.g., esp32s3).")
    parser.add_argument("--board", help="Exact board slug (e.g., tlora-t3s3-v1). If provided, auto-select the matching image.")
    parser.add_argument("--port", help="Serial port for flashing; sets/overrides ESPTOOL_PORT (e.g., /dev/ttyACM0).")
    parser.add_argument("--change-mode", action="store_true",
                        help="Run the change-mode prep step before flashing. If this step fails, the script will exit.")
    parser.add_argument("--previous", action="store_true", help="Use previous release instead of latest in the chosen channel.")
    parser.add_argument("--alpha", action="store_true", help="Use latest alpha (prerelease) instead of stable.")
    parser.add_argument("--tag", help="Override and use a specific release tag, e.g., v2.7.11.ee68575")
    parser.add_argument("--output-dir", default="./.meshtastic_firmware_cache",
                        help="Where to download/extract the firmware bundle.")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without executing flashing steps.")
    parser.add_argument("--yes", action="store_true", help="Do not prompt before flashing (still prompts to select image if --board not used).")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging.")
    args = parser.parse_args()

    platform = args.firmware.lower()

    # Set / validate ESPTOOL_PORT
    if args.port:
        os.environ["ESPTOOL_PORT"] = args.port
    esptool_port = os.environ.get("ESPTOOL_PORT")
    if not esptool_port:
        print("ERROR: ESPTOOL_PORT is not set. Use --port or set the env var.", file=sys.stderr)
        print("  e.g., --port /dev/ttyACM0  or  export ESPTOOL_PORT=/dev/ttyACM0", file=sys.stderr)
        sys.exit(2)

    # esptool presence
    esptool_path = ensure_esptool_in_path()
    if not esptool_path:
        print("ERROR: 'esptool.py' (or 'esptool') was not found in your PATH.", file=sys.stderr)
        print("Install with pipx (recommended):", file=sys.stderr)
        print("  pipx install esptool", file=sys.stderr)
        print("Or with pip (user):", file=sys.stderr)
        print("  python3 -m pip install --user esptool", file=sys.stderr)
        sys.exit(3)

    # Find release
    release = find_release(previous=args.previous, alpha=args.alpha, tag=args.tag)
    tag_name = release.get("tag_name")
    prerelease = release.get("prerelease", False)
    channel = "Alpha" if prerelease else "Stable"
    asset = pick_asset_for_platform(release, platform)
    asset_name = asset.get("name")
    asset_url = asset.get("browser_download_url")

    outdir = Path(args.output_dir).resolve() / asset_name.replace(".zip","")
    zip_path = outdir.with_suffix(".zip")

    if args.verbose:
        print(f"Selected release: {tag_name} [{channel}] (previous={args.previous})")
        print(f"Asset: {asset_name}")
        print(f"Download to: {zip_path}")
        print(f"Extract to: {outdir}")

    # Download
    if not zip_path.exists():
        if args.verbose: print(f"Downloading {asset_url} ...")
        http_download(asset_url, zip_path)
    else:
        if args.verbose: print(f"Using cached {zip_path}")

    # Extract
    if not outdir.exists():
        if args.verbose: print(f"Extracting to {outdir} ...")
        outdir.mkdir(parents=True, exist_ok=True)
        import zipfile
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(outdir)
    else:
        if args.verbose: print(f"Using existing extracted directory {outdir}")

    # Locate script & images
    device_update = find_device_update_sh(outdir)
    mode = device_update.stat().st_mode
    if not (mode & stat.S_IXUSR):
        device_update.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    images = list_update_bins(outdir)

    chosen_path = None
    if args.board:
        chosen_path = resolve_board_image(images, args.board.strip(), tag_name or "")
        if chosen_path is None:
            print(f"Could not automatically find image for board '{args.board}'.", file=sys.stderr)

    if chosen_path is None:
        print("\nAvailable update binaries in this bundle:\n")
        for i, p in enumerate(images, 1):
            print(f"  {i:2d}. {p.name}")
        # Prompt for exact filename
        while True:
            user_in = input("\nEnter the EXACT filename to flash (copy/paste from list): ").strip()
            if not user_in:
                print("Please enter a filename.")
                continue
            matches = [p for p in images if p.name == user_in]
            if len(matches) == 1:
                chosen_path = matches[0]
                break
            print("No exact match. Please copy/paste the filename exactly as shown.")

    print(f"\nReady to flash Meshtastic {tag_name} [{channel}] for platform {platform}.")
    print(f"- Bundle: {asset_name}")
    print(f"- Script: {device_update}")
    print(f"- Image : {chosen_path.name}")
    print(f"- Port  : {esptool_port}\n")

    if not args.yes:
        print(">>> ACTION REQUIRED: Put your device in BOOT/Download mode if needed.")
        print("For some boards (t3s3, etc), you may need to hold the BOOT (or 0) button while powering on.")
        input("Press Enter to continue when the device is ready...")

    env = os.environ.copy()
    env["ESPTOOL_PORT"] = esptool_port

    # Optional Step 1: change mode
    if args.change_mode:
        print("Step 1/2: Preparing flash (change mode)...")
        rc1 = run([str(device_update), "-f", str(chosen_path), "--change-mode"],
                  env=env, dry_run=args.dry_run, verbose=args.verbose)
        if rc1 != 0:
            print(f"❌ change-mode step failed with exit code {rc1}. Aborting.", file=sys.stderr)
            sys.exit(rc1)
    else:
        if args.verbose:
            print("Skipping change-mode step (not requested).")

    # Step 2: actual flash (only if prior steps succeeded)
    print("Step 2/2: Flashing firmware...")
    rc2 = run([str(device_update), "-f", str(chosen_path)],
              env=env, dry_run=args.dry_run, verbose=args.verbose)

    if rc2 == 0:
        print("✅ Flash completed successfully.")
    else:
        print(f"❌ Flash failed with exit code {rc2}. See the output above.", file=sys.stderr)
        sys.exit(rc2)

if __name__ == "__main__":
    main()
