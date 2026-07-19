#!/usr/bin/with-contenv bash
# Happier startup script
# Supports two roles controlled by the CONTAINER_ROLE env var:
#   server  — starts the relay server + web UI (default)
#   agent   — configures the CLI/daemon to connect to a remote relay server
#
# Authentication (checked in priority order):
#   1. Existing access.key → starts the daemon immediately
#   2. HAPPIER_ACCESS_KEY  → writes the pre-provisioned key, starts daemon
#   3. Default             → submits a pairing request to the server, prints
#                            the connect URL, and waits for approval (one-time)

set -euo pipefail

ROLE="${CONTAINER_ROLE:-server}"

log() {
  if [[ "${LOGGING:-}" == "verbose" ]] || [[ "$*" == *"ERROR"* ]] || [[ "$*" == *"WARNING"* ]]; then
    echo "$*"
  fi
}

# Derive a filesystem-safe server ID from HAPPIER_SERVER_URL
get_server_id() {
  local url="$1"
  echo "$url" | sed -E 's/^(http|https):\/\///' | sed 's/\/$//' \
    | sed 's/[^a-zA-Z0-9._-]/-/g' | sed -E 's/^-+|-+$//g' | tr '[:upper:]' '[:lower:]'
}

# Locate the existing access key for a given server URL
find_access_key() {
  local server_url="$1"
  local sid
  sid=$(get_server_id "$server_url")
  local key_file="$HOME/.happier/servers/$sid/access.key"
  if [ -f "$key_file" ]; then
    echo "$key_file"
    return 0
  fi
  # Also search broadly as a fallback
  local found
  found=$(find "$HOME/.happier/servers" -name "access.key" -type f 2>/dev/null | head -1)
  if [ -n "$found" ]; then
    echo "$found"
    return 0
  fi
  return 1
}

# Write a pre-provisioned access key
write_access_key() {
  local server_url="$1"
  local key_json="$2"
  local sid
  sid=$(get_server_id "$server_url")
  local key_dir="$HOME/.happier/servers/$sid"
  mkdir -p "$key_dir"
  echo "$key_json" > "$key_dir/access.key"
  chmod 600 "$key_dir/access.key"
  echo "$key_dir/access.key"
}

# Log the access key so the user can copy it for future HAPPIER_ACCESS_KEY use
log_access_key() {
  local server_url="$1"
  local key_file
  key_file=$(find_access_key "$server_url" || true)
  if [ -n "$key_file" ] && [ -f "$key_file" ]; then
    echo ""
    echo "============================================================"
    echo "  Save this access key for future fully-automated setups:"
    echo "============================================================"
    echo ""
    echo "  HAPPIER_ACCESS_KEY='$(cat "$key_file")'"
    echo ""
    echo "Set that environment variable on future containers to skip"
    echo "the pairing step entirely."
    echo "============================================================"
    echo ""
  fi
}

# Submit a pairing request, print the connect URL, and wait for approval.
# Uses the headless-friendly auth request/wait flow so the URL is captured
# and displayed prominently rather than buried in the login command output.
do_pairing() {
  local server_url="$1"
  local no_open="${2:-false}"

  echo ""
  echo "============================================================"
  echo "  Happier — Pairing Required"
  echo "============================================================"
  echo ""
  echo "No existing credentials found for $server_url."
  echo "Submitting a pairing request..."
  echo ""

  # Submit the request and capture JSON output
  AUTH_JSON=$(happier --server-url "$server_url" auth request --json 2>/dev/null || true)

  # Extract fields from the JSON response
  PUBLIC_KEY=$(echo "$AUTH_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('publicKey',''))" 2>/dev/null || true)
  WEB_URL=$(echo "$AUTH_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('links',{}).get('webUrl',''))" 2>/dev/null || true)
  MOBILE_URL=$(echo "$AUTH_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('links',{}).get('mobileUrl',''))" 2>/dev/null || true)

  if [ -z "$PUBLIC_KEY" ] || [ -z "$WEB_URL" ]; then
    echo "ERROR: Failed to create pairing request. Falling back to standard login..."
    # Fallback: just run auth login and let it print the URL natively
    open_flag=""
    if [ "$no_open" = "true" ]; then
      open_flag=" --no-open"
    fi
    happier --server-url "$server_url" auth login --method web${open_flag} || true
  else
    echo "Pairing request submitted!"
    echo ""
    echo "Open this URL in your browser to approve:"
    echo ""
    echo "  ${WEB_URL}"
    echo ""
    if [ -n "$MOBILE_URL" ]; then
      echo "Or use the mobile app:"
      echo "  ${MOBILE_URL}"
      echo ""
    fi
    echo "============================================================"
    echo ""

    # Wait for approval — this blocks until the pairing is approved
    # --persist saves the server URL as the active profile
    happier --server-url "$server_url" auth wait \
      --public-key "$PUBLIC_KEY" --json --persist 2>&1 || true
  fi
}

