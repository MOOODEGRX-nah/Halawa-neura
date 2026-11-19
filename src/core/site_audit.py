"""WEB13 web.performance and WEB14 web.metadata_seo for saved static sites.

Performance: measured from the saved files under a declared environment (static source, no network,
no device emulation). Every number is counted from the source; there is no invented speed or
Lighthouse-style score. Findings name the file/element and a concrete fix.

Metadata: title/description/Open Graph/JSON-LD are built only from facts the user supplied (name,
description, optional public URL). Missing tags are added; existing ones are kept unless the user
asks to replace them. A local preview is never described as published or indexed.
"""
import html as _html
import json
import re
from html.parser import HTMLParser
from pathlib import PurePosixPath

ENVIRONMENT = 'تحليل ثابت لملفات المشروع المحفوظة دون شبكة أو جهاز محاكى؛ الأرقام عدّ وقياس من المصدر وليست درجة سرعة.'
BUDGET = {'total': 300_000, 'html': 60_000, 'css': 80_000, 'js': 120_000, 'image': 200_000, 'dom': 1500, 'depth': 24}
KIND = {'.html': 'html', '.htm': 'html', '.css': 'css', '.js': 'js', '.mjs': 'js', '.png': 'image', '.jpg': 'image', '.jpeg': 'image',
        '.gif': 'image', '.webp': 'image', '.svg': 'image', '.avif': 'image', '.woff': 'font', '.woff2': 'font', '.ttf': 'font', '.otf': 'font'}


class _Tree(HTMLParser):
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.elements, self.depth, self.max_depth, self.tags, self.in_head = 0, 0, 0, [], False
        self.inline_style_bytes = self.inline_script_bytes = 0
        self._capture = None

    def handle_starttag(self, tag, attrs):
        self.elements += 1
        a = {k.lower(): (v or '') for k, v in attrs}
        self.tags.append((tag, a, self.in_head))
        if tag == 'head':
            self.in_head = True
        if tag not in self.VOID:
            self.depth += 1
            self.max_depth = max(self.max_depth, self.depth)
        if tag in ('style', 'script') and not a.get('src'):
            self._capture = tag

    def handle_endtag(self, tag):
        if tag == 'head':
            self.in_head = False
        if tag not in self.VOID and self.depth:
            self.depth -= 1
        if tag == self._capture:
            self._capture = None

    def handle_data(self, data):
        if self._capture == 'style':
            self.inline_style_bytes += len(data.encode())
        elif self._capture == 'script':
            self.inline_script_bytes += len(data.encode())


def _size(value):
    return len(value.encode()) if isinstance(value, str) else len(value or b'')


