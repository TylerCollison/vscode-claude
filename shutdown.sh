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

  # Get the machine ID from settings (legacy method - may be stale)
  get_machine_id_from_settings() {
    local server_url="$1"
    local sid
    sid=$(get_server_id "$server_url")
    local settings_file="/config/.happier/settings.json"
    if [ ! -f "$settings_file" ]; then
      return 1
    fi

    # Use a temporary Python script to avoid quoting issues
    local py_script
    py_script=$(mktemp)
    cat > "$py_script" << 'PYEOF'
import json, sys, os
settings_file = os.environ.get('SETTINGS_FILE', '')
sid = os.environ.get('SID', '')
try:
    with open(settings_file) as f:
        data = json.load(f)
    # Check machineIdByServerId
    if 'machineIdByServerId' in data and sid in data['machineIdByServerId']:
        print(data['machineIdByServerId'][sid])
        sys.exit(0)
    # Check machineIdByServerIdByAccountId
    if 'machineIdByServerIdByAccountId' in data:
        for account_id, machines in data['machineIdByServerIdByAccountId'].items():
            if sid in machines:
                print(machines[sid])
                sys.exit(0)
except Exception:
    pass
sys.exit(1)
PYEOF
    SETTINGS_FILE="$settings_file" SID="$sid" python3 "$py_script" 2>/dev/null || true
    local result=$?
    rm -f "$py_script"
    return $result
  }

  # Clean up stale machine ID from settings.json
  cleanup_settings() {
    local settings_file="/config/.happier/settings.json"
    local sid="$1"
    if [ ! -f "$settings_file" ]; then
      return 0
    fi

    local py_script
    py_script=$(mktemp)
    cat > "$py_script" << 'PYEOF'
import json, sys, os
settings_file = os.environ.get('SETTINGS_FILE', '')
sid = os.environ.get('SID', '')
try:
    with open(settings_file) as f:
        data = json.load(f)
    changed = False
    if 'machineIdByServerId' in data and sid in data['machineIdByServerId']:
        del data['machineIdByServerId'][sid]
        changed = True
    if 'machineIdByServerIdByAccountId' in data:
        for account_id in list(data['machineIdByServerIdByAccountId'].keys()):
            if sid in data['machineIdByServerIdByAccountId'][account_id]:
                del data['machineIdByServerIdByAccountId'][account_id][sid]
                changed = True
    if changed:
        with open(settings_file, 'w') as f:
            json.dump(data, f, indent=2)
        print('Cleaned up stale machine ID from settings.json')
except Exception:
    pass
PYEOF
    SETTINGS_FILE="$settings_file" SID="$sid" python3 "$py_script" 2>/dev/null || true
    rm -f "$py_script"
  }

  # Find machine ID from server machine list matching current hostname
  find_machine_id_from_server() {
    local server_url="$1"
    local access_key="$2"
    local hostname="$3"

    local response
    response=$(curl -k -s -w "\n%{http_code}" -X GET \
      -H "Authorization: Bearer $access_key" \
      "$server_url/v1/machines" 2>/dev/null || true)

    local http_code
    http_code=$(echo "$response" | tail -n1)
    local body
    body=$(echo "$response" | head -n-1)

    if [ "$http_code" != "200" ] || [ -z "$body" ]; then
      return 1
    fi

    # Use a temporary Python script to parse the machine list
    local py_script
    py_script=$(mktemp)
    cat > "$py_script" << 'PYEOF'
import json, sys, os
body = os.environ.get('BODY', '')
hostname = os.environ.get('HOSTNAME', '')
try:
    data = json.loads(body)
    machines = data.get('machines', data) if isinstance(data, dict) else data

    # First, try to find machine with matching hostname
    for machine in machines:
        if machine.get('hostname') == hostname and machine.get('active', True):
            print(machine.get('id', ''))
            sys.exit(0)

    # Fallback: find most recently created active machine for this account
    active_machines = [m for m in machines if m.get('active', True)]
    if active_machines:
        active_machines.sort(key=lambda m: m.get('createdAt', ''), reverse=True)
        print(active_machines[0].get('id', ''))
        sys.exit(0)
except Exception:
    pass
sys.exit(1)
PYEOF
    BODY="$body" HOSTNAME="$hostname" python3 "$py_script" 2>/dev/null || true
    local result=$?
    rm -f "$py_script"
    return $result
  }

  # Determine the server URL based on HAPPIER_MODE
  if [ "$HAPPIER_MODE" = "server" ]; then
    SERVER_URL="${HAPPIER_SERVER_URL:-https://localhost:3005}"
  else
    SERVER_URL="${HAPPIER_SERVER_URL:-http://happier-server:3006}"
  fi

  log "Server URL: $SERVER_URL"

  # Pre-compute server ID for use in cleanup
  SERVER_ID=$(get_server_id "$SERVER_URL")

  # Find access key
  ACCESS_KEY_FILE=$(find_access_key "$SERVER_URL" || true)
  if [ -n "$ACCESS_KEY_FILE" ] && [ -f "$ACCESS_KEY_FILE" ]; then
    log "Found access key at $ACCESS_KEY_FILE"

    # Read the access key. The file is a JSON object with the auth token in
    # the "token" field (not the raw file contents); extract that token.
    ACCESS_KEY=$(node -e "
const fs = require('fs');
try {
  const key = JSON.parse(fs.readFileSync(process.argv[1], 'utf8'));
  console.log(key.token || '');
} catch {
  // Fall back to raw contents for legacy non-JSON access keys
  console.log(fs.readFileSync(process.argv[1], 'utf8').replace(/\s+/g, ''));
}
" "$ACCESS_KEY_FILE")

    # Get current hostname for matching against server machine list
    CURRENT_HOSTNAME=$(hostname)

    # Try to find the correct machine ID by querying the server's machine list
    # This is more reliable than using the potentially stale settings.json
    MACHINE_ID=""

    log "Querying server for machine list to find current instance..."
    MATCHED_ID=$(find_machine_id_from_server "$SERVER_URL" "$ACCESS_KEY" "$CURRENT_HOSTNAME" || true)

    if [ -n "$MATCHED_ID" ]; then
      MACHINE_ID="$MATCHED_ID"
      log "Found matching machine on server: $MACHINE_ID (hostname: $CURRENT_HOSTNAME)"
    else
      log "No matching active machine found on server for hostname: $CURRENT_HOSTNAME"
    fi

    # Fallback to settings.json if server query didn't find a match
    if [ -z "$MACHINE_ID" ]; then
      MACHINE_ID=$(get_machine_id_from_settings "$SERVER_URL" || true)
      if [ -n "$MACHINE_ID" ]; then
        log "Using machine ID from settings.json: $MACHINE_ID"
      fi
    fi

    if [ -n "$MACHINE_ID" ]; then
      log "Found machine ID: $MACHINE_ID"

      # Remove this machine from the server's active machine list.
      # The Happier server has no DELETE /v1/machines/:id endpoint (it returns
      # 404). The correct way to de-register a machine is POST .../revoke,
      # which marks the machine active=false and sets revokedAt.
      log "Revoking machine $MACHINE_ID from Happier server..."
      RESPONSE=$(curl -k -s -w "\n%{http_code}" -X POST \
        -H "Authorization: Bearer $ACCESS_KEY" \
        "$SERVER_URL/v1/machines/$MACHINE_ID/revoke" 2>/dev/null || true)

      HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
      BODY=$(echo "$RESPONSE" | head -n-1)

      if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "204" ]; then
        log "Successfully revoked machine $MACHINE_ID from Happier server"
        # Clean up local settings to remove the stale machine ID
        cleanup_settings "$SERVER_ID"
      elif [ "$HTTP_CODE" = "404" ]; then
        log "Machine $MACHINE_ID not found on server (already removed or ID is stale)"
        # Even if 404, clean up local settings to prevent future stale lookups
        cleanup_settings "$SERVER_ID"
      elif [ "$HTTP_CODE" = "401" ]; then
        log "WARNING: Authentication failed when revoking machine (token may be expired)"
      else
        log "WARNING: Failed to revoke machine (HTTP $HTTP_CODE): $BODY"
      fi
    else
      log "No machine ID found (neither from server nor settings), skipping machine deletion"
    fi
  else
    log "No access key found, skipping machine deletion"
  fi

  # NOTE: do NOT stop the Happier daemon here — we intentionally leave it
  # running so other sessions/tools on the machine keep working.
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