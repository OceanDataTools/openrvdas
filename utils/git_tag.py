import subprocess
import sys


def get_current_git_tag():
    """
    Get the current git tag. Returns the exact tag if HEAD is on a tag,
    otherwise returns a descriptive string like 'v1.2.3-5-gabcdef'.
    """
    try:
        # Try to get exact tag at current commit
        result = subprocess.run(
            ['git', 'describe', '--exact-match', '--tags'],
            capture_output=True,
            text=True,
            check=False
        )

        if result.returncode == 0:
            return result.stdout.strip()

        # If no exact tag, get descriptive tag
        result = subprocess.run(
            ['git', 'describe', '--tags', '--always'],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()

    except subprocess.CalledProcessError as e:
        print(f"Error getting git tag: {e}", file=sys.stderr)
        return None
    except FileNotFoundError:
        print("Git command not found. Is git installed?", file=sys.stderr)
        return None
