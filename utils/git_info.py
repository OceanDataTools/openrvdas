import os
import logging
import subprocess


def get_git_info(path="."):
    """
    Returns a dict:
        tag:         exact tag or `git describe --tags --always`
        remote_url:  URL of 'origin' or first remote
        branch:      current branch (None if detached)
        commit:      HEAD commit hash
    """

    def _run_git(args, cwd):
        """Run `git <args>` and return stripped stdout, or raise CalledProcessError."""
        return subprocess.check_output(
            ["git"] + args,
            cwd=cwd,
            stderr=subprocess.STDOUT,
            text=True
        ).strip()

    info = {"tag": None, "remote_url": None, "branch": None, "commit": None}

    abs_path = os.path.abspath(path)

    # --- Ensure inside a git repo ---
    try:
        _run_git(["rev-parse", "--is-inside-work-tree"], abs_path)
    except Exception:
        logging.error("Not a git repository: %s", abs_path)
        return info

    # --- Commit hash ---
    try:
        info["commit"] = _run_git(["rev-parse", "HEAD"], abs_path)
    except Exception as e:
        logging.error("Error getting commit hash: %s", e)

    # --- Branch name (safe) ---
    try:
        branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], abs_path)
        info["branch"] = branch if branch != "HEAD" else None  # detached HEAD
    except Exception:
        info["branch"] = None

    # --- Exact tag (`git tag --points-at HEAD`) ---
    try:
        tag_output = _run_git(["tag", "--points-at", "HEAD"], abs_path)
        if tag_output:
            info["tag"] = tag_output.splitlines()[0].strip()
        else:
            # Fallback: git describe
            try:
                info["tag"] = _run_git(["describe", "--tags", "--always"], abs_path)
            except Exception:
                info["tag"] = None
    except Exception:
        info["tag"] = None

    # --- Remote URL (origin preferred) ---
    try:
        remotes = _run_git(["remote"], abs_path).splitlines()
        if remotes:
            if "origin" in remotes:
                info["remote_url"] = _run_git(
                    ["remote", "get-url", "origin"], abs_path
                )
            else:
                # Use first remote
                info["remote_url"] = _run_git(
                    ["remote", "get-url", remotes[0]], abs_path
                )
    except Exception:
        info["remote_url"] = None

    return info


# -------------------------------------------------------------------------------------
# Stand-alone execution
# -------------------------------------------------------------------------------------
if __name__ == "__main__":
    print(get_git_info())
