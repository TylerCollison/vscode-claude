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
