#!/usr/bin/with-contenv bash
# Script to automate git repository cloning and branch management
# Environment variables required:
# - GIT_REPO_URL: Repository URL (required)
# - DEFAULT_WORKSPACE: Target directory (optional, defaults to /workspace)
# - GIT_BRANCH_NAME: Branch name (optional, generates procedural name if not specified)

set -euo pipefail

# Use existing logging patterns from codebase
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

# Error handling function
error_exit() {
    log "ERROR: $1" >&2
    exit 1
}

# Success logging function
log_success() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - SUCCESS: $1"
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
    error_exit "Repository URL must start with http:// or https://: $GIT_REPO_URL"
fi

# Optional environment variables with defaults
DEFAULT_WORKSPACE="${DEFAULT_WORKSPACE:-/workspace}"
GIT_BRANCH_NAME="${GIT_BRANCH_NAME:-}"

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
log "  URL: $GIT_REPO_URL"
log "  Branch: $GIT_BRANCH_NAME"
log "  Target: $TARGET_DIR"

# Clone repository
log "Cloning repository..."
if ! git clone "$GIT_REPO_URL" "$TARGET_DIR"; then
    error_exit "Failed to clone git repository: $GIT_REPO_URL"
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
    # Branch doesn't exist, create new branch from current HEAD
    log "Branch '$GIT_BRANCH_NAME' does not exist, creating new branch..."
    if ! git checkout -b "$GIT_BRANCH_NAME"; then
        error_exit "Failed to create branch '$GIT_BRANCH_NAME'"
    fi
fi

log "Branch '$GIT_BRANCH_NAME' is now active"

# Set workspace permissions (following existing pattern)
log "Setting workspace permissions..."
chmod -R 777 "$DEFAULT_WORKSPACE/"

# Output success information
log_success "Git repository setup completed successfully"
log "Repository location: $TARGET_DIR"
log "Active branch: $GIT_BRANCH_NAME"
log "Remote URL: $GIT_REPO_URL"

# Cleanup will happen automatically via trap
exit 0