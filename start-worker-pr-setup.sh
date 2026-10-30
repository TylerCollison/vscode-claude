#!/usr/bin/with-contenv bash
# Start the Worker PR/MR Setup step.
# Runs the one-shot setup that gives a beads-dispatched worker its draft
# PR/MR, which the worker killer then watches.
#
# The logic lives in /usr/local/bin/worker_pr_setup.py (unit-tested); this
# wrapper matches the pattern of start-worker-reaper.sh. The script is
# invoked via python3 rather than executed directly so it does not depend on
# the executable bit, and its failure must never abort the rest of the
# startup sequence (the agent still starts; the killer simply has no
# association until a PR exists).

set -euo pipefail

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log "Running worker PR/MR setup..."
python3 /usr/local/bin/worker_pr_setup.py || \
    log "WARNING: worker PR/MR setup exited non-zero — continuing startup"
log "Worker PR/MR setup finished"
