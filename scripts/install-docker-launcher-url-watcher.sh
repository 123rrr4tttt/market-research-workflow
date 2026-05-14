#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
WATCHER_SCRIPT="${ROOT_DIR}/scripts/docker-launcher-url-watcher.sh"
PLIST_DIR="${HOME}/Library/LaunchAgents"
PLIST_PATH="${PLIST_DIR}/com.market-research-workflow.docker-launcher-url-watcher.plist"
LOG_DIR="${HOME}/Library/Logs/MarketResearchWorkflow"

if [[ "${OSTYPE:-}" != darwin* ]]; then
  echo "This installer is for macOS LaunchAgents only." >&2
  exit 1
fi

chmod +x "$WATCHER_SCRIPT"
mkdir -p "$PLIST_DIR" "$LOG_DIR"

cat >"$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.market-research-workflow.docker-launcher-url-watcher</string>
  <key>ProgramArguments</key>
  <array>
    <string>${WATCHER_SCRIPT}</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>LAUNCHER_PROJECT_NAME</key>
    <string>mrw-launcher</string>
    <key>LAUNCHER_SERVICE_NAME</key>
    <string>launcher-ui</string>
    <key>LAUNCHER_URL</key>
    <string>http://127.0.0.1:5176</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/docker-launcher-url-watcher.out.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/docker-launcher-url-watcher.err.log</string>
</dict>
</plist>
PLIST

launchctl bootout "gui/$(id -u)" "$PLIST_PATH" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"
launchctl kickstart -k "gui/$(id -u)/com.market-research-workflow.docker-launcher-url-watcher"

echo "Installed Docker Desktop URL watcher:"
echo "  ${PLIST_PATH}"
echo "Logs:"
echo "  ${LOG_DIR}/docker-launcher-url-watcher.out.log"
echo "  ${LOG_DIR}/docker-launcher-url-watcher.err.log"
