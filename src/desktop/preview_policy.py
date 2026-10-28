"""Pure URL policy shared by Qt interception tests and the native page."""
import re
from urllib.parse import urlsplit


def origin(url):
    parsed = urlsplit(url)
    if parsed.scheme not in ('http', 'https') or parsed.username or parsed.password:
        return None
    try:
        return (parsed.scheme, parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80))
    except ValueError:
        return None


def navigation_allowed(url, application, preview, main_frame):
    if main_frame:
        return origin(url) is not None and origin(url) == origin(application)
    if url == 'about:blank':
        return True
    return bool(preview and origin(url) == origin(preview) and re.match(r'^/p/[a-f0-9]{48}/', urlsplit(url).path))


def request_allowed(url, initiator, application, preview, main_frame=False):
    scheme = urlsplit(url).scheme
    if scheme in ('data', 'blob'):
        return True  # CSP further restricts these to the app's images/media.
    target = origin(url)
    if target is None:
        return False
    if target == origin(application):
        return main_frame or origin(initiator) == origin(application)
    return bool(preview and target == origin(preview) and re.match(r'^/p/[a-f0-9]{48}/', urlsplit(url).path))
