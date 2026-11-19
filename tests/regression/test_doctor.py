"""N030 Doctor and N031 synced-folder warning."""
from fastapi.testclient import TestClient

from src.core.doctor import synced_root
from tests.regression.test_chat_dispatch import application


def test_synced_folder_detection_uses_markers_and_client_names(tmp_path):
    (tmp_path / 'Dropbox' / 'neura').mkdir(parents=True)
    assert synced_root(tmp_path / 'Dropbox' / 'neura') == (tmp_path / 'Dropbox').resolve()
    (tmp_path / 'sync' / 'data').mkdir(parents=True)
    (tmp_path / 'sync' / '.stfolder').mkdir()
    assert synced_root(tmp_path / 'sync' / 'data') == (tmp_path / 'sync').resolve()
    (tmp_path / 'local' / 'my-dropbox-notes').mkdir(parents=True)
    assert synced_root(tmp_path / 'local' / 'my-dropbox-notes') is None


def test_doctor_reports_named_checks_with_fixes(system):
    app, desktop, dispatch = application(system)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        assert client.get('/assistant/doctor').status_code == 403
        report = client.get('/assistant/doctor', headers={'X-Neura-Token': 'test-token'}).json()
        ids = {c['id'] for c in report['checks']}
        assert {'version', 'data_dir', 'synced_folder', 'disk', 'models_dir', 'engine', 'context', 'stt', 'tts', 'embedding', 'notifications'} <= ids
        assert report['count'] == len(report['checks']) == sum(report['summary'].values())
        assert all(c['fix'] for c in report['checks'] if c['status'] in ('warn', 'fail'))
    app.state.project_store.close()
