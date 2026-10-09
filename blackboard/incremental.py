"""Reconcile visible content and reuse enrichment for verified revisions.

Stored inside the account's atomic snapshot. Failed inventories cannot remove
cached items; absence must be confirmed by two complete course inventories.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlparse

from blackboard.models import ContentNode

VERSION = 1
PARSER_VERSION = 2
REVALIDATE_AFTER = timedelta(days=1)
FIELDS = 'id,parentId,created,modified,hasChildren'
MAX_ITEMS = 5000
MAX_PAGES = 30


def _check(session):
    check = getattr(session, '_check_cancelled', None)
    if check:
        check()


def _fresh(value, now):
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return timedelta(0) <= now - dt < REVALIDATE_AFTER
    except (TypeError, ValueError):
        return False


def _revision(item):
    from blackboard.api import parse_dt
    modified = item.get('modified')
    if not modified or parse_dt(modified) is None:
        return None
    return [modified, item.get('parentId') or item.get('_parentId') or '',
            item.get('created'), bool(item.get('hasChildren'))]


def _listings(session, requests):
    """Batch independent pagination chains, preserving explicit completeness."""
    from blackboard.api import _json_rows_for, _bb_pk
    result = {key: {'items': [], 'complete': False, 'status': 0} for key in requests}
    pending = dict(requests)
    seen = {key: set() for key in requests}
    ids = {key: set() for key in requests}
    for _ in range(MAX_PAGES):
        _check(session)
        batch = {}
        for key, path in pending.items():
            url, origin = urlparse(path), urlparse(session.base_url)
            if (url.netloc and (url.scheme, url.netloc) != (origin.scheme, origin.netloc)) or path in seen[key]:
                continue
            seen[key].add(path)
            batch[key] = path
        if not batch:
            break
        rows = _json_rows_for(session, list(batch.values()))
        _check(session)
        pending = {}
        for key, row in zip(batch, rows):
            state = result[key]
            state['status'] = int(row.get('status') or 0)
            data = row.get('data')
            if state['status'] != 200 or not isinstance(data, (dict, list)):
                continue
            page = data if isinstance(data, list) else data.get('results')
            if page is None and isinstance(data, dict):
                page = data.get('items', data.get('contents'))
            if not isinstance(page, list):
                continue
            # Overlaps can signal a changing inventory. Never prune from it.
            valid = True
            for item in page:
                iid = _bb_pk(item.get('id')) if isinstance(item, dict) else ''
                if not iid or iid in ids[key]:
                    valid = False
                    continue
                ids[key].add(iid)
                state['items'].append(item)
            if not valid or len(state['items']) > MAX_ITEMS:
                state['items'] = state['items'][:MAX_ITEMS]
                continue
            paging = (data.get('paging') or {}) if isinstance(data, dict) else {}
            if not isinstance(paging, dict):
                continue
            nxt = paging.get('nextPage') or paging.get('next') or ''
            if nxt:
                pending[key] = str(nxt)
            else:
                state['complete'] = True
    return result


def _inventory(session, course_ids, compact):
    """Prefer recursive listing; traverse accessible folders on fallback."""
    from blackboard.api import _is_folder_item

    def path(cid, folder='', recursive=False, internal=False):
        prefix = '/learn/api/v1' if internal else '/learn/api/public/v1'
        p = f'{prefix}/courses/{quote(cid, safe="")}/contents'
        if folder:
            p += f'/{quote(folder, safe="")}/children'
        p += '?limit=200&includeInActivityTracking=false'
        if recursive:
            p += '&recursive=true'
        if compact[cid]:
            p += '&fields=' + FIELDS
        return p

    roots = _listings(session, {c: path(c, recursive=True) for c in course_ids})
    fallback = [c for c in course_ids if not roots[c]['complete']]
    if fallback:
        plain = _listings(session, {c: path(c) for c in fallback})
        internal = [c for c in fallback if not plain[c]['complete']]
        if internal:
            alt = _listings(session, {c: path(c, internal=True) for c in internal})
            for c in internal:
                if alt[c]['complete']:
                    plain[c] = alt[c]
        for c in fallback:
            roots[c] = plain[c]
    visited = {c: set() for c in fallback}
    queue = {(c, x['id']) for c in fallback for x in roots[c]['items'] if _is_folder_item(x)}
    while queue:
        _check(session)
        batch = {}
        for c, folder in sorted(queue):
            if folder in visited[c]:
                continue
            if len(roots[c]['items']) >= MAX_ITEMS:
                roots[c]['complete'] = False
                continue
            visited[c].add(folder)
            batch[(c, folder)] = path(c, folder)
        if not batch:
            break
        scopes = _listings(session, batch)
        failed = [key for key, state in scopes.items() if not state['complete']]
        if failed:
            alt = _listings(session, {key: path(*key, internal=True) for key in failed})
            for key in failed:
                if alt[key]['complete']:
                    scopes[key] = alt[key]
        queue = set()
        for (c, folder), scope in scopes.items():
            roots[c]['complete'] &= scope['complete']
            known = {x['id'] for x in roots[c]['items']}
            for item in scope['items']:
                if item['id'] in known:
                    continue
                if len(roots[c]['items']) >= MAX_ITEMS:
                    roots[c]['complete'] = False
                    break
                item.setdefault('parentId', folder)
                roots[c]['items'].append(item)
                known.add(item['id'])
                if _is_folder_item(item):
                    queue.add((c, item['id']))
    return roots


def crawl(session, snapshot, courses, *, previous=None, full=False, include_html=True, now=None):
    from blackboard.api import (
        ContentEntry, _entry_from_content_item, content_nodes_from_items,
        _enrich_attachments_parallel, _merge_parallel_html, _json_rows_for, parse_dt,
    )
    now = now or datetime.now(timezone.utc)
    origin = session.base_url.rstrip('/').lower()
    old_cache = previous.content_cache if previous else {}
    if (old_cache.get('version') != VERSION or old_cache.get('origin') != origin
            or not snapshot.user_id or old_cache.get('user_id') != snapshot.user_id):
        old_cache = {}
    old_courses = old_cache.get('courses') or {}
    # Older app versions have nodes but no revision manifest. Preserve their
    # unobserved nodes until this school's course inventory confirms absence.
    legacy_allowed = bool(previous and previous.user_id == snapshot.user_id and
                          previous.courses and all(c.blackboard_url and
                          urlparse(c.blackboard_url).netloc.lower() == urlparse(origin).netloc
                          and urlparse(c.blackboard_url).scheme == 'https'
                          for c in previous.courses))
    # Preserve unselected courses when the user changes a load filter.
    cache = {'version': VERSION, 'origin': origin, 'user_id': snapshot.user_id,
             'courses': deepcopy(old_courses)}
    compact = {c.id: not full and old_courses.get(c.id, {}).get('parser_version') == PARSER_VERSION and bool(old_courses.get(c.id)) and
               _fresh(old_courses[c.id].get('checked'), now) for c in courses}
    session._tell('Checking course content for changes…', .34)
    inventories = _inventory(session, [c.id for c in courses], compact)
    stats = dict(reused=0, fetched=0, removed=0, pending_removal=0, incomplete_courses=0)
    states = {}
    details = []
    for course in courses:
        cid = course.id
        old = old_courses.get(cid) or {}
        records = deepcopy(old.get('records') or {})
        inv = inventories[cid]
        seen = {x['id'] for x in inv['items']}
        dirty = not compact[cid] or old.get('html') != include_html
        for iid in list(records):
            if iid in seen:
                records[iid]['missing'] = 0
            elif inv['complete']:
                records[iid]['missing'] = int(records[iid].get('missing') or 0) + 1
                if records[iid]['missing'] >= 2:
                    del records[iid]
                    stats['removed'] += 1
                    dirty = True
                else:
                    stats['pending_removal'] += 1
        states[cid] = {'records': records, 'complete': inv['complete'], 'dirty': dirty, 'groups': {}}
        for item in inv['items']:
            iid = item['id']
            record = records.get(iid)
            rev = _revision(item)
            if (compact[cid] and record and rev is not None and record.get('revision') == rev
                    and _fresh(record.get('checked'), now)):
                stats['reused'] += 1
                continue
            details.append((cid, iid, item))
    paths = [f'/learn/api/public/v1/courses/{quote(c, safe="")}/contents/{quote(i, safe="")}?includeInActivityTracking=false'
             for c, i, item in details if 'title' not in item]
    fetched = iter(_json_rows_for(session, paths))
    _check(session)
    for cid, iid, manifest in details:
        item = manifest
        if 'title' not in item:
            row = next(fetched)
            item = row.get('data') if row.get('status') == 200 else None
        if not isinstance(item, dict) or item.get('id') != iid or 'title' not in item:
            states[cid]['complete'] = False
            continue
        item = deepcopy(item)
        if manifest.get('parentId') and not item.get('parentId'):
            item['parentId'] = manifest['parentId']
        state = states[cid]
        state['dirty'] = True
        nodes = content_nodes_from_items([item], cid, session.base_url)
        state['records'][iid] = {'raw': item, 'revision': _revision(item),
                                  'checked': now.isoformat(), 'missing': 0}
        state['groups'][iid] = nodes
        stats['fetched'] += 1
    groups = [(cid, nodes) for cid, state in states.items() for nodes in state['groups'].values()]
    session._tell(f"Reusing {stats['reused']} unchanged items; loading {stats['fetched']} items…", .58)
    session._content_bodies_loaded = {
        (cid, iid) for cid, state in states.items() for iid in state['groups']
        if 'body' in state['records'][iid]['raw']
    }
    failed = _enrich_attachments_parallel(session, groups, session.base_url)
    for cid, iid in failed:
        state = states[cid]
        state['complete'] = False
        old = (old_courses.get(cid) or {}).get('records', {}).get(iid)
        if old:
            state['records'][iid] = deepcopy(old)
            state['groups'][iid] = [ContentNode.from_dict(n) for n in old.get('nodes', [])]
        else:
            state['records'][iid]['checked'] = ''
    _check(session)
    built = []
    for cid, state in states.items():
        records = state['records']
        for iid, record in records.items():
            if iid not in state['groups']:
                state['groups'][iid] = [ContentNode.from_dict(x) for x in record.get('nodes', [])]
        nodes = [n for group in state['groups'].values() for n in group]
        if state['dirty']:
            entries = [_entry_from_content_item(r['raw'], cid, session.base_url) for r in records.values()]
        else:
            entries = []
            for data in old_courses[cid].get('entries', []):
                data = dict(data)
                data['due_at'] = parse_dt(data.get('due_at'))
                entries.append(ContentEntry(**data))
        old = old_courses.get(cid) or {}
        legacy = old.get('legacy_nodes', [])
        if not old and legacy_allowed:
            legacy = [n.to_dict() for n in previous.content_nodes if n.course_id == cid]
        legacy = [n for n in legacy if n['id'].split(':')[0] not in records]
        missing = int(old.get('legacy_missing') or 0) + int(state['complete'])
        state['legacy_nodes'] = legacy if missing < 2 else []
        state['legacy_missing'] = missing
        nodes.extend(ContentNode.from_dict(n) for n in state['legacy_nodes'])
        built.append((cid, entries, nodes))
    if include_html:
        _merge_parallel_html(session, [b for b in built if states[b[0]]['dirty']])
    _check(session)
    from blackboard.file_sizes import enrich_file_sizes
    enrich_file_sizes(session, [n for _, _, nodes in built for n in nodes], now=now)
    _check(session)
    for cid, entries, nodes in built:
        state = states[cid]
        legacy_ids = {n['id'] for n in state['legacy_nodes']}
        state['legacy_nodes'] = [n.to_dict() for n in nodes if n.id in legacy_ids]
        for iid, group in state['groups'].items():
            state['records'][iid]['nodes'] = [n.to_dict() for n in group]
        serialized = []
        for entry in entries:
            obj = asdict(entry)
            obj['due_at'] = entry.due_at.isoformat() if entry.due_at else None
            serialized.append(obj)
        cache['courses'][cid] = {'records': state['records'], 'entries': serialized,
                                  'checked': (old_courses[cid].get('checked') if compact[cid] else now.isoformat()), 'html': include_html,
                                  'legacy_nodes': state['legacy_nodes'], 'legacy_missing': state['legacy_missing'],
                                  'parser_version': PARSER_VERSION}
        if not state['complete']:
            stats['incomplete_courses'] += 1
    cache['stats'] = stats
    snapshot.content_cache = cache
    snapshot.completeness['files'] = not stats['incomplete_courses']
    getattr(session, 'metrics', {}).update({'content_' + k: v for k, v in stats.items()})
    session._tell('Finished checking course content…', .75)
    return [e for _, entries, _ in built for e in entries], [n for _, _, nodes in built for n in nodes]
