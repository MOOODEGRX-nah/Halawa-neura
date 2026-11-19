"""Read a public web page or a Wikipedia summary for the user, with its source.

Only http(s) on ports 80/443 to public addresses is fetched; every redirect is re-checked, so a
page cannot steer Neura to localhost, the LAN or link-local metadata services. Bodies are
capped, scripts and styles are discarded, and the text is data for the model, never instructions.
"""
import html
import ipaddress
import re
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, quote

MAX_BYTES = 2_000_000
TIMEOUT = 10.0


class ReaderError(ValueError):
    pass


def check_url(url):
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.hostname:
        raise ReaderError('أقرأ روابط http أو https فقط.')
    if parts.username or parts.password:
        raise ReaderError('الروابط التي تحتوي بيانات دخول غير مسموحة.')
    port = parts.port or (443 if parts.scheme == 'https' else 80)
    if port not in (80, 443):
        raise ReaderError('المنفذ غير مسموح؛ أقرأ المواقع العامة على 80 و443 فقط.')
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(parts.hostname, port, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise ReaderError('تعذر العثور على الموقع «' + parts.hostname + '».') from exc
    for address in addresses:
        ip = ipaddress.ip_address(address.split('%')[0])
        if not ip.is_global or ip.is_multicast:
            raise ReaderError('هذا الرابط يشير إلى عنوان محلي أو خاص؛ لا أقرؤه حمايةً لجهازك وشبكتك.')
    return url


class _Text(HTMLParser):
    SKIP = {'script', 'style', 'noscript', 'svg', 'nav', 'footer', 'header', 'form', 'aside', 'template', 'iframe'}
    BLOCK = {'p', 'div', 'li', 'br', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'tr', 'section', 'article', 'blockquote', 'pre'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip, self.title, self._in_title = [], 0, '', False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        if tag == 'title':
            self._in_title = True
        if tag in self.BLOCK:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        if tag == 'title':
            self._in_title = False
        if tag in self.BLOCK:
            self.parts.append('\n')

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self.skip:
            self.parts.append(data)


def extract(markup):
    parser = _Text()
    parser.feed(markup)
    text = re.sub(r'[ \t\r\f\v]+', ' ', ''.join(parser.parts))
    lines = [line.strip() for line in text.split('\n')]
    # Drop menu-like fragments; keep sentences.
    kept = [line for line in lines if len(line) >= 40 or re.search(r'[.!؟?:،]$', line)]
    return html.unescape(parser.title.strip())[:200], '\n'.join(kept)


class WebReader:
    def __init__(self, fetch=None, resolve=check_url):
        self._fetch = fetch or self._http
        self.resolve = resolve

    def _http(self, url):
        import httpx
        for _ in range(4):
            self.resolve(url)
            with httpx.Client(timeout=TIMEOUT, follow_redirects=False, headers={'User-Agent': 'NeuraAI-desktop (reader)', 'Accept-Language': 'ar,en;q=0.8'}) as client:
                with client.stream('GET', url) as response:
                    if response.status_code in (301, 302, 303, 307, 308) and response.headers.get('location'):
                        url = urljoin(url, response.headers['location'])
                        continue
                    if response.status_code >= 400:
                        raise ReaderError('الموقع رد بالخطأ ' + str(response.status_code) + '.')
                    kind = response.headers.get('content-type', '')
                    if not re.match(r'text/(?:html|plain|xml)|application/(?:xhtml\+xml|json|xml)', kind):
                        raise ReaderError('هذا الرابط ليس صفحة نصية (' + (kind.split(';')[0] or 'غير معروف') + ').')
                    body = b''
                    for chunk in response.iter_bytes():
                        body += chunk
                        if len(body) > MAX_BYTES:
                            break
                    return url, kind, body[:MAX_BYTES].decode(response.encoding or 'utf-8', errors='replace')
        raise ReaderError('تحويلات كثيرة؛ توقفت عن متابعة الرابط.')

    def page(self, url):
        try:
            final, kind, body = self._fetch(url)
        except ReaderError:
            raise
        except Exception as exc:
            raise ReaderError('تعذر فتح الصفحة الآن؛ تحقق من الرابط والإنترنت.') from exc
        if 'html' in kind:
            title, text = extract(body)
        else:
            title, text = '', body
        text = text.strip()
        if len(text) < 80:
            raise ReaderError('لم أجد نصًا كافيًا في هذه الصفحة (قد تعتمد على JavaScript أو تتطلب تسجيل دخول).')
        return {'url': final, 'title': title or urlsplit(final).hostname, 'text': text}

    def wikipedia(self, topic, language='ar'):
        topic = topic.strip()[:120]
        base = 'https://' + language + '.wikipedia.org'
        try:
            import json
            final, _, body = self._fetch(base + '/w/api.php?action=opensearch&format=json&limit=1&namespace=0&search=' + quote(topic))
            found = json.loads(body)
            if not found[1]:
                raise ReaderError('لم أجد مقالة في ويكيبيديا عن «' + topic + '».')
            title = found[1][0]
            _, _, body = self._fetch(base + '/api/rest_v1/page/summary/' + quote(title.replace(' ', '_'), safe=''))
            summary = json.loads(body)
        except ReaderError:
            raise
        except Exception as exc:
            raise ReaderError('تعذر الوصول إلى ويكيبيديا الآن.') from exc
        extract_text = (summary.get('extract') or '').strip()
        if not extract_text:
            raise ReaderError('مقالة «' + title + '» بلا ملخص متاح.')
        page = (summary.get('content_urls') or {}).get('desktop', {}).get('page') or base + '/wiki/' + quote(title.replace(' ', '_'))
        return {'title': summary.get('title') or title, 'text': extract_text, 'url': page}


YOUTUBE_ID = re.compile(r'(?:youtube\.com/(?:watch\?(?:[^#\s]*&)?v=|shorts/|embed/|live/)|youtu\.be/)([A-Za-z0-9_-]{11})')


def youtube_id(url):
    match = YOUTUBE_ID.search(url or '')
    return match.group(1) if match else None


def _youtube(self, url):
    """N075: the video's own caption track (Arabic, then English, then any); never the title alone."""
    import json as _json
    video = youtube_id(url)
    if not video:
        raise ReaderError('هذا ليس رابط فيديو YouTube صالحًا.')
    try:
        _, _, page = self._fetch('https://www.youtube.com/watch?v=' + video + '&hl=ar')
    except ReaderError:
        raise
    except Exception as exc:
        raise ReaderError('تعذر فتح صفحة الفيديو الآن.') from exc
    title = re.search(r'"videoDetails":\{"videoId":"[^"]+","title":"((?:[^"\\]|\\.)*)"', page)
    title = _json.loads('"' + title.group(1) + '"') if title else 'فيديو YouTube'
    tracks = re.search(r'"captionTracks":(\[.*?\])\s*,\s*"(?:audioTracks|translationLanguages)"', page)
    if not tracks:
        raise ReaderError('لا توجد ترجمة نصية متاحة لهذا الفيديو، لذلك لا أستطيع تلخيص محتواه بصدق (لن ألخص من العنوان وحده).')
    try:
        options = _json.loads(tracks.group(1))
    except ValueError as exc:
        raise ReaderError('تعذر قراءة قائمة الترجمات في صفحة الفيديو.') from exc
    def rank(track):
        code = track.get('languageCode', '')
        return (0 if code.startswith('ar') else 1 if code.startswith('en') else 2, 1 if track.get('kind') == 'asr' else 0)
    track = sorted(options, key=rank)[0]
    base = track.get('baseUrl', '')
    if not base.startswith('https://www.youtube.com/'):
        raise ReaderError('رابط الترجمة غير متوقع؛ توقفت حمايةً لجهازك.')
    try:
        _, _, xml = self._fetch(base)
    except Exception as exc:
        raise ReaderError('تعذر جلب نص الترجمة من YouTube.') from exc
    lines = [html.unescape(re.sub(r'<[^>]+>', '', t)).strip() for t in re.findall(r'<text[^>]*>(.*?)</text>', xml, re.S)]
    text = re.sub(r'\s+', ' ', ' '.join(l for l in lines if l)).strip()
    if len(text) < 80:
        raise ReaderError('رجعت ترجمة الفيديو فارغة أو قصيرة جدًا (قد يتطلب YouTube تحققًا إضافيًا)؛ لم ألخص شيئًا.')
    return {'title': title, 'url': 'https://www.youtube.com/watch?v=' + video, 'text': text,
            'language': track.get('languageCode', ''), 'automatic': track.get('kind') == 'asr'}


def _research(self, topic):
    """N078: several Wikipedia articles (Arabic first, English second) as cited, bounded sources."""
    import json as _json
    sources = []
    for language, limit in (('ar', 3), ('en', 2)):
        base = 'https://' + language + '.wikipedia.org'
        try:
            _, _, body = self._fetch(base + '/w/api.php?action=opensearch&format=json&namespace=0&limit=' + str(limit) + '&search=' + quote(topic[:120]))
            titles = _json.loads(body)[1]
        except Exception:
            continue
        for title in titles:
            try:
                _, _, raw = self._fetch(base + '/api/rest_v1/page/summary/' + quote(title.replace(' ', '_'), safe=''))
                summary = _json.loads(raw)
            except Exception:
                continue
            text = (summary.get('extract') or '').strip()
            if len(text) > 60:
                sources.append({'title': summary.get('title') or title, 'text': text[:1800], 'language': language,
                                'url': (summary.get('content_urls') or {}).get('desktop', {}).get('page') or base + '/wiki/' + quote(title.replace(' ', '_'))})
    if not sources:
        raise ReaderError('لم أجد مصادر في ويكيبيديا عن «' + topic[:80] + '». جرّب صياغة أخرى أو أعطني رابطًا لألخصه.')
    return sources[:5]


WebReader.youtube = _youtube
WebReader.research = _research
