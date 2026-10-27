#!/usr/bin/env python3
"""One-time GitHub installer for Arch/CachyOS. Normal launches use the menu icon."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import urllib.request

REPO='MOOODEGRX-nah/Halawa-neura'
with urllib.request.urlopen(urllib.request.Request(f'https://api.github.com/repos/{REPO}/releases/latest',headers={'User-Agent':'Neura-Installer'}),timeout=20) as response:
    release=json.load(response)
version=release['tag_name'].removeprefix('v')
if not re.fullmatch(r'\d+\.\d+\.\d+',version):raise SystemExit('Unsupported release version')
assets=[a for a in release['assets'] if re.fullmatch(r'neura-ai-bin-'+re.escape(version)+r'-\d+-x86_64\.pkg\.tar\.zst',a['name'])]
if len(assets)!=1:raise SystemExit('The current release has no Arch Linux package yet.')
asset=assets[0];expected_url=f'https://github.com/{REPO}/releases/download/v{version}/{asset["name"]}'
if asset['browser_download_url']!=expected_url or not re.fullmatch(r'sha256:[0-9a-f]{64}',asset.get('digest','')):
    raise SystemExit('Missing trusted package URL or SHA256 digest')
if not 0<asset['size']<=512*1024*1024:raise SystemExit('Invalid package size')
print('Downloading Neura AI',version)
with tempfile.TemporaryDirectory(prefix='neura-install-') as directory:
    destination=Path(directory)/asset['name'];digest=hashlib.sha256();received=0
    with urllib.request.urlopen(expected_url,timeout=30) as response,destination.open('xb') as output:
        for block in iter(lambda:response.read(256*1024),b''):
            received+=len(block)
            if received>asset['size']:raise SystemExit('Package exceeds expected size')
            digest.update(block);output.write(block)
    if received!=asset['size'] or digest.hexdigest()!=asset['digest'][7:]:raise SystemExit('Package checksum verification failed')
    # Pacman presents the package/dependency transaction once. No terminal is needed for later launches.
    subprocess.run(['sudo','pacman','-U',str(destination)],check=True)
print('Neura AI installed. Open it from your Applications menu.')
