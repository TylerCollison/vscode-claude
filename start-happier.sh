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

    # --- SQLite WAL recovery ---
    # In Docker container environments, SQLite WAL files (.sqlite-wal and .sqlite-shm)
    # can be deleted while the server process keeps them open. When this happens,
    # all writes that went to the deleted WAL are invisible to other processes
    # (including the web UI and new API connections).
    #
    # To prevent this, checkpoint any orphaned WAL before starting the server,
    # then add a background loop that keeps the WAL small by checkpointing regularly.
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

    # Background WAL checkpoint loop — runs every 5 minutes to keep the WAL
    # file small and prevent data loss if the WAL gets orphaned.
    (
      while true; do
        sleep 300
        if command -v sqlite3 &>/dev/null && [ -f "$DATABASE_FILE" ]; then
          sqlite3 "$DATABASE_FILE" "PRAGMA wal_checkpoint(PASSIVE);" 2>/dev/null || true
        fi
      done
    ) &
    # Track the checkpoint loop PID so we can clean it up
    CHECKPOINT_PID=$!
    trap "kill $CHECKPOINT_PID 2>/dev/null || true" EXIT

    echo "Starting TLS tunnel on 0.0.0.0:3005 -> localhost:3006"
    node /app/happier-tls-tunnel.js &

    # Configure the CLI environment for local use within the container.
    # The TLS tunnel uses a self-signed cert, so NODE_TLS_REJECT_UNAUTHORIZED=0 is needed.
    export HAPPIER_SERVER_URL="${HAPPIER_SERVER_URL:-https://localhost:3005}"
    export NODE_TLS_REJECT_UNAUTHORIZED=0

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
