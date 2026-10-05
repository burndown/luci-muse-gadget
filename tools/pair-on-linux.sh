#!/bin/bash
# Pair a Muse gadget over Bluetooth on a Debian/Ubuntu/Raspberry Pi OS machine and
# print a one-line pairing bundle that you paste into the router's LuCI page.
#
#   bash pair-on-linux.sh                 asks for the SDK token
#   bash pair-on-linux.sh --keep-packages don't offer to remove the packages it installed
#
# Needs: a Bluetooth LE adapter, sudo, internet. Nothing is left running; the temporary
# state (including the token) is wiped at the end.

set -euo pipefail

SDK_REF=74a5e2d7fc895f109f83a9a1dbed705dbcd8b1ff
SDK_URL="https://codeload.github.com/facebookincubator/muse-gadget-sdk/tar.gz/$SDK_REF"
PACKAGES=(bluez python3 python3-dbus python3-gi python3-cryptography python3-websockets curl ca-certificates)
KEEP=0
[ "${1:-}" = "--keep-packages" ] && KEEP=1

say() { printf '==> %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

command -v apt-get >/dev/null || die "this script needs a Debian-based system (apt-get)"
sudo -v || die "sudo is required"

if [ -z "${MUSEGADGET_SDK_TOKEN:-}" ]; then
	read -r -s -p "SDK token from gadgets.muse.ai (mgst_...): " MUSEGADGET_SDK_TOKEN
	echo
fi
[[ "$MUSEGADGET_SDK_TOKEN" =~ ^mgst_[A-Za-z0-9_-]{43}$ ]] || die "that does not look like an SDK token"

WORK="$(mktemp -d)"
cleanup() { sudo shred -u "$WORK"/state/* 2>/dev/null || true; sudo rm -rf "$WORK"; }
trap cleanup EXIT

INSTALLED=()
for pkg in "${PACKAGES[@]}"; do
	dpkg -s "$pkg" >/dev/null 2>&1 || INSTALLED+=("$pkg")
done
if [ "${#INSTALLED[@]}" -gt 0 ]; then
	say "Installing: ${INSTALLED[*]}"
	sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq
	sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends "${INSTALLED[@]}"
fi

sudo systemctl start bluetooth
sleep 1
bluetoothctl list | grep -q Controller || die "no Bluetooth adapter found (try: bluetoothctl list, rfkill list)"
sudo bluetoothctl power on >/dev/null

say "Downloading the SDK"
curl -fsSL "$SDK_URL" | tar xz -C "$WORK"
SRC="$(echo "$WORK"/muse-gadget-sdk-*/linux/src)"
mkdir -p "$WORK/state" && chmod 700 "$WORK/state"
printf '%s' "$MUSEGADGET_SDK_TOKEN" > "$WORK/state/sdk_token"

say "Pairing window open for 10 minutes."
say "In the Muse app: Settings > Devices > turn on Developer mode, tap + and choose the MuseGadget device."
say "Do not connect to it with any other Bluetooth tool, that stops it from advertising."
sudo env PYTHONPATH="$SRC" MUSEGADGET_STATE_DIR="$WORK/state" python3 -m musegadget pair --timeout 600 \
	|| die "pairing did not complete"

say "Pairing done. Your bundle (paste the whole line into LuCI > Services > Muse Gadget):"
echo
sudo python3 - "$WORK/state" <<'PY'
import base64, json, sys, pathlib
d = pathlib.Path(sys.argv[1])
bundle = {
    "identity": json.loads((d / "identity.json").read_text()),
    "pairing": json.loads((d / "pairing.json").read_text()),
    "sdk_token": (d / "sdk_token").read_text().strip(),
}
print("MUSE1:" + base64.b64encode(json.dumps(bundle, separators=(",", ":")).encode()).decode())
PY
echo
say "The bundle holds your device credentials. Treat it like a password and do not run this device identity anywhere else at the same time."

if [ "$KEEP" = 0 ] && [ "${#INSTALLED[@]}" -gt 0 ]; then
	read -r -p "Remove the packages this script installed (${INSTALLED[*]})? [y/N] " ans
	if [[ "$ans" =~ ^[Yy]$ ]]; then
		sudo systemctl disable --now bluetooth || true
		sudo DEBIAN_FRONTEND=noninteractive apt-get purge -y -qq "${INSTALLED[@]}"
	fi
fi
