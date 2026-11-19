# Claude Code conventions

## Bash tool calls: one JSON object per call

Each Bash tool invocation must contain a **single** JSON object with one set of parameters:

```json
// ✅ Correct — single command per call
{"command": "find /workspace -type f | head -10", "description": "List files"}

// ✅ Correct — chained shell operators in one command string
{"command": "find /workspace -type f && grep -rn 'pattern' /workspace", "description": "List files and grep"}

// ❌ Wrong — two JSON objects in one call (causes JSON parse error)
{"command": "find ...", "description": "List files"}{"command": "grep ...", "description": "Search files"}
```

If you need to run multiple independent commands, make separate Bash tool calls for each.

## Reading files

Prefer the `Read` tool over `cat`/`head`/`tail`/`sed` for reading file contents. The `Read` tool returns line-numbered output.

## File editing

Prefer `Edit` (targeted string replacement) over `Write` (full file overwrite) for incremental changes. Always `Read` a file before editing it — edits fail without a recent read.

## Testing changes

After making any code changes, rebuild the container and use it to verify the changes work correctly. Run the following commands:

```bash
# Rebuild the container
docker build -t test-container .

# Run the container to test changes
docker run --rm test-container
```

Ensure all tests pass before committing changes.

Once all tests pass and the changes are verified, commit and push the changes.

## Container Registry

After successful testing and verification, push the working container to the container registry at `registry.home.com`. Build the container with a tag following the format:

```
registry.home.com/system-utilities/container-registry/vscode-claude:<version>-amd64
```

Where `<version>` is a bump of the patch octet over the latest version in the `registry.home.com` container registry.

Authenticate with the container registry using the `GITLAB_TOKEN` and `GITLAB_USER` environment variables:

```bash
# Login to the container registry
echo "$GITLAB_TOKEN" | docker login registry.home.com -u "$GITLAB_USER" --password-stdin

# Build with the proper tag (replace <version> with the bumped patch version)
docker build -t registry.home.com/system-utilities/container-registry/vscode-claude:<version>-amd64 .

# Push to the registry
docker push registry.home.com/system-utilities/container-registry/vscode-claude:<version>-amd64
```

Ensure the container pushes successfully before considering the release complete.


<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:46cd31e7 -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/core-concepts/sync-concepts.md for details and anti-patterns.

## Agent Context Profiles

The managed Beads block is task-tracking guidance, not permission to override repository, user, or orchestrator instructions.

- **Conservative (default)**: Use `bd` for task tracking. Do not run git commits, git pushes, or Dolt remote sync unless explicitly asked. At handoff, report changed files, validation, and suggested next commands.
- **Minimal**: Keep tool instruction files as pointers to `bd prime`; use the same conservative git policy unless active instructions say otherwise.
- **Team-maintainer**: Only when the repository explicitly opts in, agents may close beads, run quality gates, commit, and push as part of session close. A current "do not commit" or "do not push" instruction still wins.

## Session Completion

This protocol applies when ending a Beads implementation workflow. It is subordinate to explicit user, repository, and orchestrator instructions.

1. **File issues for remaining work** - Create beads for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **Handle git/sync by active profile**:
   ```bash
   # Conservative/minimal/default: report status and proposed commands; wait for approval.
   git status

   # Team-maintainer opt-in only, unless current instructions forbid it:
   git pull --rebase
   bd dolt push
   git push
   git status
   ```
5. **Hand off** - Summarize changes, validation, issue status, and any blocked sync/commit/push step

**Critical rules:**
- Explicit user or orchestrator instructions override this Beads block.
- Do not commit or push without clear authority from the active profile or the current user request.
- If a required sync or push is blocked, stop and report the exact command and error.
<!-- END BEADS INTEGRATION -->
