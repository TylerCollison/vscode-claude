#!/usr/bin/with-contenv bash
# Configure plugin installations from environment variables
#
# Automated plugin installer for standard plugin marketplaces
# (.claude-plugin/marketplace.json) and OpenCode plugin npm packages:
#
# - PLUGINS_MARKETPLACES  comma-separated marketplace git URLs, GitHub
#                         shorthands (owner/repo), or local paths; each must
#                         contain a .claude-plugin/marketplace.json manifest
# - PLUGINS               comma-separated plugin names (marketplace entry
#                         names) to install from those marketplaces
# - PLUGINS_SCOPE         user | project | both (default: user)
# - OPENCODE_PLUGINS      comma-separated OpenCode plugin npm packages,
#                         registered in the plugin array of opencode.json
#
# Plugin skills are installed copy-based into the harness discovery
# directories (.claude/skills and .agents/skills per scope), so they load in
# Claude Code, Codex, OpenCode, and any other agentskills.io-compatible
# harness without needing each harness's CLI. OpenCode npm plugins are
# registered by package name and installed by OpenCode itself (via Bun) at
# startup — nothing from this repo is published to npm.
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
# Both the harness-specific .claude directory and the cross-runtime .agents
# directory are populated for each scope: Claude Code discovers skills from
# ~/.claude/skills (verified with Claude Code 2.1.282) and OpenCode reads the
# same paths, while Codex and agentskills.io-compatible harnesses discover
# them from ~/.agents/skills.
USER_CLAUDE_SKILLS_DIR="/config/.claude/skills"
USER_AGENTS_SKILLS_DIR="/config/.agents/skills"
PROJECT_CLAUDE_SKILLS_DIR="$WORKSPACE/.claude/skills"
PROJECT_AGENTS_SKILLS_DIR="$WORKSPACE/.agents/skills"

# OpenCode global configuration (abc home is /config in linuxserver images)
# and the project-level config file
USER_OPENCODE_CONFIG="/config/.config/opencode/opencode.json"
PROJECT_OPENCODE_CONFIG="$WORKSPACE/opencode.json"

# Default marketplace: bundled with the image at /marketplace, falling back to
# the workspace checkout (the repo that ships this marketplace)
DEFAULT_MARKETPLACE_CANDIDATES=("/marketplace" "$WORKSPACE")

# Check if git is available (needed to clone marketplace repos)
check_git() {
    if ! command -v git >/dev/null 2>&1; then
        log_error "git not found in PATH"
        return 1
    fi
    return 0
}

