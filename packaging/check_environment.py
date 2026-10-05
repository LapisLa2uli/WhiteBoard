"""Fail early if a release is built with an unpinned interpreter or package."""
import importlib.metadata
import platform
import sys
from pathlib import Path
from packaging.requirements import Requirement

target = sys.argv[1]
if sys.version_info[:2] != (3, 12):
    raise SystemExit('Use Python 3.12 for release builds')
if target == 'windows' and (sys.platform != 'win32' or platform.machine().lower() not in ('amd64', 'x86_64')):
    raise SystemExit('Build Windows on native Windows x64 Python')
if target == 'macos' and (sys.platform != 'darwin' or platform.machine() != 'arm64'):
    raise SystemExit('Build macOS on native Apple silicon Python (arm64)')
for line in Path(__file__).with_name('requirements-build.txt').read_text().splitlines():
    if not line or line.startswith('#'):
        continue
    requirement = Requirement(line)
    if requirement.marker and not requirement.marker.evaluate():
        continue
    try:
        installed = importlib.metadata.version(requirement.name)
    except importlib.metadata.PackageNotFoundError:
        raise SystemExit(f'Missing build dependency: {requirement.name}')
    if installed not in requirement.specifier:
        raise SystemExit(f'Install pinned build dependencies: {requirement.name} is {installed}, expected {requirement.specifier}')
print('Build environment matches pinned dependencies')
