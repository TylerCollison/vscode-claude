---
name: claude-conx-mr-pr-dispatch
description: Use when you need to dispatch automated workers for Merge Request (GitLab) or Pull Request (GitHub) review and feedback. Trigger when the user asks to set up MR/PR dispatch, review a merge request, review a pull request, or configure automated code review workers.
---

# MR/PR Dispatch (ClaudeConX)

Automatically dispatch AI worker containers to review Merge Requests (GitLab) or Pull Requests (GitHub) and post feedback.

## Overview

The MR/PR Dispatch system monitors GitLab MRs and GitHub PRs, spawns worker containers to review changes, and posts comments/feedback directly on the MR/PR.

## Components

| Component | Description |
|-----------|-------------|
| `mr_pr_dispatch.py` | Main dispatcher daemon |
| `start-mr-pr-dispatch.sh` | Startup script |
| `start-mr-pr-sync.sh` | Sync daemon for webhook events |
| GitLab/GitHub webhooks | Trigger dispatch on MR/PR events |

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `GITLAB_TOKEN` | GitLab personal access token | For GitLab |
| `GITLAB_USER` | GitLab username | For GitLab |
| `GITHUB_TOKEN` | GitHub personal access token | For GitHub |
| `GITHUB_USER` | GitHub username | For GitHub |
| `DISPATCH_WORKER_IMAGE` | Worker container image | Yes |
| `DISPATCH_CONCURRENCY` | Max concurrent workers | Default: 3 |

### Webhook Setup

**GitLab:**
1. Go to Project → Settings → Webhooks
2. Add webhook URL: `https://your-server/mr-pr/webhook/gitlab`
3. Trigger on: Merge Request events (open, update, merge)
4. Secret token: Set `WEBHOOK_SECRET` env var

**GitHub:**
1. Go to Repository → Settings → Webhooks
2. Add webhook URL: `https://your-server/mr-pr/webhook/github`
3. Trigger on: Pull Request events (opened, synchronize, reopened)
4. Secret: Set `WEBHOOK_SECRET` env var

## Starting the Dispatcher

```bash
# Start dispatcher daemon
./start-mr-pr-dispatch.sh

# Start webhook sync daemon (separate process)
./start-mr-pr-sync.sh
```

## Worker Lifecycle

1. **Webhook received** → MR/PR event detected
2. **Dispatch queued** → Added to dispatcher queue
3. **Worker spawned** → Container started with `DISPATCH_WORKER_IMAGE`
4. **Repository cloned** → Worker clones repo at MR/PR commit
5. **Review executed** → Worker runs review (configured via `REVIEW_INSTRUCTIONS`)
6. **Feedback posted** → Comments posted to MR/PR via API
7. **Worker shutdown** → Container stopped and removed

## Review Instructions

Configure review behavior via `REVIEW_INSTRUCTIONS` environment variable or config file:

```bash
export REVIEW_INSTRUCTIONS="Review for security issues, performance problems, and code quality. Post inline comments on specific lines."
```

## Monitoring

```bash
# Check dispatcher status
curl http://localhost:8080/status

# List active workers
curl http://localhost:8080/workers

# View logs
journalctl -u mr-pr-dispatch -f
```

## Integration with Happier

- Each worker container registers as a machine on Happier server
- Machine name format: `mr-pr-<platform>-<repo>-<number>`
- Example: `mr-pr-github-myorg-myapp-123`
- Use `happier machine list` to see active review workers
- Use `happier session send` to communicate with running reviews

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Webhook not received | Check server accessibility; verify webhook secret; check firewall |
| Worker fails to start | Check `DISPATCH_WORKER_IMAGE` exists; verify Docker daemon; check concurrency limit |
| Review not posted | Verify API tokens have write permissions; check rate limits |
| Duplicate reviews | Check webhook deduplication; verify `mr_pr_dispatch.py` state |
| Worker stuck | Check worker logs; `happier run stop <run-id>`; increase timeout |

## Cross-Harness Notes

- **Discovery:** This skill follows agentskills.io discovery paths. Install to `~/.agents/skills/` for cross-harness availability, or to `<project>/.<harness>/skills/` for harness-specific installation.
- **Auto-loading:** Some harnesses auto-load on keywords like "MR dispatch", "PR dispatch", "merge request review", "pull request review", "code review automation"; others require explicit `skill` tool invocation.
- **Tool mapping:** Uses generic action language:
  - "run a shell command" → executes dispatcher scripts, `curl` for API calls
  - "read a file" → reads config, webhook payloads, worker logs
  - "write a file" → writes review instructions, config files
  - "fetch a URL" → calls GitLab/GitHub REST APIs, webhook endpoints
  - "search files" → searches repository code during review
- **No hardcoded harness list:** Works with ANY harness implementing agentskills.io spec.
- **Harness-specific caveats:**
  - This is a **server-side daemon** that manages worker containers
  - The harness may run inside workers (as the review agent) or outside (as the orchestrator)
  - Workers appear as Happier machines — harness-agnostic orchestration
  - GitLab/GitHub API calls are standard HTTP — works from any harness
  - Review instructions should use generic action language for worker harness compatibility