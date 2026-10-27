from pathlib import Path
import pytest
from src.agent.session_vault import SessionVault


def test_browser_sessions_are_confined_and_private(tmp_path):
    vault=SessionVault(tmp_path/'sessions')
    with pytest.raises(ValueError):vault.save_persistent('../escape',{})
    file=Path(vault.save_persistent('test',{'cookies':[]},'example.com'))
    assert file.stat().st_mode & 0o777 == 0o600
    assert vault.get_state('test')=={'cookies':[]}
    assert vault.get_state_for_domain('sub.example.com')[0]=='test'
    assert vault.get_state_for_domain('evilexample.com')==(None,None)
    assert vault.get_state_for_domain('com')==(None,None)
    assert vault.delete_persistent('test')


def test_browser_vault_rejects_symlinks_outside_root(tmp_path):
    root=tmp_path/'sessions';root.mkdir()
    target=tmp_path/'outside.json';target.write_text('{}')
    (root/'test.json').symlink_to(target)
    with pytest.raises(ValueError):SessionVault(root).get_state('test')