def performance(files, entry):
    if not entry or not isinstance(files.get(entry), str):
        return None
    sizes = {path: _size(value) for path, value in files.items()}
    by_kind = {}
    for path, size in sizes.items():
        kind = KIND.get(PurePosixPath(path).suffix.lower(), 'other')
        by_kind[kind] = by_kind.get(kind, 0) + size
    tree = _Tree()
    tree.feed(files[entry])
    tree.close()
    texts = {p: v for p, v in files.items() if isinstance(v, str)}
    data_uri = sum(len(m) for v in texts.values() for m in re.findall(r'data:[a-z]+/[a-z0-9.+-]+;base64,[A-Za-z0-9+/=]+', v))
    images = [a for t, a, _ in tree.tags if t == 'img']
    blocking = [a.get('src') for t, a, head in tree.tags if t == 'script' and a.get('src') and head and 'defer' not in a and 'async' not in a and a.get('type') != 'module']
    css = '\n'.join(v for p, v in texts.items() if p.endswith('.css')) + '\n'.join(re.findall(r'<style[^>]*>([\s\S]*?)</style>', files[entry]))
    js = '\n'.join(v for p, v in texts.items() if p.endswith(('.js', '.mjs'))) + '\n'.join(re.findall(r'<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)</script>', files[entry]))
    measured = {
        'bytes_total': sum(sizes.values()), 'bytes_by_kind': by_kind, 'largest_files': sorted(sizes.items(), key=lambda kv: -kv[1])[:5],
        'dom_elements': tree.elements, 'dom_max_depth': tree.max_depth, 'images': len(images),
        'images_without_dimensions': sum(1 for a in images if not (a.get('width') and a.get('height'))),
        'images_not_lazy_after_first': sum(1 for a in images[1:] if a.get('loading') != 'lazy'),
        'render_blocking_scripts': blocking, 'inline_data_uri_bytes': data_uri,
        'css_imports': len(re.findall(r'@import\b', css)), 'css_animations': len(re.findall(r'@keyframes\b', css)),
        'css_heavy_effects': len(re.findall(r'\b(?:backdrop-filter|filter)\s*:|box-shadow\s*:[^;]*,[^;]*,', css)),
        'js_timers': len(re.findall(r'\bset(?:Interval|Timeout)\s*\(', js)), 'js_layout_reads_in_loops': len(re.findall(r'for\s*\([^)]*\)\s*\{[^}]*(?:offset(?:Width|Height|Top)|getBoundingClientRect)', js)),
        'external_fonts': [a.get('href') for t, a, _ in tree.tags if t == 'link' and re.search(r'fonts\.(?:googleapis|gstatic)|typekit', a.get('href', ''))],
    }
    findings = []

    def add(key, ok, detail, fix):
        findings.append({'id': key, 'ok': bool(ok), 'detail': detail, 'fix': '' if ok else fix})
    add('total_weight', measured['bytes_total'] <= BUDGET['total'], f"{measured['bytes_total']:,} بايت لكل الملفات (الميزانية {BUDGET['total']:,})", 'صغّر الصور أو اضغطها، واحذف الأنماط والسكربتات غير المستخدمة.')
    for kind in ('html', 'css', 'js', 'image'):
        if by_kind.get(kind):
            add(kind + '_weight', by_kind[kind] <= BUDGET[kind], f'{by_kind[kind]:,} بايت {kind} (الميزانية {BUDGET[kind]:,})', 'قسّم الملف أو أزل الأجزاء غير المستخدمة.' if kind != 'image' else 'استخدم WebP بأبعاد العرض الفعلية.')
    add('dom_size', tree.elements <= BUDGET['dom'], f'{tree.elements} عنصرًا في الصفحة، أقصى عمق {tree.max_depth}', 'بسّط البنية وقلّل التداخل والعناصر المتكررة.')
    add('image_dimensions', not measured['images_without_dimensions'], f"{measured['images_without_dimensions']} من {len(images)} صور بلا width/height", 'أضف width وheight لكل صورة لمنع قفز المحتوى أثناء التحميل.')
    add('lazy_images', not measured['images_not_lazy_after_first'], f"{measured['images_not_lazy_after_first']} صورة بعد الأولى بلا loading=lazy", 'أضف loading="lazy" للصور غير الظاهرة أولًا.')
    add('blocking_scripts', not blocking, 'سكربتات تحجب العرض في head: ' + (', '.join(blocking) or 'لا يوجد'), 'أضف defer أو انقل السكربت لنهاية body.')
    add('data_uri', data_uri <= 50_000, f'{data_uri:,} بايت صور مضمنة base64', 'احفظ الصور الكبيرة كملفات منفصلة.')
    add('css_imports', not measured['css_imports'], f"{measured['css_imports']} ‏@import في CSS", 'اجمع الأنماط في ملف واحد بدل @import المتسلسل.')
    add('heavy_effects', measured['css_heavy_effects'] <= 6, f"{measured['css_heavy_effects']} تأثيرات ثقيلة (filter/backdrop-filter/ظلال متعددة)", 'خفف المؤثرات الثقيلة خصوصًا على الجوال.')
    add('external_fonts', not measured['external_fonts'], 'خطوط خارجية: ' + (', '.join(measured['external_fonts']) or 'لا يوجد'), 'استخدم خطوط النظام أو ضمّن الخط محليًا.')
    return {'environment': ENVIRONMENT, 'entry': entry, 'measured': measured, 'findings': findings,
            'advice': [f['id'] for f in findings if not f['ok']], 'budget': BUDGET}


