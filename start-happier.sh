#!/usr/bin/with-contenv bash
# Happier startup script
# Supports two roles controlled by the CONTAINER_ROLE env var:
#   server  — starts the relay server + web UI (default)
#   agent   — configures the CLI/daemon to connect to a remote relay server

set -euo pipefail

ROLE="${CONTAINER_ROLE:-server}"

case "$ROLE" in
  server)
    echo "=== Happier: SERVER mode ==="

    # --- Generate self-signed TLS cert for HTTPS access ---
    # Needed because crypto.subtle (Web Crypto API) is only available in
    # secure contexts (HTTPS or localhost). The TLS tunnel wraps port 3005
    # so the browser treats it as a secure context.
    CERT_DIR="/app/.happy/server-light"
    if [ ! -f "$CERT_DIR/tunnel.key" ] || [ ! -f "$CERT_DIR/tunnel.crt" ]; then
      echo "Generating self-signed TLS certificate for happier HTTPS tunnel..."
      mkdir -p "$CERT_DIR"
      openssl req -x509 -newkey rsa:2048 -keyout "$CERT_DIR/tunnel.key" \
        -out "$CERT_DIR/tunnel.crt" -days 3650 -nodes \
        -subj "/CN=happier" 2>/dev/null || \
        echo "WARNING: Failed to generate TLS certificate — HTTPS tunnel will not start"
      echo "Self-signed certificate generated"
    fi

    # The TLS tunnel uses a self-signed cert, so disable TLS verification
    # for all processes launched by this script (daemon, socket.io polling, etc.)
    export NODE_TLS_REJECT_UNAUTHORIZED=0

    # --- Patch xmlhttprequest-ssl to respect NODE_TLS_REJECT_UNAUTHORIZED ---
    # The socket.io client engine.io-client uses xmlhttprequest-ssl for HTTP
    # polling in Node.js. This module does NOT check the
    # NODE_TLS_REJECT_UNAUTHORIZED env var — it defaults rejectUnauthorized to
    # true. This causes the daemon's machine-sync WebSocket connection to fail
    # silently ("xhr poll error") when connecting through the TLS tunnel with
    # a self-signed certificate, because the socket.io client never establishes
    # its polling transport.
    #
    # The REST API (built-in https module) works fine because Node.js does
    # respect the env var. Only socket.io polling via xmlhttprequest-ssl is
    # affected.
    XHR_FILE="/usr/lib/node_modules/@happier-dev/cli/node_modules/xmlhttprequest-ssl/lib/XMLHttpRequest.js"
    if [ -f "$XHR_FILE" ]; then
      if grep -q "NODE_TLS_REJECT_UNAUTHORIZED" "$XHR_FILE" 2>/dev/null; then
        echo "xmlhttprequest-ssl already patched"
      else
        echo "Patching xmlhttprequest-ssl to respect NODE_TLS_REJECT_UNAUTHORIZED=0..."
        sed -i \
          's/rejectUnauthorized === false ? false : true/rejectUnauthorized === false ? false : (process.env.NODE_TLS_REJECT_UNAUTHORIZED === '\''0'\'' ? false : true)/g' \
          "$XHR_FILE"
        echo "xmlhttprequest-ssl patched successfully"
      fi
    else
      echo "WARNING: xmlhttprequest-ssl not found at $XHR_FILE — daemon machine sync may not work"
    fi

    # Run happier-server on an internal port; the TLS tunnel forwards to it.
    export PORT=3006
    export HAPPIER_SQLITE_AUTO_MIGRATE=true
    DATABASE_FILE="/app/.happy/server-light/happier-server-light.sqlite"
    export DATABASE_URL="file:${DATABASE_FILE}"

    # Ensure Prisma migrations are available where the server expects them.
    # They are pre-copied at build time; this is a runtime fallback for version
    # bumps where the cache directory contains a newer path.
    if [ ! -d "/app/.happy/server-light/migrations/sqlite" ]; then
      MIGRATIONS_SRC=$(find "/app/.cache/happier/server" -path "*/prisma/sqlite/migrations" -type d 2>/dev/null | head -1)
      if [ -n "$MIGRATIONS_SRC" ]; then
        mkdir -p /app/.happy/server-light/migrations
        cp -r "$MIGRATIONS_SRC" /app/.happy/server-light/migrations/sqlite
        echo "Migrations copied at runtime (fallback)"
      fi
    fi

    # --- SQLite WAL keeper ---
    # Root cause: happier-server uses Prisma with SQLite in WAL journal mode.
    # Prisma's connection pool opens and closes SQLite connections. When the LAST
    # connection to a WAL-mode database closes, SQLite unlinks (deletes) the
    # .sqlite-wal and .sqlite-shm files. If the server's long-lived connections
    # still have open file descriptors to the deleted files, all subsequent writes
    # go into the invisible deleted WAL — new connections (including the web UI)
    # see a stale database.
    #
    # The fix: keep a permanent SQLite connection open with WAL mode set.
    # As long as at least one connection holds the WAL/SHM open, SQLite will not
    # delete them when Prisma recycles its pool.
    if [ -f "$DATABASE_FILE" ]; then
      if command -v sqlite3 &>/dev/null; then
        echo "Checkpointing SQLite WAL before server start..."
        sqlite3 "$DATABASE_FILE" "PRAGMA wal_checkpoint(TRUNCATE);" 2>/dev/null || true
      fi
    fi

    # PID file to prevent duplicate server starts (s6 may re-run cont-init.d scripts)
    SERVER_PID_FILE="/var/run/happier-server.pid"
    if [ -f "$SERVER_PID_FILE" ] && kill -0 "$(cat "$SERVER_PID_FILE")" 2>/dev/null; then
      echo "Happier relay server is already running (PID $(cat "$SERVER_PID_FILE"))"
    else
      echo "Starting Happier relay server on port 3006..."
      happier-server --ui &
      echo $! > "$SERVER_PID_FILE"

      # Wait for the server to actually start listening on port 3006
      echo "Waiting for Happier relay server to be ready..."
      MAX_RETRIES=30
      COUNT=0
      while ! nc -z 127.0.0.1 3006 >/dev/null 2>&1; do
        sleep 1
        COUNT=$((COUNT + 1))
        if [ $COUNT -ge $MAX_RETRIES ]; then
          echo "ERROR: Happier relay server failed to start after ${MAX_RETRIES} seconds"
          exit 1
        fi
      done
      echo "Happier relay server is ready"
    fi

    # WAL keeper — holds a permanent SQLite connection in WAL mode to prevent
    # Prisma pool teardown from unlinking the WAL/SHM files. Runs a checkpoint
    # every 5 minutes as well.
    echo "Starting SQLite WAL keeper..."
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
        # Checkpoint every 5 minutes (300 seconds)
        if time.time() - last_checkpoint >= 300:
            conn.execute(\"PRAGMA wal_checkpoint(PASSIVE)\")
            last_checkpoint = time.time()
except Exception:
    pass
" "$DATABASE_FILE" &
    WAL_KEEPER_PID=$!
    echo "WAL keeper started (PID $WAL_KEEPER_PID)"

    echo "Starting TLS tunnel on 0.0.0.0:3005 -> localhost:3006"
    node /app/happier-tls-tunnel.js &

    # Configure the CLI environment for local use within the container.
    # NODE_TLS_REJECT_UNAUTHORIZED=0 already exported above (before the xhr patch).
    export HAPPIER_SERVER_URL="${HAPPIER_SERVER_URL:-https://localhost:3005}"

    # Ensure the config directory exists.
    mkdir -p "$HOME/.happier"

    # Check whether this instance has already been authenticated with the server.
    # The access key lives in a per-server subdirectory: $HOME/.happier/servers/<server-id>/access.key
    ACCESS_KEY_FILE=$(find "$HOME/.happier/servers" -name "access.key" -type f 2>/dev/null | head -1)
    if [ -n "$ACCESS_KEY_FILE" ]; then
      echo "Happier CLI is authenticated with $HAPPIER_SERVER_URL"
      echo "Starting Happier daemon for local use..."
      happier --server-url "$HAPPIER_SERVER_URL" daemon start || true
    else
      echo ""
      echo "============================================================"
      echo "  Happier Server — Local CLI Access"
      echo "============================================================"
      echo ""
      echo "To use the happier CLI from within this container,"
      echo "authenticate with the local relay server:"
      echo ""
      echo "  NODE_TLS_REJECT_UNAUTHORIZED=0 happier --server-url $HAPPIER_SERVER_URL auth login"
      echo ""
      echo "After authenticating, start the daemon:"
      echo ""
      echo "  happier --server-url $HAPPIER_SERVER_URL daemon start"
      echo ""
      echo "Then launch a Claude Code session through Happier:"
      echo ""
      echo "  happier --server-url $HAPPIER_SERVER_URL claude"
      echo ""
      echo "============================================================"
      echo ""
    fi
    ;;

  agent)
    echo "=== Happier: AGENT mode ==="

    # Point the CLI and daemon at the relay server.
    export HAPPIER_SERVER_URL="${HAPPIER_SERVER_URL:-http://happier-server:3006}"

    # If the URL uses HTTPS, enable support for self-signed certificates (such as our TLS tunnel)
    # by setting NODE_TLS_REJECT_UNAUTHORIZED to 0.
    NODE_TLS_PREFIX=""
    if [[ "$HAPPIER_SERVER_URL" == https://* ]]; then
      echo "HTTPS server URL detected. Enabling support for self-signed TLS certificates..."
      export NODE_TLS_REJECT_UNAUTHORIZED=0
      NODE_TLS_PREFIX="NODE_TLS_REJECT_UNAUTHORIZED=0 "

      # Also patch xmlhttprequest-ssl (see server mode for detailed rationale)
      XHR_FILE="/usr/lib/node_modules/@happier-dev/cli/node_modules/xmlhttprequest-ssl/lib/XMLHttpRequest.js"
      if [ -f "$XHR_FILE" ]; then
        if ! grep -q "NODE_TLS_REJECT_UNAUTHORIZED" "$XHR_FILE" 2>/dev/null; then
          sed -i \
            's/rejectUnauthorized === false ? false : true/rejectUnauthorized === false ? false : (process.env.NODE_TLS_REJECT_UNAUTHORIZED === '\''0'\'' ? false : true)/g' \
            "$XHR_FILE"
        fi
      fi
    fi

    # Ensure the config directory exists.
    mkdir -p "$HOME/.happier"

    # Check whether this agent has already been authenticated with the server
    # by looking for the local key material generated by `happier auth login`.
    # The access key lives in a per-server subdirectory: $HOME/.happier/servers/<server-id>/access.key
    ACCESS_KEY_FILE=$(find "$HOME/.happier/servers" -name "access.key" -type f 2>/dev/null | head -1)
    if [ -n "$ACCESS_KEY_FILE" ]; then
      echo "Happier agent is authenticated with $HAPPIER_SERVER_URL"
      echo "Starting Happier daemon..."
      happier --server-url "$HAPPIER_SERVER_URL" daemon start || true
    else
      echo "============================================================"
      echo "  Happier Agent — Not Yet Authenticated"
      echo "============================================================"
      echo ""
      echo "Relay server URL: $HAPPIER_SERVER_URL"
      echo ""
      echo "Connect this agent to the relay server:"
      echo ""
      echo "  1. Run the interactive auth command:"
      echo "     ${NODE_TLS_PREFIX}happier --server-url $HAPPIER_SERVER_URL auth login"
      echo ""
      echo "  2. Follow the pairing instructions shown on screen."
      echo ""
      echo "  3. Start the daemon (persistent background sync):"
      echo "     ${NODE_TLS_PREFIX}happier --server-url $HAPPIER_SERVER_URL daemon start"
      echo ""
      echo "  4. Launch a Claude Code session through Happier:"
      echo "     ${NODE_TLS_PREFIX}happier --server-url $HAPPIER_SERVER_URL claude"
      echo ""
      echo "These steps only need to be done once per agent container."
      echo "============================================================"
    fi
    ;;

  *)
    echo "ERROR: Unknown CONTAINER_ROLE='$ROLE'. Supported: server, agent"
    exit 1
    ;;
esac
