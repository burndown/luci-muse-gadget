#!/bin/sh
# Install the Muse gadget client and its LuCI page on OpenWrt / ImmortalWrt.
# Run on the router from a copy of this directory:
#   sh install.sh              install or upgrade
#   sh install.sh --uninstall  remove (keeps /etc/musegadget unless --purge)
#
# Environment overrides:
#   SDK_URL   tarball of facebookincubator/muse-gadget-sdk (default: pinned commit on GitHub)
#   SDK_DIR   use a local checkout of that repo instead of downloading
#   PIP_INDEX_URL  PyPI mirror for the websockets package

set -e

SDK_REF=74a5e2d7fc895f109f83a9a1dbed705dbcd8b1ff
SDK_URL="${SDK_URL:-https://codeload.github.com/facebookincubator/muse-gadget-sdk/tar.gz/$SDK_REF}"
WEBSOCKETS_VERSION=15.0.1
CODE=/usr/lib/musegadget
STATE=/etc/musegadget
HERE="$(cd "$(dirname "$0")" && pwd)"

say() { printf '==> %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" = 0 ] || die "run as root"
[ -f /etc/openwrt_release ] || die "this installer is for OpenWrt-based systems"

if [ "$1" = "--uninstall" ]; then
	say "Stopping and removing the service"
	[ -x /etc/init.d/musegadget ] && { /etc/init.d/musegadget stop || true; /etc/init.d/musegadget disable || true; }
	rm -rf "$CODE" /etc/init.d/musegadget /usr/libexec/rpcd/musegadget \
		/usr/share/rpcd/acl.d/luci-app-musegadget.json \
		/usr/share/luci/menu.d/luci-app-musegadget.json \
		/www/luci-static/resources/view/musegadget
	if [ "$2" = "--purge" ]; then
		rm -rf "$STATE" /etc/config/musegadget
		say "Removed $STATE and the config (pairing is gone)"
	else
		say "Kept $STATE and /etc/config/musegadget (use --uninstall --purge to delete)"
	fi
	/etc/init.d/rpcd restart || true
	rm -rf /tmp/luci-indexcache* /tmp/luci-modulecache
	exit 0
fi

if command -v apk >/dev/null 2>&1; then
	say "Installing packages with apk"
	apk update
	apk add python3 python3-cryptography python3-pip bash shadow-useradd curl
elif command -v opkg >/dev/null 2>&1; then
	say "Installing packages with opkg"
	opkg update
	opkg install python3 python3-cryptography python3-pip bash shadow-useradd curl
else
	die "neither apk nor opkg found"
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

if [ -n "$SDK_DIR" ]; then
	SRC="$SDK_DIR/linux/src/musegadget"
else
	say "Downloading the Muse Gadget SDK ($SDK_REF)"
	curl -fsSL "$SDK_URL" | tar xz -C "$TMP"
	SRC="$(echo "$TMP"/muse-gadget-sdk-*/linux/src/musegadget)"
fi
[ -f "$SRC/__init__.py" ] || die "SDK source not found at $SRC"

say "Installing the SDK into $CODE"
rm -rf "$CODE/musegadget"
mkdir -p "$CODE/lib"
cp -r "$SRC" "$CODE/musegadget"
find "$CODE/musegadget" -name __pycache__ -prune -exec rm -rf {} +
rm -rf "$CODE/musegadget_router"
cp -r "$HERE/files/usr/lib/musegadget/musegadget_router" "$CODE/musegadget_router"

say "Installing websockets $WEBSOCKETS_VERSION (the repo's package is too old for the SDK)"
pip install --quiet --no-cache-dir --upgrade --root-user-action=ignore \
	--target "$CODE/lib" "websockets==$WEBSOCKETS_VERSION"

say "Installing the service and the LuCI page"
[ -f /etc/config/musegadget ] || cp "$HERE/files/etc/config/musegadget" /etc/config/musegadget
cp "$HERE/files/etc/init.d/musegadget" /etc/init.d/musegadget
mkdir -p /usr/libexec/rpcd /usr/share/rpcd/acl.d /usr/share/luci/menu.d \
	/www/luci-static/resources/view/musegadget
cp "$HERE/files/usr/libexec/rpcd/musegadget" /usr/libexec/rpcd/musegadget
cp "$HERE/files/usr/share/rpcd/acl.d/luci-app-musegadget.json" /usr/share/rpcd/acl.d/
cp "$HERE/files/usr/share/luci/menu.d/luci-app-musegadget.json" /usr/share/luci/menu.d/
cp "$HERE/files/www/luci-static/resources/view/musegadget/main.js" \
	/www/luci-static/resources/view/musegadget/main.js
chmod 755 /etc/init.d/musegadget /usr/libexec/rpcd/musegadget
mkdir -p "$STATE" && chmod 700 "$STATE"

/etc/init.d/musegadget enable
/etc/init.d/rpcd restart
rm -rf /tmp/luci-indexcache* /tmp/luci-modulecache

PYTHONPATH="$CODE:$CODE/lib" python3 -c 'import cryptography, websockets.asyncio.client, musegadget' \
	|| die "python dependency check failed"

say "Done. Open LuCI > Services > Muse Gadget, import a pairing bundle (docs/pairing.md), then enable the service."
