#!/usr/bin/env bash
# ==============================================================================
# Build Script: Packages openmediavault-agent-station into a Debian (.deb) package
# Works on Debian/Ubuntu and macOS/BSD without requiring dpkg-deb installed.
# ==============================================================================

set -e

PACKAGE_NAME="openmediavault-agent-station"
VERSION="1.0.0"
ARCH="all"
DEB_FILE="${PACKAGE_NAME}_${VERSION}_${ARCH}.deb"
BUILD_DIR="./build-pkg"

echo "=========================================================="
echo "📦 Building $DEB_FILE for OpenMediaVault 6 & 7"
echo "=========================================================="

rm -rf "$BUILD_DIR" "$DEB_FILE"
mkdir -p "$BUILD_DIR/DEBIAN"
mkdir -p "$BUILD_DIR/usr/share/openmediavault/engined/rpc"
mkdir -p "$BUILD_DIR/usr/share/openmediavault/datamodels"
mkdir -p "$BUILD_DIR/usr/share/openmediavault/workbench/component.d"
mkdir -p "$BUILD_DIR/usr/share/openmediavault/workbench/navigation.d"
mkdir -p "$BUILD_DIR/usr/share/openmediavault/workbench/route.d"
mkdir -p "$BUILD_DIR/usr/share/openmediavault/workbench/dashboard.d"
mkdir -p "$BUILD_DIR/usr/share/openmediavault/agent-station/litellm"
mkdir -p "$BUILD_DIR/usr/share/openmediavault/agent-station/telegram-agent-bot"
mkdir -p "$BUILD_DIR/usr/sbin"

# Copy package control files
cp openmediavault-agent-station/debian/control "$BUILD_DIR/DEBIAN/"
cp openmediavault-agent-station/debian/postinst "$BUILD_DIR/DEBIAN/" 2>/dev/null || true
cp openmediavault-agent-station/debian/prerm "$BUILD_DIR/DEBIAN/" 2>/dev/null || true
cp openmediavault-agent-station/debian/postrm "$BUILD_DIR/DEBIAN/" 2>/dev/null || true
chmod 755 "$BUILD_DIR/DEBIAN/"* 2>/dev/null || true

