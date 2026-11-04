"""A finished recorder must not turn incomplete or mismatched evidence green."""
import json
from tools.check_accuracy_evidence import check_run


def write_plan(tmp_path):
    (tmp_path/'identity.json').write_text(json.dumps({'workflow':'plan','inference':'real'}))
    data={'environment':'test evidence only','turns':[{'dispatch':[{'kind':'plan','planning':{
        'accepted':True,'finish_reason':'stop','plan':{'steps':['حدد الأقسام','نفذ الهيكل','افحص النتيجة']}}}],
        'jobs':[],'after':{'projects':[]}}]}
    (tmp_path/'composer.json').write_text(json.dumps(data))
    return data


def test_checker_rejects_length_stop_despite_accepted_flag(tmp_path):
    data=write_plan(tmp_path)
    assert check_run(tmp_path)['passed']
    data['turns'][0]['dispatch'][0]['planning']['finish_reason']='length'
    (tmp_path/'composer.json').write_text(json.dumps(data))
    assert not check_run(tmp_path)['passed']


def test_checker_rejects_fake_or_interrupted_evidence(tmp_path):
    write_plan(tmp_path)
    (tmp_path/'failure.json').write_text('{}')
    assert not check_run(tmp_path)['passed']
    (tmp_path/'failure.json').unlink()
    (tmp_path/'identity.json').write_text(json.dumps({'workflow':'plan','inference':'fake'}))
    assert not check_run(tmp_path)['passed']


def test_checker_rejects_incomplete_exact_conversation(tmp_path):
    (tmp_path/'identity.json').write_text(json.dumps({'workflow':'exact','inference':'real'}))
    (tmp_path/'composer.json').write_text(json.dumps({'environment':'test','turns':[]}))
    result=check_run(tmp_path)
    assert not result['passed']
    assert 'Incomplete conversation' in result['errors']
    assert 'Restart evidence absent' in result['errors']
