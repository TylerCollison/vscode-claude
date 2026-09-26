# ClaudeConX Plugins Marketplace

A standard plugins marketplace for the ClaudeConX container. Plugins package skills that teach AI agents (Claude Code, Codex, OpenCode, and any future harness) how to use container features. The marketplace follows the [Claude Code plugin marketplace](https://code.claude.com/docs/en/plugin-marketplaces) structure — a `.claude-plugin/marketplace.json` manifest listing plugins — and every skill follows the [agentskills.io](https://agentskills.io) specification for universal harness compatibility.

## Marketplace Structure

```
/ (marketplace root)
├── .claude-plugin/
│   └── marketplace.json                    # Marketplace manifest (name, owner, plugins)
└── plugins/
    ├── README.md                           # This file
    ├── claude-conx-build-env/              # Persistent build environment plugin
    │   ├── .claude-plugin/
    │   │   └── plugin.json                 # Plugin manifest (name, description, version)
    │   └── skills/
    │       └── claude-conx-build-env/
    │           └── SKILL.md
    ├── claude-conx-cconx/                  # cconx Docker management plugin
    ├── claude-conx-dispatch-beads/         # Manual Beads Dispatch trigger plugin
    ├── claude-conx-happier/                # Happier CLI orchestration plugin
    ├── claude-conx-litellm-health-check/   # LiteLLM health check plugin
    ├── claude-conx-shutdown/               # Container shutdown plugin
    └── ...more plugins as added
```

Each plugin is a directory with a `.claude-plugin/plugin.json` manifest; its skills live under `skills/<skill-name>/SKILL.md` following the agentskills.io specification. Each skill is a directory containing a single `SKILL.md` file.

## Installation

### Via Claude Code (Marketplace Install)

```bash
# Register the marketplace (git URL or owner/repo shorthand)
claude plugin marketplace add TylerCollison/vscode-claude

# Install a plugin by name (entry-name@marketplace-name)
claude plugin install claude-conx-happier@claude-conx
```

### Via Docker Environment Variables (Container Startup)

Set these environment variables when starting the container to auto-install plugins:

```bash
docker run -d \
  -e PLUGINS_MARKETPLACES="https://github.com/TylerCollison/vscode-claude.git" \
  -e PLUGINS="claude-conx-build-env,claude-conx-happier,claude-conx-dispatch-beads" \
  tylercollison2089/vscode-claude
```

**Environment Variables:**
- `PLUGINS_MARKETPLACES` — Comma-separated list of plugin marketplaces (git URLs, GitHub shorthands, or local paths). Each must contain a `.claude-plugin/marketplace.json` manifest
- `PLUGINS` — Comma-separated list of plugin names (marketplace entry names) to auto-install
- `PLUGINS_SCOPE` — Installation scope: `user` (default, `/config/.claude/skills/` and `/config/.agents/skills/` — the abc home in the container), `project` (`<workspace>/.claude/skills/` and `<workspace>/.agents/skills/`), or `both`
- `OPENCODE_PLUGINS` — Comma-separated list of OpenCode plugin npm packages to register (installed by OpenCode itself via Bun at startup)

When `PLUGINS` is set without `PLUGINS_MARKETPLACES`, the marketplace bundled in the container image at `/marketplace` is used automatically. Each plugin is installed from the first marketplace that lists it.

The container installer (`configure-plugins.sh`) installs plugin skills copy-based into **both** harness discovery directories per scope — `.claude/skills` (read by Claude Code and OpenCode) and `.agents/skills` (read by Codex and OpenCode) — so the skills work across harnesses without needing each harness's CLI. It also resolves the standard plugin source types (`github`, `git-subdir`, and `url` objects with optional `ref` pinning, in addition to relative paths within the marketplace).

### Manual Installation

```bash
# Clone the marketplace
git clone https://github.com/TylerCollison/vscode-claude.git /tmp/vscode-claude

# Install a specific skill (e.g., happier) — Claude Code discovers
# ~/.claude/skills (the .agents path is for other agentskills.io harnesses)
cp -r /tmp/vscode-claude/plugins/claude-conx-happier/skills/claude-conx-happier ~/.claude/skills/
```

## Cross-Harness Compatibility

The marketplace is designed to work with **any harness** that reads agentskills.io skill directories, including:

| Harness | Skill Discovery Paths | Auto-Load | Explicit Load |
|---------|----------------------|-----------|---------------|
| Claude Code | `~/.claude/skills/`, `.claude/skills/` (+ plugin mechanism) | Pattern matching | `skill` tool |
| Codex | `~/.agents/skills/`, `.agents/skills/` | Pattern matching | `skill` tool |
| OpenCode | `~/.config/opencode/skills/`, `.opencode/skills/`, `~/.claude/skills/`, `.claude/skills/`, `~/.agents/skills/`, `.agents/skills/` | Pattern matching | `skill` tool |
| Custom | `~/.agents/skills/`, `.agents/skills/` (cross-runtime alias) | Varies | Varies |

> **Note:** Claude Code (verified with 2.1.282) discovers skills from the `.claude` paths only — it does not read the `.agents` cross-runtime alias, so the container installer populates **both** paths for each scope.

> **Note:** OpenCode *plugins* (as opposed to skills) are JavaScript/TypeScript npm packages registered in the `plugin` array of `opencode.json` and installed by OpenCode itself (via Bun) at startup. This marketplace does not publish anything to npm — use the `OPENCODE_PLUGINS` environment variable to register OpenCode plugin npm packages from the npm registry.

### Discovery Paths (Priority Order)

1. **User-wide** (highest priority):
   - `~/.<harness>/skills/`
   - `~/.agents/skills/` (cross-runtime alias)
2. **Project-specific** (overrides user-wide):
   - `<project>/.<harness>/skills/`
   - `<project>/.agents/skills/`

### YAML Frontmatter (Required by All Harnesses)

Every skill **must** include these fields:

```yaml
---
name: <unique-skill-name>
description: Use when <specific trigger conditions>. <One-sentence summary of what this skill teaches.>
---
```

- `name`: Unique identifier (kebab-case, e.g., `claude-conx-happier`) — must match the skill's directory name
- `description`: Must start with "Use when..." and include specific triggers

## Generic Tool Mapping Table

Skills **MUST** use generic action language, NOT harness-specific tool names. Each harness maps these generic actions to its own tools:

| Generic Action | Description | Claude Code | Codex | OpenCode |
|----------------|-------------|-------------|-------|----------|
| `run a shell command` | Execute a command in the terminal | `Bash` tool | `shell` tool | `bash` tool |
| `read a file` | Read file contents | `Read` tool | `read` tool | `read` tool |
| `write a file` | Create or overwrite a file | `Write` tool | `write` tool | `write` tool |
| `edit a file` | Make targeted changes to a file | `Edit` tool | `edit` tool | `edit` tool |
| `search files` | Find files or content by pattern | `Grep`/`Glob` tools | `grep`/`glob` tools | `grep`/`glob` tools |
| `list directory` | List files in a directory | `Bash` with `ls` | `shell` with `ls` | `bash` with `ls` |
| `fetch a URL` | Retrieve content from a web URL | `WebFetch` tool | `webfetch` tool | `fetch` tool |
| `search the web` | Search the web for information | `WebSearch` tool | `websearch` tool | `search` tool |
| `invoke a skill` | Load another skill | `Skill` tool | `skill` tool | `skill` tool |
| `spawn an agent` | Launch a subagent for a task | `Agent` tool | `agent` tool | `agent` tool |
| `run a script` | Execute a script file | `Bash` with script path | `shell` with script path | `bash` with script path |

**⚠️ Rule:** Never use harness-specific tool names (like `Bash`, `Read`, `Edit`) in skill content. Always use the generic action from the left column.

## Cross-Harness Notes Template

Every skill **MUST** include a "Cross-Harness Notes" section documenting:

```markdown
## Cross-Harness Notes

- **Discovery:** This skill follows agentskills.io discovery paths. Install to `~/.agents/skills/` for cross-harness availability, or to `<project>/.<harness>/skills/` for harness-specific installation.
- **Auto-loading:** Some harnesses auto-load skills on keyword match; others require explicit invocation via the `skill` tool.
- **Tool mapping:** This skill uses generic action language (see table above). Each harness maps these to its native tools.
- **No hardcoded harness list:** This skill works with ANY harness implementing the agentskills.io spec.
- **Harness-specific caveats:** [Document any known issues or differences per harness here]
```

## Available Plugins

| Plugin | Description | Container Feature |
|-------|-------------|-------------------|
| `claude-conx-build-env` | Create persistent Docker build environments | `build-env` command |
| `claude-conx-happier` | Use Happier CLI for agent orchestration | Happier CLI |
| `claude-conx-dispatch-beads` | Manually trigger Beads Dispatch daemon | `dispatch-beads` command |
| `claude-conx-shutdown` | Gracefully shut down container with cleanup | `shutdown` command |
| `claude-conx-litellm-health-check` | Run LiteLLM health check to verify router and providers | `litellm-health-check.py` |
| `claude-conx-cconx` | Manage ClaudeConX Docker instances | `cconx` CLI |

*(More plugins added as container features are documented)*

## Creating New Plugins

To add a plugin to this marketplace:

1. **Create the plugin directory** under `/workspace/plugins/` with the plugin name (letters, numbers, and dashes only):
   ```bash
   mkdir -p /workspace/plugins/claude-conx-my-feature/.claude-plugin
   mkdir -p /workspace/plugins/claude-conx-my-feature/skills/claude-conx-my-feature
   ```

2. **Create the plugin manifest** at `.claude-plugin/plugin.json`:
   ```json
   {
     "name": "claude-conx-my-feature",
     "description": "One-line summary of the plugin",
     "version": "1.0.0",
     "author": {
       "name": "Your Name"
     }
   }
   ```

3. **Create `skills/claude-conx-my-feature/SKILL.md`** following the agentskills.io spec:
   ```markdown
   ---
   name: claude-conx-my-feature
   description: Use when <specific triggers>. <One-sentence summary>.
   ---
   
   # Skill Title
   
   ## Overview
   ...
   
   ## Cross-Harness Notes
   ...
   ```

4. **Register the plugin** in `.claude-plugin/marketplace.json` with a plugin entry (`name`, `description`, `source: "./plugins/claude-conx-my-feature"`)

5. **Validate** with `claude plugin validate` and by testing with at least 2 different harnesses

6. **Update this README** to include the new plugin in the Available Plugins table

## Plugin Requirements Checklist

- [ ] Plugin directory under `/workspace/plugins/` (letters, numbers, dashes only)
- [ ] Contains `.claude-plugin/plugin.json` manifest (`name`, `description`, `version`)
- [ ] Entry in `.claude-plugin/marketplace.json` matching the manifest `name`
- [ ] Contains `skills/<skill-name>/SKILL.md` with YAML frontmatter (`name`, `description`)
- [ ] `description` starts with "Use when..." and includes specific triggers
- [ ] Uses **generic action language** only (no harness-specific tool names)
- [ ] Includes "Cross-Harness Notes" section
- [ ] Documents installation, usage, and troubleshooting
- [ ] Tested with at least 2 harnesses
- [ ] Added to Available Plugins table in this README

## License

MIT License - See LICENSE in the main repository.

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) in the main repository for contribution guidelines.
