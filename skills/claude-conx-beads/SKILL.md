---
name: claude-conx-beads
description: Use when working in a repository that uses bd or Beads for durable project task tracking, issue dependencies, blocker management, multi-session handoff, or shared work memory. Trigger when the user asks to find ready work, claim or close tasks, create follow-up work, inspect blockers, recover project context, or choose between local planning and persistent project tracking.
---

# Beads (ClaudeConX)

Use Beads as the shared project task system. Local plans, scratch files, and personal memories are useful, but they are not the durable source of truth for project work.

## First Step

Run a shell command:

```bash
bd prime
```

If that prints nothing, check whether the repository has an active Beads workspace:

```bash
bd where
```

## Preferred Route

Use the `bd` CLI when shell access is available. It is the most compact and direct Beads interface.

## Core CLI Workflow

1. Find work:

```bash
bd ready
bd list --status=open
bd list --status=in_progress
```

2. Inspect before editing:

```bash
bd show <id>
```

3. Claim work atomically:

```bash
bd update <id> --claim
```

4. Create durable follow-up work when implementation reveals new tasks:

```bash
bd create "Short title" --description="Why this exists and what needs to be done" --type=task --priority=2
```

5. Close completed work:

```bash
bd close <id> --reason="Completed"
```

## What Belongs In Beads

Use Beads for:

- shared project tasks
- blockers and dependencies
- discovered follow-up work
- work that must survive thread reset, compaction, or handoff
- status that another person or agent should be able to resume

Use agent-local planning tools only for the current turn's execution checklist. Do not treat them as shared project state.

## Rules

- Do not create markdown TODO files as the source of truth when Beads is available.
- Do not use `bd edit`; it opens an interactive editor. Use `bd update` flags instead.
- Prefer `--json` when parsing `bd` output programmatically.
- If hooks are installed, `bd prime` may already be injected. Run it manually when context is missing.
- Do not auto-close or mutate tasks unless the work is actually complete.

## Container Integration

In the ClaudeConX container, Beads is pre-installed and available at `/usr/local/bin/bd`. The database is stored in `.beads/` within your workspace.

To initialize Beads in a workspace:

```bash
bd init
```

This will set up the Dolt database and connect to the configured remote (if any).

## Cross-Harness Notes

- **Discovery:** This skill follows agentskills.io discovery paths. Install to `~/.agents/skills/` for cross-harness availability, or to `<project>/.<harness>/skills/` for harness-specific installation (e.g., `.claude/skills/`, `.codex/skills/`, `.opencode/skills/`).
- **Auto-loading:** Some harnesses auto-load skills on keyword match (e.g., "beads", "bd", "task tracking"); others require explicit invocation via the `skill` tool.
- **Tool mapping:** This skill uses generic action language. Each harness maps these to its native tools:
  - "run a shell command" → `Bash` (Claude Code), `shell` (Codex), `bash` (OpenCode)
  - "read a file" → `Read` (Claude Code), `read` (Codex), `read` (OpenCode)
  - "write a file" → `Write` (Claude Code), `write` (Codex), `write` (OpenCode)
  - "edit a file" → `Edit` (Claude Code), `edit` (Codex), `edit` (OpenCode)
  - "search files" → `Grep`/`Glob` (Claude Code), `grep`/`glob` (Codex), `grep`/`glob` (OpenCode)
- **No hardcoded harness list:** This skill works with ANY harness implementing the agentskills.io spec.
- **Harness-specific caveats:** 
  - Claude Code: `bd prime` may be auto-injected via SessionStart hook
  - Codex: May require explicit `bd prime` call at session start
  - OpenCode: Verify `bd` is in PATH (pre-installed in ClaudeConX container)