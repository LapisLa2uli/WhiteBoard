"""Obtain file lengths from metadata without consuming file bodies."""
from datetime import datetime, timedelta, timezone
import re
from urllib.parse import urlparse


def metadata_size(*sources):
    """Missing and zero-byte files must remain distinguishable."""
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in ('size', 'fileSize'):
            value = source.get(key)
            if isinstance(value, bool):
                continue
            if isinstance(value, int) and value >= 0:
                return value
            if isinstance(value, str) and re.fullmatch(r'[0-9]+', value):
                return int(value)
    return None


def size_from_headers(row, base_url):
    """Reject login/error pages, encoded lengths and partial-body lengths."""
    final = urlparse(str(row.get('final_url') or ''))
    base = urlparse(base_url)
    if final.scheme != 'https' or final.netloc.lower() != base.netloc.lower():
        return None
    if re.search(r'/login(?:[/.]|$)|/auth(?:[/.]|$)', final.path, re.I):
        return None
    headers = {str(k).lower(): str(v or '').strip() for k, v in (row.get('headers') or {}).items()}
    status = int(row.get('status') or 0)
    match = re.fullmatch(r'bytes 0-0/([0-9]+)', headers.get('content-range', ''), re.I)
    # HTML/JSON can be actual coursework files too. A valid range response
    # from the dedicated attachment download endpoint proves a file length;
    # ordinary HTML/JSON pages (including sign-in responses) do not.
    requested = urlparse(str(row.get('url') or '')).path
    attachment_range = (status == 206 and match and int(match[1]) > 0 and
                        re.fullmatch(r'/learn/api/public/v1/courses/[^/]+/contents/[^/]+/attachments/[^/]+/download', requested))
    mime = headers.get('content-type', '').split(';')[0].lower()
    if not mime:
        return None
    if mime in {'text/html', 'application/xhtml+xml'} and not attachment_range:
        return None
    if mime in {'application/json', 'application/xml', 'text/xml'} and not attachment_range and 'attachment' not in headers.get('content-disposition', '').lower():
        return None
    if headers.get('content-encoding', '').lower() not in ('', 'identity'):
        return None
    if status == 206:
        return int(match[1]) if match and int(match[1]) > 0 else None
    if status == 200:
        length = headers.get('content-length', '')
        return int(length) if re.fullmatch(r'[0-9]+', length) else None
    if status == 416 and headers.get('content-range', '').lower() == 'bytes */0':
        return 0
    return None


def enrich_file_sizes(session, nodes, *, now=None):
    getter = getattr(session, 'get_file_metadata_many', None)
    if not callable(getter):
        return
    now = now or datetime.now(timezone.utc)
    pending = []
    for node in nodes:
        if node.kind != 'file' or not node.download_path or node.size_known or node.size_bytes > 0:
            continue
        checked = node.size_checked_at
        if checked and checked.tzinfo and timedelta(0) <= now - checked < timedelta(days=1):
            continue
        pending.append(node)
    if not pending:
        return
    session._tell(f'Checking sizes for {len(pending)} files…', .73)
    paths = list(dict.fromkeys(n.download_path for n in pending))
    sizes = getter(paths)
    for node in pending:
        node.size_checked_at = now
        value = sizes.get(node.download_path)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            node.size_bytes = value
            node.size_known = True
