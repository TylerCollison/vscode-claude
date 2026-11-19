#!/usr/bin/with-contenv bash
# Configure plugin installations from environment variables
#
# Unified automated plugin installer: one set of variables makes plugins
# available across all agent harnesses, using each harness's native mechanism:
#
# - PLUGINS_MARKETPLACES  comma-separated plugin marketplaces (git URLs,
#                         GitHub shorthands (owner/repo), or local paths); each
#                         must contain a .claude-plugin/marketplace.json manifest
# - PLUGINS               comma-separated plugin names (marketplace entry
#                         names) to install from those marketplaces
# - PLUGINS_SCOPE         user | project | both (default: user)
# - OPENCODE_PLUGINS      comma-separated OpenCode plugin npm packages
#
# For each marketplace plugin:
# - Claude Code: the full plugin (skills, agents, hooks, MCP servers) is
#   installed through the Claude CLI — `claude plugin marketplace add` +
#   `claude plugin install name@marketplace`
# - Codex and OpenCode: the plugin's skills are copied into ~/.agents/skills
#   (per scope) — the cross-runtime discovery path both harnesses read
#
# For each OpenCode npm package:
# - OpenCode: registered in the plugin array of opencode.json (OpenCode
#   installs npm plugins itself, via Bun, at startup)
# - Claude Code: installed through the Claude CLI via a persistent
#   npm-source marketplace (/config/conx-npm-marketplace)
# - Codex: skills bundled in the npm package are copied into ~/.agents/skills
#
# Replaces configure-claude-plugins.sh (CLAUDE_MARKETPLACES / CLAUDE_PLUGINS),
# which is removed by this change.

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
# .agents/skills is the cross-runtime discovery path read by Codex and
# OpenCode; .claude/skills is read by Claude Code (and OpenCode). The Claude
# Code copy is only used as a fallback when the full plugin could not be
# installed through the Claude CLI — otherwise the CLI-installed plugin would
# make Claude Code load each skill twice.
USER_AGENTS_SKILLS_DIR="/config/.agents/skills"
USER_CLAUDE_SKILLS_DIR="/config/.claude/skills"
PROJECT_AGENTS_SKILLS_DIR="$WORKSPACE/.agents/skills"
PROJECT_CLAUDE_SKILLS_DIR="$WORKSPACE/.claude/skills"

# OpenCode configuration files (global — the abc home is /config in
# linuxserver images — and project-level)
USER_OPENCODE_CONFIG="/config/.config/opencode/opencode.json"
PROJECT_OPENCODE_CONFIG="$WORKSPACE/opencode.json"

# Persistent npm-source marketplace used to install OpenCode plugin npm
# packages in Claude Code (the Claude CLI installs plugins from marketplaces,
# so npm packages need a marketplace entry)
NPM_MARKETPLACE_DIR="/config/conx-npm-marketplace"
NPM_MARKETPLACE_NAME="conx-npm"

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
# Sets PLUGIN_SOURCE_JSON and PLUGIN_MARKETPLACE_NAME on success.
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

    local marketplace_name
    marketplace_name=$(jq -r '.name // empty' "$manifest" 2>/dev/null) || return 1
    if [ -z "$marketplace_name" ]; then
        return 1
    fi
    PLUGIN_MARKETPLACE_NAME="$marketplace_name"
    return 0
}

# Resolve a plugin entry's source to a local plugin directory. Handles the
# standard source types: relative paths (within the marketplace root), the
# git-based source objects — github (repo), git-subdir (url + path), and url —
# each with optional ref pinning, and npm packages (downloaded with npm pack).
# The resolved directory is what the copy-based installation (Codex/OpenCode)
# reads; Claude Code fetches the source itself when installing via the CLI.
# Sets RESOLVED_PLUGIN_DIR on success.
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
        npm)
            local pkg
            pkg=$(jq -r '.package // empty' <<< "$source_json")
            if [ -z "$pkg" ]; then
                log_error "Plugin source of type 'npm' has no package"
                return 1
            fi
            resolve_npm_package "$pkg" || return 1
            return 0
            ;;
        *)
            log_error "Unsupported plugin source type '$kind' (supported: relative paths, github/git-subdir/url objects, npm packages)"
            return 1
            ;;
    esac

    RESOLVED_PLUGIN_DIR="$plugin_dir"
    return 0
}

