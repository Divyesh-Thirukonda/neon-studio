#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
APP_DIR="$REPO_ROOT/mac/build/Neon Studio.app"
CONTENTS_DIR="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"

rm -rf "$APP_DIR"
mkdir -p "$MACOS_DIR" "$RESOURCES_DIR"

swiftc \
  -O \
  -framework AppKit \
  -framework AVFoundation \
  "$SCRIPT_DIR/Sources/main.swift" \
  -o "$MACOS_DIR/NeonStudio"

mkdir -p "$RESOURCES_DIR/seed"
for seed_dir in public data exports tools; do
  if [ -e "$REPO_ROOT/$seed_dir" ]; then
    rm -rf "$RESOURCES_DIR/seed/$seed_dir"
    cp -R "$REPO_ROOT/$seed_dir" "$RESOURCES_DIR/seed/$seed_dir"
  fi
done

cat > "$CONTENTS_DIR/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key>
  <string>en</string>
  <key>CFBundleExecutable</key>
  <string>NeonStudio</string>
  <key>CFBundleIdentifier</key>
  <string>local.neonstudio.native</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleName</key>
  <string>Neon Studio</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>0.1.0</string>
  <key>CFBundleVersion</key>
  <string>1</string>
  <key>LSMinimumSystemVersion</key>
  <string>14.0</string>
  <key>NSHighResolutionCapable</key>
  <true/>
  <key>NSMicrophoneUsageDescription</key>
  <string>Neon Studio records audio takes into local project files.</string>
</dict>
</plist>
PLIST

echo "$APP_DIR"
