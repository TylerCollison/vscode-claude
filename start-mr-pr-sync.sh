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
        seen=($(cat "$STATE_FILE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(' '.join(data.get('seen', [])))
except:
    pass
"))
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
import json
with open('$STATE_FILE', 'w') as f:
    json.dump({'seen': $seen}, f)
"
    }

    # Get MRs/PRs based on provider
    mr_pr_list=()

    if [[ "$PROVIDER" == "github" ]]; then
        log "Fetching GitHub PRs assigned to $RESPONDER_USER in $REPO_OWNER_REPO..."
        rc=0
        output=$(setpriv --reuid="$RUN_USER" --regid="$RUN_USER" --init-groups \
            env HOME="$SYNC_HOME" GH_TOKEN="${GH_TOKEN:-}" \
            gh pr list --assignee "$RESPONDER_USER" --state open --json number,title,headRefName,url --repo "$REPO_OWNER_REPO" 2>&1) || rc=$?

        if [[ $rc -eq 0 && -n "$output" && "$output" != "[]" ]]; then
            mr_pr_list=($(echo "$output" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for item in data:
        print(f\"{item['number']}|{item['title']}|{item['headRefName']}|{item['url']}\")
except:
    pass
"))
        fi
    elif [[ "$PROVIDER" == "gitlab" ]]; then
        log "Fetching GitLab MRs assigned to $RESPONDER_USER in $REPO_OWNER_REPO..."
        rc=0
        output=$(setpriv --reuid="$RUN_USER" --regid="$RUN_USER" --init-groups \
            env HOME="$SYNC_HOME" GITLAB_TOKEN="${GITLAB_TOKEN:-}" \
            glab mr list --assignee "$RESPONDER_USER" --state opened --json iid,title,source_branch,web_url --repo "$REPO_OWNER_REPO" 2>&1) || rc=$?

        if [[ $rc -eq 0 && -n "$output" && "$output" != "[]" ]]; then
            mr_pr_list=($(echo "$output" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for item in data:
        print(f\"{item['iid']}|{item['title']}|{item['source_branch']}|{item['web_url']}\")
except:
    pass
"))
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

            # Trigger the MR/PR dispatcher
            python3 -c "
import socket, json, sys
try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(1.0)
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
    print('MR/PR dispatcher triggered successfully for #$mr_pr_id.')
except Exception as e:
    print(f'WARNING: Failed to trigger MR/PR dispatcher: {e}', file=sys.stderr)
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

# Run initial sync if enabled
if [[ "$RUN_ON_START" == "true" ]]; then
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