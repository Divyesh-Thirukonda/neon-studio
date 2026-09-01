#!/usr/bin/env bash
#
# Builds "Neon Studio.app".
#
# The app is a SwiftPM package (see Package.swift) rather than a single swiftc
# invocation, which gives incremental builds, a testable NeonStudioKit library,
# and a self-contained test runner. This script compiles the package and then
# assembles the .app bundle around the produced binary, because SwiftPM has no
# notion of macOS app bundles.
#
# Usage:
#   ./build.sh              release build
#   ./build.sh --debug      debug build (much faster to iterate on)
#   ./build.sh --test       run the unit tests, then build
#
# Tests are a plain executable rather than an XCTest bundle, because XCTest
# ships with Xcode and this project builds with Command Line Tools alone.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
APP_DIR="$REPO_ROOT/mac/build/Neon Studio.app"
CONTENTS_DIR="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"

CONFIGURATION="release"
RUN_TESTS=0
for arg in "$@"; do
  case "$arg" in
    --debug) CONFIGURATION="debug" ;;
    --test) RUN_TESTS=1 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

if [ "$RUN_TESTS" -eq 1 ]; then
  echo "==> tests"
  swift run --package-path "$SCRIPT_DIR" NeonStudioTests
fi

echo "==> swift build ($CONFIGURATION)"
swift build --package-path "$SCRIPT_DIR" -c "$CONFIGURATION"
BINARY="$(swift build --package-path "$SCRIPT_DIR" -c "$CONFIGURATION" --show-bin-path)/NeonStudioApp"

if [ ! -x "$BINARY" ]; then
  echo "build produced no executable at $BINARY" >&2
  exit 1
fi

echo "==> assembling bundle"
rm -rf "$APP_DIR"
mkdir -p "$MACOS_DIR" "$RESOURCES_DIR"
cp "$BINARY" "$MACOS_DIR/NeonStudio"

# Seed content the app copies into ~/Library/Application Support on launch.
# __pycache__ is excluded so stale bytecode never ships.
mkdir -p "$RESOURCES_DIR/seed"
for seed_dir in factory data exports tools skills; do
  if [ -e "$REPO_ROOT/$seed_dir" ]; then
    rm -rf "$RESOURCES_DIR/seed/$seed_dir"
    mkdir -p "$RESOURCES_DIR/seed/$seed_dir"
    (cd "$REPO_ROOT/$seed_dir" && \
      find . -type d -name __pycache__ -prune -o -type f -print0 | \
      cpio -pdm0 --quiet "$RESOURCES_DIR/seed/$seed_dir" 2>/dev/null) || \
      cp -R "$REPO_ROOT/$seed_dir/." "$RESOURCES_DIR/seed/$seed_dir/"
    find "$RESOURCES_DIR/seed/$seed_dir" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
  fi
done

# App icon. Generated once by tools/make_icon.swift and committed, so an
# ordinary build needs no extra tooling.
if [ -f "$SCRIPT_DIR/Resources/AppIcon.icns" ]; then
  cp "$SCRIPT_DIR/Resources/AppIcon.icns" "$RESOURCES_DIR/AppIcon.icns"
fi

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
  <key>CFBundleDisplayName</key>
  <string>Neon Studio</string>
  <key>CFBundleIconFile</key>
  <string>AppIcon</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0.0</string>
  <key>CFBundleVersion</key>
  <string>1</string>
  <key>LSMinimumSystemVersion</key>
  <string>14.0</string>
  <key>LSApplicationCategoryType</key>
  <string>public.app-category.music</string>
  <key>NSHighResolutionCapable</key>
  <true/>
  <key>NSHumanReadableCopyright</key>
  <string>Neon Studio</string>
  <key>NSMicrophoneUsageDescription</key>
  <string>Neon Studio records audio takes straight into your project.</string>
  <key>NSSupportsSuddenTermination</key>
  <false/>
  <key>NSSupportsAutomaticTermination</key>
  <false/>

  <!-- Makes .neon.json a real document type: double-clicking one in the Finder
       opens it here, it can be dropped on the Dock icon, it appears in Open
       Recent, and the window gets a working proxy icon. -->
  <key>CFBundleDocumentTypes</key>
  <array>
    <dict>
      <key>CFBundleTypeName</key>
      <string>Neon Studio Project</string>
      <key>CFBundleTypeRole</key>
      <string>Editor</string>
      <key>LSHandlerRank</key>
      <string>Owner</string>
      <key>CFBundleTypeExtensions</key>
      <array>
        <string>neon.json</string>
      </array>
      <key>LSItemContentTypes</key>
      <array>
        <string>studio.neon.project</string>
      </array>
      <key>NSDocumentClass</key>
      <string>NeonDocument</string>
    </dict>
    <dict>
      <key>CFBundleTypeName</key>
      <string>JSON Project File</string>
      <key>CFBundleTypeRole</key>
      <string>Editor</string>
      <key>LSHandlerRank</key>
      <string>Alternate</string>
      <key>CFBundleTypeExtensions</key>
      <array>
        <string>json</string>
      </array>
      <key>LSItemContentTypes</key>
      <array>
        <string>public.json</string>
      </array>
      <key>NSDocumentClass</key>
      <string>NeonDocument</string>
    </dict>
  </array>

  <key>UTExportedTypeDeclarations</key>
  <array>
    <dict>
      <key>UTTypeIdentifier</key>
      <string>studio.neon.project</string>
      <key>UTTypeDescription</key>
      <string>Neon Studio Project</string>
      <key>UTTypeConformsTo</key>
      <array>
        <string>public.json</string>
        <string>public.composite-content</string>
      </array>
      <key>UTTypeTagSpecification</key>
      <dict>
        <key>public.filename-extension</key>
        <array>
          <string>neon.json</string>
        </array>
      </dict>
    </dict>
  </array>
</dict>
</plist>
PLIST

# An ad-hoc signature gives the bundle a stable identity, which is what macOS
# uses to remember the microphone permission. Unsigned builds re-prompt (or
# silently fail) every time the binary changes.
if command -v codesign >/dev/null 2>&1; then
  codesign --force --sign - --timestamp=none "$APP_DIR" >/dev/null 2>&1 || \
    echo "note: ad-hoc code signing failed; microphone permission may be re-requested each build" >&2
fi

# Let LaunchServices notice the document type registration right away.
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
if [ -x "$LSREGISTER" ]; then
  "$LSREGISTER" -f "$APP_DIR" >/dev/null 2>&1 || true
fi

echo "$APP_DIR"
