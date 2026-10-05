"""Local completion and ignore state shared by views and calendar export."""
def setting_keys(settings, name):
    keys = set()
    for item in settings.get(name) or []:
        if isinstance(item, str) and item:
            keys.add(item)
        elif isinstance(item, dict):
            if item.get('id'):
                keys.add(str(item['id']))
            keys.add(f"{item.get('course_id') or ''}::{str(item.get('title') or '').strip().lower()}")
    return keys


def flagged(item, keys):
    return item.id in keys or f'{item.course_id}::{(item.title or "").strip().lower()}' in keys


def effective(item, marked, ignored):
    manual = flagged(item, marked)
    base = getattr(item, 'status', 'todo') or 'todo'
    return {'id': item.id, 'status': 'submitted' if manual else base,
            'manual': manual, 'ignored': flagged(item, ignored)}
