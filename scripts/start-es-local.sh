#!/usr/bin/env bash
# Start Elasticsearch locally via Homebrew (no Docker).
# Usage: ./scripts/start-es-local.sh [install|start|stop|status]

set -e
ACTION="${1:-start}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Ensure Homebrew in PATH
[[ -x /opt/homebrew/bin/brew ]] && eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null)" || true
[[ -x /usr/local/bin/brew ]] && eval "$(/usr/local/bin/brew shellenv 2>/dev/null)" || true

# Use OpenJDK on ARM (brew's bundled JDK may be x86)
export JAVA_HOME="${JAVA_HOME:-/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home}"
[[ -d "$JAVA_HOME" ]] || export JAVA_HOME="/usr/local/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home"

ES_FORMULA="elastic/tap/elasticsearch-full"

install_es() {
    echo "📦 Installing Elasticsearch via Homebrew..."
    brew tap elastic/tap 2>/dev/null || true
    brew install "$ES_FORMULA"
    echo "✅ Elasticsearch installed"
    if [[ "$(uname -m)" == "arm64" ]] && ! brew list openjdk@17 &>/dev/null 2>&1; then
        echo "📦 Installing OpenJDK 17 for ARM..."
        brew install openjdk@17
    fi
}

start_es() {
    if ! brew list --formula 2>/dev/null | grep -q elasticsearch; then
        install_es
    fi
    # Ensure xpack.ml.enabled: false (avoids ML native code failure on ARM)
    local cfg="/opt/homebrew/etc/elasticsearch/elasticsearch.yml"
    if [[ -f "$cfg" ]] && ! grep -q "xpack.ml.enabled" "$cfg" 2>/dev/null; then
        echo "xpack.ml.enabled: false" >> "$cfg"
    fi
    echo "🚀 Starting Elasticsearch (JAVA_HOME=$JAVA_HOME)..."
    brew services stop "$ES_FORMULA" 2>/dev/null || true
    nohup env JAVA_HOME="$JAVA_HOME" /opt/homebrew/opt/elasticsearch-full/bin/elasticsearch >>/opt/homebrew/var/log/elasticsearch.log 2>&1 &
    echo $! > /tmp/elasticsearch-local.pid
    echo "⏳ Waiting for ES on :9200..."
    for i in {1..30}; do
        if curl -sf http://localhost:9200 >/dev/null 2>&1; then
            echo "✅ Elasticsearch ready at http://localhost:9200"
            return 0
        fi
        sleep 2
    done
    echo "❌ ES did not become ready in 60s"
    return 1
}

stop_es() {
    brew services stop "$ES_FORMULA" 2>/dev/null || true
    if [[ -f /tmp/elasticsearch-local.pid ]]; then
        kill "$(cat /tmp/elasticsearch-local.pid)" 2>/dev/null || true
        rm -f /tmp/elasticsearch-local.pid
    fi
    pkill -f "elasticsearch" 2>/dev/null || true
    echo "✅ Elasticsearch stopped"
}

status_es() {
    if curl -sf http://localhost:9200 >/dev/null 2>&1; then
        echo "✅ Elasticsearch running at http://localhost:9200"
        curl -s http://localhost:9200 | head -5
    else
        echo "❌ Elasticsearch not responding on :9200"
        return 1
    fi
}

case "$ACTION" in
    install) install_es ;;
    start)   start_es ;;
    stop)   stop_es ;;
    status) status_es ;;
    *)
        echo "Usage: $0 {install|start|stop|status}"
        exit 2
        ;;
esac
