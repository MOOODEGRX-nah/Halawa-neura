import json
import os
import pytest
from src.core.project_files import SafeTree, ProjectError, Conflict
from src.core.project_store import ProjectStore

WEB = {'index.html': '<!doctype html><link rel="stylesheet" href="style.css"><h1>CV</h1><script src="script.js"></script>',
       'style.css': 'h1 {color: teal}', 'script.js': 'document.querySelector("h1").onclick=()=>document.body.dataset.clicked="yes";'}


def test_persistence_duplicate_titles_and_metadata(tmp_path):
    store = ProjectStore(tmp_path)
    a = store.create('سيرتي', 'موقع سيرة ذاتية')
    b = store.create('سيرتي', 'برنامج Python')
    assert store.directory(a['project_id']) != store.directory(b['project_id'])
    a = store.commit(a['project_id'], WEB, 0)
    b = store.commit(b['project_id'], {'main.py': 'def add(a,b):\n    return a+b\n'}, 0)
    assert len(a['files']) == 3
    assert a['source_freshness'] == 'current'
    assert a['preview']['supported'] and b['type'] == 'python' and not b['preview']['supported']
    assert a['languages'] == ['CSS', 'HTML', 'JavaScript']
    assert a['summary_revision'] == a['project_revision'] == 1
    assert store.answer(a['project_id'], 'ما هي اللغة؟')['model_called'] is False
    store.close()
    store = ProjectStore(tmp_path)
    assert len(store.list()) == 2
    assert store.read(a['project_id'], 'style.css')['content'] == WEB['style.css']
    assert (store.directory(a['project_id']) / '.neura/summary.md').exists()
    store.close()


@pytest.mark.parametrize('path', ['../bad', '/tmp/bad', 'a/../../bad', '.neura/project.json',
                                  'x/.env', 'x\\bad', 'a//b', 'a/./b', 'C:/bad', '%2e%2e/a', 'NUL.txt'])
def test_reject_unsafe_paths(tmp_path, path):
    store = ProjectStore(tmp_path)
    project = store.create('test', 'test')
    with pytest.raises(ProjectError):
        store.commit(project['project_id'], {path: 'data'}, 0)
    assert not store.get(project['project_id'])['files']
    store.close()


def test_symlink_escape_and_atomic_final_symlink(tmp_path):
    root = tmp_path / 'root';root.mkdir()
    outside = tmp_path / 'outside';outside.mkdir()
    (outside/'safe.txt').write_text('unchanged')
    (root/'linked').symlink_to(outside, target_is_directory=True)
    (root/'final.txt').symlink_to(outside/'safe.txt')
    with SafeTree(root) as tree:
        for path in ['linked/safe.txt', 'final.txt']:
            with pytest.raises(ProjectError):tree.read(path)
            with pytest.raises(ProjectError):tree.write(path, 'bad')
        with pytest.raises(ProjectError):tree.inventory()
    assert (outside/'safe.txt').read_text() == 'unchanged'
    alias=tmp_path/'parent-link';alias.symlink_to(outside,target_is_directory=True)
    child=outside/'project';child.mkdir()
    with pytest.raises(ProjectError):SafeTree(alias/'project')
    hard=root/'hard.txt';os.link(outside/'safe.txt',hard)
    with SafeTree(root) as tree:
        with pytest.raises(ProjectError):tree.read('hard.txt')
        with pytest.raises(ProjectError):tree.write('hard.txt','bad')
    assert (outside/'safe.txt').read_text()=='unchanged'


def test_failed_generation_does_not_replace_good_revision(tmp_path):
    store=ProjectStore(tmp_path);p=store.create('test','test')['project_id']
    store.commit(p, {'main.py':'def add(a,b): return a+b'}, 0)
    for invalid in [{}, {'main.py':'def bad(:'}, {'../escape':'bad'}]:
        with pytest.raises(ProjectError):store.commit(p,invalid,1)
    assert store.get(p)['project_revision']==1
    assert store.read(p,'main.py')['content']=='def add(a,b): return a+b'
    store.close()


def test_revision_conflict_external_edit_and_rebuild(tmp_path):
    store=ProjectStore(tmp_path);p=store.create('test','test')['project_id']
    store.commit(p,WEB,0);opened=store.read(p,'style.css')
    store.save_file(p,'style.css','h1{color:red}',1,opened['sha256'])
    with pytest.raises(Conflict):store.save_file(p,'style.css','h1{color:blue}',1,opened['sha256'])
    (store.directory(p)/'style.css').write_text('h1{color:green}')
    assert store.get(p)['source_freshness']=='stale'
    assert store.answer(p,'ما هذا المشروع؟')['stale']
    current=store.read(p,'style.css')
    with pytest.raises(Conflict):store.save_file(p,'style.css','h1{}',2,current['sha256'])
    rebuilt=store.rebuild(p,2)
    assert rebuilt['project_revision']==3 and rebuilt['source_freshness']=='current'
    assert store.read(p,'style.css')['content']=='h1{color:green}'
    store.close()


def test_crash_journal_restores_last_good_revision(tmp_path):
    store=ProjectStore(tmp_path);p=store.create('test','test')['project_id']
    store.commit(p,WEB,0);folder=store.directory(p)
    with SafeTree(folder) as tree:
        tree.write('.neura/transaction.json',json.dumps({'old_revision':1,'new_revision':2,'paths':list(WEB)+['bad.txt']}),internal=True)
        tree.write('index.html','broken partial')
        tree.write('bad.txt','partial')
    store.close();store=ProjectStore(tmp_path)
    assert store.read(p,'index.html')['content']==WEB['index.html']
    assert not (folder/'bad.txt').exists()
    assert store.get(p)['project_revision']==1 and store.get(p)['source_freshness']=='current'
    assert list((folder/'.neura').glob('recovery-*.json'))
    store.close()


def test_preview_manifest_excludes_private_unreferenced_and_builds(tmp_path):
    store=ProjectStore(tmp_path);p=store.create('test','test')['project_id']
    files={**WEB,'notes.txt':'private note','secret.json':'{}'}
    meta=store.commit(p,files,0)
    assert set(meta['preview']['assets'])==set(WEB)
    assert 'notes.txt' not in meta['preview']['assets']
    q=store.create('React','test')['project_id']
    meta=store.commit(q,{'index.html':'<div>hi</div>','app.tsx':'export default ()=> <div/>;'},0)
    assert not meta['preview']['supported']
    store.close()
