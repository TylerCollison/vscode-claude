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

  # Get this instance's machine ID from settings.json (the daemon writes it
  # here when it registers with the server; may be stale if the registration
  # did not happen for this server URL)
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

  # Look up the state of a machine ID in the server's machine list.
  # Prints "active", "inactive", "absent", or "unknown".
  # This can only verify a machine ID we already know: the server's machine
  # list carries no hostname field (hostname only lives inside the encrypted
  # metadata blob), so it cannot be used to identify our own machine.
  # The response body is written to a temp file rather than passed as an
  # environment variable: it grows with the account's machine count and
  # overflows the kernel's ~128KB per-string exec limit (E2BIG, "Argument
  # list too long"), which silently broke this lookup.
  get_machine_state_from_server() {
    local server_url="$1"
    local access_key="$2"
    local machine_id="$3"

    local body_file
    body_file=$(mktemp)
    local http_code
    http_code=$(curl -k -s -o "$body_file" -w "%{http_code}" -X GET \
      -H "Authorization: Bearer $access_key" \
      "$server_url/v1/machines" 2>/dev/null || true)

    if [ "$http_code" != "200" ]; then
      log "Machine list request failed (HTTP $http_code)"
      rm -f "$body_file"
      echo "unknown"
      return 0
    fi
    if [ ! -s "$body_file" ]; then
      log "Machine list response was empty"
      rm -f "$body_file"
      echo "unknown"
      return 0
    fi

    # Use a temporary Python script to parse the machine list
    local py_script
    py_script=$(mktemp)
    cat > "$py_script" << 'PYEOF'
import json, sys, os
body_file = os.environ.get('BODY_FILE', '')
machine_id = os.environ.get('MACHINE_ID', '')
try:
    with open(body_file) as f:
        data = json.load(f)
    machines = data.get('machines', data) if isinstance(data, dict) else data
    for machine in machines:
        if machine.get('id') == machine_id:
            # The server deactivates machines via active=false; revokedAt
            # may stay null even after deactivation.
            print('active' if machine.get('active', True) else 'inactive')
            sys.exit(0)
    print('absent')
    sys.exit(0)
except Exception as e:
    print('parse-error: %s' % e, file=sys.stderr)
sys.exit(1)
PYEOF
    local state
    state=$(BODY_FILE="$body_file" MACHINE_ID="$machine_id" python3 "$py_script" 2>/dev/null || true)

    if [ -z "$state" ]; then
      # Parse failed; surface a trimmed body snippet so the failure is
      # diagnosable (e.g. an HTML fallback page instead of JSON).
      log "Failed to parse machine list response; body starts with: $(head -c 200 "$body_file" 2>/dev/null || true)"
      state="unknown"
    fi
    rm -f "$py_script"
    rm -f "$body_file"
    echo "$state"
  }

  # Determine the server URL based on HAPPIER_MODE
  if [ "$HAPPIER_MODE" = "server" ]; then
    SERVER_URL="${HAPPIER_SERVER_URL:-https://localhost:3005}"
  else
    SERVER_URL="${HAPPIER_SERVER_URL:-http://happier-server:3006}"
  fi

  # Strip trailing slashes so API paths don't double up. A trailing slash in
  # HAPPIER_SERVER_URL otherwise produces //v1/... URLs; the revoke endpoint
  # is not route-normalized and 404s on the double slash, so the machine was
  # never actually revoked. (get_server_id below normalizes the same way,
  # which is why the derived env_* server ID was still correct.)
  while [ "${SERVER_URL%/}" != "$SERVER_URL" ]; do
    SERVER_URL="${SERVER_URL%/}"
  done

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

    # The daemon writes this instance's machine ID to settings.json when it
    # registers with the server, so it is the only reliable identity for this
    # container. The server's machine list carries no hostname field, so
    # matching by hostname is impossible — and guessing (e.g. "most recently
    # created machine") risks revoking another running container's machine.
    MACHINE_ID=$(get_machine_id_from_settings "$SERVER_URL" || true)

    if [ -n "$MACHINE_ID" ]; then
      log "Machine ID from settings.json: $MACHINE_ID"

      # Check how the server sees this machine so the result is unambiguous
      STATE=$(get_machine_state_from_server "$SERVER_URL" "$ACCESS_KEY" "$MACHINE_ID")
      case "$STATE" in
        active)   log "Server reports this machine as registered and active" ;;
        inactive) log "Server reports this machine as already revoked" ;;
        absent)   log "Server machine list does not contain this machine ID (stale)" ;;
        *)        log "Could not determine machine state from server machine list" ;;
      esac

      # Remove this machine from the server's active machine list.
      # The Happier server has no DELETE /v1/machines/:id endpoint (it returns
      # 404). The correct way to de-register a machine is POST .../revoke,
      # which marks the machine active=false (revokedAt may stay null).
      # Revoke is idempotent: it returns 200 even for an already-revoked
      # machine, so a 404 here means the ID is genuinely stale (or the URL
      # was malformed — see the trailing-slash normalization above).
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
      log "No machine ID found in settings.json for this server, skipping machine revocation"
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