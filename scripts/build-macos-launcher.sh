#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SOURCE="${REPO_DIR}/tools/macos/Launcher.swift"
APP_NAME="Market Research Workflow.app"
EXECUTABLE_NAME="MarketResearchWorkflow"
DESKTOP_APP="${HOME}/Desktop/${APP_NAME}"
LOCAL_APP="${REPO_DIR}/tools/macos/${APP_NAME}"
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/mrw-launcher-build.XXXXXX")"
BUILD_APP="${WORK_DIR}/${APP_NAME}"
DESKTOP_TMP="${WORK_DIR}/desktop-${APP_NAME}"
LOCAL_BACKUP="${WORK_DIR}/local-previous-${APP_NAME}"
DESKTOP_BACKUP="${WORK_DIR}/desktop-previous-${APP_NAME}"

cleanup() {
  rm -rf "${WORK_DIR}"
}
trap cleanup EXIT INT TERM

if [[ ! -f "${SOURCE}" ]]; then
  echo "Missing launcher source: ${SOURCE}" >&2
  exit 1
fi

mkdir -p "${BUILD_APP}/Contents/MacOS" "${BUILD_APP}/Contents/Resources"

swiftc "${SOURCE}" \
  -parse-as-library \
  -o "${BUILD_APP}/Contents/MacOS/${EXECUTABLE_NAME}" \
  -framework SwiftUI \
  -framework AppKit

cat >"${BUILD_APP}/Contents/Info.plist" <<PLIST
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
  <string>1.1</string>
  <key>CFBundleVersion</key>
  <string>2</string>
  <key>LSMinimumSystemVersion</key>
  <string>13.0</string>
  <key>NSAppleEventsUsageDescription</key>
  <string>Open Terminal to run the selected project startup command.</string>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
PLIST

printf 'APPL????' >"${BUILD_APP}/Contents/PkgInfo"

codesign --force --sign - "${BUILD_APP}"
codesign --verify --deep --strict --verbose=2 "${BUILD_APP}"

replace_app() {
  local next="$1"
  local destination="$2"
  local backup="$3"

  if [[ -e "${destination}" ]]; then
    mv "${destination}" "${backup}"
  fi
  if mv "${next}" "${destination}"; then
    rm -rf "${backup}"
  else
    if [[ -e "${backup}" && ! -e "${destination}" ]]; then
      mv "${backup}" "${destination}" || true
    fi
    return 1
  fi
}

replace_app "${BUILD_APP}" "${LOCAL_APP}" "${LOCAL_BACKUP}"

mkdir -p "${WORK_DIR}/desktop-copy"
cp -R "${LOCAL_APP}" "${DESKTOP_TMP}"
codesign --verify --deep --strict --verbose=2 "${DESKTOP_TMP}"
replace_app "${DESKTOP_TMP}" "${DESKTOP_APP}" "${DESKTOP_BACKUP}"

echo "Built launcher:"
echo "  ${LOCAL_APP}"
echo "Copied to Desktop:"
echo "  ${DESKTOP_APP}"
