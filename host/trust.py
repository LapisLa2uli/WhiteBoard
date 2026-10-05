"""Only the packaged dashboard and tab strip may invoke native actions."""
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, unquote


def trusted_page(url):
    import data
    parsed = urlsplit(str(url))
    if parsed.scheme != 'file' or parsed.netloc not in ('', 'localhost'):
        return False
    path = unquote(parsed.path).replace('\\', '/').lower().lstrip('/')
    return any(path == (data.resource_root() / 'static' / name).as_posix().lower().lstrip('/') for name in ('index.html', 'tabs.html'))
