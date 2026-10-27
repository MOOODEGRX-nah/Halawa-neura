"""Polkit helper. Root independently verifies the release and stages immutable bytes."""
import hashlib
import os
from pathlib import Path
import pwd
import re
import shutil
import stat
import subprocess
import tempfile
from src.desktop.releases import fetch_release, MAX_PACKAGE_BYTES, version_tuple


def stage_package(source, expected, uid, destination):
    source = Path(source)
    home = Path(pwd.getpwuid(uid).pw_dir)
    allowed = (home / '.cache/neura-ai/updates').resolve()
    if not source.resolve().is_relative_to(allowed):
        raise ValueError('Update must come from the user update cache')
    descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    digest = hashlib.sha256()
    received = 0
    with os.fdopen(descriptor, 'rb') as incoming, Path(destination).open('xb') as output:
        info = os.fstat(incoming.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != uid or not 0 < info.st_size <= MAX_PACKAGE_BYTES:
            raise ValueError('Invalid update file ownership or size')
        while True:
            chunk = incoming.read(256 * 1024)
            if not chunk:
                break
            received += len(chunk)
            if received > expected.size:
                raise ValueError('Update size changed')
            digest.update(chunk)
            output.write(chunk)
    if received != expected.size or digest.hexdigest() != expected.sha256:
        raise ValueError('Update checksum differs from the published GitHub asset')


def install(source, version):
    if os.geteuid() != 0:
        raise PermissionError('Run through the Neura update action')
    caller = os.environ.get('PKEXEC_UID', '')
    if not re.fullmatch(r'[1-9][0-9]*', caller):
        raise PermissionError('A non-root polkit caller is required')
    installed = subprocess.run(['/usr/bin/pacman', '-Q', 'neura-ai-bin'], check=True,
                               text=True, capture_output=True).stdout.split()
    if len(installed) != 2 or installed[0] != 'neura-ai-bin':
        raise ValueError('Installed package identity mismatch')
    current = installed[1].split('-')[0]
    if version_tuple(version) <= version_tuple(current):
        raise ValueError('The requested version is not newer than the installed version')
    expected = fetch_release(version)
    if Path(source).name != expected.name:
        raise ValueError('Unexpected package filename')
    with tempfile.TemporaryDirectory(prefix='neura-update-', dir='/var/tmp') as directory:
        staged = Path(directory) / expected.name
        stage_package(source, expected, int(caller), staged)
        identity = subprocess.run(['/usr/bin/pacman', '-Qp', str(staged)], check=True,
                                  text=True, capture_output=True).stdout.split()
        if identity != ['neura-ai-bin', expected.name.removeprefix('neura-ai-bin-').removesuffix('-x86_64.pkg.tar.zst')]:
            raise ValueError('Package metadata does not match the published update')
        subprocess.run(['/usr/bin/pacman', '-U', '--noconfirm', str(staged)], check=True)


if __name__ == '__main__':
    import sys
    if len(sys.argv) != 3:
        raise SystemExit('Expected package path and version')
    try:
        install(sys.argv[1], sys.argv[2])
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
