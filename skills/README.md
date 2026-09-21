# ClaudeConX Skills Marketplace

A universal skills marketplace for the ClaudeConX container. Skills teach AI agents (Claude Code, Codex, OpenCode, and any future harness) how to use container features. All skills follow the [agentskills.io](https://agentskills.io) specification for universal harness compatibility.

## Quick Start

### Installation

#### For Users (Global Installation)

Install skills to your user-wide skill directory so they're available in all projects:

```bash
# Clone the marketplace
git clone https://github.com/TylerCollison/vscode-claude.git /tmp/vscode-claude

# Install a specific skill (e.g., happier)
cp -r /tmp/vscode-claude/skills/claude-conx-happier ~/.agents/skills/

# Or install all skills at once
cp -r /tmp/vscode-claude/skills/* ~/.agents/skills/
```

#### For Projects (Project-Specific Installation)

Install skills to a project's local skill directory:

```bash
# In your project root
mkdir -p .agents/skills

# Install a specific skill
cp -r /path/to/skills/claude-conx-happier .agents/skills/

# Or install all skills
cp -r /path/to/skills/* .agents/skills/
```

#### Via Docker Environment Variables (Container Startup)

Set these environment variables when starting the container to auto-install skills:

```bash
docker run -d \
  -e SKILLS_MARKETPLACES="https://github.com/TylerCollison/vscode-claude.git,/workspace/skills" \
  -e SKILLS="claude-conx-build-env,claude-conx-happier,claude-conx-dispatch-beads" \
  tylercollison2089/vscode-claude
```

**Environment Variables:**
- `SKILLS_MARKETPLACES` — Comma-separated list of marketplace URLs/paths (Git repos or local paths)
- `SKILLS` — Comma-separated list of skill directory names to auto-install

## Marketplace Structure

```
/workspace/skills/
├── README.md                    # This file
├── claude-conx-build-env/       # Persistent build environment skill
│   └── SKILL.md
├── claude-conx-happier/         # Happier CLI orchestration skill
│   └── SKILL.md
├── claude-conx-dispatch-beads/  # Manual Beads Dispatch trigger skill
│   └── SKILL.md
├── claude-conx-shutdown/        # Container shutdown skill
│   └── SKILL.md
├── claude-conx-litellm-health-check/  # LiteLLM health check skill
│   └── SKILL.md
├── claude-conx-cconx/           # cconx Docker management skill
│   └── SKILL.md
└── ...more skills as added
```

Each skill is a directory containing a single `SKILL.md` file following the agentskills.io specification.

## Universal Harness Compatibility

This marketplace is designed to work with **any harness** that implements the agentskills.io specification, including:

| Harness | Skill Discovery Paths | Auto-Load | Explicit Load |
|---------|----------------------|-----------|---------------|
| Claude Code | `~/.claude/skills/`, `.claude/skills/`, `~/.agents/skills/`, `.agents/skills/` | Pattern matching | `skill` tool |
| Codex | `~/.codex/skills/`, `.codex/skills/`, `~/.agents/skills/`, `.agents/skills/` | Pattern matching | `skill` tool |
| OpenCode | `~/.opencode/skills/`, `.opencode/skills/`, `~/.agents/skills/`, `.agents/skills/` | Pattern matching | `skill` tool |
| Custom | `~/.agents/skills/`, `.agents/skills/` (cross-runtime alias) | Varies | Varies |

### Discovery Paths (Priority Order)

1. **User-wide** (highest priority):
   - `~/.\<harness>/skills/`
   - `~/.agents/skills/` (cross-runtime alias)
2. **Project-specific** (overrides user-wide):
   - `<project>/.\<harness>/skills/`
   - `<project>/.agents/skills/`

### YAML Frontmatter (Required by All Harnesses)

Every skill **must** include these fields:

```yaml
---
name: <unique-skill-name>
description: Use when <specific trigger conditions>. <One-sentence summary of what this skill teaches.>
---
```

- `name`: Unique identifier (kebab-case, e.g., `claude-conx-happier`)
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

## Available Skills

| Skill | Description | Container Feature |
|-------|-------------|-------------------|
| `claude-conx-build-env` | Create persistent Docker build environments | `build-env` command |
| `claude-conx-happier` | Use Happier CLI for agent orchestration | Happier CLI |
| `claude-conx-dispatch-beads` | Manually trigger Beads Dispatch daemon | `dispatch-beads` command |
| `claude-conx-shutdown` | Gracefully shut down container with cleanup | `shutdown` command |
| `claude-conx-litellm-health-check` | Run LiteLLM health check to verify router and providers | `litellm-health-check.py` |
| `claude-conx-cconx` | Manage ClaudeConX Docker instances | `cconx` CLI |

*(More skills added as container features are documented)*

## Creating New Skills

To add a skill to this marketplace:

1. **Create a directory** under `/workspace/skills/` with the skill name (kebab-case, prefixed with `claude-conx-`):
   ```bash
   mkdir -p /workspace/skills/claude-conx-my-feature
   ```

2. **Create `SKILL.md`** following the agentskills.io spec:
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

3. **Validate** by testing with at least 2 different harnesses

4. **Update this README** to include the new skill in the Available Skills table

## Skill Requirements Checklist

- [ ] Directory named `claude-conx-<feature>` under `/workspace/skills/`
- [ ] Contains `SKILL.md` with YAML frontmatter (`name`, `description`)
- [ ] `description` starts with "Use when..." and includes specific triggers
- [ ] Uses **generic action language** only (no harness-specific tool names)
- [ ] Includes "Cross-Harness Notes" section
- [ ] Documents installation, usage, and troubleshooting
- [ ] Tested with at least 2 harnesses
- [ ] Added to Available Skills table in this README

## License

MIT License - See LICENSE in the main repository.

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) in the main repository for contribution guidelines.