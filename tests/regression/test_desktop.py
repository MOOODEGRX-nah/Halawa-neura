import hashlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from src.desktop.paths import DesktopSettings
from src.desktop.service import BackendService
from src.desktop import releases
from src.desktop.install_update import stage_package


def metadata(data=b'package', version='0.3.1'):
    name=f'neura-ai-bin-{version}-1-x86_64.pkg.tar.zst'
    return {'tag_name':'v'+version,'draft':False,'prerelease':False,'body':'Release notes',
            'assets':[{'name':name,'browser_download_url':f'https://github.com/{releases.REPOSITORY}/releases/download/v{version}/{name}',
                       'digest':'sha256:'+hashlib.sha256(data).hexdigest(),'size':len(data)}]}


def test_settings_round_trip_uses_private_user_file(tmp_path):
    path=tmp_path/'config/settings.json'
    settings=DesktopSettings(path);settings.values['models_dir']=str(tmp_path/'models');settings.save()
    assert DesktopSettings(path).values['models_dir']==str(tmp_path/'models')
    assert path.stat().st_mode & 0o777==0o600
    assert not list(path.parent.glob('.settings-*'))


@pytest.mark.parametrize('value',[0,32769,'4096'])
def test_settings_limits(tmp_path,value):
    settings=DesktopSettings(tmp_path/'settings.json');settings.values['n_ctx']=value
    with pytest.raises(ValueError):settings.save()


def test_release_identity_and_version():
    package=releases.parse_release(metadata())
    assert package.version=='0.3.1'
    assert releases.version_tuple('v0.3.10')>releases.version_tuple('0.3.2')


@pytest.mark.parametrize('change', ['url','digest','size','version','draft','arch'])
def test_reject_untrusted_or_incompatible_release(change):
    data=metadata()
    if change=='url':data['assets'][0]['browser_download_url']='https://github.com/other/project/releases/download/v0.3.1/test.pkg.tar.zst'
    if change=='digest':data['assets'][0]['digest']=None
    if change=='size':data['assets'][0]['size']=releases.MAX_PACKAGE_BYTES+1
    if change=='version':data['tag_name']='v0.3.2'
    if change=='draft':data['draft']=True
    if change=='arch':data['assets'][0]['name']=data['assets'][0]['name'].replace('x86_64','aarch64')
    with pytest.raises(ValueError):releases.parse_release(data)


def test_download_verifies_digest_before_atomic_replace(tmp_path,monkeypatch):
    package=releases.parse_release(metadata())
    monkeypatch.setattr(releases,'open_url',lambda _:io.BytesIO(b'package'))
    result=releases.download_package(package,tmp_path)
    assert result.read_bytes()==b'package'
    assert result.stat().st_mode & 0o777==0o600
    monkeypatch.setattr(releases,'open_url',lambda _:io.BytesIO(b'tampered'))
    with pytest.raises(ValueError):releases.download_package(package,tmp_path)
    assert result.read_bytes()==b'package'
    assert not list(tmp_path.glob('.download-*'))


def test_privileged_staging_never_uses_unverified_mutable_file(tmp_path,monkeypatch):
    from src.desktop import install_update
    uid=os.getuid()
    monkeypatch.setattr(install_update.pwd,'getpwuid',lambda _:SimpleNamespace(pw_dir=str(tmp_path)))
    cache=tmp_path/'.cache/neura-ai/updates';cache.mkdir(parents=True)
    package=releases.parse_release(metadata())
    source=cache/package.name;source.write_bytes(b'package')
    stage_package(source,package,uid,tmp_path/'staged')
    assert (tmp_path/'staged').read_bytes()==b'package'
    source.write_bytes(b'garbage')
    with pytest.raises(ValueError):stage_package(source,package,uid,tmp_path/'bad-staged')
    outside=tmp_path/'outside';outside.write_bytes(b'package')
    with pytest.raises(ValueError):stage_package(outside,package,uid,tmp_path/'outside-staged')
    link=cache/'linked';link.symlink_to(source)
    with pytest.raises(OSError):stage_package(link,package,uid,tmp_path/'link-staged')


def test_supervisor_owns_one_child_and_preserves_unrelated_processes(tmp_path,monkeypatch):
    from src.desktop import service
    monkeypatch.setattr(service,'data_directory',lambda:tmp_path/'data')
    monkeypatch.setattr(service,'state_directory',lambda:tmp_path/'state')
    process=MagicMock();process.poll.return_value=None
    popen=MagicMock(return_value=process)
    settings=DesktopSettings(tmp_path/'settings.json');settings.values['models_dir']=str(tmp_path/'models')
    instance=BackendService(settings,popen=popen)
    instance.start();instance.start()
    assert popen.call_count==1
    assert popen.call_args.args[0][-2]=='--port'
    assert popen.call_args.kwargs['env']['NEURA_DATA_DIR']==str(tmp_path/'data')
    assert (tmp_path/'data/runtime-config/models.yaml').exists()
    instance.stop()
    process.terminate.assert_called_once()
    assert instance.process is None


def test_dedicated_coder_requires_complete_file(tmp_path,monkeypatch):
    from src.desktop import service
    monkeypatch.setattr(service,'data_directory',lambda:tmp_path/'data')
    settings=DesktopSettings(tmp_path/'settings.json');settings.values['models_dir']=str(tmp_path)
    settings.values['dedicated_coder']=True
    instance=BackendService(settings)
    with pytest.raises(ValueError):instance.environment()
