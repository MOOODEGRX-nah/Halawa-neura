import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import pty
import select
import subprocess
import sys
import time
from types import SimpleNamespace
import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def installer():
    spec = importlib.util.spec_from_file_location('neura_test_installer', ROOT / 'packaging/linux/install.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def asset():
    return {'name': 'neura-ai-bin-0.3.0-1-x86_64.pkg.tar.zst', 'size': 7,
            'digest': 'sha256:' + hashlib.sha256(b'package').hexdigest(),
            'browser_download_url': 'https://github.com/MOOODEGRX-nah/Halawa-neura/releases/download/v0.3.0/neura-ai-bin-0.3.0-1-x86_64.pkg.tar.zst'}


class Terminal(io.BytesIO):
    def isatty(self):
        return True


def test_piped_stdin_opens_controlling_terminal(installer, monkeypatch):
    pipe = io.BytesIO(b'installer script, not a confirmation')
    tty = Terminal()
    monkeypatch.setattr(installer.sys, 'stdin', pipe)
    opened = []
    def open_tty(path, mode, buffering):
        opened.append((path, mode, buffering))
        return tty
    monkeypatch.setattr(installer, 'open', open_tty, raising=False)
    with installer.terminal_input() as selected:
        assert selected is tty
    assert opened == [('/dev/tty', 'rb', 0)]


def test_direct_terminal_is_not_closed(installer, monkeypatch):
    terminal = Terminal()
    monkeypatch.setattr(installer.sys, 'stdin', terminal)
    with installer.terminal_input() as selected:
        assert selected is terminal
    assert not terminal.closed


def test_no_terminal_fails_before_download(installer, monkeypatch, capsys):
    monkeypatch.setattr(installer.sys, 'stdin', io.BytesIO())
    def unavailable(*args, **kwargs):
        raise OSError('no terminal')
    monkeypatch.setattr(installer, 'open', unavailable, raising=False)
    monkeypatch.setattr(installer, 'release_asset', lambda: pytest.fail('Should not contact GitHub'))
    assert installer.main() == 1
    assert 'interactive terminal' in capsys.readouterr().err


def test_verified_cache_avoids_redownload(installer, monkeypatch, tmp_path):
    monkeypatch.setenv('NEURA_INSTALL_CACHE', str(tmp_path))
    metadata = asset()
    package = tmp_path / metadata['name']; package.write_bytes(b'package')
    monkeypatch.setattr(installer.urllib.request, 'urlopen', lambda *a, **k: pytest.fail('Should use verified cache'))
    assert installer.cached_package(metadata) == package


def test_corrupt_download_is_never_installed(installer, monkeypatch, tmp_path):
    monkeypatch.setenv('NEURA_INSTALL_CACHE', str(tmp_path))
    monkeypatch.setattr(installer.urllib.request, 'urlopen', lambda *a, **k: io.BytesIO(b'corrupt'))
    with pytest.raises(installer.InstallerError, match='checksum'):
        installer.cached_package(asset())
    assert not (tmp_path / asset()['name']).exists()
    assert not list(tmp_path.glob('.download-*'))


def test_pacman_abort_preserves_cache_without_traceback(installer, monkeypatch, tmp_path, capsys):
    metadata = asset(); package = tmp_path / metadata['name']; package.write_bytes(b'package')
    terminal = Terminal()
    monkeypatch.setattr(installer.sys, 'stdin', terminal)
    monkeypatch.setattr(installer, 'release_asset', lambda: ('0.3.0', metadata))
    monkeypatch.setattr(installer, 'cached_package', lambda a: package)
    calls = []
    def aborted(command, **options):
        calls.append((command, options))
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(installer.subprocess, 'run', aborted)
    assert installer.main() == 1
    assert calls[0][1]['stdin'] is terminal
    assert '--noconfirm' not in calls[0][0]
    assert package.exists()
    stderr = capsys.readouterr().err
    assert 'kept at:' in stderr and 'Traceback' not in stderr


def test_pipe_install_confirmation_uses_real_pty(tmp_path):
    """Reproduce curl|bash stdin while pacman reads Y from the controlling TTY."""
    cache = tmp_path / 'cache'; cache.mkdir()
    metadata = asset(); package = cache / metadata['name']; package.write_bytes(b'package')
    binary = tmp_path / 'bin'; binary.mkdir()
    fake_sudo = binary / 'sudo'
    fake_sudo.write_text('#!' + sys.executable + '\n' + """
import sys
assert sys.argv[1:3] == ['pacman', '-U']
print('CONFIRM_TTY=' + str(sys.stdin.isatty()), flush=True)
answer = sys.stdin.readline().strip()
print('CONFIRM_ANSWER=' + answer, flush=True)
raise SystemExit(0 if sys.stdin.isatty() and answer == 'Y' else 91)
""")
    fake_sudo.chmod(0o755)
    master, slave = pty.openpty()
    runner = tmp_path / 'runner.py'
    runner.write_text("""
import fcntl, importlib.util, json, os, termios
fcntl.ioctl(int(os.environ['NEURA_TEST_TTY_FD']), termios.TIOCSCTTY, 0)
spec = importlib.util.spec_from_file_location('installer', os.environ['NEURA_TEST_INSTALLER'])
installer = importlib.util.module_from_spec(spec); spec.loader.exec_module(installer)
installer.release_asset = lambda: ('0.3.0', json.loads(os.environ['NEURA_TEST_ASSET']))
raise SystemExit(installer.main())
""")
    process = subprocess.Popen([sys.executable, '-u', str(runner)], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True, pass_fds=(slave,),
        env={**os.environ, 'PATH':str(binary)+os.pathsep+os.environ['PATH'],
             'NEURA_INSTALL_CACHE':str(cache), 'NEURA_TEST_TTY_FD':str(slave),
             'NEURA_TEST_INSTALLER':str(ROOT/'packaging/linux/install.py'), 'NEURA_TEST_ASSET':json.dumps(metadata)})
    os.close(slave)
    output = bytearray()
    try:
        # Deliberately unrelated pipe data must not become pacman's confirmation.
        process.stdin.write(b'not a confirmation\n'); process.stdin.close()
        deadline = time.monotonic() + 8
        answered = False
        while time.monotonic() < deadline:
            ready, _, _ = select.select([process.stdout], [], [], .1)
            if ready:
                block = os.read(process.stdout.fileno(), 4096)
                if not block: break
                output.extend(block)
                if b'CONFIRM_TTY=True' in output and not answered:
                    os.write(master, b'Y\n'); answered = True
            if process.poll() is not None: break
        assert process.wait(timeout=2) == 0, output.decode()
        remaining = process.stdout.read()
        output.extend(remaining)
        assert answered and b'CONFIRM_ANSWER=Y' in output
        assert b'Neura AI installed' in output
    finally:
        if process.poll() is None: process.kill(); process.wait()
        os.close(master)
