#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

source .venv/bin/activate
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy

pyinstaller --noconfirm WoWFishing-macOS.spec

APP_PATH="dist/WoWFishingMac.app"
ZIP_PATH="dist/WoWFishingMac.zip"

if [[ -d "$APP_PATH" ]]; then
  rm -f "$ZIP_PATH"
  # 使用 ditto 打包 .app，可保留 macOS bundle 所需元数据。
  ditto -c -k --sequesterRsrc --keepParent "$APP_PATH" "$ZIP_PATH"
fi

APP_PLIST="dist/WoWFishingMac.app/Contents/Info.plist"
if [[ -f "$APP_PLIST" ]]; then
  VERSION_SHORT=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$APP_PLIST")
  VERSION_BUILD=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$APP_PLIST")
  echo "Build done: dist/WoWFishingMac.app"
  echo "Zip done: ${ZIP_PATH}"
  echo "Version: ${VERSION_SHORT} (${VERSION_BUILD})"
else
  echo "Build done, but Info.plist not found at: $APP_PLIST"
fi
