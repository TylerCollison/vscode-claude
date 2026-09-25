#!/usr/bin/with-contenv bash
# Configure skills marketplace installations from environment variables
#
# Parses SKILLS_MARKETPLACES (comma-separated marketplace URLs/paths) and
# SKILLS (comma-separated skill directory names) and installs each skill from
# the first marketplace that provides it. Installation follows the copy-based
# method described in skills/README.md, so the skills are plain directories
# readable by any agentskills.io-compatible harness (no Claude CLI needed).
#
# Complements the Claude Code plugin configuration in
# configure-claude-plugins.sh (CLAUDE_MARKETPLACES / CLAUDE_PLUGINS), which
# this script leaves untouched.

# Source container environment variables
if [ -d /run/s6/container_environment ]; then
    for file in /run/s6/container_environment/*; do
        if [ -f "$file" ]; then
            export "$(basename "$file")=$(cat "$file")"
        fi
    done
fi

# Logging function following existing patterns
log() {
    if [[ "${LOGGING:-}" == "verbose" ]] || [[ "$*" == *"ERROR"* ]] || [[ "$*" == *"WARNING"* ]]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') - $*"
    fi
}

# Error logging function
log_error() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ERROR: $*" >&2
}

# Success logging function
log_success() {
    if [[ "${LOGGING:-}" == "verbose" ]]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') - SUCCESS: $*"
    fi
}

WORKSPACE="${DEFAULT_WORKSPACE:-/workspace}"

# Skill installation destinations:
# - user-wide (the abc home in linuxserver images) — available to agents in all projects
# - project-specific — overrides user-wide for the workspace project
#
# Both the harness-specific .claude directory and the cross-harness .agents
# directory are populated for each scope: Claude Code discovers skills from
# ~/.claude/skills (verified with Claude Code 2.1.282), while
# agentskills.io-compatible harnesses discover them from ~/.agents/skills.
USER_CLAUDE_SKILLS_DIR="/config/.claude/skills"
USER_AGENTS_SKILLS_DIR="/config/.agents/skills"
PROJECT_CLAUDE_SKILLS_DIR="$WORKSPACE/.claude/skills"
PROJECT_AGENTS_SKILLS_DIR="$WORKSPACE/.agents/skills"

# Default marketplace: bundled with the image at /skills, falling back to the
# workspace checkout (the repo that ships this marketplace)
DEFAULT_MARKETPLACE_CANDIDATES=("/skills" "$WORKSPACE/skills")

# Check if git is available (needed to clone marketplace repos)
check_git() {
    if ! command -v git >/dev/null 2>&1; then
        log_error "git not found in PATH"
        return 1
    fi
    return 0
}

# Parse comma-separated environment variable
parse_env_var() {
    local var_name="$1"
    # Use indirect variable expansion
    local var_value="${!var_name:-}"

    if [ -z "$var_value" ]; then
        return 1
    fi

    # Remove leading/trailing whitespace and split by comma
    var_value=$(echo "$var_value" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    echo "$var_value" | tr ',' '\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | grep -v '^$'
}

# Check whether a marketplace entry is a git URL (as opposed to a local path)
is_git_url() {
    case "$1" in
        /*)
            return 1
            ;;
        *)
            return 0
            ;;
    esac
}

# Validate a skill name — only marketplace directory names are allowed, which
# protects the rm -rf in install_skill_to_dir from path traversal
is_valid_skill_name() {
    case "$1" in
        ""|.|..)
            return 1
            ;;
        *[!A-Za-z0-9._-]*)
            return 1
            ;;
        *)
            return 0
            ;;
    esac
}

# Resolve a marketplace entry to a local directory containing skill folders.
# Marketplaces may keep skills under a skills/ subdirectory (e.g. the
# vscode-claude repo) or directly in the given directory (e.g. /workspace/skills).
# Git URLs are cloned into a temporary directory first; GitHub shorthands
# (owner/repo) are expanded to full clone URLs like the plugin marketplaces.
# Sets RESOLVED_MARKETPLACE on success.
resolve_marketplace() {
    local entry="$1"
    local root=""

    if is_git_url "$entry"; then
        # Expand GitHub shorthand (owner/repo) to a full clone URL
        if [[ "$entry" =~ ^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$ ]]; then
            entry="https://github.com/$entry.git"
        fi

        local clone_dir
        clone_dir=$(mktemp -d "${TMPDIR:-/tmp}/skills-marketplace.XXXXXX") || {
            log_error "Failed to create temporary directory for marketplace: $entry"
            return 1
        }
        TMP_MARKETPLACE_DIRS+=("$clone_dir")

        if ! git clone --depth 1 "$entry" "$clone_dir" >/dev/null 2>&1; then
            log_error "Failed to clone skills marketplace: $entry"
            rm -rf "$clone_dir"
            return 1
        fi
        root="$clone_dir"
    else
        if [ ! -d "$entry" ]; then
            log_error "Skills marketplace path not found: $entry"
            return 1
        fi
        root="$entry"
    fi

    # Skills may live under a skills/ subdirectory (repo layout) or directly
    # in the marketplace directory
    if [ -d "$root/skills" ]; then
        root="$root/skills"
    fi

    RESOLVED_MARKETPLACE="$root"
    return 0
}

# Install a single skill into the given skills directory
install_skill_to_dir() {
    local skill_src="$1"
    local skill_name="$2"
    local dest_dir="$3"

    if ! mkdir -p "$dest_dir"; then
        log_error "Failed to create skills directory: $dest_dir"
        return 1
    fi

    # Replace any existing copy so restarts pick up marketplace updates
    rm -rf "${dest_dir:?}/${skill_name}"
    if ! cp -r "$skill_src" "${dest_dir:?}/${skill_name}"; then
        log_error "Failed to install skill '$skill_name' to $dest_dir"
        return 1
    fi

    return 0
}

# Install a skill from the first marketplace that provides it. Skills are
# optional — a missing skill is reported but never blocks the others.
install_skill() {
    local skill_name="$1"

    if ! is_valid_skill_name "$skill_name"; then
        log_error "Invalid skill name: '$skill_name'"
        return 1
    fi

    local marketplace_root skill_src found=0
    for marketplace_root in "${RESOLVED_MARKETPLACES[@]}"; do
        skill_src="$marketplace_root/$skill_name"
        if [ -d "$skill_src" ]; then
            found=1
            break
        fi
    done

    if [ $found -eq 0 ]; then
        log_error "Skill not found in any marketplace: $skill_name"
        return 1
    fi

    if [ ! -f "$skill_src/SKILL.md" ]; then
        log "WARNING: Skill directory has no SKILL.md: $skill_src"
    fi

    log "Installing skill: $skill_name (from $skill_src)"

    # Resolve the destination directories for the configured scope
    local dest_dirs=()
    case "$SKILLS_SCOPE" in
        project)
            dest_dirs=("$PROJECT_CLAUDE_SKILLS_DIR" "$PROJECT_AGENTS_SKILLS_DIR")
            ;;
        both)
            dest_dirs=("$USER_CLAUDE_SKILLS_DIR" "$USER_AGENTS_SKILLS_DIR" "$PROJECT_CLAUDE_SKILLS_DIR" "$PROJECT_AGENTS_SKILLS_DIR")
            ;;
        *)
            dest_dirs=("$USER_CLAUDE_SKILLS_DIR" "$USER_AGENTS_SKILLS_DIR")
            ;;
    esac

    local install_failed=0 dest_dir
    for dest_dir in "${dest_dirs[@]}"; do
        install_skill_to_dir "$skill_src" "$skill_name" "$dest_dir" || install_failed=1
    done

    if [ $install_failed -eq 0 ]; then
        log_success "Skill installed: $skill_name"
    fi
    return $install_failed
}

# Remove temporary marketplace clones
cleanup_tmp_dirs() {
    if [ ${#TMP_MARKETPLACE_DIRS[@]} -gt 0 ]; then
        rm -rf "${TMP_MARKETPLACE_DIRS[@]}"
    fi
}

# Main execution function
main() {
    log "Starting skills marketplace configuration"

    # Validate the installation scope
    SKILLS_SCOPE="${SKILLS_SCOPE:-user}"
    case "$SKILLS_SCOPE" in
        user|project|both)
            ;;
        *)
            log_error "Invalid SKILLS_SCOPE '$SKILLS_SCOPE' (expected user, project, or both)"
            return 1
            ;;
    esac

    # Pre-flight checks
    if ! check_git; then
        log_error "Pre-flight check failed: git not available"
        return 1
    fi

    # Parse marketplaces and skills
    marketplaces=$(parse_env_var "SKILLS_MARKETPLACES")
    local marketplace_parse_result=$?
    skills=$(parse_env_var "SKILLS")
    local skills_parse_result=$?

    # Skills are optional — nothing configured means nothing to do
    if [ $marketplace_parse_result -ne 0 ] && [ $skills_parse_result -ne 0 ]; then
        log "No skills marketplaces or skills configured"
        return 0
    fi

    if [ $skills_parse_result -ne 0 ] || [ -z "$skills" ]; then
        log "No skills configured (SKILLS unset) — nothing to install"
        return 0
    fi

    # Resolve each marketplace to a local directory. A marketplace that fails
    # to resolve is reported but never blocks the remaining ones.
    RESOLVED_MARKETPLACES=()
    TMP_MARKETPLACE_DIRS=()
    marketplace_failed=0

    if [ $marketplace_parse_result -eq 0 ] && [ -n "$marketplaces" ]; then
        log "Processing SKILLS_MARKETPLACES environment variable"
        while IFS= read -r marketplace; do
            if [ -n "$marketplace" ]; then
                if resolve_marketplace "$marketplace"; then
                    RESOLVED_MARKETPLACES+=("$RESOLVED_MARKETPLACE")
                    log "Marketplace resolved: $marketplace -> $RESOLVED_MARKETPLACE"
                else
                    ((marketplace_failed++)) || true
                fi
            fi
        done <<< "$marketplaces"
    else
        # Fall back to the bundled marketplace when SKILLS is set without
        # SKILLS_MARKETPLACES
        log "No marketplaces configured — looking for the bundled marketplace"
        for candidate in "${DEFAULT_MARKETPLACE_CANDIDATES[@]}"; do
            if [ -d "$candidate" ]; then
                RESOLVED_MARKETPLACES+=("$candidate")
                log "Using bundled marketplace: $candidate"
                break
            fi
        done
        if [ ${#RESOLVED_MARKETPLACES[@]} -eq 0 ]; then
            log_error "SKILLS is set but no marketplace found (set SKILLS_MARKETPLACES)"
            return 1
        fi
    fi

    if [ ${#RESOLVED_MARKETPLACES[@]} -eq 0 ]; then
        log_error "No skills marketplaces could be resolved"
        cleanup_tmp_dirs
        return 1
    fi

    # Install skills
    log "Processing SKILLS environment variable"
    skill_success=0
    skill_failed=0
    while IFS= read -r skill; do
        if [ -n "$skill" ]; then
            if install_skill "$skill"; then
                skill_success=$((skill_success + 1))
            else
                skill_failed=$((skill_failed + 1))
            fi
        fi
    done <<< "$skills"

    cleanup_tmp_dirs

    # Final verification and status reporting
    log "Skills configuration completed:"
    log "- Marketplaces: ${#RESOLVED_MARKETPLACES[@]} resolved, $marketplace_failed failed"
    log "- Skills: $skill_success successful, $skill_failed failed"

    # Determine overall success
    if [ $skill_failed -eq 0 ] && [ $marketplace_failed -eq 0 ]; then
        log_success "All operations completed successfully"
        return 0
    else
        log_error "Some operations failed (marketplaces: $marketplace_failed, skills: $skill_failed)"
        return 1
    fi
}

# Execute main function
main "$@"
