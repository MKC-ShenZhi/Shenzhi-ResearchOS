#!/bin/sh
set -eu
entry_file="${ADMIN_ENTRY_SECRET_FILE:-/run/secrets/admin_entry}"
entry_secret="$(cat "$entry_file")"
case "$entry_secret" in *[!0-9a-f]*|'') exit 1 ;; esac
[ "${#entry_secret}" -eq 64 ] || exit 1
sed "s/__ADMIN_ENTRY_SECRET__/$entry_secret/g" /opt/admin.conf.template > /tmp/admin-nginx.conf
chmod 600 /tmp/admin-nginx.conf
exec nginx -c /tmp/admin-nginx.conf -g 'daemon off;'
