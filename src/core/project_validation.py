"""Deterministic source facts and a reachable static preview asset manifest."""
import ast
import json
import posixpath
import re
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit
from src.core.project_files import safe_path, ProjectError
from src.core.source_syntax import javascript,css

LANGUAGES = {'.html': 'HTML', '.htm': 'HTML', '.css': 'CSS', '.js': 'JavaScript',
             '.py': 'Python', '.json': 'JSON', '.md': 'Markdown', '.svg': 'SVG',
             '.ts': 'TypeScript', '.tsx': 'TSX', '.jsx': 'JSX'}
ASSETS = {'.html', '.htm', '.css', '.js', '.svg', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.ico', '.woff', '.woff2'}
PRIVATE = re.compile(r'(^|[/_.-])(secret|credentials?|tokens?|private|passwords?)([/_.-]|$)', re.I)


class References(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.references = []
        self.inline=[]
        self.pending=None
        self.build_required=False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for name,value in attrs.items():
            if value and name.startswith('on'):self.inline.append(('javascript',value,False))
        if attrs.get('style'):self.inline.append(('css',attrs['style'],True))
        if tag=='style':self.pending=('style','css',[])
        if tag=='script' and not attrs.get('src'):
            kind=attrs.get('type','').lower()
            if kind in ('','module','text/javascript','application/javascript'):self.pending=('script','javascript',[])
            elif kind in ('application/ld+json','application/json','importmap'):self.pending=('script','json',[])
            elif kind in ('text/babel','text/jsx'):self.build_required=True
        for name in ('src', 'href', 'poster'):
            if attrs.get(name):
                self.references.append(attrs[name])
        if attrs.get('srcset'):
            self.references.extend(x.strip().split()[0] for x in attrs['srcset'].split(',') if x.strip())

    def handle_data(self,data):
        if self.pending:self.pending[2].append(data)

    def handle_endtag(self,tag):
        if self.pending and self.pending[0]==tag:
            self.inline.append((self.pending[1],''.join(self.pending[2]),False));self.pending=None

    def close(self):
        super().close()
        if self.pending:raise ValueError('Unclosed script/style element')


def inspect_files(files):
    errors, warnings = [], []
    syntax={key:'not_applicable' for key in ('python','json','javascript','css')}
    jsx_required=False
    embedded_languages=set()
    for path, text in files.items():
        suffix=PurePosixPath(path).suffix.lower()
        kind={'.py':'python','.json':'json','.js':'javascript','.css':'css'}.get(suffix)
        try:
            if isinstance(text,bytes):continue
            if suffix=='.py':
                ast.parse(text, filename=path)
            elif suffix=='.json':
                json.loads(text)
            elif suffix=='.js':jsx_required|=javascript(text)['build_required']
            elif suffix=='.css':css(text)
            elif suffix in ('.html','.htm'):
                parsed=References();parsed.feed(text);parsed.close();jsx_required|=parsed.build_required
                for inner,source,declarations in parsed.inline:
                    embedded_languages.add({'javascript':'JavaScript','css':'CSS','json':'JSON'}[inner])
                    if inner=='javascript':jsx_required|=javascript(source)['build_required']
                    elif inner=='css':css(source,declarations=declarations)
                    else:json.loads(source)
                    if syntax[inner]!='failed':syntax[inner]='passed'
            if kind and syntax[kind]!='failed':syntax[kind]='passed'
        except (SyntaxError, ValueError) as exc:
            errors.append(path + ': ' + str(exc)[:300])
            if kind:syntax[kind]='failed'
    languages = sorted({LANGUAGES.get(PurePosixPath(p).suffix.lower(), 'Text') for p,text in files.items() if isinstance(text,str)}|embedded_languages)
    entry = 'index.html' if 'index.html' in files else next((p for p in files if PurePosixPath(p).suffix.lower() in ('.html','.htm')), None)
    build_required = jsx_required or any(PurePosixPath(p).suffix.lower() in ('.tsx','.jsx','.ts','.vue','.svelte') for p in files)
    if 'package.json' in files:
        try:
            package = json.loads(files['package.json'])
            build_required |= bool(package.get('scripts') or package.get('dependencies') or package.get('devDependencies'))
        except ValueError:
            build_required = True
    assets, visited = set(), set()

    def visit(path):
        if path in visited:
            return
        visited.add(path)
        if PurePosixPath(path).suffix.lower() not in ASSETS or PRIVATE.search(path):
            return
        assets.add(path)
        refs = []
        suffix=PurePosixPath(path).suffix.lower()
        if suffix in ('.html','.htm'):
            parser = References()
            parser.feed(files[path])
            refs = parser.references
            for kind,source,_ in parser.inline:
                if kind=='css':refs+=re.findall(r'url\(\s*[\'"]?([^\s)\'"]+)',source)
                if kind=='javascript':refs+=re.findall(r'(?:from\s*|import\s*|import\s*\(\s*)[\'"]([^\'"]+)',source)
        elif suffix=='.css':
            refs = re.findall(r'url\(\s*[\'"]?([^\s)\'"]+)', files[path])
            refs += re.findall(r'@import\s+[\'"]([^\'"]+)', files[path])
        elif suffix=='.js':
            refs = re.findall(r'(?:from\s*|import\s*)[\'"]([^\'"]+)', files[path])
            refs += re.findall(r'import\s*\(\s*[\'"]([^\'"]+)', files[path])
        for ref in refs:
            parsed = urlsplit(ref)
            if parsed.scheme or parsed.netloc or ref.startswith('//'):
                if not ref.startswith('data:image/'):
                    warnings.append('مورد خارجي محظور في المعاينة: ' + ref[:160])
                continue
            if not parsed.path:
                continue
            if parsed.path.startswith('/'):
                errors.append('استخدم مرجعًا نسبيًا للمشروع: ' + ref[:160])
                continue
            target = posixpath.normpath(posixpath.join(posixpath.dirname(path), unquote(parsed.path)))
            try:
                safe_path(target)
            except ProjectError:
                errors.append('مرجع خارج حد المشروع: ' + ref[:160])
                continue
            if target not in files:
                errors.append('ملف مرجعي مفقود: ' + target)
            else:
                visit(target)

    if entry and not build_required:
        visit(entry)
    preview = {'supported': bool(entry and not build_required and not errors),
               'kind': 'static_web' if entry and not build_required else 'unsupported',
               'entry_point': entry, 'assets': sorted(assets), 'external_resources': sorted(set(warnings)),
               'reason': 'يحتاج المشروع بناءً أو خادمًا؛ لم يُشغّل أي أمر.' if build_required else
                         'لا توجد صفحة HTML للمعاينة.' if not entry else 'فشل فحص الملفات المرجعية.' if errors else ''}
    validation = {'static_checks': 'failed' if errors else 'passed', 'errors': errors,
                  'syntax':syntax,'python_json_syntax':'failed' if 'failed' in (syntax['python'],syntax['json']) else 'passed' if 'passed' in (syntax['python'],syntax['json']) else 'not_applicable',
                  'javascript_syntax':syntax['javascript'],'css_syntax':syntax['css'],
                  'behavioral_tests': 'not_run', 'executed': False}
    return languages, preview, validation
