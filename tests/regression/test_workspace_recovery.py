import base64,json,os
from pathlib import Path
import pytest
from src.core.project_store import ProjectStore
from src.core.project_files import Conflict,ProjectError
from src.core.legacy_projects import LegacyProjects
from src.backends.devices import select_device


def test_broken_index_rebuild_preserves_sources_and_snapshots(tmp_path):
    store=ProjectStore(tmp_path);p=store.create('Python','purpose')['project_id'];store.commit(p,{'main.py':'pass\n'},0)
    folder=store.directory(p);original=(folder/'main.py').read_bytes()
    store.db.execute('UPDATE projects SET metadata=? WHERE id=?',('{broken',p));store.db.commit()
    assert store.list()[0]['index_valid'] is False
    assert store.get(p)['source_freshness']=='invalid'
    rebuilt=store.rebuild(p,0)
    assert rebuilt['project_revision']==2 and rebuilt['files'][0]['path']=='main.py'
    assert (folder/'main.py').read_bytes()==original
    assert (folder/'.neura/revisions/1.json').exists()
    assert list((folder/'.neura').glob('invalid-index-*.txt'))
    store.close()


def test_invalid_external_source_never_changes_the_index(tmp_path):
    store=ProjectStore(tmp_path);p=store.create('Python','purpose')['project_id'];store.commit(p,{'main.py':'pass\n'},0)
    (store.directory(p)/'main.py').write_text('def broken(:')
    before=store.db.execute('SELECT metadata FROM projects WHERE id=?',(p,)).fetchone()[0]
    with pytest.raises(ProjectError):store.rebuild(p,1)
    assert store.db.execute('SELECT metadata FROM projects WHERE id=?',(p,)).fetchone()[0]==before
    assert (store.directory(p)/'main.py').read_text()=='def broken(:'
    store.close()


def test_same_stat_source_changes_are_guarded_at_save(tmp_path):
    store=ProjectStore(tmp_path);p=store.create('Python','purpose')['project_id'];store.commit(p,{'a.py':'pass\n','b.py':'pass\n'},0)
    path=store.directory(p)/'b.py';st=path.stat();path.write_text('#123\n');os.utime(path,ns=(st.st_atime_ns,st.st_mtime_ns))
    a=store.read(p,'a.py')
    with pytest.raises(Conflict):store.save_file(p,'a.py','#comment\n',1,a['sha256'])
    assert path.read_text()=='#123\n'
    store.close()


def test_binary_assets_persist_and_summary_does_not_read_source_secrets(tmp_path):
    store=ProjectStore(tmp_path);p=store.create('CV','Website api_key=sk-supersecret1234567890')['project_id']
    png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aQxkAAAAASUVORK5CYII=')
    files={'index.html':'<img src="avatar.png">','avatar.png':png,'notes.txt':'password=not-in-summary'}
    meta=store.commit(p,files,0)
    assert meta['preview']['supported'] and 'avatar.png' in meta['preview']['assets']
    assert 'supersecret' not in meta['summary'] and 'not-in-summary' not in meta['summary']
    assert store.committed_files(p)['avatar.png']==png
    assert store.read(p,'avatar.png')['binary']
    store.close();store=ProjectStore(tmp_path)
    assert store.committed_files(p)['avatar.png']==png
    store.close()


def test_legacy_import_is_explicit_and_copy_only(tmp_path):
    old_id='proj_'+'a'*32;old=tmp_path/'projects'/old_id;(old/'files').mkdir(parents=True)
    (old/'invoice.json').write_text(json.dumps({'user_request':'Old Python project'}))
    (old/'files/main.py').write_text('pass\n')
    store=ProjectStore(tmp_path);legacy=LegacyProjects(store)
    assert store.list()==[] and legacy.list()[0]['legacy_id']==old_id
    imported=legacy.copy(old_id)
    assert imported['original_preserved'] and (old/'files/main.py').read_text()=='pass\n'
    assert imported['project']['project_id']=='p_'+'a'*32
    assert legacy.copy(old_id)['already_imported']
    assert len(store.list())==1
    store.close()


def test_measured_device_selection_survives_index_reordering():
    large={'description':'GPU Large','gpu_index':1,'free_bytes':15e9,'total_bytes':16e9}
    small={'description':'GPU Small','gpu_index':0,'free_bytes':7e9,'total_bytes':8e9}
    assert select_device([small,large],'auto',10)['gpu_index']==1
    moved={**large,'gpu_index':0}
    assert select_device([moved,small],'GPU Large',10)['gpu_index']==0
    with pytest.raises(ValueError):select_device([small],'GPU Large',2)
    with pytest.raises(ValueError):select_device([small,large],'GPU Small',10)
