#!/usr/bin/with-contenv bash

set -euo pipefail

# Script to clone a git repository and combine specified markdown files
# Environment variables required:
# - GIT_REPO_URL: URL of git repository to clone (must start with http:// or https://)
# - MARKDOWN_FILES: Comma-separated list of markdown files to combine
# - DEFAULT_WORKSPACE: Destination directory for combined markdown file
# - GIT_BRANCH: Git branch to use (defaults to "main")

# Logging function with timestamps
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

# Error handling function
error_exit() {
    log "ERROR: $1"
    exit 1
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

if [ -z "${GIT_REPO_URL:-}" ]; then
    error_exit "GIT_REPO_URL environment variable is required"
fi

if [ -z "${MARKDOWN_FILES:-}" ]; then
    error_exit "MARKDOWN_FILES environment variable is required"
fi

if [ -z "${DEFAULT_WORKSPACE:-}" ]; then
    error_exit "DEFAULT_WORKSPACE environment variable is required"
fi

# Set default branch if not specified
GIT_BRANCH="${GIT_BRANCH:-main}"

# Validate GIT_REPO_URL format
if [[ ! "$GIT_REPO_URL" =~ ^https?:// ]]; then
    error_exit "GIT_REPO_URL must start with http:// or https://"
fi

# Validate DEFAULT_WORKSPACE directory exists and is writable
if [ ! -d "$DEFAULT_WORKSPACE" ]; then
    error_exit "DEFAULT_WORKSPACE directory '$DEFAULT_WORKSPACE' does not exist"
fi

if [ ! -w "$DEFAULT_WORKSPACE" ]; then
    error_exit "DEFAULT_WORKSPACE directory '$DEFAULT_WORKSPACE' is not writable"
fi

# Create process-specific temporary directory
TEMP_DIR="/tmp/git-repo-$$"
log "Creating temporary directory: $TEMP_DIR"
mkdir -p "$TEMP_DIR"

# Clone git repository
log "Cloning repository: $GIT_REPO_URL (branch: $GIT_BRANCH)"
if ! git clone --depth 1 --branch "$GIT_BRANCH" "$GIT_REPO_URL" "$TEMP_DIR" 2>/dev/null; then
    # Try without branch specification if branch doesn't exist
    log "Branch '$GIT_BRANCH' not found, trying default branch"
    if ! git clone --depth 1 "$GIT_REPO_URL" "$TEMP_DIR"; then
        error_exit "Failed to clone git repository"
    fi
fi

# Parse MARKDOWN_FILES into array
IFS=',' read -ra FILES_ARRAY <<< "$MARKDOWN_FILES"

# Validate each file exists in the cloned repository
log "Validating markdown files..."
for file_path in "${FILES_ARRAY[@]}"; do
    # Remove leading/trailing whitespace
    file_path=$(echo "$file_path" | xargs)

    if [ ! -f "$TEMP_DIR/$file_path" ]; then
        error_exit "File '$file_path' not found in repository"
    fi

    # Warn about files without .md/.markdown extensions
    if [[ ! "$file_path" =~ \.(md|markdown)$ ]]; then
        log "WARNING: File '$file_path' does not have .md or .markdown extension"
    fi

done

# Create combined markdown file
OUTPUT_FILE="$DEFAULT_WORKSPACE/CLAUDE.md"
log "Creating combined markdown file: $OUTPUT_FILE"

# Combine files in specified order
for file_path in "${FILES_ARRAY[@]}"; do
    file_path=$(echo "$file_path" | xargs)

    log "Adding file: $file_path"

    # Add file separator
    echo -e "\n---\n" >> "$OUTPUT_FILE"
    echo -e "## From: $file_path\n" >> "$OUTPUT_FILE"

    # Append file content
    cat "$TEMP_DIR/$file_path" >> "$OUTPUT_FILE"

    # Add extra separator between files
    echo -e "\n" >> "$OUTPUT_FILE"
done

log "Successfully created combined markdown file: $OUTPUT_FILE"
log "Processed ${#FILES_ARRAY[@]} markdown files"

# Cleanup will happen automatically via trap
exit 0