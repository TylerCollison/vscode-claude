#!/usr/bin/env python3
"""MR/PR Responder Dispatch — dispatch a worker container when an MR/PR is assigned.

This daemon listens on a unix socket for MR/PR events and creates a worker
container to review/respond to the MR/PR.

Uses shared utilities from dispatch_utils.py.
"""

import json
import os
import signal
import socket
import sys
import threading

import dispatch_utils as du

# Short-circuit expensive imports when only type-checking.
# These are only used by the worker-cloning logic, which itself only runs
# inside the daemon.
import json
import os
import pwd
import re
import shutil
import subprocess
import time

SOCKET_PATH = "/run/mr-pr-dispatch.sock"


class Config:
    def __init__(self):
        self.workspace = du.env("DEFAULT_WORKSPACE", "/workspace")
        self.port_base = int(du.env("MR_PR_DISPATCH_PORT_BASE", "8100"))
        self.state_dir = du.env("MR_PR_DISPATCH_STATE_DIR", "/config/.mr-pr-dispatch")
        self.worker_port = int(du.env("MR_PR_DISPATCH_WORKER_PORT", "8443"))
        # Custom prompt for MR/PR responder, with placeholder replacement
        self.responder_prompt = du.env("MR_RESPONDER_PROMPT")
        # Placeholder for MR/PR ID in the prompt
        self.id_placeholder = du.env("MR_PR_ID_PLACEHOLDER", "{{MR_PR_ID}}")


def state_path(cfg):
    return os.path.join(cfg.state_dir, "state.json")


def default_mr_pr_prompt(mr_pr_id, title, branch, repo_url, provider):
    """Generate the default prompt for an MR/PR responder worker."""
    if provider == "github":
        cli = "gh"
        id_label = "Pull Request"
        cmd_prefix = "pr"
    else:
        cli = "glab"
        id_label = "Merge Request"
        cmd_prefix = "mr"

    return (
        "You are an AI assistant tasked with reviewing and responding to a %s.\n"
        "\n"
        "Context:\n"
        "- %s ID: %s\n"
        "- Title: %s\n"
        "- Branch: '%s'\n"
        "- Repository: %s\n"
        "\n"
        "Instructions:\n"
        "1. Use the `%s %s` commands to interact with the %s.\n"
        "2. First, examine the current state of the %s, including its description and any existing comments.\n"
        "3. **If there are NO comments yet**:\n"
        "   - Review the code changes thoroughly.\n"
        "   - Provide constructive feedback by adding comments directly on the %s.\n"
        "   - Suggest improvements or ask clarifying questions where necessary.\n"
        "4. **If there ARE existing comments**:\n"
        "   - Address each comment systematically.\n"
        "   - If a comment requires a code change: Implement the fix, commit it, and push to the branch.\n"
        "   - If a comment is a question or doesn't require code: Reply to the comment directly using the CLI.\n"
        "   - Ensure you acknowledge or address every piece of feedback.\n"
        "5. Your goal is to move the %s toward being ready for merge.\n"
        "\n"
        "Use the appropriate CLI tools as needed."
    ) % (id_label, id_label, mr_pr_id, title, branch, repo_url, cli, cmd_prefix, id_label, id_label, id_label, id_label)


def compose_worker_env(parent_env, branch, repo_url, mr_pr_id, dispatch_prompt=None):
    env = [e for e in parent_env if not e.startswith("GIT_BRANCH_NAME=")]
    env.append("GIT_BRANCH_NAME=%s" % branch)
    if repo_url:
        env = [e for e in env if not e.startswith("GIT_REPO_URL=")]
        env.append("GIT_REPO_URL=%s" % repo_url)
    env = [e for e in env if not e.startswith("MR_PR_ID=")]
    env.append("MR_PR_ID=%s" % mr_pr_id)
    env = [e for e in env if not e.startswith("BEADS_DISPATCH=")]
    env.append("BEADS_DISPATCH=false")
    # Inject the prompt if provided (or default)
    if dispatch_prompt:
        env = [e for e in env if not e.startswith("PROMPT=")]
        env.append("PROMPT=%s" % dispatch_prompt)
    return env