def _first_meta(markup, attribute, value):
    return re.search(r'<meta\b[^>]*\b' + attribute + r'\s*=\s*["\']' + re.escape(value) + r'["\'][^>]*>', markup, re.I)


def metadata_plan(files, entry, facts):
    """Suggested tags from the user's own facts only; nothing about publishing or ranking."""
    markup = files.get(entry) if entry else None
    if not isinstance(markup, str):
        return None
    name = re.sub(r'\s+', ' ', str(facts.get('name') or '')).strip()[:70]
    description = re.sub(r'\s+', ' ', str(facts.get('description') or '')).strip()[:170]
    url = str(facts.get('url') or '').strip()
    if url and not re.match(r'^https://[^\s/$.?#].[^\s]*$', url):
        url = ''
    lang = (re.search(r'<html\b[^>]*\blang\s*=\s*["\']([^"\']+)', markup, re.I) or [None, 'ar'])[1]
    title = re.search(r'<title[^>]*>([\s\S]*?)</title>', markup, re.I)
    current = {'title': _html.unescape(title.group(1)).strip() if title else '',
               'description': (re.search(r'content\s*=\s*["\']([^"\']*)', (_first_meta(markup, 'name', 'description') or [''])[0]) or [None, ''])[1],
               'og:title': bool(_first_meta(markup, 'property', 'og:title')), 'og:description': bool(_first_meta(markup, 'property', 'og:description')),
               'json_ld': 'application/ld+json' in markup}
    tags = []
    if name:
        tags += [('title', name), ('og:title', name)]
    if description:
        tags += [('description', description), ('og:description', description)]
    if name or description:
        tags.append(('og:type', 'website'))
        tags.append(('og:locale', 'ar_SA' if lang.startswith('ar') else 'en_US'))
    if url:
        tags.append(('og:url', url))
    structured = None
    if name:
        structured = {'@context': 'https://schema.org', '@type': 'WebSite', 'name': name, 'inLanguage': lang}
        if description:
            structured['description'] = description
        if url:
            structured['url'] = url
    return {'current': current, 'suggested': [{'name': k, 'content': v} for k, v in tags], 'json_ld': structured,
            'note': 'معاينة محلية فقط؛ إضافة البيانات الوصفية لا تعني أن الموقع منشور أو مفهرس في محركات البحث.'}


def apply_metadata(markup, plan, replace=False):
    """Insert (or, with replace=True, update) the planned tags inside <head>; returns new markup and changes."""
    changes = []
    head = re.search(r'<head\b[^>]*>', markup, re.I)
    if not head:
        raise ValueError('الصفحة بلا <head>؛ لا أعدّل بنية غير متوقعة.')
    additions = []
    for tag in plan['suggested']:
        name, content = tag['name'], _html.escape(tag['content'], quote=True)
        if name == 'title':
            existing = re.search(r'<title[^>]*>[\s\S]*?</title>', markup, re.I)
            if existing and (replace or not existing.group(0)[7:-8].strip()):
                markup = markup[:existing.start()] + '<title>' + _html.escape(tag['content']) + '</title>' + markup[existing.end():]
                changes.append('title')
            elif not existing:
                additions.append('<title>' + _html.escape(tag['content']) + '</title>')
                changes.append('title')
            continue
        attribute = 'name' if name == 'description' else 'property'
        existing = _first_meta(markup, attribute, name)
        element = '<meta ' + attribute + '="' + name + '" content="' + content + '">'
        if existing and replace:
            markup = markup[:existing.start()] + element + markup[existing.end():]
            changes.append(name)
        elif not existing:
            additions.append(element)
            changes.append(name)
    if plan.get('json_ld') and 'application/ld+json' not in markup:
        payload = json.dumps(plan['json_ld'], ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
        additions.append('<script type="application/ld+json">' + payload + '</script>')
        changes.append('json_ld')
    if additions:
        head = re.search(r'<head\b[^>]*>', markup, re.I)
        markup = markup[:head.end()] + '\n' + '\n'.join(additions) + markup[head.end():]
    return markup, changes
