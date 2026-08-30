#!/usr/bin/with-contenv bash
# Start the MR/PR Responder Sync daemon.
# Opt-in via MR_PR_SYNC_ENABLED=true.
# Polls GitHub/GitLab for MRs/PRs assigned to MR_RESPONDER_USER.
# Runs at the specified interval.

set -euo pipefail

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

# Skip unless explicitly enabled
SYNC_ENABLED="${MR_PR_SYNC_ENABLED:-false}"
if [[ "$SYNC_ENABLED" != "true" ]]; then
    log "MR/PR sync not enabled (MR_PR_SYNC_ENABLED is not 'true'). Skipping."
    exit 0
fi

# MR_RESPONDER_USER is required
RESPONDER_USER="${MR_RESPONDER_USER:-}"
if [ -z "$RESPONDER_USER" ]; then
    log "ERROR: MR_RESPONDER_USER is not set but MR_PR_SYNC_ENABLED is true. Skipping."
    exit 0
fi

# Verify prerequisites
for binary in gh glab docker python3; do
    if ! command -v "$binary" &> /dev/null; then
        log "WARNING: $binary not found on PATH — skipping."
        exit 0
    fi
done

DEFAULT_WORKSPACE="${DEFAULT_WORKSPACE:-/workspace}"
GIT_REPO_URL="${GIT_REPO_URL:-}"

if [ -z "$GIT_REPO_URL" ]; then
    log "ERROR: GIT_REPO_URL not set. Skipping."
    exit 0
fi

# Determine provider from GIT_REPO_URL
PROVIDER=""
# Extract owner/repo from GIT_REPO_URL for --repo flag
REPO_OWNER_REPO=""
if [[ "$GIT_REPO_URL" == *"github.com"* ]]; then
    PROVIDER="github"
    REPO_OWNER_REPO="${GIT_REPO_URL#*github.com/}"
    REPO_OWNER_REPO="${REPO_OWNER_REPO%.git}"
elif [[ "$GIT_REPO_URL" == *"gitlab.com"* ]]; then
    PROVIDER="gitlab"
    REPO_OWNER_REPO="${GIT_REPO_URL#*gitlab.com/}"
    REPO_OWNER_REPO="${REPO_OWNER_REPO%.git}"
else
    log "ERROR: Could not determine provider from GIT_REPO_URL ($GIT_REPO_URL). Only github.com and gitlab.com are supported."
    exit 0
fi

if [ -z "$REPO_OWNER_REPO" ]; then
    log "ERROR: Could not extract owner/repo from GIT_REPO_URL ($GIT_REPO_URL)"
    exit 0
fi

log "MR/PR sync enabled for $PROVIDER (user: $RESPONDER_USER, repo: $REPO_OWNER_REPO)"

# Configuration
SYNC_INTERVAL="${MR_PR_SYNC_INTERVAL:-300}"
RUN_ON_START="${MR_PR_SYNC_RUN_ON_START:-true}"

# State file for tracking seen MRs/PRs
STATE_DIR="${MR_PR_DISPATCH_STATE_DIR:-/config/.mr-pr-dispatch}"
mkdir -p "$STATE_DIR"
STATE_FILE="$STATE_DIR/seen.json"

# PID file
PID_FILE="/var/run/mr-pr-sync.pid"
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    log "MR/PR sync already running (PID $(cat "$PID_FILE")). Skipping."
    exit 0
fi

# Run as abc user for git credentials
RUN_USER="abc"

