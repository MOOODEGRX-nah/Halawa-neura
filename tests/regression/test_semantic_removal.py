"""Allowlisted source units are parsed; JavaScript is never executed."""
import pytest
from src.core.semantic_removal import feature_ranges
from src.core.feature_intent import build_contract
from src.core.repair_targets import RepairTargets
from src.core.project_files import ProjectError
from src.core.source_syntax import javascript
from src.core.required_interactions import compile_theme


def remove(files,feature='Login'):
    contract=build_contract('احذف '+feature,[],{'intent':'project.edit'})
    ranges=feature_ranges(files,contract);targets=RepairTargets(files,1,ranges=ranges)
    return targets.apply(files,[{'target_id':key,'after':''} for key in targets.targets],1),ranges


def test_static_control_and_only_its_isolated_listener_are_deleted():
    listener="document.querySelector('.login-button').addEventListener('click',()=>alert('Login'));"
    script="// عربي قبل الاستماع\nconst unrelated = 42;\n"+listener+"\nconsole.log(unrelated);"
    html='<html><head></head><body><h1>Login architecture</h1><button class="login-button">Login</button><button id="theme">Theme</button><script>'+script+'</script></body></html>'
    result,ranges=remove({'index.html':html})
    assert [html[a:b] for a,b in ranges['index.html']]==['<button class="login-button">Login</button>',listener]
    assert result['index.html']==html.replace('<button class="login-button">Login</button>','').replace(listener,'')
    javascript(script.replace(listener,''))
    assert 'Login architecture' in result['index.html'] and '<button id="theme">Theme</button>' in result['index.html']


def test_static_append_and_isolated_handler_are_removed_without_dropping_script():
    append='document.querySelector(".header").innerHTML += \'<button class="login-button">Login</button>\';'
    handler="document.querySelector('.login-button').onclick=()=>alert('placeholder');"
    html='<html><head></head><body><div class="header"><h1>Keep</h1></div><script>const keep=1;'+append+handler+'</script></body></html>'
    result,_=remove({'index.html':html})
    assert result['index.html']==html.replace(append,'').replace(handler,'')


def test_multiple_related_files_and_unicode_offsets_are_exact():
    html='<html><body>عربي<button id="login">Login</button><script src="script.js"></script></body></html>'
    js="// تعليق عربي\nconst keep=1;\ndocument.getElementById('login').addEventListener('click',()=>{});\n"
    result,ranges=remove({'index.html':html,'script.js':js})
    assert len(ranges['index.html'])==len(ranges['script.js'])==1
    assert result['script.js']=='// تعليق عربي\nconst keep=1;\n\n'
    assert 'عربي' in result['index.html'] and 'script.js' in result['index.html']


def test_owned_theme_blocks_and_control_are_removed_together():
    before={'index.html':'<html><head></head><body><h1>Keep</h1><button>Login</button></body></html>'}
    compiled,_=compile_theme(before,'index.html')
    result,ranges=remove(compiled,'الوضع الداكن')
    assert len(ranges['index.html'])==3
    assert 'data-neura-interaction="theme"' not in result['index.html'] and 'neura-theme-toggle' not in result['index.html']
    assert '<h1>Keep</h1><button>Login</button>' in result['index.html']


@pytest.mark.parametrize('source',[
 '<html><body><h1>Login architecture</h1></body></html>',
 '<html><body><script>const b=document.createElement("button");b.textContent="Login";document.body.append(b);</script></body></html>',
 '<html><body><button id="login">Login</button><script>const b=document.getElementById("login");b.onclick=()=>{};</script></body></html>',
 '<html><body><script>document.body.innerHTML += \'<button>Login</button><button>Theme</button>\';</script></body></html>',
 '<html><body><button>Login<button>Login</button></button></body></html>',
])
def test_unknown_dynamic_mixed_or_overlapping_units_are_not_guessed(source):
    with pytest.raises(ProjectError):remove({'index.html':source})


def test_forged_owned_marker_does_not_authorize_deleting_arbitrary_script():
    source='<html><head></head><body><button id="neura-theme-toggle">Theme</button><script data-neura-interaction="theme">const unrelated=42;</script></body></html>'
    with pytest.raises(ProjectError):remove({'index.html':source},'الوضع الداكن')


def test_recorded_style_wrapper_corruption_is_not_an_eligible_removal():
    import json
    from pathlib import Path
    from src.core.project_validation import inspect_files
    data=json.loads((Path(__file__).parents[1]/'fixtures/ax07_review/removal/scope-wrapper-corruption.json').read_text())
    assert inspect_files(data['rejected_candidate'])[2]['errors']
    contract=build_contract(data['request'],data['accepted_requirements'],{'intent':'project.edit'})
    units=feature_ranges(data['files'],contract)
    targets=RepairTargets(data['files'],1,ranges=units)
    after=targets.apply(data['files'],[{'target_id':key,'after':''} for key in targets.targets],1)
    assert not inspect_files(after)[2]['errors']
    for path,source in data['files'].items():
        assert source.count('<style')==after[path].count('<style')
        assert source.count('</style>')==after[path].count('</style>')
        assert 'neura-theme-toggle' in after[path]