case "$ROLE" in
  server)
    log "=== Happier: SERVER mode ==="

    # --- Generate self-signed TLS cert for HTTPS access ---
    # Needed because crypto.subtle (Web Crypto API) is only available in
    # secure contexts (HTTPS or localhost). The TLS tunnel wraps port 3005
    # so the browser treats it as a secure context.
    CERT_DIR="/app/.happy/server-light"
    if [ ! -f "$CERT_DIR/tunnel.key" ] || [ ! -f "$CERT_DIR/tunnel.crt" ]; then
      log "Generating self-signed TLS certificate for happier HTTPS tunnel..."
      mkdir -p "$CERT_DIR"
      openssl req -x509 -newkey rsa:2048 -keyout "$CERT_DIR/tunnel.key" \
        -out "$CERT_DIR/tunnel.crt" -days 3650 -nodes \
        -subj "/CN=happier" 2>/dev/null || \
        log "WARNING: Failed to generate TLS certificate — HTTPS tunnel will not start"
      log "Self-signed certificate generated"
    fi

    # The TLS tunnel uses a self-signed cert, so disable TLS verification
    # for all processes launched by this script (daemon, socket.io polling, etc.)
    export NODE_TLS_REJECT_UNAUTHORIZED=0

    # --- Patch xmlhttprequest-ssl to respect NODE_TLS_REJECT_UNAUTHORIZED ---
    XHR_FILE="/usr/lib/node_modules/@happier-dev/cli/node_modules/xmlhttprequest-ssl/lib/XMLHttpRequest.js"
    if [ -f "$XHR_FILE" ]; then
      if grep -q "NODE_TLS_REJECT_UNAUTHORIZED" "$XHR_FILE" 2>/dev/null; then
        log "xmlhttprequest-ssl already patched"
      else
        log "Patching xmlhttprequest-ssl to respect NODE_TLS_REJECT_UNAUTHORIZED=0..."
        sed -i \
          's/rejectUnauthorized === false ? false : true/rejectUnauthorized === false ? false : (process.env.NODE_TLS_REJECT_UNAUTHORIZED === '\''0'\'' ? false : true)/g' \
          "$XHR_FILE"
        log "xmlhttprequest-ssl patched successfully"
      fi
    else
      log "WARNING: xmlhttprequest-ssl not found at $XHR_FILE — daemon machine sync may not work"
    fi

    # Run happier-server on an internal port; the TLS tunnel forwards to it.
    export PORT=3006
    export HAPPIER_SQLITE_AUTO_MIGRATE=true
    DATABASE_FILE="/app/.happy/server-light/happier-server-light.sqlite"
    export DATABASE_URL="file:${DATABASE_FILE}"

    # Ensure Prisma migrations are available where the server expects them.
    if [ ! -d "/app/.happy/server-light/migrations/sqlite" ]; then
      MIGRATIONS_SRC=$(find "/app/.cache/happier/server" -path "*/prisma/sqlite/migrations" -type d 2>/dev/null | head -1)
      if [ -n "$MIGRATIONS_SRC" ]; then
        mkdir -p /app/.happy/server-light/migrations
        cp -r "$MIGRATIONS_SRC" /app/.happy/server-light/migrations/sqlite
        log "Migrations copied at runtime (fallback)"
      fi
    fi

    # --- SQLite WAL keeper ---
    if [ -f "$DATABASE_FILE" ]; then
      if command -v sqlite3 &>/dev/null; then
        log "Checkpointing SQLite WAL before server start..."
        sqlite3 "$DATABASE_FILE" "PRAGMA wal_checkpoint(TRUNCATE);" 2>/dev/null || true
      fi
    fi

    # PID file to prevent duplicate server starts
    SERVER_PID_FILE="/var/run/happier-server.pid"
    if [ -f "$SERVER_PID_FILE" ] && kill -0 "$(cat "$SERVER_PID_FILE")" 2>/dev/null; then
      log "Happier relay server is already running (PID $(cat "$SERVER_PID_FILE"))"
    else
      log "Starting Happier relay server on port 3006..."
      if [[ "${LOGGING:-}" == "verbose" ]]; then
        happier-server --ui &
      else
        happier-server --ui >/dev/null 2>&1 &
      fi
      echo $! > "$SERVER_PID_FILE"

      # Wait for the server to actually start listening on port 3006
      log "Waiting for Happier relay server to be ready..."
      MAX_RETRIES=30
      COUNT=0
      while ! nc -z 127.0.0.1 3006 >/dev/null 2>&1; do
        sleep 1
        COUNT=$((COUNT + 1))
        if [ $COUNT -ge $MAX_RETRIES ]; then
          log "ERROR: Happier relay server failed to start after ${MAX_RETRIES} seconds"
          exit 1
        fi
      done
      log "Happier relay server is ready"
    fi

    # WAL keeper
    log "Starting SQLite WAL keeper..."
    python3 -c "
