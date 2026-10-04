#!/usr/bin/env bash
# MRW service: run the vendored Codex WebUI backend on 127.0.0.1:8172 via launchd.
# The backend (dist/main.js) spawns `codex app-server` over stdio itself.
# MRW nginx proxies /codex/ to this port (see main/frontend-modern/nginx.conf).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="$ROOT/launchd/com.mrw.codex-webui.plist.template"
RUNTIME_PLIST="$ROOT/.run/com.mrw.codex-webui.plist"
LABEL="com.mrw.codex-webui"
HOST_PLIST="$HOME/Library/LaunchAgents/com.mrw.codex-webui.plist"
PORT="${PORT:-8172}"
CODEX_VERSION="${CODEX_VERSION:-0.160.0}"
NODE_BIN="${NODE_BIN:-$(command -v node)}"
CODEX_BIN="${CODEX_BIN:-$ROOT/node_modules/.bin/codex}"
CODEX_HOME="${CODEX_HOME:-$HOME/.codex-mrw-agent}"
HOST_AUTH_FILE="${HOST_AUTH_FILE:-$HOME/.codex/auth.json}"
WEBUI_DB_PATH="${WEBUI_DB_PATH:-$ROOT/.tmp/codex-webui.sqlite}"
DOMAIN="gui/$(id -u)"

if [ ! -f "$TEMPLATE" ] || [ ! -f "$ROOT/dist/main.js" ]; then
  echo "[codex-webui] template or backend build missing; run 'pnpm run build' in $ROOT first" >&2
  exit 1
fi
if [ ! -x "$NODE_BIN" ] || [ ! -x "$CODEX_BIN" ]; then
  echo "[codex-webui] node or pinned Codex CLI is unavailable" >&2
  exit 1
fi

ACTUAL_CODEX_VERSION="$("$CODEX_BIN" --version)"
if [ "$ACTUAL_CODEX_VERSION" != "codex-cli $CODEX_VERSION" ]; then
  echo "[codex-webui] Codex version mismatch: expected $CODEX_VERSION, got $ACTUAL_CODEX_VERSION" >&2
  exit 1
fi
if [ ! -f "$HOST_AUTH_FILE" ]; then
  echo "[codex-webui] host OAuth file missing: $HOST_AUTH_FILE" >&2
  exit 1
fi

mkdir -p "$CODEX_HOME" "$ROOT/.tmp" "$ROOT/.run"
if [ -L "$CODEX_HOME/auth.json" ]; then
  EXISTING_AUTH_TARGET="$(readlink "$CODEX_HOME/auth.json")"
  if [ "$EXISTING_AUTH_TARGET" != "$HOST_AUTH_FILE" ]; then
    echo "[codex-webui] $CODEX_HOME/auth.json points to $EXISTING_AUTH_TARGET, expected $HOST_AUTH_FILE" >&2
    exit 1
  fi
elif [ -e "$CODEX_HOME/auth.json" ]; then
  echo "[codex-webui] refusing to replace non-symlink $CODEX_HOME/auth.json" >&2
  exit 1
else
  ln -s "$HOST_AUTH_FILE" "$CODEX_HOME/auth.json"
fi

# Render the complete launchd document in one pass. The API key is read only
# from this process environment or the existing host plist, never from argv.
MRW_WEBUI_TEMPLATE="$TEMPLATE" \
MRW_WEBUI_RUNTIME_PLIST="$RUNTIME_PLIST" \
MRW_WEBUI_HOST_PLIST="$HOST_PLIST" \
MRW_WEBUI_ROOT="$ROOT" \
MRW_WEBUI_NODE_BIN="$NODE_BIN" \
MRW_WEBUI_PORT="$PORT" \
MRW_WEBUI_API_KEY="${WEBUI_API_KEY:-}" \
MRW_WEBUI_DB_PATH="$WEBUI_DB_PATH" \
MRW_WEBUI_CODEX_BIN="$CODEX_BIN" \
MRW_WEBUI_CODEX_HOME="$CODEX_HOME" \
  /usr/bin/python3 - <<'PY'
import os
import plistlib
import tempfile
from pathlib import Path

template_path = Path(os.environ["MRW_WEBUI_TEMPLATE"])
runtime_path = Path(os.environ["MRW_WEBUI_RUNTIME_PLIST"])
host_plist_path = Path(os.environ["MRW_WEBUI_HOST_PLIST"])
root = os.environ["MRW_WEBUI_ROOT"]