def dispatch_mr_pr_worker(mr_pr_info, cfg, self_info):
    """Dispatch a worker for an MR/PR. Returns True when handled."""
    mr_pr_id = mr_pr_info["mr_pr_id"]
    title = mr_pr_info["title"]
    branch = mr_pr_info["branch"]
    repo_url = mr_pr_info["repo_url"]
    provider = mr_pr_info["provider"]

    # Generate worker name
    slug = du.slugify(title)
    if slug:
        worker = "mr-pr-%s-%s" % (slug, mr_pr_id)
    else:
        worker = "mr-pr-%s" % mr_pr_id
    worker = re.sub(r"[^a-zA-Z0-9]+", "-", worker).strip("-").lower()[:120]

    git_user = du.env("MR_PR_DISPATCH_GIT_USER") or du.get_workspace_owner(cfg.workspace)

    if not repo_url:
        du.log("WARNING: no repo_url for MR/PR #%s — skipping" % mr_pr_id)
        return False

    port = du.find_free_host_port(cfg.port_base)
    if port is None:
        du.log("WARNING: no free host port >= %d — skipping MR/PR #%s" % (cfg.port_base, mr_pr_id))
        return False

    # Build the dispatch prompt: use override from config, or generate default
    if cfg.responder_prompt:
        prompt_template = cfg.responder_prompt
        dispatch_prompt = prompt_template.replace(cfg.id_placeholder, str(mr_pr_id))
    else:
        dispatch_prompt = default_mr_pr_prompt(mr_pr_id, title, branch, repo_url, provider)

    env_vars = compose_worker_env(self_info["env"], branch, repo_url, mr_pr_id,
                                  dispatch_prompt=dispatch_prompt)

    swarm = du.is_swarm_manager()
    if du.worker_exists(worker, swarm):
        du.log("Worker %s already exists for MR/PR #%s — skipping." % (worker, mr_pr_id))
        return True  # treated as handled (dedup)

    if swarm:
        du.log("Swarm manager detected — dispatching service %s for MR/PR #%s (branch %s)"
            % (worker, mr_pr_id, branch))
        rc, out, err = du.dispatch_swarm(worker, self_info["image"], env_vars, port,
                                          cfg.worker_port, mr_pr_id, net=self_info,
                                          labels={"mr_pr.id": mr_pr_id, "mr_pr.provider": provider})
    else:
        du.log("Local mode — dispatching container %s for MR/PR #%s (branch %s)"
            % (worker, mr_pr_id, branch))
        rc, out, err = du.dispatch_local(worker, self_info["image"], env_vars, port,
                                          cfg.worker_port, self_info.get("restart_policy", ""),
                                          mr_pr_id, net=self_info,
                                          labels={"mr_pr.id": mr_pr_id, "mr_pr.provider": provider})

    if rc != 0:
        du.log("ERROR: dispatch failed for MR/PR #%s: %s" % (mr_pr_id, err or out))
        return False
    du.log("Dispatched %s for MR/PR #%s — branch %s, http://localhost:%d"
        % (worker, mr_pr_id, branch, port))
    return True


def dispatch_mr_pr(cfg, self_info, mr_pr_info, seen):
    """Dispatch a worker for the MR/PR if not already seen."""
    mr_pr_id = mr_pr_info["mr_pr_id"]
    if mr_pr_id in seen:
        return 0

    if dispatch_mr_pr_worker(mr_pr_info, cfg, self_info):
        seen.add(mr_pr_id)
        du.save_state(state_path(cfg), seen)
        return 1
    return 0