import sqlite3, time, sys
db = sys.argv[1]
try:
    conn = sqlite3.connect(db)
    conn.execute(\"PRAGMA journal_mode=WAL\")
    conn.execute(\"SELECT 1\")
    last_checkpoint = time.time()
    while True:
        time.sleep(15)
        conn.execute(\"SELECT 1\")
        if time.time() - last_checkpoint >= 300:
            conn.execute(\"PRAGMA wal_checkpoint(PASSIVE)\")
            last_checkpoint = time.time()
except Exception:
    pass
" "$DATABASE_FILE" &
    WAL_KEEPER_PID=$!
    log "WAL keeper started (PID $WAL_KEEPER_PID)"

    log "Starting TLS tunnel on 0.0.0.0:3005 -> localhost:3006"
    node /app/happier-tls-tunnel.js &

    # Configure the CLI environment for local use within the container.
    export HAPPIER_SERVER_URL="${HAPPIER_SERVER_URL:-https://localhost:3005}"

    # --- Authentication ---
    ACCESS_KEY_FILE=$(find_access_key "$HAPPIER_SERVER_URL" || true)
    if [ -n "$ACCESS_KEY_FILE" ] && [ -f "$ACCESS_KEY_FILE" ]; then
      log "Happier CLI is authenticated with $HAPPIER_SERVER_URL"
      log "Starting Happier daemon for local use..."
      happier --server-url "$HAPPIER_SERVER_URL" daemon start || true

    elif [ -n "${HAPPIER_ACCESS_KEY:-}" ]; then
      log "HAPPIER_ACCESS_KEY provided — writing access key..."
      ACCESS_KEY_FILE=$(write_access_key "$HAPPIER_SERVER_URL" "$HAPPIER_ACCESS_KEY")
      log "Access key written to $ACCESS_KEY_FILE"
      log "Starting Happier daemon for local use..."
      happier --server-url "$HAPPIER_SERVER_URL" daemon start || true

    else
      do_pairing "$HAPPIER_SERVER_URL" "false"
      # After pairing completes, log the key and start daemon
      log_access_key "$HAPPIER_SERVER_URL"
      ACCESS_KEY_FILE=$(find_access_key "$HAPPIER_SERVER_URL" || true)
      if [ -n "$ACCESS_KEY_FILE" ] && [ -f "$ACCESS_KEY_FILE" ]; then
        log "Happier daemon auto-started after authentication."
        happier --server-url "$HAPPIER_SERVER_URL" daemon start || true
      fi
    fi
    ;;

  agent)
    log "=== Happier: AGENT mode ==="

    # Point the CLI and daemon at the relay server.
    export HAPPIER_SERVER_URL="${HAPPIER_SERVER_URL:-http://happier-server:3006}"

    # If the URL uses HTTPS, enable support for self-signed certificates
    NODE_TLS_PREFIX=""
    if [[ "$HAPPIER_SERVER_URL" == https://* ]]; then
      log "HTTPS server URL detected. Enabling support for self-signed TLS certificates..."
      export NODE_TLS_REJECT_UNAUTHORIZED=0
      NODE_TLS_PREFIX="NODE_TLS_REJECT_UNAUTHORIZED=0 "

      # Also patch xmlhttprequest-ssl
      XHR_FILE="/usr/lib/node_modules/@happier-dev/cli/node_modules/xmlhttprequest-ssl/lib/XMLHttpRequest.js"
      if [ -f "$XHR_FILE" ]; then
        if ! grep -q "NODE_TLS_REJECT_UNAUTHORIZED" "$XHR_FILE" 2>/dev/null; then
          sed -i \
            's/rejectUnauthorized === false ? false : true/rejectUnauthorized === false ? false : (process.env.NODE_TLS_REJECT_UNAUTHORIZED === '\''0'\'' ? false : true)/g' \
            "$XHR_FILE"
        fi
      fi
    fi

    # --- Authentication ---
    ACCESS_KEY_FILE=$(find_access_key "$HAPPIER_SERVER_URL" || true)
    if [ -n "$ACCESS_KEY_FILE" ] && [ -f "$ACCESS_KEY_FILE" ]; then
      log "Happier agent is authenticated with $HAPPIER_SERVER_URL"
      log "Starting Happier daemon..."
      happier --server-url "$HAPPIER_SERVER_URL" daemon start || true

    elif [ -n "${HAPPIER_ACCESS_KEY:-}" ]; then
      log "HAPPIER_ACCESS_KEY provided — writing access key..."
      ACCESS_KEY_FILE=$(write_access_key "$HAPPIER_SERVER_URL" "$HAPPIER_ACCESS_KEY")
      log "Access key written to $ACCESS_KEY_FILE"
      log "Starting Happier daemon..."
      happier --server-url "$HAPPIER_SERVER_URL" daemon start || true

    else
      do_pairing "$HAPPIER_SERVER_URL" "true"
      # After pairing completes, log the key and start daemon
      log_access_key "$HAPPIER_SERVER_URL"
      ACCESS_KEY_FILE=$(find_access_key "$HAPPIER_SERVER_URL" || true)
      if [ -n "$ACCESS_KEY_FILE" ] && [ -f "$ACCESS_KEY_FILE" ]; then
        log "Happier daemon auto-started after authentication."
        happier --server-url "$HAPPIER_SERVER_URL" daemon start || true
      fi
    fi
    ;;

  *)
    log "ERROR: Unknown CONTAINER_ROLE='$ROLE'. Supported: server, agent"
    exit 1
    ;;
esac
