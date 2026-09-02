#!/usr/bin/with-contenv bash
# Shutdown script for the container
# If HAPPIER_MODE is set, first removes this machine from the Happier server
# Then shuts down the container

set -euo pipefail

log() {
  echo "[SHUTDOWN] $*"
}

# If HAPPIER_MODE is not set, skip Happier cleanup
if [ -z "${HAPPIER_MODE:-}" ]; then
  log "HAPPIER_MODE not set, skipping Happier cleanup"
else
  log "HAPPIER_MODE is set ($HAPPIER_MODE), cleaning up Happier machine..."

  # Use /config (abc user's home) for consistent paths
  HOME=/config

  # Derive server ID from HAPPIER_SERVER_URL (same logic as start-happier.sh)
  get_server_id() {
    local url="$1"
    node -e "
const url = process.argv[1];
const normalizeUrl = (u) => String(u ?? '').trim().replace(/\/+\$/, '');
let comparableKey = '';
try {
  comparableKey = new URL(normalizeUrl(url)).href.replace(/\/+\$/, '');
} catch {}
const value = comparableKey || normalizeUrl(url) || (url || '');
let h = 2166136261;
for (let i = 0; i < value.length; i++) { h ^= value.charCodeAt(i); h = Math.imul(h, 16777619); }
console.log('env_' + (h >>> 0).toString(16));
" "$url"
  }

  # Find the access key for the current server
  find_access_key() {
    local server_url="$1"
    local sid
    sid=$(get_server_id "$server_url")
    local key_file="/config/.happier/servers/$sid/access.key"
    if [ -f "$key_file" ]; then
      echo "$key_file"
      return 0
    fi
    # Also search broadly as a fallback
    local found
    found=$(find "/config/.happier/servers" -name "access.key" -type f -print -quit 2>/dev/null || true)
    if [ -n "$found" ]; then
      echo "$found"
      return 0
    fi
    return 1
  }

  # Get the machine ID from settings
  get_machine_id() {
    local server_url="$1"
    local sid
    sid=$(get_server_id "$server_url")
    # Try to read from settings.json first
    local settings_file="/config/.happier/settings.json"
    if [ -f "$settings_file" ]; then
      python3 -c "
import json, sys
try:
    with open('$settings_file') as f:
        data = json.load(f)
    # Check machineIdByServerId
    if 'machineIdByServerId' in data and '$sid' in data['machineIdByServerId']:
        print(data['machineIdByServerId']['$sid'])
        sys.exit(0)
    # Check machineIdByServerIdByAccountId
    if 'machineIdByServerIdByAccountId' in data:
        for account_id, machines in data['machineIdByServerIdByAccountId'].items():
            if '$sid' in machines:
                print(machines['$sid'])
                sys.exit(0)
except Exception:
    pass
sys.exit(1)
" 2>/dev/null || true
    fi
    return 1
  }

  # Determine the server URL based on HAPPIER_MODE
  if [ "$HAPPIER_MODE" = "server" ]; then
    SERVER_URL="${HAPPIER_SERVER_URL:-https://localhost:3005}"
  else
    SERVER_URL="${HAPPIER_SERVER_URL:-http://happier-server:3006}"
  fi

  log "Server URL: $SERVER_URL"

  # Find access key
  ACCESS_KEY_FILE=$(find_access_key "$SERVER_URL" || true)
  if [ -n "$ACCESS_KEY_FILE" ] && [ -f "$ACCESS_KEY_FILE" ]; then
    log "Found access key at $ACCESS_KEY_FILE"

    # Read the access key (strip whitespace)
    ACCESS_KEY=$(cat "$ACCESS_KEY_FILE" | tr -d '[:space:]')

    # Get machine ID
    MACHINE_ID=$(get_machine_id "$SERVER_URL" || true)
    if [ -n "$MACHINE_ID" ]; then
      log "Found machine ID: $MACHINE_ID"

      # Delete the machine via API
      log "Deleting machine from Happier server..."
      RESPONSE=$(curl -k -s -w "\n%{http_code}" -X DELETE \
        -H "Authorization: Bearer $ACCESS_KEY" \
        -H "Content-Type: application/json" \
        -d '{}' \
        "$SERVER_URL/v1/machines/$MACHINE_ID" 2>/dev/null || true)

      HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
      BODY=$(echo "$RESPONSE" | head -n-1)

      if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "204" ]; then
        log "Successfully deleted machine $MACHINE_ID from Happier server"
      elif [ "$HTTP_CODE" = "404" ]; then
        log "Machine $MACHINE_ID not found on server (already removed)"
      elif [ "$HTTP_CODE" = "401" ]; then
        log "WARNING: Authentication failed when deleting machine (token may be expired)"
      else
        log "WARNING: Failed to delete machine (HTTP $HTTP_CODE): $BODY"
      fi
    else
      log "No machine ID found in settings, skipping machine deletion"
    fi
  else
    log "No access key found, skipping machine deletion"
  fi

  # Stop the Happier daemon if running
  log "Stopping Happier daemon..."
  happier --server-url "$SERVER_URL" daemon stop 2>/dev/null || true
  log "Happier daemon stopped"
fi

# Shutdown the container by sending SIGTERM to PID 1 (the s6-overlay init process)
log "Shutting down container..."
kill -TERM 1

# Give it a moment to shut down gracefully
sleep 2

# If still running, force kill
if kill -0 1 2>/dev/null; then
  log "Container still running, forcing shutdown..."
  kill -KILL 1
fi

log "Shutdown complete"