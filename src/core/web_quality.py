"""WEB B3 (first slice): advisory static-site quality report; never blocks a save.

Measured from the saved source itself: metadata/SEO basics, document language/direction, heading
structure, image alternatives, offline/local references, inline handlers and page weight. Each item
is a concrete observation with a pass/advice flag; the report is not an aesthetic or SEO score and
does not prove behavior. Recipe contracts and acceptance gates are unchanged.
"""
import re
from html.parser import HTMLParser

LIMIT_BYTES = 150_000  # advisory page-weight budget for a small offline static site


class _Doc(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []; self.title = ''; self._in_title = False; self.handlers = 0
    def handle_starttag(self, tag, attrs):
        a = dict(attrs); self.tags.append((tag, a))
        self.handlers += sum(1 for k in a if k.lower().startswith('on'))
        if tag == 'title': self._in_title = True
    def handle_endtag(self, tag):
        if tag == 'title': self._in_title = False
    def handle_data(self, data):
        if self._in_title: self.title += data


def report(files, entry):
    if not entry or not isinstance(files.get(entry), str): return None
    doc = _Doc(); doc.feed(files[entry]); doc.close()
    tags = doc.tags
    def first(tag, **want):
        return next((a for t, a in tags if t == tag and all(a.get(k, '').lower() == v for k, v in want.items())), None)
    html = first('html') or {}
    description = (first('meta', name='description') or {}).get('content', '').strip()
    viewport = (first('meta', name='viewport') or {}).get('content', '')
    charset = any(t == 'meta' and (a.get('charset') or 'charset=' in a.get('content', '').lower()) for t, a in tags)
    images = [a for t, a in tags if t == 'img']
    refs = [a.get(k) for t, a in tags for k in ('src', 'href') if a.get(k)]
    external = [r for r in refs if re.match(r'^(?:[a-z][a-z0-9+.-]*:|//)', r, re.I) and not r.lower().startswith(('mailto:', 'tel:', 'data:', '#'))]
    weight = {p: len(v.encode()) if isinstance(v, str) else len(v) for p, v in files.items()}
    title = ' '.join(doc.title.split())
    items = {
        'title': {'value': title[:120], 'ok': 3 <= len(title) <= 70},
        'meta_description': {'value': description[:200], 'ok': 30 <= len(description) <= 170},
        'viewport': {'value': viewport[:120], 'ok': 'width=device-width' in viewport.replace(' ', '')},
        'charset': {'ok': charset},
        'lang_dir': {'value': [html.get('lang'), html.get('dir')], 'ok': bool(html.get('lang'))},
        'single_h1': {'value': sum(t == 'h1' for t, a in tags), 'ok': sum(t == 'h1' for t, a in tags) == 1},
        'image_alt': {'value': [len(images), sum(1 for a in images if a.get('alt') is None)], 'ok': all(a.get('alt') is not None for a in images)},
        'external_references': {'value': external[:10], 'ok': not external},
        'inline_event_handlers': {'value': doc.handlers, 'ok': doc.handlers == 0},
        'page_weight_bytes': {'value': sum(weight.values()), 'ok': sum(weight.values()) <= LIMIT_BYTES, 'per_file': weight},
    }
    return {'version': 1, 'entry': entry, 'items': items, 'advice': sorted(k for k, v in items.items() if not v['ok']),
            'scope': 'Advisory source observations only; not an SEO/aesthetic score; never blocks saving'}
