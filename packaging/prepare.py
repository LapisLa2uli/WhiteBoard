"""Validate release inputs and record the exact source revision, without secrets."""
import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from version import APP_VERSION


def prepare(target, release=False):
    notes = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
    marker = f'## [{APP_VERSION}]'
    if marker not in notes:
        raise SystemExit('Current version is missing from CHANGELOG.md')
    section = notes.split(marker, 1)[1].split('\n## [', 1)[0]
    for heading in ('Added features', 'Bugfixes', 'Other changes'):
        if f'### {heading}' not in section:
            raise SystemExit(f'Missing changelog heading: {heading}')
    for resource in ('index.html', 'app.js', 'app.css', 'tabs.html', 'tabs.js', 'logo.png'):
        if not (ROOT / 'static' / resource).is_file():
            raise SystemExit(f'Missing runtime resource: {resource}')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=normal'], cwd=ROOT, text=True).strip())
    if release and dirty:
        raise SystemExit('Release builds require a clean committed checkout')
    if release and not (ROOT / 'authid.txt').is_file():
        raise SystemExit('Release builds require the public Google desktop OAuth configuration in authid.txt')
    payload = {'version': APP_VERSION, 'revision': revision + ('-dirty' if dirty else ''),
               'platform': target, 'python': platform.python_version()}
    output = ROOT / 'build' / target / 'build-info.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    print(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('target', choices=('windows', 'macos'))
    parser.add_argument('--release', action='store_true')
    args = parser.parse_args()
    prepare(args.target, args.release)
