"""Build the runtime archive and real pacman package from an explicit vendor tree."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    hasher = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): hasher.update(block)
    return hasher.hexdigest()


def build(vendor, output, run_makepkg=True):
    version = (ROOT / 'VERSION').read_text().strip()
    import re
    if not re.fullmatch(r'\d+\.\d+\.\d+', version): raise ValueError('Invalid VERSION')
    vendor = Path(vendor).resolve(); output = Path(output).resolve()
    if not (vendor / 'llama_cpp/lib/libllama.so').is_file(): raise ValueError('Vulkan inference runtime missing from vendor directory')
    output.mkdir(parents=True, exist_ok=True)
    runtime = output / f'neura-ai-{version}-linux-x86_64.tar.zst'
    with tempfile.TemporaryDirectory(prefix='neura-build-') as directory:
        staging = Path(directory) / 'payload'; staging.mkdir()
        app = staging / 'opt/neura-ai/app'; app.mkdir(parents=True)
        for name in ['src','web','configs','assets']:
            shutil.copytree(ROOT/name, app/name, ignore=shutil.ignore_patterns('__pycache__','*.bak'), symlinks=True)
        for name in ['VERSION','neura-desktop.py','LICENSE']:
            shutil.copy2(ROOT/name, app/name)
        shutil.copytree(vendor, staging / 'opt/neura-ai/vendor', symlinks=True,
                        ignore=shutil.ignore_patterns('__pycache__','pip','pip-*','bin','*.pyc','*.pth'))
        files = {'neura-ai':'usr/bin/neura-ai', 'install-update':'usr/lib/neura-ai/install-update',
                 'neura-ai.desktop':'usr/share/applications/neura-ai.desktop',
                 'org.neura.ai.policy':'usr/share/polkit-1/actions/org.neura.ai.policy'}
        for source, destination in files.items():
            path=staging/destination;path.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(ROOT/'packaging/linux'/source,path)
        icon=staging/'usr/share/icons/hicolor/128x128/apps/neura-ai.png';icon.parent.mkdir(parents=True)
        shutil.copy2(ROOT/'assets/logo.png',icon)
        license_file=staging/'usr/share/licenses/neura-ai-bin/LICENSE';license_file.parent.mkdir(parents=True)
        shutil.copy2(ROOT/'LICENSE',license_file)
        for path in [staging/'usr/bin/neura-ai',staging/'usr/lib/neura-ai/install-update',app/'neura-desktop.py']:
            path.chmod(0o755)
        subprocess.run(['tar','--sort=name','--mtime=@1793059200','--owner=0','--group=0','--numeric-owner',
                        '-I','zstd -T0 -10','-cf',str(runtime),'-C',str(staging),'.'],check=True)
    sha=digest(runtime)
    aur=output/'aur';aur.mkdir(exist_ok=True)
    recipe=(ROOT/'packaging/aur/PKGBUILD.in').read_text().replace('@VERSION@',version).replace('@SHA256@',sha)
    (aur/'PKGBUILD').write_text(recipe)
    srcinfo=subprocess.run(['makepkg','--printsrcinfo'],cwd=aur,check=True,text=True,capture_output=True).stdout
    (aur/'.SRCINFO').write_text(srcinfo)
    if run_makepkg:
        # The very same AUR recipe is used locally; use the already verified source archive.
        shutil.copy2(runtime,aur/runtime.name)
        subprocess.run(['makepkg','--nodeps','--noconfirm','--cleanbuild'],cwd=aur,check=True,
                       env={**os.environ,'PKGDEST':str(output),'SOURCE_DATE_EPOCH':'1793059200'})
        (aur/runtime.name).unlink()
    aur_tar=output/f'neura-ai-bin-{version}-aur.tar.gz'
    with tarfile.open(aur_tar,'w:gz') as archive:
        for name in ['PKGBUILD','.SRCINFO']:archive.add(aur/name,arcname='neura-ai-bin/'+name)
    for name in ['install.sh','install.py']:
        shutil.copy2(ROOT/'packaging/linux'/name,output/name)
    artifacts=[p for p in output.iterdir() if p.is_file() and p.name!='SHA256SUMS.txt']
    (output/'SHA256SUMS.txt').write_text(''.join(digest(p)+'  '+p.name+'\n' for p in sorted(artifacts)))
    print(json.dumps({'version':version,'runtime':runtime.name,'runtime_sha256':sha,'output':str(output)},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vendor',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--no-package',action='store_true')
    args=parser.parse_args()
    build(args.vendor,args.output,not args.no_package)