# Copy OMV RPC backend & WebGUI assets
cp openmediavault-agent-station/usr/share/openmediavault/engined/rpc/* "$BUILD_DIR/usr/share/openmediavault/engined/rpc/" 2>/dev/null || true
cp openmediavault-agent-station/usr/share/openmediavault/datamodels/* "$BUILD_DIR/usr/share/openmediavault/datamodels/" 2>/dev/null || true
cp openmediavault-agent-station/usr/share/openmediavault/workbench/component.d/* "$BUILD_DIR/usr/share/openmediavault/workbench/component.d/" 2>/dev/null || true
cp openmediavault-agent-station/usr/share/openmediavault/workbench/navigation.d/* "$BUILD_DIR/usr/share/openmediavault/workbench/navigation.d/" 2>/dev/null || true
cp openmediavault-agent-station/usr/share/openmediavault/workbench/route.d/* "$BUILD_DIR/usr/share/openmediavault/workbench/route.d/" 2>/dev/null || true
cp openmediavault-agent-station/usr/share/openmediavault/workbench/dashboard.d/* "$BUILD_DIR/usr/share/openmediavault/workbench/dashboard.d/" 2>/dev/null || true

# Copy executable helpers
cp openmediavault-agent-station/usr/sbin/omv-agent-station "$BUILD_DIR/usr/sbin/"
chmod 755 "$BUILD_DIR/usr/sbin/omv-agent-station"
cp openmediavault-agent-station/usr/sbin/omv-agent-station "$BUILD_DIR/usr/sbin/" 2>/dev/null || true
chmod 755 "$BUILD_DIR/usr/sbin/omv-agent-station" 2>/dev/null || true

# Copy stack files (Docker compose, LiteLLM config, Telegram, Signal & Discord Bots)
cp docker-compose.yml "$BUILD_DIR/usr/share/openmediavault/agent-station/"
cp litellm/config.yaml "$BUILD_DIR/usr/share/openmediavault/agent-station/litellm/"
cp -r telegram-agent-bot/* "$BUILD_DIR/usr/share/openmediavault/agent-station/telegram-agent-bot/"
mkdir -p "$BUILD_DIR/usr/share/openmediavault/agent-station/signal-agent-bot"
cp -r signal-agent-bot/* "$BUILD_DIR/usr/share/openmediavault/agent-station/signal-agent-bot/"
mkdir -p "$BUILD_DIR/usr/share/openmediavault/agent-station/discord-agent-bot"
cp -r discord-agent-bot/* "$BUILD_DIR/usr/share/openmediavault/agent-station/discord-agent-bot/"

# Also provide backwards-compatible directory symlink /usr/share/openmediavault/ai-orchestrator
mkdir -p "$BUILD_DIR/usr/share/openmediavault/ai-orchestrator"
cp -r "$BUILD_DIR/usr/share/openmediavault/agent-station/"* "$BUILD_DIR/usr/share/openmediavault/ai-orchestrator/"

if command -v dpkg-deb >/dev/null 2>&1; then
    echo "🔨 Building with native dpkg-deb..."
    dpkg-deb --build --root-owner-group "$BUILD_DIR" "$DEB_FILE" 2>/dev/null || dpkg-deb --build "$BUILD_DIR" "$DEB_FILE"
else
    echo "🔨 Building with universal Python deb packager..."
    python3 - << PYEOF
import os
import tarfile
import struct
import io
import time

build_dir = "./build-pkg"
deb_filename = "$DEB_FILE"

# 1. Create control.tar.gz
control_buf = io.BytesIO()
with tarfile.open(fileobj=control_buf, mode="w:gz") as tar:
    for item in sorted(os.listdir(os.path.join(build_dir, "DEBIAN"))):
        path = os.path.join(build_dir, "DEBIAN", item)
        tar.add(path, arcname=item)
control_data = control_buf.getvalue()

# 2. Create data.tar.gz
data_buf = io.BytesIO()
with tarfile.open(fileobj=data_buf, mode="w:gz") as tar:
    for root, dirs, files in os.walk(build_dir):
        rel_root = os.path.relpath(root, build_dir)
        if rel_root == "DEBIAN" or rel_root.startswith("DEBIAN/"):
            continue
        if rel_root != ".":
            tar.add(root, arcname=rel_root, recursive=False)
        for f in sorted(files):
            file_path = os.path.join(root, f)
            arcname = os.path.relpath(file_path, build_dir)
            tar.add(file_path, arcname=arcname)
data_data = data_buf.getvalue()

# 3. Create debian-binary
binary_data = b"2.0\n"

# Helper for AR format entry
def ar_entry(name, data):
    # name(16), timestamp(12), uid(6), gid(6), mode(8), size(10), magic(2)
    header = f"{name:<16}{int(time.time()):<12}0     0     100644  {len(data):<10}\`\n".encode("latin1")
    # Pad to even boundary
    if len(data) % 2 != 0:
        data += b"\n"
    return header + data

with open(deb_filename, "wb") as deb:
    deb.write(b"!<arch>\n")
    deb.write(ar_entry("debian-binary", binary_data))
    deb.write(ar_entry("control.tar.gz", control_data))
    deb.write(ar_entry("data.tar.gz", data_data))

print(f"📦 Successfully created {deb_filename} ({os.path.getsize(deb_filename)} bytes)")
PYEOF
fi

rm -rf "$BUILD_DIR"

echo "✅ Package ready: $DEB_FILE"
echo "=========================================================="
echo "Installation on OpenMediaVault (OMV 6 / OMV 7):"
echo "  1. Upload $DEB_FILE to your OMV server"
echo "  2. Run: sudo dpkg -i $DEB_FILE"
echo "  3. Open your OMV WebGUI -> Services -> Agent Station"
echo "=========================================================="