# Check if jq is available (needed to read marketplace.json manifests)
check_jq() {
    if ! command -v jq >/dev/null 2>&1; then
        log_error "jq not found in PATH"
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

# Validate a plugin name — only marketplace entry names are allowed, which
# protects the rm -rf in install_skill_to_dir from path traversal
is_valid_plugin_name() {
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

# Resolve a marketplace entry to a local directory (the marketplace root).
# Standard marketplaces are git repositories or directories carrying a
# .claude-plugin/marketplace.json manifest. Git URLs are cloned into a
# temporary directory first; GitHub shorthands (owner/repo) are expanded to
# full clone URLs like the Claude Code plugin marketplaces.
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
        clone_dir=$(mktemp -d "${TMPDIR:-/tmp}/plugins-marketplace.XXXXXX") || {
            log_error "Failed to create temporary directory for marketplace: $entry"
            return 1
        }
        TMP_MARKETPLACE_DIRS+=("$clone_dir")

        if ! git clone --depth 1 "$entry" "$clone_dir" >/dev/null 2>&1; then
            log_error "Failed to clone plugins marketplace: $entry"
            rm -rf "$clone_dir"
            return 1
        fi
        root="$clone_dir"
    else
        if [ ! -d "$entry" ]; then
            log_error "Plugins marketplace path not found: $entry"
            return 1
        fi
        root="$entry"
    fi

    # Standard marketplaces carry a .claude-plugin/marketplace.json manifest
    # at the marketplace root
    if [ ! -f "$root/.claude-plugin/marketplace.json" ]; then
        log_error "Not a plugins marketplace (missing .claude-plugin/marketplace.json): $root"
        return 1
    fi

    RESOLVED_MARKETPLACE="$root"
    return 0
}

# Look up a plugin entry in a resolved marketplace's manifest and normalize
# its source to a JSON object. String sources (relative paths within the
# marketplace) are normalized to {"source":"relative","path":<string>}.
# Sets PLUGIN_SOURCE_JSON on success.
marketplace_lookup() {
    local marketplace_root="$1"
    local plugin_name="$2"
    local manifest="$marketplace_root/.claude-plugin/marketplace.json"

    local source_json
    source_json=$(jq -c --arg name "$plugin_name" \
        '(.plugins[] | select(.name == $name) | .source) // empty' "$manifest" 2>/dev/null) || return 1

    if [ -z "$source_json" ]; then
        return 1
    fi

    PLUGIN_SOURCE_JSON=$(jq -c 'if type == "string" then {source: "relative", path: .} else . end' <<< "$source_json") || return 1
    return 0
}

# Resolve a plugin entry's source to a local plugin directory. Handles the
# standard source types: relative paths (within the marketplace root) and the
# git-based source objects — github (repo), git-subdir (url + path), and url —
# each with optional ref pinning. npm / archive / command sources are not
# supported by this installer (OpenCode npm packages are handled via
# OPENCODE_PLUGINS). Sets RESOLVED_PLUGIN_DIR on success.
resolve_plugin_source() {
    local marketplace_root="$1"
    local source_json="$2"

    local kind path url ref clone_dir plugin_dir

    kind=$(jq -r '.source' <<< "$source_json")
    case "$kind" in
        relative)
            path=$(jq -r '.path' <<< "$source_json")
            plugin_dir="$marketplace_root/$path"
            if [ ! -d "$plugin_dir" ]; then
                log_error "Plugin source path does not exist: $plugin_dir"
                return 1
            fi
            ;;
        github|git-subdir|url)
            url=$(jq -r 'if .source == "github" then "https://github.com/\(.repo).git" else .url end' <<< "$source_json")
            ref=$(jq -r '.ref // empty' <<< "$source_json")
            path=$(jq -r '.path // "."' <<< "$source_json")

            if [ -z "$url" ]; then
                log_error "Plugin source of type '$kind' has no url/repo"
                return 1
            fi

            clone_dir=$(mktemp -d "${TMPDIR:-/tmp}/plugins-source.XXXXXX") || {
                log_error "Failed to create temporary directory for plugin source: $url"
                return 1
            }
            TMP_MARKETPLACE_DIRS+=("$clone_dir")

            local clone_args=(--depth 1)
            if [ -n "$ref" ]; then
                clone_args=(--depth 1 --branch "$ref")
            fi
            if ! git clone "${clone_args[@]}" "$url" "$clone_dir" >/dev/null 2>&1; then
                log_error "Failed to clone plugin source: $url${ref:+ (ref $ref)}"
                rm -rf "$clone_dir"
                return 1
            fi

            plugin_dir="$clone_dir/$path"
            if [ ! -d "$plugin_dir" ]; then
                log_error "Plugin source path does not exist: $plugin_dir"
                return 1
            fi
            ;;
        *)
            log_error "Unsupported plugin source type '$kind' (this installer supports relative paths and git-based sources; OpenCode npm packages are handled via OPENCODE_PLUGINS)"
            return 1
            ;;
    esac

    RESOLVED_PLUGIN_DIR="$plugin_dir"
    return 0
}

# Install a single skill directory into the given skills directory
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

