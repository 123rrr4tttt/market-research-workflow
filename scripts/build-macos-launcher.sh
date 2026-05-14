#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SOURCE="${REPO_DIR}/tools/macos/Launcher.swift"
APP_NAME="Market Research Workflow.app"
EXECUTABLE_NAME="MarketResearchWorkflow"
DESKTOP_APP="${HOME}/Desktop/${APP_NAME}"
LOCAL_APP="${REPO_DIR}/tools/macos/${APP_NAME}"

if [[ ! -f "${SOURCE}" ]]; then
  echo "Missing launcher source: ${SOURCE}" >&2
  exit 1
fi

mkdir -p "${LOCAL_APP}/Contents/MacOS" "${LOCAL_APP}/Contents/Resources"
rm -rf "${LOCAL_APP}" "${DESKTOP_APP}"
mkdir -p "${LOCAL_APP}/Contents/MacOS" "${LOCAL_APP}/Contents/Resources"

swiftc "${SOURCE}" \
  -parse-as-library \
  -o "${LOCAL_APP}/Contents/MacOS/${EXECUTABLE_NAME}" \
  -framework SwiftUI \
  -framework AppKit

cat >"${LOCAL_APP}/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key>
  <string>en</string>
  <key>CFBundleExecutable</key>
  <string>${EXECUTABLE_NAME}</string>
  <key>CFBundleIdentifier</key>
  <string>local.market-research.workflow.launcher</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleName</key>
  <string>Market Research Workflow</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0</string>
  <key>CFBundleVersion</key>
  <string>1</string>
  <key>LSMinimumSystemVersion</key>
  <string>13.0</string>
  <key>NSAppleEventsUsageDescription</key>
  <string>Open Terminal to run the selected project startup command.</string>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
PLIST

printf 'APPL????' >"${LOCAL_APP}/Contents/PkgInfo"

codesign --force --sign - "${LOCAL_APP}" >/dev/null 2>&1 || true
cp -R "${LOCAL_APP}" "${DESKTOP_APP}"

echo "Built launcher:"
echo "  ${LOCAL_APP}"
echo "Copied to Desktop:"
echo "  ${DESKTOP_APP}"
