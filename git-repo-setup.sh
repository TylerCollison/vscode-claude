#!/usr/bin/with-contenv bash
# Script to automate git repository cloning and branch management
# Environment variables required:
# - GIT_REPO_URL: Repository URL (required)
# - DEFAULT_WORKSPACE: Target directory (optional, defaults to /workspace)
# - GIT_BRANCH_NAME: Branch name (optional, generates procedural name if not specified)
# - GIT_CHECKOUT_BASE_BRANCH: Base branch to create new branch from if target branch doesn't exist (optional, defaults to default branch/HEAD)

set -euo pipefail

# Use existing logging patterns from codebase
log() {
    if [[ "${LOGGING:-}" == "verbose" ]] || [[ "$1" == *"ERROR"* ]] || [[ "$1" == *"WARNING"* ]]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
    fi
}

# Error handling function
error_exit() {
    log "ERROR: $1" >&2
    exit 1
}

# Strip userinfo (user:token@) from a URL so embedded credentials in
# GIT_REPO_URL never reach log or error output.
strip_userinfo() {
    sed -E 's#^([a-zA-Z][a-zA-Z0-9+.-]*://)[^/@]*@#\1#' <<< "$1"
}

# Success logging function
log_success() {
    if [[ "${LOGGING:-}" == "verbose" ]]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') - SUCCESS: $1"
    fi
}

# Generate procedural branch name (YYYYMMDD-HHMMSS format)
generate_procedural_branch() {
    local timestamp=$(date '+%Y%m%d-%H%M%S')
    echo "claude-generated-$timestamp"
}

# Check if a branch exists (both locally and remotely)
branch_exists() {
    local repo_dir="$1"
    local branch_name="$2"

    # Check local branches
    if git -C "$repo_dir" show-ref --verify --quiet "refs/heads/$branch_name" 2>/dev/null; then
        return 0
    fi

    # Check remote branches
    if git -C "$repo_dir" show-ref --verify --quiet "refs/remotes/origin/$branch_name" 2>/dev/null; then
        return 0
    fi

    return 1
}

# Cleanup function
cleanup() {
    if [ -d "${TEMP_DIR:-}" ]; then
        log "Cleaning up temporary directory: $TEMP_DIR"
        rm -rf "$TEMP_DIR"
    fi
}

# Set up trap to ensure cleanup happens on exit
trap cleanup EXIT

# Validate environment variables
log "Validating environment variables..."

# Required environment variable
if [ -z "${GIT_REPO_URL:-}" ]; then
    error_exit "GIT_REPO_URL environment variable is required"
fi