api_key = os.environ.get("MRW_WEBUI_API_KEY", "")
if not api_key:
    try:
        with host_plist_path.open("rb") as host_file:
            host_plist = plistlib.load(host_file)
        api_key = host_plist.get("EnvironmentVariables", {}).get(
            "WEBUI_API_KEY", ""
        )
    except (OSError, plistlib.InvalidFileException) as error:
        raise SystemExit(
            "[codex-webui] WEBUI_API_KEY is required: set it or provide "
            f"the host LaunchAgent key ({error.__class__.__name__})"
        ) from None

if not isinstance(api_key, str) or not api_key:
    raise SystemExit(
        "[codex-webui] WEBUI_API_KEY is required: set it or provide the "
        "host LaunchAgent key"
    )

with template_path.open("rb") as template_file:
    plist = plistlib.load(template_file)

plist["ProgramArguments"] = [
    os.environ["MRW_WEBUI_NODE_BIN"],
    str(Path(root) / "dist/main.js"),
]
plist["WorkingDirectory"] = root
plist["EnvironmentVariables"].update(
    {
        "CODEX_BIN": os.environ["MRW_WEBUI_CODEX_BIN"],
        "CODEX_HOME": os.environ["MRW_WEBUI_CODEX_HOME"],
        "PORT": os.environ["MRW_WEBUI_PORT"],
        "WEBUI_API_KEY": api_key,
        "WEBUI_DB_PATH": os.environ["MRW_WEBUI_DB_PATH"],
    }
)

placeholders = ("__NODE_BIN__", "__WEBUI_ROOT__", "__HOME__", "__SET_BY_START_SH__")


def has_placeholder(value):
    if isinstance(value, str):
        return any(placeholder in value for placeholder in placeholders)
    if isinstance(value, list):
        return any(has_placeholder(item) for item in value)
    if isinstance(value, dict):
        return any(has_placeholder(item) for item in value.values())
    return False


if has_placeholder(plist):
    raise SystemExit("[codex-webui] launchd template placeholders remain")

render_path = None
try:
    with tempfile.NamedTemporaryFile(
        mode="wb", prefix=f".{runtime_path.name}.", dir=runtime_path.parent, delete=False
    ) as render_file:
        render_path = Path(render_file.name)
        plistlib.dump(plist, render_file, sort_keys=True)
    os.chmod(render_path, 0o600)
    os.replace(render_path, runtime_path)
    render_path = None
finally:
    if render_path is not None:
        render_path.unlink()
PY
plutil -lint "$RUNTIME_PLIST"

if [ "${MRW_WEBUI_RENDER_ONLY:-0}" = "1" ]; then
  echo "[codex-webui] rendered $RUNTIME_PLIST without changing launchd" >&2
  exit 0
fi

# Stop any existing instance, then load under launchd so it persists.
launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
# launchd can acknowledge bootout before removing the service registration.
for _ in $(seq 1 10); do
  if ! launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
BOOTSTRAP_EXIT=0
for attempt in $(seq 1 5); do
  if launchctl bootstrap "$DOMAIN" "$RUNTIME_PLIST"; then
    BOOTSTRAP_EXIT=0
    break
  else
    BOOTSTRAP_EXIT=$?
  fi
  # Only launchd's transient I/O failure is retryable here.
  if [ "$BOOTSTRAP_EXIT" != "5" ] || [ "$attempt" = "5" ]; then
    echo "[codex-webui] launchd bootstrap failed (exit $BOOTSTRAP_EXIT)" >&2
    exit "$BOOTSTRAP_EXIT"
  fi
  sleep 1
done

for _ in $(seq 1 30); do
  nc -z -G 1 127.0.0.1 "$PORT" >/dev/null 2>&1 && break
  sleep 1
done

if ! nc -z -G 1 127.0.0.1 "$PORT" >/dev/null 2>&1; then
  echo "[codex-webui] failed to start on $PORT" >&2
  launchctl print "$DOMAIN/$LABEL" 2>&1 | tail -n 12 >&2 || true
  exit 1
fi

echo "[codex-webui] ready: http://127.0.0.1:$PORT/ (MRW route /codex/) (launchd $LABEL)"
