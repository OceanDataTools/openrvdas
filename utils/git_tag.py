import os
import logging

try:
    from git import Repo, InvalidGitRepositoryError, GitCommandError
    GIT_PYTHON_ENABLED = True
except ModuleNotFoundError:
    GIT_PYTHON_ENABLED = False


def get_current_git_tag(path="."):

    if not GIT_PYTHON_ENABLED:
        raise ModuleNotFoundError('get_current_git_tag(): GitPython is not installed. Please '
                                  'try "pip install GitPython" prior to use.')

    try:
        repo = Repo(os.path.abspath(path), search_parent_directories=True)
        commit = repo.commit("HEAD")

        # Try exact tag first
        tags = [tag for tag in repo.tags if tag.commit == commit]
        if tags:
            return tags[0].name

        # Otherwise mimic: git describe --tags --always
        try:
            return repo.git.describe('--tags', '--always').strip()
        except GitCommandError:
            return None

    except InvalidGitRepositoryError:
        logging.error("%s is Not a git repository", path)
        return None
    except Exception as err:
        logging.error("Error: %s", err)
        return None