def run_daemon(cfg, self_info, seen):
    """Listen on the unix socket; on each trigger, dispatch the MR/PR."""
    try:
        os.unlink(SOCKET_PATH)
    except OSError:
        pass
    try:
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(SOCKET_PATH)
        os.chmod(SOCKET_PATH, 0o666)
        srv.listen(16)
    except OSError as e:
        du.log("ERROR: cannot bind %s: %s" % (SOCKET_PATH, e))
        return 1

    stop = threading.Event()
    def _sig(_signum, _frame):
        stop.set()
    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)

    du.log("MR/PR dispatch daemon listening on %s (workspace=%s, image=%s)"
        % (SOCKET_PATH, cfg.workspace, self_info["image"]))
    srv.settimeout(1.0)
    while not stop.is_set():
        try:
            conn, _ = srv.accept()
        except socket.timeout:
            continue
        except OSError:
            if stop.is_set():
                break
            continue
        with conn:
            try:
                data = conn.recv(4096)
                if not data:
                    continue
                mr_pr_info = json.loads(data.decode())
            except Exception as e:
                du.log("ERROR: failed to parse MR/PR info: %s" % e)
                continue

        du.log("MR/PR trigger received: #%s (%s)" % (mr_pr_info.get("mr_pr_id", "unknown"), mr_pr_info.get("title", "")))
        try:
            dispatch_mr_pr(cfg, self_info, mr_pr_info, seen)
        except Exception as e:
            du.log("ERROR: unexpected error during MR/PR dispatch: %s" % str(e))

    try:
        os.unlink(SOCKET_PATH)
    except OSError:
        pass
    du.log("MR/PR dispatch daemon stopped.")
    return 0


def main(argv):
    cfg = Config()

    if du.env("MR_PR_DISPATCH") != "true":
        du.log("MR/PR dispatch not enabled (MR_PR_DISPATCH is not 'true'). Exiting.")
        return 0

    for binary in ("docker", "git", "python3", "gh", "glab"):
        if not shutil.which(binary):
            du.log("WARNING: %s not found on PATH. Exiting." % binary)
            return 0

    # Check for docker socket at both common locations
    docker_sock = None
    for sock in ("/var/run/docker.sock", "/run/docker.sock"):
        if os.path.exists(sock):
            docker_sock = sock
            break
    if not docker_sock:
        du.log("WARNING: Docker socket not found at /var/run/docker.sock or /run/docker.sock. Exiting.")
        return 0

    worker_image = du.env("MR_PR_WORKER_IMAGE")
    container_id = du.self_container_id()
    self_info = du.inspect_self(container_id) if container_id else None

    if not self_info:
        if worker_image:
            du.log("WARNING: could not inspect self, but MR_PR_WORKER_IMAGE is set. Using that.")
            self_info = {
                "image": worker_image,
                "env": list(os.environ),
                "dns": [],
                "dns_search": [],
                "dns_options": [],
                "extra_hosts": [],
            }
        else:
            du.log("ERROR: could not determine this container's image (is the docker socket mounted?). Provide MR_PR_WORKER_IMAGE to override. Exiting.")
            return 0
    elif worker_image:
        du.log("Using MR_PR_WORKER_IMAGE override: %s" % worker_image)
        self_info["image"] = worker_image

    seen = du.load_state(state_path(cfg))

    du.ensure_safe_directory(cfg.workspace)
    du.copy_abc_git_credentials(cfg.workspace)
    du.configure_credential_helpers()

    if "--once" in argv:
        n = dispatch_mr_pr(cfg, self_info, argv[1] if len(argv) > 1 else {}, seen)
        du.save_state(state_path(cfg), seen)
        du.log("One-shot dispatch complete (%d dispatched)." % n)
        return 0

    if "--daemon" in argv:
        return run_daemon(cfg, self_info, seen)

    # Default: run once
    n = dispatch_mr_pr(cfg, self_info, {}, seen)
    du.save_state(state_path(cfg), seen)
    du.log("One-shot dispatch complete (%d dispatched)." % n)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))