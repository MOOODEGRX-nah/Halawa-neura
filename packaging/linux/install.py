#!/usr/bin/env python3
"""One-time Arch installer, including when invoked through curl | bash."""
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import urllib.request

REPO = 'MOOODEGRX-nah/Halawa-neura'
MAX_PACKAGE_BYTES = 512 * 1024 * 1024


class InstallerError(RuntimeError):
    pass


def terminal_input():
    """The script pipe is never the input source for pacman's confirmation."""
    if sys.stdin.isatty():
        return nullcontext(sys.stdin)
    try:
        return open('/dev/tty', 'rb', buffering=0)
    except OSError as error:
        raise InstallerError('An interactive terminal is required. Run the installer from a terminal window.') from error


def release_asset():
    request = urllib.request.Request(f'https://api.github.com/repos/{REPO}/releases/latest',
                                     headers={'User-Agent': 'Neura-Installer'})
    with urllib.request.urlopen(request, timeout=20) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise InstallerError('Release metadata too large')
    release = json.loads(raw)
    version = str(release.get('tag_name', '')).removeprefix('v')
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise InstallerError('Unsupported release version')
    assets = [asset for asset in release.get('assets', [])
              if re.fullmatch(r'neura-ai-bin-' + re.escape(version) + r'-\d+-x86_64\.pkg\.tar\.zst', asset.get('name', ''))]
    if len(assets) != 1:
        raise InstallerError('The current release has no unique Arch Linux package')
    asset = assets[0]
    expected_url = f'https://github.com/{REPO}/releases/download/v{version}/{asset["name"]}'
    if asset.get('browser_download_url') != expected_url or not re.fullmatch(r'sha256:[0-9a-f]{64}', str(asset.get('digest', ''))):
        raise InstallerError('Missing trusted package URL or SHA256 digest')
    if type(asset.get('size')) is not int or not 0 < asset['size'] <= MAX_PACKAGE_BYTES:
        raise InstallerError('Invalid package size')
    return version, asset


def verified(path, asset):
    if path.is_symlink() or not path.is_file() or path.stat().st_size != asset['size']:
        return False
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest() == asset['digest'][7:]


def cached_package(asset):
    cache = Path(os.environ.get('NEURA_INSTALL_CACHE', Path.home() / '.cache/neura-ai/updates')).expanduser()
    cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = cache / asset['name']
    if verified(destination, asset):
        print('Using verified cached package:', destination, flush=True)
        return destination
    print('Downloading Neura AI package...', flush=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix='.download-', dir=cache)
    temporary = Path(temporary_name)
    digest = hashlib.sha256()
    received = 0
    last_progress = -1
    try:
        with os.fdopen(descriptor, 'wb') as output:
            with urllib.request.urlopen(asset['browser_download_url'], timeout=30) as response:
                for block in iter(lambda: response.read(256 * 1024), b''):
                    received += len(block)
                    if received > asset['size']:
                        raise InstallerError('Package exceeds expected size')
                    digest.update(block)
                    output.write(block)
                    progress = received * 100 // asset['size']
                    if progress // 10 != last_progress:
                        last_progress = progress // 10
                        print(f'Download: {progress}%', flush=True)
        if received != asset['size'] or digest.hexdigest() != asset['digest'][7:]:
            raise InstallerError('Package checksum verification failed')
        temporary.replace(destination)
        return destination
    finally:
        temporary.unlink(missing_ok=True)


def main():
    try:
        # Check access to the controlling terminal before any package download.
        with terminal_input() as terminal:
            version, asset = release_asset()
            package = cached_package(asset)
            print('Installing Neura AI', version, flush=True)
            result = subprocess.run(['sudo', 'pacman', '-U', str(package)], stdin=terminal)
            if result.returncode:
                print(f'Installation did not complete (exit {result.returncode}). Verified package kept at: {package}', file=sys.stderr)
                return result.returncode if 0 < result.returncode < 126 else 1
        print('Neura AI installed. Open it from your Applications menu.')
        return 0
    except KeyboardInterrupt:
        print('\nInstallation cancelled. Any verified cached package is kept.', file=sys.stderr)
        return 130
    except (InstallerError, OSError, ValueError, KeyError) as error:
        print('Installation failed: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
