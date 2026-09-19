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
