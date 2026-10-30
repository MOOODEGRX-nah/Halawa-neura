"""Selected-target static checks, in a clean child with explicit QA paths."""
import argparse,ast,hashlib,importlib,importlib.metadata,importlib.util,json,os,platform,sys
from pathlib import Path


def static(target,output):
    # cwd is the QA run directory, not the checkout. Target wins over this tool.
    sys.path.insert(0,str(target))
    repo=Path(__file__).resolve().parents[2]
    checks={};errors=[];origins={}
    active=['src.runtime','src.core.neura_loop','src.backend.api','src.core.project_store',
            'src.core.project_jobs','src.core.application_targets','src.tools.desktop_skills',
            'src.desktop.app','src.desktop.service','src.channels.telegram_gateway']
    for name in active:
        try:
            mod=importlib.import_module(name);origin=Path(mod.__file__).resolve();origins[name]=str(origin)
            if not origin.is_relative_to(target):raise ValueError('Wrong target import: '+name)
        except Exception as exc:errors.append({'module':name,'error':str(exc),'type':type(exc).__name__})
    checks['imports']={'passed':not errors,'origins':origins,'errors':errors,'inference_requested':False}
    syntax=[]
    for path in (target/'src').rglob('*.py'):
        try:ast.parse(path.read_text(),filename=str(path))
        except SyntaxError as exc:syntax.append(str(exc))
    checks['syntax']={'passed':not syntax,'errors':syntax,'scope':'src only; snippets/legacy scripts not treated as standalone modules'}
    files=[];mismatch=[]
    for name in ('src','web','configs','assets','VERSION','neura-desktop.py','LICENSE'):
        root=repo/name
        for path in [root] if root.is_file() else root.rglob('*'):
            if not path.is_file() or '__pycache__' in path.parts or path.name.endswith(('.pyc','.bak')):continue
            rel=path.relative_to(repo);other=target/rel
            same=other.is_file() and hashlib.sha256(path.read_bytes()).digest()==hashlib.sha256(other.read_bytes()).digest()
            files.append({'path':str(rel),'same':same})
            if not same:mismatch.append(str(rel))
    checks['package_match']={'passed':not mismatch,'files':len(files),'mismatch':mismatch,'target':str(target),'comparison':files,'limitation':'File identity, not a clean installation or administrative update.'}
    import re
    external=[]
    for path in (target/'web').glob('*.html'):
        external+=re.findall(r'<script[^>]+src=["\'](https?://[^"\']+)',path.read_text())
    checks['local_assets']={'passed':not external,'external_scripts':external}
    import yaml
    ci=repo/'.github/workflows/build.yml';config=yaml.safe_load(ci.read_text())
    checks['ci_config']={'passed':isinstance(config.get('jobs'),dict) and bool(config['jobs']),'file':str(ci),'jobs':list(config.get('jobs',{})),'limitation':'YAML/source validated locally; no GitHub workflow dispatched.'}
    checks['diagnostic_scope']={'passed':None,'limitation':'No controlled synced-folder acceptance fixture is implemented; source review only. Doctor must be modernized separately.'}
    try:
        spec=importlib.util.spec_from_file_location('qa_gguf_audit',repo/'tools/audit_models.py');audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
        from src.desktop.paths import DesktopSettings
        production=Path.home()/'.config/neura-ai/settings.json'
        saved=json.loads(production.read_text()) if production.is_file() else {}
        folder=Path(saved.get('models_dir','/opt/neura-ai/models')).resolve()
        records=audit.audit(folder,hashes=True)
        checks['model_metadata']={'passed':not any(x.get('error') for x in records['models']),'audit':records,'limitation':'Local hashes/metadata do not establish publisher provenance or generation quality; incomplete markers prevent readiness.'}
        selected={k:saved.get(k) for k in ('models_dir','dedicated_coder','n_ctx','n_gpu_layers','gpu_device')}
    except Exception as exc:
        selected={};checks['model_metadata']={'passed':False,'error':str(exc)}
    from src.backend.api import app
    endpoints=[{'path':route.path,'methods':sorted(route.methods or [])} for route in app.routes if hasattr(route,'methods')]
    dependencies={}
    for name in ('fastapi','pydantic','uvicorn','httpx','pytest','PySide6','llama-cpp-python','numpy','PyYAML'):
        try:dependencies[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:dependencies[name]=None
    result={'executable':sys.executable,'python':sys.version,'platform':platform.platform(),
        'session':{k:os.environ.get(k) for k in ('XDG_SESSION_TYPE','XDG_CURRENT_DESKTOP','QT_QPA_PLATFORM')},
        'target_root':str(target),'version':(target/'VERSION').read_text().strip(),'dependencies':dependencies,
        'production_model_options_read_only':selected,'checks':checks,'endpoints':endpoints}
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps({'imports':not errors,'source_matches_target':not mismatch,'files':len(files),'endpoints':len(endpoints)},indent=2))
    return int(any(v['passed'] is False for v in checks.values()))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('suite',choices=['static']);p.add_argument('--target',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    raise SystemExit(static(a.target.resolve(),a.output.resolve()))