# Validate repository URL format
if [[ ! "$GIT_REPO_URL" =~ ^https?:// ]]; then
    error_exit "Repository URL must start with http:// or https://: $(strip_userinfo "$GIT_REPO_URL")"
fi

# Optional environment variables with defaults
DEFAULT_WORKSPACE="${DEFAULT_WORKSPACE:-/workspace}"
GIT_BRANCH_NAME="${GIT_BRANCH_NAME:-}"
GIT_CHECKOUT_BASE_BRANCH="${GIT_CHECKOUT_BASE_BRANCH:-}"

# If no branch name specified, generate procedural name
if [ -z "$GIT_BRANCH_NAME" ]; then
    GIT_BRANCH_NAME=$(generate_procedural_branch)
    log "No branch specified, generating procedural branch name: $GIT_BRANCH_NAME"
fi

# Create process-specific temporary directory
TEMP_DIR="/tmp/git-setup-$$"
log "Creating temporary directory: $TEMP_DIR"
mkdir -p "$TEMP_DIR"

# Extract repository name from URL for target directory
TARGET_DIR="$DEFAULT_WORKSPACE"

# Check if target directory already exists
if [ -d "$TARGET_DIR" ]; then
    error_exit "Target directory '$TARGET_DIR' already exists"
fi

log "Preparing to clone repository:"
log "  URL: $(strip_userinfo "$GIT_REPO_URL")"
log "  Branch: $GIT_BRANCH_NAME"
if [ -n "$GIT_CHECKOUT_BASE_BRANCH" ]; then
    log "  Base branch (for new branch creation): $GIT_CHECKOUT_BASE_BRANCH"
fi
log "  Target: $TARGET_DIR"

# Clone repository (with submodules to reduce fetches; the post-checkout
# submodule update below is the authoritative sync point)
log "Cloning repository..."
if ! git clone --recurse-submodules "$GIT_REPO_URL" "$TARGET_DIR"; then
    error_exit "Failed to clone git repository: $(strip_userinfo "$GIT_REPO_URL")"
fi

log "Successfully cloned repository"

# Change to repository directory
cd "$TARGET_DIR"

# Handle branch operations
log "Processing branch '$GIT_BRANCH_NAME'..."

if branch_exists "$TARGET_DIR" "$GIT_BRANCH_NAME"; then
    # Reset branch first to ensure transition works
    git reset --hard

    # Branch exists, check it out
    log "Branch '$GIT_BRANCH_NAME' exists, checking out..."
    if ! git checkout "$GIT_BRANCH_NAME"; then
        error_exit "Failed to checkout branch '$GIT_BRANCH_NAME'"
    fi
else
    # Branch doesn't exist, create new branch
    log "Branch '$GIT_BRANCH_NAME' does not exist, creating new branch..."

    # If GIT_CHECKOUT_BASE_BRANCH is set, check it out first
    if [ -n "$GIT_CHECKOUT_BASE_BRANCH" ]; then
        log "Checking out base branch '$GIT_CHECKOUT_BASE_BRANCH' before creating new branch..."
        if ! git checkout "$GIT_CHECKOUT_BASE_BRANCH"; then
            error_exit "Failed to checkout base branch '$GIT_CHECKOUT_BASE_BRANCH'"
        fi
    fi

    # Create new branch from current HEAD (which is either the base branch or default branch)
    if ! git checkout -b "$GIT_BRANCH_NAME"; then
        error_exit "Failed to create branch '$GIT_BRANCH_NAME'"
    fi
fi

log "Branch '$GIT_BRANCH_NAME' is now active"

# Initialize submodules recursively. Runs after the branch checkout so
# submodules match the checked-out branch (the checkout can point submodules
# at different commits than the default-branch clone would have initialized).
# Unconditional: a fast no-op for repos without submodules.
log "Initializing submodules recursively..."
if ! git submodule update --init --recursive; then
    error_exit "Failed to initialize submodules recursively (private or unreachable submodule?): $(strip_userinfo "$GIT_REPO_URL")"
fi

# ---------------------------------------------------------------------------
# Configure git credentials from environment variables
# ---------------------------------------------------------------------------
log "Configuring git credentials from environment variables..."

# ---------------------------------------------------------------------------
# Step 1: If GIT_TOKEN + GIT_USER are explicitly set, use those (override host)
# ---------------------------------------------------------------------------
if [[ -n "${GIT_TOKEN:-}" && -n "${GIT_USER:-}" ]]; then
    CRED_ENV_NAME="${GIT_USER}"
    CRED_ENV_TOKEN="$GIT_TOKEN"
    log "Using GIT_TOKEN + GIT_USER (override mode)"
fi

# ---------------------------------------------------------------------------
# Step 2: If no override, detect host from GIT_REPO_URL and prefer appropriate token
# ---------------------------------------------------------------------------
if [[ -z "$CRED_ENV_TOKEN" ]]; then
    # Parse host from GIT_REPO_URL (strip userinfo if present)
    HOST_FROM_URL=$(echo "$GIT_REPO_URL" | sed -E 's#^https?://([^/:]+).*/#\1#')
    log "Detected host from GIT_REPO_URL: $HOST_FROM_URL"

    if [[ "$HOST_FROM_URL" == "github.com" ]]; then
        # Prefer GH_TOKEN / GITHUB_TOKEN for GitHub hosts
        if [[ -n "${GH_TOKEN:-}" ]]; then
            CRED_ENV_NAME="${GIT_USER:-oauth2}"
            CRED_ENV_TOKEN="$GH_TOKEN"
            log "Using GH_TOKEN for GitHub host"
        elif [[ -n "${GITHUB_TOKEN:-}" ]]; then
            CRED_ENV_NAME="${GIT_USER:-oauth2}"
            CRED_ENV_TOKEN="$GITHUB_TOKEN"
            log "Using GITHUB_TOKEN for GitHub host"
        fi
    elif [[ "$HOST_FROM_URL" == "gitlab.com" || -n "${GITLAB_HOST:-}" ]]; then
        # Prefer GITLAB_TOKEN for GitLab hosts (gitlab.com or self-hosted)
        if [[ -n "${GITLAB_TOKEN:-}" ]]; then
            CRED_ENV_NAME="${GITLAB_USER:-gitlab-token}"
            CRED_ENV_TOKEN="$GITLAB_TOKEN"
            log "Using GITLAB_TOKEN for GitLab host"
        fi
    fi
fi

# Fallback: if GITLAB_TOKEN was already set from the original check above,
# the earlier block would have caught it. But if we somehow got here without it,
# check once more as a safety net.
if [[ -z "$CRED_ENV_TOKEN" && -n "${GITLAB_TOKEN:-}" ]]; then
    CRED_ENV_NAME="${GITLAB_USER:-gitlab-token}"
    CRED_ENV_TOKEN="$GITLAB_TOKEN"
    log "Using GITLAB_TOKEN (fallback after host detection)"
fi

if [[ -n "$CRED_ENV_TOKEN" ]]; then
    # Configure credential helper that reads username/password from env vars at call time.
    # We export the vars so they're available when git invokes the helper.
    export GIT_REPO_SETUP_USER="$CRED_ENV_NAME"
    export GIT_REPO_SETUP_PASS="$CRED_ENV_TOKEN"
    git config --local credential.helper '!f() { echo "username=$GIT_REPO_SETUP_USER"; echo "password=$GIT_REPO_SETUP_PASS"; }; f'

    # Rewrite https remote URLs to embed the token for push.
    # This avoids storing the token in .git/config; instead the credential helper
    # reads the env vars at request time.
    git config --local --replace-all url."https://$CRED_ENV_NAME:@git.example.com/".insteadOf "git@git.example.com:" 2>/dev/null || true

    log "Credentials configured for push"
else
    log "No token env vars found (GITLAB_TOKEN, GIT_TOKEN, GH_TOKEN, GITHUB_TOKEN); "
    log "push will fail until credentials are provided (e.g. embed in GIT_REPO_URL: https://user:token@host/repo.git)"
fi

# Output success information
log_success "Git repository setup completed successfully"
log "Repository location: $TARGET_DIR"
log "Active branch: $GIT_BRANCH_NAME"
log "Remote URL: $(strip_userinfo "$GIT_REPO_URL")"

# Cleanup will happen automatically via trap
exit 0