"""P04 REC02–REC06: five offline Arabic site recipes with validated sources and probed interactions."""
import json
import threading
import time
from pathlib import Path

import pytest

from src.core.project_files import ProjectError
from src.tools.web_recipes import RECIPES, SITE_IDS, manifest, select_for_request, validate_source

FIXTURES = json.loads((Path(__file__).resolve().parents[1] / 'fixtures/web_sites.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('recipe_id', SITE_IDS)
def test_reference_sites_pass_source_validation(recipe_id):
    result = validate_source(FIXTURES[recipe_id], recipe_id)
    assert result['status'] == 'passed' and result['recipe']['id'] == recipe_id and RECIPES[recipe_id]['skill'] == 'prepare_static_site'


BROKEN = {
    'arabic_landing_v1': [('index.html', 'aria-expanded="false" aria-controls="faq-1"', 'aria-expanded="false"'),
                          ('index.html', 'class="cta-button" href="#contact"', 'class="cta-button" href="#about"')],
    'arabic_dashboard_v1': [('index.html', 'بيانات تجريبية', 'بيانات'), ('index.html', '<p id="empty-state" hidden>', '<p id="empty-state">')],
    'arabic_blog_v1': [('index.html', 'data-tag="all" aria-pressed="true"', 'data-tag="all" aria-pressed="false"'),
                       ('index.html', 'id="post-search" type="search"', 'id="post-search" type="text"')],
    'arabic_store_v1': [('index.html', 'سلة تجريبية', 'سلة'), ('index.html', 'data-price="25"', 'data-price="مجانًا"')],
    'arabic_saas_v1': [('index.html', 'aria-selected="false" aria-controls="panel-2"', 'aria-selected="true" aria-controls="panel-2"'),
                       ('index.html', 'أسعار توضيحية', 'أسعار'), ('style.css', '[hidden]{display:none!important}', '')],
}


@pytest.mark.parametrize('recipe_id,file,old,new', [(r, *case) for r, cases in BROKEN.items() for case in cases])
def test_broken_contracts_are_rejected(recipe_id, file, old, new):
    files = dict(FIXTURES[recipe_id])
    assert old in files[file]
    files[file] = files[file].replace(old, new)
    with pytest.raises(ProjectError):
        validate_source(files, recipe_id)


def test_remote_assets_and_storage_are_rejected_for_every_site():
    for recipe_id in SITE_IDS:
        files = dict(FIXTURES[recipe_id])
        files['script.js'] += '\nlocalStorage.setItem("x","1");'
        with pytest.raises(ProjectError):
            validate_source(files, recipe_id)


@pytest.mark.parametrize('text,expected', [
    ('برمج لي صفحة تعريفية عربية لمطعم بدون انترنت', 'arabic_landing_v1'),
    ('اصنع موقع لشركة عربي محلي', 'arabic_landing_v1'),
    ('برمج لي لوحة بيانات عربية محلية للمبيعات', 'arabic_dashboard_v1'),
    ('أنشئ مدونة عربية محلية', 'arabic_blog_v1'),
    ('برمج لي متجر عربي بدون انترنت', 'arabic_store_v1'),
    ('صمم واجهة تطبيق SaaS عربية محلية مع خطط أسعار', 'arabic_saas_v1'),
    ('برمج لي لوحة بيانات عربية محلية لطلبات متجر', 'arabic_dashboard_v1'),
    ('برمج لي متجر', None),                                   # no explicit local/Arabic signal: the general path
    ('برمج لي متجر عربي محلي بـ React', None),               # an unsupported stack is never forced into a recipe
    ('برمج لي موقع سيرة ذاتية عربي محلي', 'arabic_cv_v1'),
])
def test_recipe_selection(text, expected):
    assert select_for_request(text, 'project.create') == expected
    assert select_for_request(text, 'project.edit') is None


def test_manifests_are_stable_and_distinct():
    hashes = {manifest(r)['sha256'] for r in SITE_IDS}
    assert len(hashes) == len(SITE_IDS) and all(manifest(r)['version'] == 1 for r in SITE_IDS)


def browser(files, recipe_id):
    from src.core.candidate_browser import check_candidate
    from src.core.project_validation import inspect_files
    preview = inspect_files(files)[1]
    try:
        return True, check_candidate(files, preview, threading.Event(), time.monotonic() + 60, required={'web_recipe': recipe_id})
    except ProjectError as error:
        return False, getattr(error, 'browser_report', {'errors': [str(error)]})


BREAK_BEHAVIOR = {'arabic_landing_v1': "panel.hidden=open;", 'arabic_dashboard_v1': "r.hidden=!ok;", 'arabic_blog_v1': "p.hidden=!ok;",
                  'arabic_store_v1': "count++;", 'arabic_saas_v1': "p.textContent=yearly?p.dataset.yearly:p.dataset.monthly;"}


@pytest.mark.parametrize('recipe_id', SITE_IDS)
def test_isolated_browser_probe_accepts_working_and_rejects_broken_behavior(recipe_id, monkeypatch):
    monkeypatch.setattr('src.core.project_jobs.check_candidate', None, raising=False)
    passed, report = browser(FIXTURES[recipe_id], recipe_id)
    assert passed, report.get('errors')
    assert len(report['web_recipe']['samples']) == 4 and all(not s['errors'] for s in report['web_recipe']['samples'])
    broken = dict(FIXTURES[recipe_id])
    assert BREAK_BEHAVIOR[recipe_id] in broken['script.js']
    broken['script.js'] = broken['script.js'].replace(BREAK_BEHAVIOR[recipe_id], '', 1)
    passed, report = browser(broken, recipe_id)
    assert not passed and report['errors']


@pytest.mark.parametrize('text,recipe_id', [('برمج لي متجر عربي بدون انترنت', 'arabic_store_v1'), ('برمج لي لوحة بيانات عربية محلية', 'arabic_dashboard_v1'),
                                            ('أنشئ مدونة عربية محلية', 'arabic_blog_v1')])
def test_chat_request_creates_a_recipe_project(system, text, recipe_id):
    from tests.regression.test_chat_dispatch import application, request_id
    app, desktop, dispatch = application(system)
    try:
        result = dispatch.dispatch(text, request_id(), session_id='s-recipe')
        assert result['kind'] == 'project' and result['job']['invoice']['web_recipe'] == recipe_id
        app.state.project_jobs.cancel(result['job']['job_id'])
    finally:
        app.state.project_jobs.shutdown(); app.state.project_store.close()


def test_shape_repair_adds_only_missing_attributes_caption_and_baseline_css():
    from src.tools.web_recipes import repair_missing_button_type
    files = dict(FIXTURES['arabic_dashboard_v1'])
    files['index.html'] = (files['index.html'].replace('<caption>بيانات تجريبية للطلبات</caption>', '')
                           .replace('<p id="empty-state" hidden>', '<p id="empty-state">'))
    files['style.css'] = files['style.css'].replace('[hidden]{display:none!important}', '')
    with pytest.raises(ProjectError):
        validate_source(files, 'arabic_dashboard_v1')
    repaired, receipt = repair_missing_button_type(files, 'arabic_dashboard_v1', 'x', 0, {'project_id': 'p', 'job_id': 'j', 'purpose': 't'})
    assert receipt['model_called'] is False and validate_source(repaired, 'arabic_dashboard_v1')['status'] == 'passed'
    assert '<caption>بيانات تجريبية</caption>' in repaired['index.html'] and '<p id="empty-state" hidden>' in repaired['index.html']
    overflow, receipt = repair_missing_button_type(repaired, 'arabic_dashboard_v1', 'فشل فحص المعاينة: 480px horizontal overflow', 0, {'project_id': 'p', 'job_id': 'j', 'purpose': 't'})
    assert 'neura-overflow-guard' in overflow['style.css']
    assert repair_missing_button_type(overflow, 'arabic_dashboard_v1', '480px horizontal overflow', 0, {'project_id': 'p', 'job_id': 'j', 'purpose': 't'}) is None


def test_shape_repair_never_changes_existing_values():
    from src.tools.web_recipes import repair_missing_button_type
    files = dict(FIXTURES['arabic_landing_v1'])
    files['index.html'] = files['index.html'].replace('aria-controls="faq-1"', 'aria-controls="faq-1" aria-expanded="true"', 1).replace(
        '<button type="button" class="faq-question" aria-expanded="false" aria-controls="faq-1" aria-expanded="true">', '<button class="faq-question" aria-controls="faq-1" aria-expanded="true">')
    repaired, _ = repair_missing_button_type(files, 'arabic_landing_v1', 'x', 0, {'project_id': 'p', 'job_id': 'j', 'purpose': 't'})
    assert '<button class="faq-question" aria-controls="faq-1" aria-expanded="true" type="button">' in repaired['index.html']
