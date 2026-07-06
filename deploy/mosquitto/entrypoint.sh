#!/bin/sh
# Mosquitto entrypoint with auth-file self-reload.
#
# The Django app rewrites /mosquitto/auth/{passwd,acl} whenever a Source
# Authority is saved (post_save signal → Celery task). Mosquitto does not
# re-read those files on its own, so this entrypoint watches them and sends
# the broker a SIGHUP when they change.
set -e

AUTH_DIR=/mosquitto/auth

# Ensure the files exist so the broker can start before the first sync
touch "$AUTH_DIR/passwd" "$AUTH_DIR/acl"

mosquitto -c /mosquitto/config/mosquitto.conf &
MOSQ_PID=$!

checksum() {
  md5sum "$AUTH_DIR/passwd" "$AUTH_DIR/acl" 2>/dev/null
}

last=$(checksum)
(
  while kill -0 "$MOSQ_PID" 2>/dev/null; do
    sleep 3
    cur=$(checksum)
    if [ "$cur" != "$last" ]; then
      echo "mosquitto-entrypoint: auth files changed — reloading broker"
      kill -HUP "$MOSQ_PID" 2>/dev/null || true
      last="$cur"
    fi
  done
) &

# Forward termination to the broker
trap 'kill -TERM "$MOSQ_PID" 2>/dev/null' TERM INT
wait "$MOSQ_PID"