# Download an npm package into a temporary directory (npm pack + tar extract;
# the tarball's package/ root is the npm convention). Sets RESOLVED_PLUGIN_DIR
# on success.
resolve_npm_package() {
    local pkg="$1"
    local tmp_dir

    if ! command -v npm >/dev/null 2>&1; then
        log_error "npm not found in PATH (cannot fetch npm package: $pkg)"
        return 1
    fi

    tmp_dir=$(mktemp -d "${TMPDIR:-/tmp}/npm-plugin.XXXXXX") || {
        log_error "Failed to create temporary directory for npm package: $pkg"
        return 1
    }
    TMP_MARKETPLACE_DIRS+=("$tmp_dir")

    local tarball
    tarball=$(npm pack "$pkg" --pack-destination "$tmp_dir" 2>/dev/null | tail -1)
    if [ -z "$tarball" ] || [ ! -f "$tmp_dir/$tarball" ]; then
        log_error "Failed to download npm package: $pkg"
        return 1
    fi

    if ! tar -xzf "$tmp_dir/$tarball" -C "$tmp_dir"; then
        log_error "Failed to extract npm package: $pkg"
        return 1
    fi

    RESOLVED_PLUGIN_DIR="$tmp_dir/package"
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

# Install all of a plugin's skill directories into the given skills directory
install_plugin_skills_to_dir() {
    local skills_dir="$1"
    local dest_dir="$2"

    local install_failed=0 skill_dir
    for skill_dir in "$skills_dir"/*/; do
        [ -d "$skill_dir" ] || continue
        if [ ! -f "$skill_dir/SKILL.md" ]; then
            log "WARNING: Skill directory has no SKILL.md: $skill_dir"
        fi
        install_skill_to_dir "$skill_dir" "$(basename "$skill_dir")" "$dest_dir" || install_failed=1
    done
    return $install_failed
}

# Install a plugin through the Claude CLI at the configured scope(s)
claude_plugin_install() {
    local install_id="$1"
    local failed=0

    case "$PLUGINS_SCOPE" in
        project)
            claude plugin install "$install_id" --scope project || failed=1
            ;;
        both)
            claude plugin install "$install_id" --scope user || failed=1
            claude plugin install "$install_id" --scope project || failed=1
            ;;
        *)
            claude plugin install "$install_id" --scope user || failed=1
            ;;
    esac
    return $failed
}

# Remove stale .claude/skills copies of a plugin's skills (left by earlier
# copy-based fallback runs) after a successful Claude CLI install, so the
# skill is not loaded twice in Claude Code (plugin + plain skill)
cleanup_stale_claude_skills() {
    local skills_dir="$1"

    set_copy_dest_dirs

    local dest_dir skill_dir skill_name
    for dest_dir in "${CLAUDE_DEST_DIRS[@]}"; do
        for skill_dir in "$skills_dir"/*/; do
            [ -d "$skill_dir" ] || continue
            skill_name=$(basename "$skill_dir")
            if [ -d "$dest_dir/$skill_name" ]; then
                rm -rf "${dest_dir:?}/$skill_name"
                log "Removed stale Claude Code skill copy: $dest_dir/$skill_name"
            fi
        done
    done
    return 0
}

# Set OPENCODE_CONFIGS to the opencode.json files for the configured scope
set_opencode_configs() {
    OPENCODE_CONFIGS=()
    case "$PLUGINS_SCOPE" in
        project)
            OPENCODE_CONFIGS=("$PROJECT_OPENCODE_CONFIG")
            ;;
        both)
            OPENCODE_CONFIGS=("$USER_OPENCODE_CONFIG" "$PROJECT_OPENCODE_CONFIG")
            ;;
        *)
            OPENCODE_CONFIGS=("$USER_OPENCODE_CONFIG")
            ;;
    esac
}

# Set AGENTS_DEST_DIRS and CLAUDE_DEST_DIRS to the skill directories for the
# configured scope
set_copy_dest_dirs() {
    case "$PLUGINS_SCOPE" in
        project)
            AGENTS_DEST_DIRS=("$PROJECT_AGENTS_SKILLS_DIR")
            CLAUDE_DEST_DIRS=("$PROJECT_CLAUDE_SKILLS_DIR")
            ;;
        both)
            AGENTS_DEST_DIRS=("$USER_AGENTS_SKILLS_DIR" "$PROJECT_AGENTS_SKILLS_DIR")
            CLAUDE_DEST_DIRS=("$USER_CLAUDE_SKILLS_DIR" "$PROJECT_CLAUDE_SKILLS_DIR")
            ;;
        *)
            AGENTS_DEST_DIRS=("$USER_AGENTS_SKILLS_DIR")
            CLAUDE_DEST_DIRS=("$USER_CLAUDE_SKILLS_DIR")
            ;;
    esac
}

