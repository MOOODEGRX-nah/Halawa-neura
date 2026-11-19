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
                    if not re.match(r'text/(?:html|plain)|application/(?:xhtml\+xml|json)', kind):
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
