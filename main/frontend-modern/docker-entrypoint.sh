#!/bin/sh
set -eu

upstream="${MRW_WEBUI_UPSTREAM:-host.docker.internal:8172}"
server_key="${MRW_SERVER_API_KEY:-}"

case "$upstream" in
  *[!A-Za-z0-9_.:-]*)
    echo "MRW_WEBUI_UPSTREAM contains unsupported characters" >&2
    exit 1
    ;;
esac
case "$server_key" in
  *[!A-Za-z0-9_-]*)
    echo "MRW_SERVER_API_KEY must contain only letters, digits, underscore or hyphen" >&2
    exit 1
    ;;
esac

awk -v upstream="$upstream" -v key="$server_key" '
  {
    gsub(/__MRW_WEBUI_UPSTREAM__/, upstream)
    gsub(/__MRW_SERVER_API_KEY__/, key)
    print
  }
' /etc/nginx/mrw-nginx.conf.template > /etc/nginx/conf.d/default.conf

exec /docker-entrypoint.sh "$@"