# Install a plugin from the first marketplace that lists it. Plugins are
# optional — a missing plugin is reported but never blocks the others. Each
# plugin's skills/ directories are copied into the harness discovery paths for
# the configured scope.
install_plugin() {
    local plugin_name="$1"

    if ! is_valid_plugin_name "$plugin_name"; then
        log_error "Invalid plugin name: '$plugin_name'"
        return 1
    fi

    local marketplace_root found=0
    for marketplace_root in "${RESOLVED_MARKETPLACES[@]}"; do
        if marketplace_lookup "$marketplace_root" "$plugin_name"; then
            found=1
            break
        fi
    done

    if [ $found -eq 0 ]; then
        log_error "Plugin not found in any marketplace: $plugin_name"
        return 1
    fi

    if ! resolve_plugin_source "$marketplace_root" "$PLUGIN_SOURCE_JSON"; then
        return 1
    fi

    log "Installing plugin: $plugin_name (from $RESOLVED_PLUGIN_DIR)"

    local skills_dir="$RESOLVED_PLUGIN_DIR/skills"
    if [ ! -d "$skills_dir" ]; then
        log "WARNING: Plugin has no skills directory: $RESOLVED_PLUGIN_DIR"
        return 0
    fi

    # Resolve the destination directories for the configured scope
    local dest_dirs=()
    case "$PLUGINS_SCOPE" in
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

    local install_failed=0 skill_dir dest_dir
    for dest_dir in "${dest_dirs[@]}"; do
        for skill_dir in "$skills_dir"/*/; do
            [ -d "$skill_dir" ] || continue
            if [ ! -f "$skill_dir/SKILL.md" ]; then
                log "WARNING: Skill directory has no SKILL.md: $skill_dir"
            fi
            install_skill_to_dir "$skill_dir" "$(basename "$skill_dir")" "$dest_dir" || install_failed=1
        done
    done

    if [ $install_failed -eq 0 ]; then
        log_success "Plugin installed: $plugin_name"
    fi
    return $install_failed
}

# Add a single npm package to the plugin array of an opencode.json config
# file (idempotent, preserves other config keys). OpenCode installs npm
# plugins itself (via Bun) at startup — nothing here is published to npm.
add_opencode_plugin() {
    local config="$1"
    local pkg="$2"
    local dir
    dir=$(dirname "$config")

    if ! mkdir -p "$dir"; then
        log_error "Failed to create OpenCode config directory: $dir"
        return 1
    fi

    if ! python3 - "$config" "$pkg" <<'PYEOF'
import json, sys

path, pkg = sys.argv[1], sys.argv[2]
try:
    with open(path) as f:
        config = json.load(f)
except FileNotFoundError:
    config = {}
except json.JSONDecodeError:
    sys.exit(2)

plugins = config.get("plugin", [])
if pkg not in plugins:
    plugins.append(pkg)
config["plugin"] = plugins

with open(path, "w") as f:
    json.dump(config, f, indent=2)
    f.write("\n")
PYEOF
    then
        log_error "Failed to register OpenCode plugin '$pkg' in $config (is the existing config valid JSON?)"
        return 1
    fi

    return 0
}

# Register OpenCode plugin npm packages in the opencode.json plugin array for
# the configured scope
install_opencode_plugins() {
    local plugins="$1"

    local configs=()
    case "$PLUGINS_SCOPE" in
        project)
            configs=("$PROJECT_OPENCODE_CONFIG")
            ;;
        both)
            configs=("$USER_OPENCODE_CONFIG" "$PROJECT_OPENCODE_CONFIG")
            ;;
        *)
            configs=("$USER_OPENCODE_CONFIG")
            ;;
    esac

    local install_failed=0 pkg config
    for config in "${configs[@]}"; do
        while IFS= read -r pkg; do
            [ -n "$pkg" ] || continue
            if add_opencode_plugin "$config" "$pkg"; then
                log_success "OpenCode plugin registered: $pkg ($config)"
            else
                install_failed=1
            fi
        done <<< "$plugins"
    done

    return $install_failed
}

# Remove temporary marketplace/source clones
cleanup_tmp_dirs() {
    if [ ${#TMP_MARKETPLACE_DIRS[@]} -gt 0 ]; then
        rm -rf "${TMP_MARKETPLACE_DIRS[@]}"
    fi
}

# Main execution function
main() {
    log "Starting plugins configuration"

    # Validate the installation scope
    PLUGINS_SCOPE="${PLUGINS_SCOPE:-user}"
    case "$PLUGINS_SCOPE" in
        user|project|both)
            ;;
        *)
            log_error "Invalid PLUGINS_SCOPE '$PLUGINS_SCOPE' (expected user, project, or both)"
            return 1
            ;;
    esac

    # Pre-flight checks
    if ! check_git; then
        log_error "Pre-flight check failed: git not available"
        return 1
    fi

    if ! check_jq; then
        log_error "Pre-flight check failed: jq not available"
        return 1
    fi

    # Parse marketplaces, plugins, and OpenCode npm plugins
    marketplaces=$(parse_env_var "PLUGINS_MARKETPLACES")
    local marketplace_parse_result=$?
    plugins=$(parse_env_var "PLUGINS")
    local plugins_parse_result=$?
    opencode_plugins=$(parse_env_var "OPENCODE_PLUGINS")
    local opencode_parse_result=$?

    # Nothing configured means nothing to do
    if [ $marketplace_parse_result -ne 0 ] && [ $plugins_parse_result -ne 0 ] && [ $opencode_parse_result -ne 0 ]; then
        log "No plugins marketplaces or plugins configured"
        return 0
    fi

    # Resolve each marketplace to a local directory (only needed when plugins
    # are requested — OpenCode npm packages need no marketplace). A marketplace
    # that fails to resolve is reported but never blocks the remaining ones.
    RESOLVED_MARKETPLACES=()
    TMP_MARKETPLACE_DIRS=()
    marketplace_failed=0

    if [ $plugins_parse_result -eq 0 ] && [ -n "$plugins" ]; then
        if [ $marketplace_parse_result -eq 0 ] && [ -n "$marketplaces" ]; then
            log "Processing PLUGINS_MARKETPLACES environment variable"
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
            # Fall back to the bundled marketplace when PLUGINS is set without
            # PLUGINS_MARKETPLACES
            log "No marketplaces configured — looking for the bundled marketplace"
            for candidate in "${DEFAULT_MARKETPLACE_CANDIDATES[@]}"; do
                if resolve_marketplace "$candidate"; then
                    RESOLVED_MARKETPLACES+=("$RESOLVED_MARKETPLACE")
                    log "Using bundled marketplace: $candidate"
                    break
                fi
            done
            if [ ${#RESOLVED_MARKETPLACES[@]} -eq 0 ]; then
                log_error "PLUGINS is set but no marketplace found (set PLUGINS_MARKETPLACES)"
                return 1
            fi
        fi

        if [ ${#RESOLVED_MARKETPLACES[@]} -eq 0 ]; then
            log_error "No plugins marketplaces could be resolved"
            cleanup_tmp_dirs
            return 1
        fi
    fi

    # Install plugins
    plugin_success=0
    plugin_failed=0
    if [ $plugins_parse_result -eq 0 ] && [ -n "$plugins" ]; then
        log "Processing PLUGINS environment variable"
        while IFS= read -r plugin; do
            if [ -n "$plugin" ]; then
                if install_plugin "$plugin"; then
                    plugin_success=$((plugin_success + 1))
                else
                    plugin_failed=$((plugin_failed + 1))
                fi
            fi
        done <<< "$plugins"
    fi

    # Register OpenCode plugin npm packages
    opencode_success=0
    opencode_failed=0
    if [ $opencode_parse_result -eq 0 ] && [ -n "$opencode_plugins" ]; then
        log "Processing OPENCODE_PLUGINS environment variable"
        if install_opencode_plugins "$opencode_plugins"; then
            while IFS= read -r pkg; do
                [ -n "$pkg" ] || continue
                opencode_success=$((opencode_success + 1))
            done <<< "$opencode_plugins"
        else
            opencode_failed=1
        fi
    fi

    cleanup_tmp_dirs

    # Final verification and status reporting
    log "Plugins configuration completed:"
    log "- Marketplaces: ${#RESOLVED_MARKETPLACES[@]} resolved, $marketplace_failed failed"
    log "- Plugins: $plugin_success successful, $plugin_failed failed"
    log "- OpenCode plugins: $opencode_success successful, $opencode_failed failed"

    # Determine overall success
    if [ $plugin_failed -eq 0 ] && [ $marketplace_failed -eq 0 ] && [ $opencode_failed -eq 0 ]; then
        log_success "All operations completed successfully"
        return 0
    else
        log_error "Some operations failed (marketplaces: $marketplace_failed, plugins: $plugin_failed, opencode plugins: $opencode_failed)"
        return 1
    fi
}

# Execute main function
main "$@"