# Maintain the persistent npm-source marketplace used to install OpenCode
# plugin npm packages in Claude Code: every requested package gets an entry
# with an npm source (idempotent, existing entries are kept) and the
# marketplace is registered with the Claude CLI (idempotent)
ensure_npm_marketplace() {
    local packages="$1"
    local manifest="$NPM_MARKETPLACE_DIR/.claude-plugin/marketplace.json"

    if ! mkdir -p "$NPM_MARKETPLACE_DIR/.claude-plugin"; then
        log_error "Failed to create npm marketplace directory: $NPM_MARKETPLACE_DIR"
        return 1
    fi

    if ! python3 - "$manifest" "$packages" <<'PYEOF'
import json, sys

path, packages = sys.argv[1], [p.strip() for p in sys.argv[2].split(",") if p.strip()]
try:
    with open(path) as f:
        manifest = json.load(f)
except FileNotFoundError:
    manifest = {"name": "conx-npm", "owner": {"name": "ClaudeConX"}, "plugins": []}
except json.JSONDecodeError:
    sys.exit(2)

manifest.setdefault("name", "conx-npm")
manifest.setdefault("owner", {"name": "ClaudeConX"})
plugins = manifest.get("plugins", [])
existing = {p.get("name") for p in plugins if isinstance(p, dict)}
for pkg in packages:
    if pkg not in existing:
        plugins.append({"name": pkg, "source": {"source": "npm", "package": pkg}})
manifest["plugins"] = plugins

with open(path, "w") as f:
    json.dump(manifest, f, indent=2)
    f.write("\n")
PYEOF
    then
        log_error "Failed to update npm marketplace manifest: $manifest"
        return 1
    fi

    if ! claude plugin marketplace add "$NPM_MARKETPLACE_DIR"; then
        log_error "Failed to add npm marketplace to Claude Code: $NPM_MARKETPLACE_DIR"
        return 1
    fi

    return 0
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

# Make OpenCode plugin npm packages available across harnesses:
# 1. OpenCode: registered in the plugin array of opencode.json (per scope)
# 2. Claude Code: installed through the Claude CLI via the persistent
#    npm-source marketplace
# 3. Codex: skills bundled in the npm packages are copied into
#    ~/.agents/skills (and Claude Code too when the CLI is missing)
install_opencode_plugins() {
    local plugins="$1"
    local install_failed=0 pkg

    set_opencode_configs

    # 1. OpenCode registration
    local config
    for config in "${OPENCODE_CONFIGS[@]}"; do
        while IFS= read -r pkg; do
            [ -n "$pkg" ] || continue
            if add_opencode_plugin "$config" "$pkg"; then
                log_success "OpenCode plugin registered: $pkg ($config)"
            else
                install_failed=1
            fi
        done <<< "$plugins"
    done

    # 2. Claude Code via the persistent npm-source marketplace
    if [ "$CLAUDE_CLI_AVAILABLE" -eq 1 ]; then
        if ensure_npm_marketplace "$plugins"; then
            while IFS= read -r pkg; do
                [ -n "$pkg" ] || continue
                if claude_plugin_install "$pkg@$NPM_MARKETPLACE_NAME"; then
                    log_success "OpenCode plugin installed in Claude Code: $pkg"
                else
                    log_error "Failed to install OpenCode plugin in Claude Code: $pkg"
                    install_failed=1
                fi
            done <<< "$plugins"
        else
            install_failed=1
        fi
    fi

    # 3. Codex: skills bundled in the npm packages
    set_copy_dest_dirs
    local skills_dir dest_dir
    while IFS= read -r pkg; do
        [ -n "$pkg" ] || continue
        if ! resolve_npm_package "$pkg"; then
            install_failed=1
            continue
        fi
        skills_dir="$RESOLVED_PLUGIN_DIR/skills"
        if [ ! -d "$skills_dir" ]; then
            log "OpenCode plugin provides no skills for Codex: $pkg"
            continue
        fi
        for dest_dir in "${AGENTS_DEST_DIRS[@]}"; do
            install_plugin_skills_to_dir "$skills_dir" "$dest_dir" || install_failed=1
        done
        if [ "$CLAUDE_CLI_AVAILABLE" -eq 0 ]; then
            for dest_dir in "${CLAUDE_DEST_DIRS[@]}"; do
                install_plugin_skills_to_dir "$skills_dir" "$dest_dir" || install_failed=1
            done
        fi
        log_success "OpenCode plugin skills installed for Codex: $pkg"
    done <<< "$plugins"

    return $install_failed
}

# Install a plugin from the first marketplace that lists it. Plugins are
# optional — a missing plugin is reported but never blocks the others. Claude
# Code gets the full plugin through the Claude CLI; Codex and OpenCode get the
# plugin's skills copied into the cross-runtime .agents discovery path.
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

    log "Installing plugin: $plugin_name (from $marketplace_root)"

    # Resolve the source locally — the copy-based installation (Codex and
    # OpenCode) reads it. Claude Code fetches the source itself when
    # installing via the CLI, so a failed local resolution only blocks the
    # copy-based part.
    local skills_dir="" resolved=0
    if resolve_plugin_source "$marketplace_root" "$PLUGIN_SOURCE_JSON"; then
        resolved=1
        skills_dir="$RESOLVED_PLUGIN_DIR/skills"
    fi

    # 1. Claude Code: the full plugin through the Claude CLI (the marketplace
    #    was registered in main; every standard source type is handled
    #    natively, including npm packages)
    local claude_installed=0 install_failed=0
    if [ "$CLAUDE_CLI_AVAILABLE" -eq 1 ]; then
        if claude_plugin_install "$plugin_name@$PLUGIN_MARKETPLACE_NAME"; then
            claude_installed=1
            # Clean stale .claude/skills copies left by earlier fallback runs
            # so Claude Code does not load each skill twice
            if [ "$resolved" -eq 1 ] && [ -d "$skills_dir" ]; then
                cleanup_stale_claude_skills "$skills_dir"
            fi
        else
            log_error "Claude Code plugin install failed: $plugin_name@$PLUGIN_MARKETPLACE_NAME"
            install_failed=1
        fi
    fi

    # 2. OpenCode: register the npm package when the plugin's source is npm
    if [ "$(jq -r '.source' <<< "$PLUGIN_SOURCE_JSON")" = "npm" ]; then
        local opencode_pkg config
        opencode_pkg=$(jq -r '.package // empty' <<< "$PLUGIN_SOURCE_JSON")
        if [ -n "$opencode_pkg" ]; then
            set_opencode_configs
            for config in "${OPENCODE_CONFIGS[@]}"; do
                if add_opencode_plugin "$config" "$opencode_pkg"; then
                    log_success "OpenCode plugin registered: $opencode_pkg ($config)"
                else
                    install_failed=1
                fi
            done
        fi
    fi

    # 3. Codex and OpenCode: copy the plugin's skills into the cross-runtime
    #    .agents path (both harnesses read it). When Claude Code did not get
    #    the plugin through the CLI, also copy into .claude/skills so its
    #    skills still load there.
    if [ "$resolved" -eq 1 ] && [ -d "$skills_dir" ]; then
        set_copy_dest_dirs

        local dest_dir
        for dest_dir in "${AGENTS_DEST_DIRS[@]}"; do
            install_plugin_skills_to_dir "$skills_dir" "$dest_dir" || install_failed=1
        done

        if [ "$claude_installed" -eq 0 ]; then
            for dest_dir in "${CLAUDE_DEST_DIRS[@]}"; do
                install_plugin_skills_to_dir "$skills_dir" "$dest_dir" || install_failed=1
            done
        fi
    elif [ "$resolved" -eq 1 ]; then
        log "Plugin has no skills directory (nothing to copy for Codex/OpenCode): $RESOLVED_PLUGIN_DIR"
    fi

    if [ $install_failed -eq 0 ]; then
        log_success "Plugin installed: $plugin_name"
    fi
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

    # Claude CLI availability (soft — when it is missing, plugins are
    # installed copy-based for every harness instead)
    CLAUDE_CLI_AVAILABLE=0
    if command -v claude >/dev/null 2>&1; then
        CLAUDE_CLI_AVAILABLE=1
        log "Claude CLI is available"
    else
        log "WARNING: Claude CLI not found in PATH — plugins will be installed copy-based for all harnesses"
    fi

    # Parse marketplaces, plugins, and OpenCode npm packages
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
                        # Register the marketplace with the Claude CLI so the
                        # full plugins can be installed through it. Uses the
                        # original entry (remote URL/shorthand/local path) —
                        # not the temporary clone, which is deleted below.
                        if [ "$CLAUDE_CLI_AVAILABLE" -eq 1 ]; then
                            if ! claude plugin marketplace add "$marketplace"; then
                                log_error "Failed to add Claude Code marketplace: $marketplace"
                                ((marketplace_failed++)) || true
                            fi
                        fi
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
                    if [ "$CLAUDE_CLI_AVAILABLE" -eq 1 ]; then
                        if ! claude plugin marketplace add "$candidate"; then
                            log_error "Failed to add Claude Code marketplace: $candidate"
                            ((marketplace_failed++)) || true
                        fi
                    fi
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

    # Make OpenCode plugin npm packages available across harnesses
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
