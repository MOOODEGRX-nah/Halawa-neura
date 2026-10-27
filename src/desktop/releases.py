"""Release metadata and verified package downloads from this repository only."""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.parse
import urllib.request

REPOSITORY = 'MOOODEGRX-nah/Halawa-neura'
API = f'https://api.github.com/repos/{REPOSITORY}/releases'
MAX_PACKAGE_BYTES = 512 * 1024 * 1024
VERSION_PATTERN = re.compile(r'^v?(\d+)\.(\d+)\.(\d+)$')
PACKAGE_PATTERN = re.compile(r'^neura-ai-bin-(\d+\.\d+\.\d+)-(\d+)-x86_64\.pkg\.tar\.zst$')


def version_tuple(version):
    match = VERSION_PATTERN.fullmatch(version)
    if not match:
        raise ValueError('Unsupported release version')
    return tuple(map(int, match.groups()))


class TrustedRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        if parsed.scheme != 'https' or parsed.hostname not in ('github.com', 'api.github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'):
            raise ValueError('Unexpected release download redirect')
        return super().redirect_request(request, fp, code, message, headers, newurl)


def open_url(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'Neura-AI-Desktop', 'Accept': 'application/vnd.github+json'})
    return urllib.request.build_opener(TrustedRedirects()).open(request, timeout=20)


@dataclass(frozen=True)
class ReleasePackage:
    version: str
    name: str
    url: str
    sha256: str
    size: int
    notes: str


def parse_release(payload):
    if payload.get('draft') or payload.get('prerelease'):
        raise ValueError('Only stable published releases are supported')
    version = str(payload.get('tag_name', '')).removeprefix('v')
    version_tuple(version)
    packages = [asset for asset in payload.get('assets', []) if PACKAGE_PATTERN.fullmatch(asset.get('name', ''))]
    if len(packages) != 1:
        raise ValueError('This release has no unique Arch Linux desktop package')
    asset = packages[0]
    match = PACKAGE_PATTERN.fullmatch(asset['name'])
    if match[1] != version:
        raise ValueError('Package version does not match its release')
    url = asset.get('browser_download_url', '')
    expected = f'https://github.com/{REPOSITORY}/releases/download/v{version}/{asset["name"]}'
    if url != expected:
        raise ValueError('Package URL is outside the expected repository release')
    digest = str(asset.get('digest', ''))
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
        raise ValueError('GitHub has not supplied a SHA256 digest for this package')
    size = asset.get('size')
    if type(size) is not int or not 0 < size <= MAX_PACKAGE_BYTES:
        raise ValueError('Package size exceeds the supported limit')
    return ReleasePackage(version, asset['name'], url, digest[7:], size, str(payload.get('body', ''))[:20_000])


def fetch_release(version=None):
    if version is not None:
        version_tuple(version)
    url = API + ('/tags/v' + version if version else '/latest')
    with open_url(url) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError('Release metadata too large')
    return parse_release(json.loads(raw))


def download_package(package, cache, progress=None):
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = cache / package.name
    temporary = cache / ('.download-' + os.urandom(8).hex())
    digest = hashlib.sha256()
    received = 0
    try:
        with open_url(package.url) as response, temporary.open('xb') as output:
            temporary.chmod(0o600)
            while True:
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                received += len(chunk)
                if received > package.size or received > MAX_PACKAGE_BYTES:
                    raise ValueError('Package exceeds advertised size')
                digest.update(chunk)
                output.write(chunk)
                if progress:
                    progress(received, package.size)
        if received != package.size or digest.hexdigest() != package.sha256:
            raise ValueError('Downloaded package failed SHA256/size verification')
        temporary.replace(target)
        return target
    finally:
        temporary.unlink(missing_ok=True)
