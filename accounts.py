"""Account-scoped disk state, keyed by school origin and authenticated user ID."""
import hashlib
from urllib.parse import urlsplit
from persistence import read_json, write_json, remove_json


def school_origin(value):
    parsed = urlsplit(str(value).strip())
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Enter an HTTPS school address, such as https://school.example.edu.')
    if parsed.path not in ('', '/') or parsed.query or parsed.fragment:
        raise ValueError('Use the school address without a page path, query, or fragment.')
    port = f':{parsed.port}' if parsed.port and parsed.port != 443 else ''
    return f'https://{parsed.hostname.lower()}{port}'


def profile_key(origin, account_id):
    if not account_id:
        raise ValueError('Blackboard did not identify the signed-in account.')
    return hashlib.sha256((school_origin(origin) + '\n' + account_id).encode()).hexdigest()


def restore():
    import data
    record, _ = read_json(data.APP_DIR / 'active.json', {})
    key = str(record.get('key') or '') if isinstance(record, dict) else ''
    if len(key) == 64 and all(c in '0123456789abcdef' for c in key):
        data.use_profile(key)
    else:
        data.use_profile('signed-out')


def activate(origin, user, username):
    import data
    from blackboard.store import load_settings, save_settings
    key = profile_key(origin, str(user.get('id') or user.get('uuid') or ''))
    data.use_profile(key)
    # Migrate legacy dashboard/preferences only after verifying both identity and school.
    legacy, _ = read_json(data.APP_DIR / 'snapshot.json', {})
    legacy_settings, _ = read_json(data.APP_DIR / 'settings.json', {})
    if not data.SNAPSHOT_PATH.exists() and isinstance(legacy, dict) and legacy.get('user_id') == str(user.get('id') or user.get('uuid')):
        try:
            same_school = school_origin(legacy_settings.get('base_url', '')) == school_origin(origin)
        except ValueError:
            same_school = False
        if same_school:
            write_json(data.SNAPSHOT_PATH, legacy)
            write_json(data.SETTINGS_PATH, legacy_settings)
            remove_json(data.APP_DIR / 'snapshot.json')
            remove_json(data.APP_DIR / 'settings.json')
    settings = load_settings()
    settings.update(base_url=school_origin(origin), username=username)
    save_settings(settings)
    write_json(data.APP_DIR / 'active.json', {'key': key, 'offline': False}, backup=False)
    return key


def logout(keep_offline=False):
    import data
    import host
    import crawl
    from secure_storage import delete_secret
    crawl.cancel_job(wait=True)
    host.clear_cookies()
    delete_secret(data.GOOGLE_PATH)
    if keep_offline:
        record, _ = read_json(data.APP_DIR / 'active.json', {})
        record['offline'] = True
        write_json(data.APP_DIR / 'active.json', record, backup=False)
    else:
        remove_json(data.SNAPSHOT_PATH)
        remove_json(data.SNAPSHOT_PATH.with_name('dashboard.json'))
        remove_json(data.APP_DIR / 'active.json')
        data.use_profile('signed-out')


def is_offline():
    import data
    record, _ = read_json(data.APP_DIR / 'active.json', {})
    return bool(record.get('offline', False))
