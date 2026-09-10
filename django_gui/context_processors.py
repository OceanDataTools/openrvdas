from logger.utils.read_version import get_version


def openrvdas_version(request):
    """Make the OpenRVDAS release version available in every template context."""
    return {'openrvdas_version': get_version()}