# Function to run sync
run_sync() {
    log "Starting MR/PR sync cycle..."

    # Get credentials home
    if [ -d "/config" ]; then
        SYNC_HOME="/config"
    else
        SYNC_HOME="/root"
    fi

    # Load seen state
    seen=()
    if [ -f "$STATE_FILE" ]; then
        mapfile -t seen < <(python3 -c "
import sys, json
try:
    with open('$STATE_FILE', 'r') as f:
        data = json.load(f)
        for item in data.get('seen', []):
            print(str(item))
except Exception as e:
    print(f\"ERROR: Failed to load seen state: {e}\", file=sys.stderr)
")
    fi

    # Function to check if an MR/PR is in seen
    is_seen() {
        local id="$1"
        for s in "${seen[@]}"; do
            if [[ "$s" == "$id" ]]; then
                return 0
            fi
        done
        return 1
    }

    # Function to add to seen
    add_seen() {
        local id="$1"
        seen+=("$id")
        python3 -c "
import json, sys
with open('$STATE_FILE', 'w') as f:
    json.dump({'seen': sys.argv[1:]}, f)
" "${seen[@]}"
    }

    # Get MRs/PRs based on provider
    mr_pr_list=()

    if [[ "$PROVIDER" == "github" ]]; then
        output=""
        rc=0
        for attempt in 1 2 3; do
            log "Attempting to fetch GitHub PRs (attempt $attempt/3) for user: $RESPONDER_USER, repo: $REPO_OWNER_REPO"
            local gh_cmd=(
                setpriv --reuid="$RUN_USER" --regid="$RUN_USER" --init-groups \
                env HOME="$SYNC_HOME" GH_TOKEN="${GH_TOKEN:-}" \
                gh pr list --assignee "$RESPONDER_USER" --state open --json number,title,headRefName,url --repo "$REPO_OWNER_REPO"
            )
            rc=0
            output=$( "${gh_cmd[@]}" 2>"$STATE_DIR/gh_error.log" ) || rc=$?
            local gh_stderr=$(cat "$STATE_DIR/gh_error.log") || true

            if [[ $rc -eq 0 ]]; then
                if [[ -n "$output" && "$output" != "[]" ]]; then # Found PRs
                    break
                elif [[ "$output" == "[]" ]]; then # No PRs, but successful empty list
                    log "INFO: gh pr list returned an empty list for $RESPONDER_USER in $REPO_OWNER_REPO (rc=0)."
                    break
                fi
            fi

            if [[ $attempt -lt 3 ]]; then
                log "WARNING: gh pr list attempt $attempt failed (rc=$rc). Stderr: $gh_stderr. Output: $(echo "$output" | head -c 200). Retrying in 2s..."
                sleep 2
            fi
        done

        if [[ $rc -ne 0 ]]; then
            log "WARNING: gh pr list failed after 3 attempts (rc=$rc). Stderr: $gh_stderr. Output: $(echo "$output" | head -c 200)"
        elif [[ -z "$output" || "$output" == "[]" ]]; then
            log "No open PRs found for $RESPONDER_USER in $REPO_OWNER_REPO (output: '$output')"
        else
            local python_script=$(cat <<PYTHON_EOF
import sys, json

try:
    content = sys.stdin.read()
    start = content.find('[')
    if start != -1:
        data = json.loads(content[start:])
        for item in data:
            print(f"{item.get('number', '')}|{item.get('title', '')}|{item.get('headRefName', '')}|{item.get('url', '')}")
    else:
        print(f"ERROR: No JSON array start character '[' found in GitHub output. Content: {content[:200]}", file=sys.stderr)
except Exception as e:
    print(f"ERROR: Python parsing failed for GitHub: {e}. Content: {content[:200]}", file=sys.stderr)
PYTHON_EOF
            )
            mapfile -t mr_pr_list < <(echo "$output" | python3 -c "$python_script" 2>&1)
            if [[ ${#mr_pr_list[@]} -eq 0 ]]; then
                 log "WARNING: GitHub Python parsing returned empty list despite non-empty output. Output: $(echo "$output" | head -c 200)"
            fi
        fi
    elif [[ "$PROVIDER" == "gitlab" ]]; then
        output=""
        rc=0
        for attempt in 1 2 3; do
            log "Attempting to fetch GitLab MRs (attempt $attempt/3) for user: $RESPONDER_USER, repo: $REPO_OWNER_REPO"
            local glab_cmd=(
                setpriv --reuid="$RUN_USER" --regid="$RUN_USER" --init-groups \
                env HOME="$SYNC_HOME" GITLAB_TOKEN="${GITLAB_TOKEN:-}" \
                glab mr list --assignee "$RESPONDER_USER" --state opened --json iid,title,source_branch,web_url --repo "$REPO_OWNER_REPO"
            )
            rc=0
            output=$( "${glab_cmd[@]}" 2>"$STATE_DIR/glab_error.log" ) || rc=$?
            local glab_stderr=$(cat "$STATE_DIR/glab_error.log") || true

            if [[ $rc -eq 0 ]]; then
                if [[ -n "$output" && "$output" != "[]" ]]; then # Found MRs
                    break
                elif [[ "$output" == "[]" ]]; then # No MRs, but successful empty list
                    log "INFO: glab mr list returned an empty list for $RESPONDER_USER in $REPO_OWNER_REPO (rc=0)."
                    break
                fi
            fi

            if [[ $attempt -lt 3 ]]; then
                log "WARNING: glab mr list attempt $attempt failed (rc=$rc). Stderr: $glab_stderr. Output: $(echo "$output" | head -c 200). Retrying in 2s..."
                sleep 2
            fi
        done

        if [[ $rc -ne 0 ]]; then
            log "WARNING: glab mr list failed after 3 attempts (rc=$rc). Stderr: $glab_stderr. Output: $(echo "$output" | head -c 200)"
        elif [[ -z "$output" || "$output" == "[]" ]]; then
            log "No open MRs found for $RESPONDER_USER in $REPO_OWNER_REPO (output: '$output')"
        else
            local python_script=$(cat <<PYTHON_EOF
import sys, json

try:
    content = sys.stdin.read()
    start = content.find('[')
    if start != -1:
        data = json.loads(content[start:])
        for item in data:
            print(f"{item.get('iid', '')}|{item.get('title', '')}|{item.get('source_branch', '')}|{item.get('web_url', '')}")
    else:
        print(f"ERROR: No JSON array start character '[' found in GitLab output. Content: {content[:200]}", file=sys.stderr)
except Exception as e:
    print(f"ERROR: Python parsing failed for GitLab: {e}. Content: {content[:200]}", file=sys.stderr)
PYTHON_EOF
            )
            mapfile -t mr_pr_list < <(echo "$output" | python3 -c "$python_script" 2>&1)
            if [[ ${#mr_pr_list[@]} -eq 0 ]]; then
                 log "WARNING: GitLab Python parsing returned empty list despite non-empty output. Output: $(echo "$output" | head -c 200)"
            fi
        fi
    fi

    if [[ ${#mr_pr_list[@]} -eq 0 ]]; then
        log "No MRs/PRs found assigned to $RESPONDER_USER"
    else
        log "Found ${#mr_pr_list[@]} MR(s)/PR(s) assigned to $RESPONDER_USER"

        # Process each MR/PR
        for entry in "${mr_pr_list[@]}"; do
            IFS='|' read -r mr_pr_id title branch url <<< "$entry"

            if is_seen "$mr_pr_id"; then
                log "MR/PR #$mr_pr_id already processed, skipping"
                continue
            fi

            log "New MR/PR #$mr_pr_id: $title (branch: $branch) - triggering dispatcher"

            # Trigger the MR/PR dispatcher with retries
            python3 -c "
import socket, json, sys, time
for attempt in range(5):
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect('/run/mr-pr-dispatch.sock')
        msg = json.dumps({
            'mr_pr_id': '$mr_pr_id',
            'title': '$title',
            'branch': '$branch',
            'url': '$url',
            'provider': '$PROVIDER',
            'repo_url': '$GIT_REPO_URL'
        }).encode()
        s.sendall(msg)
        s.close()
        print(f'MR/PR dispatcher triggered successfully for #$mr_pr_id.')
        sys.exit(0)
    except Exception as e:
        if attempt < 4:
            time.sleep(1)
            continue
        print(f'WARNING: Failed to trigger MR/PR dispatcher after 5 attempts: {e}', file=sys.stderr)
        sys.exit(1)
" 2>&1 | while IFS= read -r line; do
                log "[dispatcher-trigger] $line"
            done

            if [[ ${PIPESTATUS[0]} -eq 0 ]]; then
                add_seen "$mr_pr_id"
            fi
        done
    fi

    log "Sync cycle completed"
}

# Start the sync daemon
log "Starting MR/PR sync daemon (workspace: $DEFAULT_WORKSPACE, interval: ${SYNC_INTERVAL}s)..."

# Wait for the MR/PR dispatch socket to be ready before initial sync (max 15 seconds)
if [[ "$RUN_ON_START" == "true" ]]; then
    SOCKET_PATH="/run/mr-pr-dispatch.sock"
    for i in {1..15}; do
        if [ -S "$SOCKET_PATH" ]; then
            log "MR/PR dispatch socket ready at $SOCKET_PATH"
            break
        fi
        if [[ $i -eq 15 ]]; then
            log "WARNING: MR/PR dispatch socket not ready after 15 seconds. Initial sync may fail."
        fi
        sleep 1
    done
    run_sync
fi

# Background loop
(
    while true; do
        sleep "$SYNC_INTERVAL"
        run_sync
    done
) > /tmp/mr-pr-sync.log 2>&1 &

echo $! > "$PID_FILE"
log "MR/PR sync daemon started (PID $(cat "$PID_FILE")). Log: /tmp/mr-pr-sync.log"