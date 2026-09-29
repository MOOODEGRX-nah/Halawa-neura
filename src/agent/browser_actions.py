"""
Neura Browser Actions
تصفح آمن - قراءة فقط في المرحلة الأولى.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


class SafeBrowser:
    """متصفح Neura الآمن - قراءة فقط."""

    def __init__(self, headless=True, timeout=20000):
        self.headless = headless
        self.timeout = timeout
        self._playwright = None
        self._browser = None

    def __enter__(self):
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=['--disable-blink-features=AutomationControlled']
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    def read_page(self, url, selector=None, max_text=5000):
        """
        زيارة URL واستخراج النص.
        قراءة فقط - لا Safety Gate مطلوب.
        """
        print(f'🌐 زيارة: {url}')
        page = self._browser.new_page()
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=self.timeout)
            page.wait_for_timeout(1000)  # انتظر JS

            if selector:
                try:
                    elements = page.query_selector_all(selector)
                    texts = [e.inner_text() for e in elements if e.inner_text().strip()]
                    content = '\n'.join(texts)
                except Exception:
                    content = ''
            else:
                content = page.inner_text('body')

            # تنظيف النص
            content = '\n'.join(
                line.strip() for line in content.split('\n')
                if line.strip()
            )
            if len(content) > max_text:
                content = content[:max_text] + '\n... [مقطوع]'

            return {
                'ok': True,
                'url': url,
                'title': page.title(),
                'content': content,
                'length': len(content)
            }
        except PlaywrightTimeout:
            return {'ok': False, 'error': 'انتهت مهلة الصفحة'}
        except Exception as e:
            return {'ok': False, 'error': str(e)}
        finally:
            page.close()

    def extract_headlines(self, url, selector='h1, h2, h3', limit=20):
        """استخراج عناوين الصفحة."""
        print(f'📰 استخراج عناوين: {url}')
        page = self._browser.new_page()
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=self.timeout)
            page.wait_for_timeout(1000)

            elements = page.query_selector_all(selector)
            headlines = []
            for e in elements[:limit]:
                text = e.inner_text().strip()
                if text and len(text) > 5:
                    headlines.append(text)

            return {
                'ok': True,
                'url': url,
                'title': page.title(),
                'headlines': headlines
            }
        except Exception as e:
            return {'ok': False, 'error': str(e)}
        finally:
            page.close()

    def google_search(self, query, site=None, count=5):
        """
        بحث Google (مع site: اختياري).
        يُرجع روابط للزيارة.
        """
        search_query = f'site:{site} {query}' if site else query
        print(f'🔍 Google: {search_query}')
        page = self._browser.new_page()
        try:
            page.goto(
                f'https://www.google.com/search?q={search_query}&num={count}',
                wait_until='domcontentloaded',
                timeout=self.timeout
            )
            page.wait_for_timeout(1500)

            # استخراج روابط النتائج
            links = page.query_selector_all('a[href^="/url?q="]')
            results = []
            for a in links[:count]:
                href = a.get_attribute('href')
                if href and '/url?q=' in href:
                    actual_url = href.split('/url?q=')[1].split('&')[0]
                    text = a.inner_text().strip()
                    if text and actual_url.startswith('http'):
                        results.append({'title': text, 'url': actual_url})

            return {'ok': True, 'query': search_query, 'results': results}
        except Exception as e:
            return {'ok': False, 'error': str(e)}
        finally:
            page.close()


if __name__ == '__main__':
    print('Neura Browser Actions - Demo')
    print('=' * 60)

    # اختبار 1: قراءة صفحة بسيطة
    print('\n--- اختبار 1: قراءة صفحة ---')
    with SafeBrowser(headless=True) as browser:
        result = browser.read_page('https://example.com')
        if result['ok']:
            print(f'✅ العنوان: {result["title"]}')
            print(f'📄 المحتوى ({result["length"]} حرف):')
            print(result['content'][:300])
        else:
            print(f'❌ فشل: {result["error"]}')

    # اختبار 2: استخراج عناوين
    print('\n--- اختبار 2: عناوين BBC ---')
    with SafeBrowser(headless=True) as browser:
        result = browser.extract_headlines('https://www.bbc.com')
        if result['ok']:
            print(f'✅ العنوان: {result["title"]}')
            print(f'📰 {len(result["headlines"])} عنوان:')
            for i, h in enumerate(result['headlines'][:10], 1):
                print(f'  {i}. {h}')
        else:
            print(f'❌ فشل: {result["error"]}')

    print('\n✅ انتهت الاختبارات')
