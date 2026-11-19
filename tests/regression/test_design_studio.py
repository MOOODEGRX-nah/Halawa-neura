"""P05/P06 design studio: versioned scenes, scoped AI edits and exports."""
import base64
import json

import pytest
from fastapi.testclient import TestClient

from src.core.design_store import DesignStore, DesignError, Document, TEMPLATES, apply_ai_changes, export_site
from tests.regression.test_chat_dispatch import application

PNG = 'data:image/png;base64,' + base64.b64encode(bytes.fromhex('89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63f8ffff3f0005fe02fea7d6a45d0000000049454e44ae426082')).decode()
H = {'X-Neura-Token': 'test-token'}


@pytest.mark.parametrize('name', list(TEMPLATES))
def test_every_template_is_a_valid_document(tmp_path, name):
    store = DesignStore(tmp_path)
    design = store.create(name)
    assert Document.model_validate(design['document']) and design['revision'] == 1
    assert (tmp_path / 'designs.sqlite3').stat().st_mode & 0o777 == 0o600


def test_saves_are_revisioned_and_stale_saves_are_refused(tmp_path):
    store = DesignStore(tmp_path)
    design = store.create('post')
    document = design['document']
    document['nodes'][1]['text'] = 'عرض خاص'
    saved = store.save(design['id'], document, 1)
    assert saved['revision'] == 2
    with pytest.raises(DesignError) as stale:
        store.save(design['id'], document, 1)
    assert stale.value.status == 409
    restored = store.restore(design['id'], 1, 2)
    assert restored['revision'] == 3 and restored['document']['nodes'][1]['text'] == 'عنوان المنشور'
    assert [r['revision'] for r in store.revisions(design['id'])] == [3, 2, 1]


@pytest.mark.parametrize('bad', [
    {'nodes': [{'id': 'n_12345678', 'type': 'text', 'x': 0, 'y': 0, 'w': 10, 'h': 10, 'color': 'red'}]},
    {'nodes': [{'id': 'n_12345678', 'type': 'image', 'x': 0, 'y': 0, 'w': 10, 'h': 10, 'src': 'https://example.com/a.png'}]},
    {'nodes': [{'id': 'n_12345678', 'type': 'script', 'x': 0, 'y': 0, 'w': 10, 'h': 10}]},
    {'nodes': [{'id': 'n_12345678', 'type': 'text', 'x': 0, 'y': 0, 'w': 10, 'h': 10}] * 2},
    {'width': 99999},
])
def test_invalid_documents_are_rejected(tmp_path, bad):
    store = DesignStore(tmp_path)
    design = store.create('blank-graphic')
    with pytest.raises(ValueError):
        store.save(design['id'], {**design['document'], **bad}, 1)


def test_ai_changes_are_limited_to_selected_nodes_and_allowed_properties(tmp_path):
    store = DesignStore(tmp_path)
    document = Document.model_validate(store.create('post')['document'])
    selected = {document.nodes[1].id}
    updated, touched, note = apply_ai_changes(document, selected, json.dumps({'changes': [{'id': document.nodes[1].id, 'set': {'text': 'خصم 20٪', 'color': '#aa0000', 'fontSize': 90}}], 'note': 'تم'}))
    assert updated.nodes[1].text == 'خصم 20٪' and updated.nodes[1].fontSize == 90 and touched == [document.nodes[1].id]
    assert updated.nodes[0] == document.nodes[0]
    for reply in [{'changes': [{'id': document.nodes[0].id, 'set': {'text': 'x'}}]},
                  {'changes': [{'id': document.nodes[1].id, 'set': {'src': PNG}}]},
                  {'changes': [{'id': document.nodes[1].id, 'set': {'color': 'blue'}}]},
                  'not json']:
        with pytest.raises(DesignError):
            apply_ai_changes(document, selected, reply if isinstance(reply, str) else json.dumps(reply))


def test_site_export_is_scaled_rtl_with_real_image_files(tmp_path):
    store = DesignStore(tmp_path)
    document = store.create('landing')['document']
    document['nodes'].append({'id': 'n_abcdef12', 'type': 'image', 'name': 'صورة', 'x': 10, 'y': 10, 'w': 100, 'h': 100, 'src': PNG})
    document['nodes'].append({'id': 'n_abcdef13', 'type': 'text', 'x': 0, 'y': 0, 'w': 10, 'h': 10, 'text': '<script>alert(1)</script>', 'hidden': False})
    files = export_site(document, 'd_x', 4)
    page = files['index.html']
    assert 'lang="ar" dir="rtl"' in page and page.count('<h1') == 1 and '<button type="button"' in page
    assert '<script>alert' not in page and '&lt;script&gt;' in page
    assert isinstance(files['assets/image-11.png'], bytes) and 'container-type:inline-size' in files['style.css']


def test_api_flow_create_edit_ai_and_export_with_divergence_protection(system):
    app, desktop, dispatch = application(system)
    store = app.state.project_store
    with TestClient(app, base_url='http://127.0.0.1') as client:
        assert client.get('/designs').status_code == 403
        listing = client.get('/designs', headers=H).json()
        assert set(listing['templates']) == set(TEMPLATES)
        design = client.post('/designs', json={'template': 'landing'}, headers=H).json()
        title_node = next(n for n in design['document']['nodes'] if n['name'] == 'العنوان')
        system.backend.text = json.dumps({'changes': [{'id': title_node['id'], 'set': {'text': 'قهوة مختصة كل صباح', 'fontSize': 60}}], 'note': 'غيرت العنوان'})
        edited = client.post('/designs/' + design['id'] + '/ai', json={'base_revision': 1, 'node_ids': [title_node['id']], 'instruction': 'اكتب عنوانًا لمقهى'}, headers=H)
        assert edited.status_code == 200, edited.text
        edited = edited.json()
        assert edited['revision'] == 2 and edited['changed_nodes'] == [title_node['id']]
        assert client.post('/designs/' + design['id'] + '/ai', json={'base_revision': 1, 'node_ids': [title_node['id']], 'instruction': 'مرة أخرى'}, headers=H).status_code == 409
        exported = client.post('/designs/' + design['id'] + '/export-site', json={'base_revision': 2}, headers=H).json()
        project = store.get(exported['project_id'])
        assert project['project_revision'] == 1 and 'قهوة مختصة كل صباح' in store.read(exported['project_id'], 'index.html')['content']
        again = client.post('/designs/' + design['id'] + '/export-site', json={'base_revision': 2}, headers=H)
        assert again.status_code == 200 and store.get(exported['project_id'])['project_revision'] == 2
        store.commit(exported['project_id'], {**store.committed_files(exported['project_id']), 'extra.js': 'console.log(1)'}, 2)
        blocked = client.post('/designs/' + design['id'] + '/export-site', json={'base_revision': 2}, headers=H)
        assert blocked.status_code == 409 and store.get(exported['project_id'])['project_revision'] == 3
        fresh = client.post('/designs/' + design['id'] + '/export-site', json={'base_revision': 2, 'new_project': True}, headers=H).json()
        assert fresh['project_id'] != exported['project_id']
        assert client.delete('/designs/' + design['id'], headers=H).status_code == 200
    app.state.project_store.close()


def test_studio_page_and_assets_are_served(system):
    app, desktop, dispatch = application(system)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        page = client.get('/').text
        assert 'id="tab-studio"' in page and 'id="pg-studio"' in page and '/assets/studio.js' in page
        assert client.get('/assets/studio.js').headers['content-type'].startswith('text/javascript')
        assert client.get('/assets/studio.css').headers['content-type'].startswith('text/css')
    app.state.project_store.close()
