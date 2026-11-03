from logger.utils.read_version import get_version

# Computed once at import time rather than per-request: the version can't
# change within a process's lifetime, and get_version() otherwise re-walks
# sys.path's *.dist-info on every call (and re-logs a warning on every
# request if the package isn't installed).
_VERSION = get_version()


def openrvdas_version(request):
    """Make the OpenRVDAS release version available in every template context."""
    return {'openrvdas_version': _VERSION}
