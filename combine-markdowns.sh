#!/usr/bin/with-contenv bash

set -euo pipefail

# Script to clone git repositories and combine specified markdown files
# Environment variables required:
# - KNOWLEDGE_REPOS: Structured configuration mapping repositories to files
#   Format: "url1:branch1:file1.md,file2.md;url2:branch2:file3.md;url3:file4.md"
#   Branch is optional - defaults to "main" if omitted
# - DEFAULT_WORKSPACE: Destination directory for combined markdown file

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

if [ -z "${KNOWLEDGE_REPOS:-}" ]; then
    error_exit "KNOWLEDGE_REPOS environment variable is required"
fi

if [ -z "${DEFAULT_WORKSPACE:-}" ]; then
    error_exit "DEFAULT_WORKSPACE environment variable is required"
fi

# Validate DEFAULT_WORKSPACE directory exists and is writable
if [ ! -d "$DEFAULT_WORKSPACE" ]; then
    error_exit "DEFAULT_WORKSPACE directory '$DEFAULT_WORKSPACE' does not exist"
fi

if [ ! -w "$DEFAULT_WORKSPACE" ]; then
    error_exit "DEFAULT_WORKSPACE directory '$DEFAULT_WORKSPACE' is not writable"
fi

# Parse repository configuration
log "Parsing repository configuration..."

# Parse repository configurations separated by ;
IFS=';' read -ra REPO_CONFIGS <<< "$KNOWLEDGE_REPOS"

# Initialize arrays for repository data
REPO_URLS=()
REPO_BRANCHES=()
REPO_FILES_LISTS=()

for ((i=0; i<${#REPO_CONFIGS[@]}; i++)); do
    config="${REPO_CONFIGS[i]}"
    config=$(echo "$config" | xargs)  # Remove leading/trailing whitespace

    # Skip empty configs
    if [ -z "$config" ]; then
        continue
    fi

    # Parse URL:branch:files or URL:files format
    # Parse from the end to handle URLs containing colons

    # We need to account for URLs containing colons (like https://)
    # Strategy: count separators added by our format

    # Count colons that are separators (not part of URL)
    # URLs with protocol have at least 2 colons (https: and //)
    # Our separators add 1 or 2 more colons

    # Extract files part (everything after last colon)
    files_part="${config##*:}"

    # Remove files part to get the remaining config
    remaining="${config%:*}"

    # Check if there's a branch specification
    # If remaining part ends with something that looks like a branch name
    # (not containing slashes, which would be part of URL path)
    if [[ "$remaining" =~ :[^/]+$ ]]; then
        # URL:branch:files format
        branch_part="${remaining##*:}"
        url_part="${remaining%:*}"

        REPO_URLS+=("$url_part")
        REPO_BRANCHES+=("$branch_part")
        REPO_FILES_LISTS+=("$files_part")
        log "Repository $((i+1)): $url_part (branch: $branch_part) - files: $files_part"
    else
        # URL:files format (no branch specified)
        url_part="$remaining"

        REPO_URLS+=("$url_part")
        REPO_BRANCHES+=("main")
        REPO_FILES_LISTS+=("$files_part")
        log "Repository $((i+1)): $url_part (branch: main) - files: $files_part"
    fi

    # Validate repository URL format
    if [[ ! "${REPO_URLS[-1]}" =~ ^https?:// ]]; then
        error_exit "Repository URL must start with http:// or https://: ${REPO_URLS[-1]}"
    fi
done

if [ ${#REPO_URLS[@]} -eq 0 ]; then
    error_exit "No valid repository configurations found in KNOWLEDGE_REPOS"
fi

log "Found ${#REPO_URLS[@]} repository configurations"

# Create process-specific temporary directory
TEMP_DIR="/tmp/git-repo-$$"
log "Creating temporary directory: $TEMP_DIR"
mkdir -p "$TEMP_DIR"

# Clone repositories
REPO_DIRS=()
for ((i=0; i<${#REPO_URLS[@]}; i++)); do
    repo_url="${REPO_URLS[i]}"
    repo_branch="${REPO_BRANCHES[i]}"
    repo_dir="$TEMP_DIR/repo-$i"
    REPO_DIRS+=("$repo_dir")

    log "Cloning repository $((i+1)): $repo_url (branch: $repo_branch)"

    if ! git clone --depth 1 --branch "$repo_branch" "$repo_url" "$repo_dir" 2>/dev/null; then
        # Try without branch specification if branch doesn't exist
        log "Branch '$repo_branch' not found for repository $((i+1)), trying default branch"
        if ! git clone --depth 1 "$repo_url" "$repo_dir"; then
            error_exit "Failed to clone git repository: $repo_url"
        fi
    fi
    log "Successfully cloned repository $((i+1))"
done

# Parse and validate files for each repository
FILES_ARRAY=()
REPO_INDICES=()

for ((i=0; i<${#REPO_URLS[@]}; i++)); do
    repo_dir="${REPO_DIRS[i]}"
    files_list="${REPO_FILES_LISTS[i]}"

    # Parse files list into array
    IFS=',' read -ra FILES_IN_REPO <<< "$files_list"

    # Validate each file exists in the cloned repository
    log "Validating files for repository $((i+1))..."
    for file_path in "${FILES_IN_REPO[@]}"; do
        # Remove leading/trailing whitespace
        file_path=$(echo "$file_path" | xargs)

        if [ ! -f "$repo_dir/$file_path" ]; then
            error_exit "File '$file_path' not found in repository ${REPO_URLS[i]}"
        fi

        # Warn about files without .md/.markdown extensions
        if [[ ! "$file_path" =~ \.(md|markdown)$ ]]; then
            log "WARNING: File '$file_path' does not have .md or .markdown extension"
        fi

        # Add to global files array with repository index
        FILES_ARRAY+=("$file_path")
        REPO_INDICES+=("$i")
    done
done

# Create combined markdown file
OUTPUT_FILE="$DEFAULT_WORKSPACE/CLAUDE.md"
log "Creating combined markdown file: $OUTPUT_FILE"

# Add header showing source repositories
echo "# Combined Documentation" > "$OUTPUT_FILE"
echo -e "\n## Source Repositories" >> "$OUTPUT_FILE"
for ((i=0; i<${#REPO_URLS[@]}; i++)); do
    echo "$((i+1)). ${REPO_URLS[i]} (branch: ${REPO_BRANCHES[i]})" >> "$OUTPUT_FILE"
done

# Combine files in specified order
for ((i=0; i<${#FILES_ARRAY[@]}; i++)); do
    file_path="${FILES_ARRAY[i]}"
    file_path=$(echo "$file_path" | xargs)
    repo_index="${REPO_INDICES[i]}"
    repo_url="${REPO_URLS[repo_index]}"

    log "Adding file: $file_path (from repository $((repo_index+1)))"

    # Add file separator
    echo -e "\n---\n" >> "$OUTPUT_FILE"
    echo -e "## From: $file_path\n" >> "$OUTPUT_FILE"
    echo -e "**Repository:** ${repo_url}\n" >> "$OUTPUT_FILE"

    # Append file content
    cat "${REPO_DIRS[repo_index]}/$file_path" >> "$OUTPUT_FILE"

    # Add extra separator between files
    echo -e "\n" >> "$OUTPUT_FILE"
done

# Set workspace permissions
chmod -R 777 "$DEFAULT_WORKSPACE/"

log "Successfully created combined markdown file: $OUTPUT_FILE"
log "Processed ${#FILES_ARRAY[@]} markdown files from ${#REPO_URLS[@]} repositories"

# Cleanup will happen automatically via trap
exit 0